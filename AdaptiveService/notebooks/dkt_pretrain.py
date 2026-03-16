"""
Phase 1: Pre-train DKT on ASSIST09 dataset.

Usage:
    python dkt_pretrain.py [--data skill_builder_data.csv] [--epochs 10]
"""

from __future__ import annotations

import argparse
import pathlib
import random

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset

SEED = 42
HIDDEN_SIZE = 128
MAX_SEQ_LEN = 200
BATCH_SIZE = 64
MODELS_DIR = pathlib.Path(__file__).parent.parent / "models"


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


# Dataset

class DKTDataset(Dataset):
    """
    Each sample is a student sequence.
    Input:  one-hot(skill_idx * 2 + correct), shape [T, 2*num_skills]
    Target: correct_{t+1} for skill_{t+1}
    """

    def __init__(self, seqs: list[list[tuple[int, int]]], num_skills: int, max_seq_len: int = MAX_SEQ_LEN):
        self.seqs = [s[:max_seq_len] for s in seqs]
        self.num_skills = num_skills

    def __len__(self) -> int:
        return len(self.seqs)

    def __getitem__(self, idx: int):
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


class DKTModel(nn.Module):
    def __init__(self, num_skills: int, hidden_size: int = HIDDEN_SIZE, dropout: float = 0.2):
        super().__init__()
        self.num_skills = num_skills
        self.hidden_size = hidden_size
        self.lstm = nn.LSTM(input_size=2 * num_skills, hidden_size=hidden_size, num_layers=1, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.linear = nn.Linear(hidden_size, num_skills)

    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.linear(self.dropout(out)))


# Training helpers

def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> float:
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


def load_assist09(data_path: pathlib.Path) -> tuple[list, int]:
    """Load ASSIST09 csv → (sequences, num_skills)."""
    df = pd.read_csv(data_path, encoding="latin-1",
                     usecols=["user_id", "skill_id", "correct", "order_id"],
                     low_memory=False)
    df = df.dropna(subset=["skill_id", "correct"])
    df["correct"] = df["correct"].astype(int).clip(0, 1)
    df["skill_id"] = df["skill_id"].astype(int)
    unique_skills = sorted(df["skill_id"].unique())
    skill2idx = {s: i for i, s in enumerate(unique_skills)}
    df["skill_idx"] = df["skill_id"].map(skill2idx)
    df_sorted = df.sort_values(["user_id", "order_id"])
    sequences = {}
    for uid, group in df_sorted.groupby("user_id"):
        seq = list(zip(group["skill_idx"].tolist(), group["correct"].tolist()))
        if len(seq) >= 3:
            sequences[uid] = seq
    print(f"ASSIST09: {len(df):,} interactions, {df.user_id.nunique()} students, "
          f"{len(unique_skills)} skills, {len(sequences)} valid sequences")
    return list(sequences.values()), len(unique_skills)


def train(args) -> None:
    set_seed()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    seqs, num_skills = load_assist09(args.data)
    train_seqs, val_seqs = train_test_split(seqs, test_size=0.1, random_state=SEED)
    print(f"Train: {len(train_seqs)}, Val: {len(val_seqs)}")

    train_loader = DataLoader(
        DKTDataset(train_seqs, num_skills), batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_pad
    )
    val_loader = DataLoader(
        DKTDataset(val_seqs, num_skills), batch_size=BATCH_SIZE, shuffle=False, collate_fn=collate_pad
    )

    model = DKTModel(num_skills, HIDDEN_SIZE).to(device)
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.BCELoss(reduction="none")
    best_auc = 0.0
    out_path = MODELS_DIR / "dkt_assist09_best.pth"

    for epoch in range(args.epochs):
        model.train()
        total_loss, n_batches = 0.0, 0
        for xs, targets, next_skills, mask in train_loader:
            xs, targets, next_skills, mask = (
                xs.to(device), targets.to(device), next_skills.to(device), mask.to(device)
            )
            optimizer.zero_grad()
            preds = model(xs)
            preds_skill = preds.gather(2, next_skills.unsqueeze(-1)).squeeze(-1)
            loss = criterion(preds_skill, targets)
            loss = (loss * mask.float()).sum() / mask.float().sum()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        val_auc = evaluate(model, val_loader, device)
        print(f"Epoch {epoch+1:2d}/{args.epochs}  loss={total_loss/n_batches:.4f}  val_AUC={val_auc:.4f}")

        if val_auc > best_auc:
            best_auc = val_auc
            torch.save(model.state_dict(), out_path)

    print(f"\nBest val AUC: {best_auc:.4f}")
    print(f"Checkpoint saved: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-train DKT on ASSIST09")
    parser.add_argument("--data", type=pathlib.Path, default=pathlib.Path("skill_builder_data.csv"),
                        help="Path to skill_builder_data.csv")
    parser.add_argument("--epochs", type=int, default=10)
    train(parser.parse_args())
