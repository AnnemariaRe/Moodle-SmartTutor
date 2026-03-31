"""
Fine-tune DKT on real course data from DB
Usage:
    python dkt_finetune.py --course 10
    python dkt_finetune.py --course 10 --no-finetune
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random

import numpy as np
import pandas as pd
import psycopg2
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset

SEED = 42
HIDDEN_SIZE = 128
# MASTERY_THRESHOLD
THRESH = 0.7
MODELS_DIR = pathlib.Path(__file__).parent.parent / "models"

ADAPTIVE_DSN = "postgresql://adaptive:adaptive@localhost:5434/adaptive"
TRACKING_DSN = "postgresql://tracking:tracking@localhost:5435/tracking"

TRACKING_QUERY = """
SELECT student_id, cmid, event_type, ts, payload
FROM events
WHERE course_id = %(course_id)s
  AND event_type IN (
      'quiz_attempt_submitted', 'assign_submission_graded',
      'lesson_completed', 'lesson_answer_submitted'
  )
ORDER BY student_id, ts
"""
CMID_QUERY = """
SELECT moodle_cmid, concept_id FROM content_item
WHERE course_id = %(course_id)s AND role != 'placement'
"""


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class DKTDataset(Dataset):
    def __init__(self, seqs, num_skills, max_seq_len=200):
        self.seqs = [s[:max_seq_len] for s in seqs]
        self.num_skills = num_skills

    def __len__(self):
        return len(self.seqs)

    def __getitem__(self, idx):
        seq = self.seqs[idx]
        T = len(seq)
        x = np.zeros((T, 2 * self.num_skills), dtype=np.float32)
        for t, (skill, correct) in enumerate(seq):
            x[t, skill * 2 + correct] = 1.0
        targets = np.array([seq[t + 1][1] for t in range(T - 1)], dtype=np.float32)
        next_skills = np.array([seq[t + 1][0] for t in range(T - 1)], dtype=np.int64)
        return torch.tensor(x[:-1]), torch.tensor(targets), torch.tensor(next_skills)


def collate_pad(batch):
    xs, targets, next_skills = zip(*batch)
    max_len = max(x.size(0) for x in xs)
    S2 = xs[0].size(1)
    xs_pad = torch.zeros(len(xs), max_len, S2)
    tgt_pad = torch.zeros(len(xs), max_len)
    ns_pad = torch.zeros(len(xs), max_len, dtype=torch.long)
    mask = torch.zeros(len(xs), max_len, dtype=torch.bool)
    for i, (x, t, ns) in enumerate(zip(xs, targets, next_skills)):
        L = x.size(0)
        xs_pad[i, :L] = x
        tgt_pad[i, :L] = t
        ns_pad[i, :L] = ns
        mask[i, :L] = True
    return xs_pad, tgt_pad, ns_pad, mask


class DKTFineTuned(nn.Module):
    def __init__(self, num_course_skills: int, hidden_size: int = HIDDEN_SIZE, dropout: float = 0.2):
        super().__init__()
        self.num_skills = num_course_skills
        self.hidden_size = hidden_size
        self.lstm = nn.LSTM(input_size=2 * num_course_skills, hidden_size=hidden_size,
                            num_layers=1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.linear = nn.Linear(hidden_size, num_course_skills)

    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.linear(self.dropout(out)))


def evaluate(model, loader, device) -> float:
    model.eval()
    all_preds, all_targets = [], []
    with torch.no_grad():
        for xs, targets, next_skills, mask in loader:
            xs, targets, next_skills, mask = (
                xs.to(device), targets.to(device), next_skills.to(device), mask.to(device)
            )
            preds = model(xs)
            preds_skill = preds.gather(2, next_skills.unsqueeze(-1)).squeeze(-1)
            valid = mask.view(-1)
            all_preds.extend(preds_skill.view(-1)[valid].cpu().numpy())
            all_targets.extend(targets.view(-1)[valid].cpu().numpy())
    return roc_auc_score(all_targets, all_preds) if len(set(all_targets)) > 1 else 0.5


def load_course_sequences(course_id: int) -> tuple[dict[int, int], list]:
    """Load and preprocess course events from DB"""
    conn_a = psycopg2.connect(ADAPTIVE_DSN)
    cmid_df = pd.read_sql(CMID_QUERY, conn_a, params={"course_id": course_id})
    conn_a.close()
    cmid_to_concept = dict(zip(cmid_df["moodle_cmid"], cmid_df["concept_id"]))
    if not cmid_to_concept:
        raise ValueError(f"No content_items for course_id={course_id}. Run auto-extract first.")

    conn_t = psycopg2.connect(TRACKING_DSN)
    events_df = pd.read_sql(TRACKING_QUERY, conn_t, params={"course_id": course_id})
    conn_t.close()
    if events_df.empty:
        raise ValueError(f"No events for course_id={course_id}. Collect student data first.")

    print(f"Events: {len(events_df)}, students: {events_df.student_id.nunique()}")

    def _rel_score(row) -> float | None:
        import json as _j
        p = _j.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        et = row["event_type"]
        try:
            if et == "quiz_attempt_submitted":
                return float(p["score"]) / float(p["max_score"]) if float(p.get("max_score", 0)) > 0 else 0.0
            if et == "assign_submission_graded":
                return float(p["grade"]) / float(p["max_grade"]) if float(p.get("max_grade", 0)) > 0 else 0.0
            if et == "lesson_completed":
                nq = int(p.get("num_questions", 0))
                return int(p["num_correct"]) / nq if nq > 0 else float(p.get("score_percent", 0)) / 100.0
            if et == "lesson_answer_submitted":
                return 1.0 if p.get("is_correct") else 0.0
        except (KeyError, TypeError, ZeroDivisionError):
            return None
        return None

    events_df["rel_score"] = events_df.apply(_rel_score, axis=1)
    events_df = events_df.dropna(subset=["rel_score"])
    events_df["concept_id"] = events_df["cmid"].map(cmid_to_concept)
    events_df = events_df.dropna(subset=["concept_id"]).copy()
    events_df["concept_id"] = events_df["concept_id"].astype(int)
    events_df["correct"] = (events_df["rel_score"] >= THRESH).astype(int)

    unique_concepts = sorted(events_df["concept_id"].unique())
    concept2idx = {c: i for i, c in enumerate(unique_concepts)}
    sequences = []
    for _, group in events_df.sort_values("ts").groupby("student_id"):
        seq = [(concept2idx[r["concept_id"]], r["correct"]) for _, r in group.iterrows()]
        if len(seq) >= 2:
            sequences.append(seq)

    if not sequences:
        raise ValueError(f"All students have < 2 events for course_id={course_id}.")

    print(f"Sequences: {len(sequences)}, concepts: {len(concept2idx)}")
    return concept2idx, sequences


def export_weights(model: nn.Module, course_id: int, concept2idx: dict, models_dir: pathlib.Path) -> None:
    """Export PyTorch LSTM → NumPy .npz + skill_map.json"""
    H = model.hidden_size
    wih = model.lstm.weight_ih_l0.detach().cpu().numpy()
    whh = model.lstm.weight_hh_l0.detach().cpu().numpy()
    b = (model.lstm.bias_ih_l0 + model.lstm.bias_hh_l0).detach().cpu().numpy()
    w_out = model.linear.weight.detach().cpu().numpy()
    b_out = model.linear.bias.detach().cpu().numpy()

    weights_path = models_dir / f"dkt_weights_{course_id}.npz"
    np.savez(
        weights_path,
        Wi=wih[:H], Wf=wih[H:2*H], Wg=wih[2*H:3*H], Wo=wih[3*H:],
        Ri=whh[:H], Rf=whh[H:2*H], Rg=whh[2*H:3*H], Ro=whh[3*H:],
        bi=b[:H], bf=b[H:2*H], bg=b[2*H:3*H], bo=b[3*H:],
        W_out=w_out, b_out=b_out,
    )
    skill_map_path = models_dir / f"dkt_skill_map_{course_id}.json"
    with open(skill_map_path, "w") as f:
        json.dump({
            "concept2idx": {str(k): v for k, v in concept2idx.items()},
            "num_skills": len(concept2idx),
            "hidden_size": H,
        }, f, indent=2)
    print(f"Weights:   {weights_path}")
    print(f"Skill map: {skill_map_path}")


def export_assist_only(pretrain_model: nn.Module, course_id: int, concept2idx: dict,
                       models_dir: pathlib.Path) -> None:
    """Fallback: trim ASSIST09 model to K course concepts and export."""
    K = len(concept2idx)
    H = pretrain_model.hidden_size
    wih = pretrain_model.lstm.weight_ih_l0.detach().cpu().numpy()
    whh = pretrain_model.lstm.weight_hh_l0.detach().cpu().numpy()
    b = (pretrain_model.lstm.bias_ih_l0 + pretrain_model.lstm.bias_hh_l0).detach().cpu().numpy()
    w_out_k = pretrain_model.linear.weight.detach().cpu().numpy()[:K]
    b_out_k = pretrain_model.linear.bias.detach().cpu().numpy()[:K]
    wih_k = wih[:, :2*K]

    weights_path = models_dir / f"dkt_weights_{course_id}.npz"
    np.savez(
        weights_path,
        Wi=wih_k[:H], Wf=wih_k[H:2*H], Wg=wih_k[2*H:3*H], Wo=wih_k[3*H:],
        Ri=whh[:H], Rf=whh[H:2*H], Rg=whh[2*H:3*H], Ro=whh[3*H:],
        bi=b[:H], bf=b[H:2*H], bg=b[2*H:3*H], bo=b[3*H:],
        W_out=w_out_k, b_out=b_out_k,
    )
    skill_map_path = models_dir / f"dkt_skill_map_{course_id}.json"
    with open(skill_map_path, "w") as f:
        json.dump({
            "concept2idx": {str(k): v for k, v in concept2idx.items()},
            "num_skills": K,
            "hidden_size": H,
            "source": "assist09_pretrained",
        }, f, indent=2)
    print(f"ASSIST09 fallback exported (K={K} concepts): {weights_path}")


def finetune(args) -> None:
    set_seed()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}, course_id: {args.course}")

    concept2idx, course_seqs = load_course_sequences(args.course)
    num_skills = len(concept2idx)

    pretrain_path = MODELS_DIR / "dkt_assist09_best.pth"
    if not pretrain_path.exists():
        raise FileNotFoundError(f"Pretrained model not found: {pretrain_path}\nRun dkt_pretrain.py first.")

    # Detect num_skills of pretrained model from checkpoint shape
    state = torch.load(pretrain_path, map_location="cpu")
    pretrain_num_skills = state["linear.weight"].shape[0]

    class _PretrainModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.hidden_size = HIDDEN_SIZE
            self.lstm = nn.LSTM(2 * pretrain_num_skills, HIDDEN_SIZE, batch_first=True)
            self.dropout = nn.Dropout(0.2)
            self.linear = nn.Linear(HIDDEN_SIZE, pretrain_num_skills)
        def forward(self, x):
            out, _ = self.lstm(x)
            return torch.sigmoid(self.linear(self.dropout(out)))

    pretrain_model = _PretrainModel()
    pretrain_model.load_state_dict(state)
    print(f"Pretrained model loaded: {pretrain_num_skills} ASSIST09 skills")

    if args.no_finetune:
        print("\nSkipping fine-tune (--no-finetune). Exporting ASSIST09 fallback...")
        export_assist_only(pretrain_model, args.course, concept2idx, MODELS_DIR)
        return

    # Fine-tune
    ft_train, ft_val = train_test_split(course_seqs, test_size=0.15, random_state=SEED)
    ft_train_loader = DataLoader(DKTDataset(ft_train, num_skills), batch_size=16,
                                 shuffle=True, collate_fn=collate_pad)
    ft_val_loader = DataLoader(DKTDataset(ft_val, num_skills), batch_size=16,
                               shuffle=False, collate_fn=collate_pad)

    ft_model = DKTFineTuned(num_skills, HIDDEN_SIZE).to(device)
    # Transfer hidden-to-hidden weights from pretrained model
    ft_model.lstm.weight_hh_l0.data.copy_(pretrain_model.lstm.weight_hh_l0.data)
    b_avg = (pretrain_model.lstm.bias_ih_l0.data + pretrain_model.lstm.bias_hh_l0.data) * 0.5
    ft_model.lstm.bias_hh_l0.data.copy_(b_avg)
    print("Transferred hidden-to-hidden LSTM weights from ASSIST09")

    optimizer = torch.optim.Adam(ft_model.parameters(), lr=5e-4)
    criterion = nn.BCELoss(reduction="none")
    best_auc = 0.0
    best_path = MODELS_DIR / f"dkt_course_{args.course}_best.pth"

    for epoch in range(args.epochs):
        ft_model.train()
        total_loss, n_batches = 0.0, 0
        for xs, targets, next_skills, mask in ft_train_loader:
            xs, targets, next_skills, mask = (
                xs.to(device), targets.to(device), next_skills.to(device), mask.to(device)
            )
            optimizer.zero_grad()
            preds = ft_model(xs)
            preds_skill = preds.gather(2, next_skills.unsqueeze(-1)).squeeze(-1)
            loss = (criterion(preds_skill, targets) * mask.float()).sum() / mask.float().sum()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(ft_model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        if len(ft_val) > 1:
            ft_auc = evaluate(ft_model, ft_val_loader, device)
            if ft_auc > best_auc:
                best_auc = ft_auc
                torch.save(ft_model.state_dict(), best_path)
            if (epoch + 1) % 5 == 0:
                print(f"FT Epoch {epoch+1:2d}/{args.epochs}  "
                      f"loss={total_loss/n_batches:.4f}  AUC={ft_auc:.4f}")

    print(f"\nFine-tuning done. Best AUC: {best_auc:.4f}")
    if best_path.exists():
        ft_model.load_state_dict(torch.load(best_path, map_location="cpu"))

    print("\nExporting weights...")
    export_weights(ft_model, args.course, concept2idx, MODELS_DIR)
    print("\nDeploy to container:")
    print(f"  docker cp models/dkt_weights_{args.course}.npz "
          f"adaptiveservice-adaptive-service-1:/app/models/")
    print(f"  docker cp models/dkt_skill_map_{args.course}.json "
          f"adaptiveservice-adaptive-service-1:/app/models/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune DKT on course data and export weights")
    parser.add_argument("--course", type=int, default=10, help="Moodle course_id")
    parser.add_argument("--epochs", type=int, default=20, help="Fine-tune epochs")
    parser.add_argument("--no-finetune", action="store_true",
                        help="Skip fine-tune, export ASSIST09 model directly (scarce data fallback)")
    finetune(parser.parse_args())
