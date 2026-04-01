"""
Usage:
    python dkt_export.py --course 10
    python dkt_export.py --course 10 --seq-file sample_seq.json   # custom sequence
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

MODELS_DIR = pathlib.Path(__file__).parent.parent / "models"


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def lstm_step(x: np.ndarray, h: np.ndarray, c: np.ndarray, W: dict) -> tuple[np.ndarray, np.ndarray]:
    i = sigmoid(W["Wi"] @ x + W["Ri"] @ h + W["bi"])
    f = sigmoid(W["Wf"] @ x + W["Rf"] @ h + W["bf"])
    g = np.tanh(W["Wg"] @ x + W["Rg"] @ h + W["bg"])
    o = sigmoid(W["Wo"] @ x + W["Ro"] @ h + W["bo"])
    c_new = f * c + i * g
    h_new = o * np.tanh(c_new)
    return h_new, c_new


def run_sequence(seq: list[tuple[int, int]], W: dict, num_skills: int,
                 hidden_size: int) -> list[np.ndarray]:
    """Run LSTM over a sequence; return list of P(correct) vectors per step."""
    h = np.zeros(hidden_size)
    c = np.zeros(hidden_size)
    preds = []
    for skill_idx, correct in seq:
        x = np.zeros(2 * num_skills)
        x[skill_idx * 2 + correct] = 1.0
        h, c = lstm_step(x, h, c, W)
        preds.append(sigmoid(W["W_out"] @ h + W["b_out"]))
    return preds


def sanity_check_good_vs_poor(W: dict, num_skills: int, hidden_size: int) -> float:
    """Return avg P(correct) difference: good student minus poor student."""
    n_steps = max(20, num_skills * 3)
    good = [(i % num_skills, 1) for i in range(n_steps)]
    poor = [(i % num_skills, 0) for i in range(n_steps)]
    p_good = run_sequence(good, W, num_skills, hidden_size)[-1]
    p_poor = run_sequence(poor, W, num_skills, hidden_size)[-1]
    return float(np.mean(p_good) - np.mean(p_poor))


def verify(args) -> None:
    weights_path = MODELS_DIR / f"dkt_weights_{args.course}.npz"
    map_path = MODELS_DIR / f"dkt_skill_map_{args.course}.json"

    if not weights_path.exists():
        raise FileNotFoundError(f"Weights not found: {weights_path}\nRun dkt_finetune.py first.")
    if not map_path.exists():
        raise FileNotFoundError(f"Skill map not found: {map_path}\nRun dkt_finetune.py first.")

    W = dict(np.load(weights_path))
    with open(map_path) as f:
        meta = json.load(f)

    num_skills = meta["num_skills"]
    hidden_size = meta["hidden_size"]
    concept2idx = {int(k): v for k, v in meta["concept2idx"].items()}
    idx2concept = {v: k for k, v in concept2idx.items()}
    source = meta.get("source", "fine_tuned")

    print(f"=== DKT Export Verification ===")
    print(f"Course:      {args.course}")
    print(f"Concepts:    {num_skills}")
    print(f"Hidden size: {hidden_size}")
    print(f"Source:      {source}")
    print(f"Concept IDs: {list(concept2idx.keys())}")

    # Check 1: probabilities in range
    h = np.zeros(hidden_size)
    c = np.zeros(hidden_size)
    x = np.zeros(2 * num_skills)
    x[0] = 1.0
    h, c = lstm_step(x, h, c, W)
    p = sigmoid(W["W_out"] @ h + W["b_out"])
    assert p.shape == (num_skills,), f"Output shape mismatch: {p.shape} vs ({num_skills},)"
    assert np.all(p >= 0.0) and np.all(p <= 1.0), "Probabilities out of [0, 1]"
    print("\n[OK] Output shape and probability range")

    # Check 2: good vs poor student
    avg_diff = sanity_check_good_vs_poor(W, num_skills, hidden_size)
    print(f"\n=== Good student vs Poor student ===")
    good_seq = [(i % num_skills, 1) for i in range(max(20, num_skills * 3))]
    poor_seq = [(i % num_skills, 0) for i in range(max(20, num_skills * 3))]
    p_good = run_sequence(good_seq, W, num_skills, hidden_size)[-1]
    p_poor = run_sequence(poor_seq, W, num_skills, hidden_size)[-1]

    print(f"{'Concept':>10} | {'Good':>8} | {'Poor':>8} | {'Diff':>8}")
    print("-" * 45)
    for idx in range(num_skills):
        cid = idx2concept.get(idx, idx)
        diff = p_good[idx] - p_poor[idx]
        print(f"  {cid:>8} | {p_good[idx]:>8.3f} | {p_poor[idx]:>8.3f} | {diff:>+8.3f}")

    print(f"\nAvg diff: {avg_diff:+.3f}")
    if avg_diff > 0.05:
        print("[PASS] Model correctly distinguishes good vs poor students")
    elif avg_diff > 0.0:
        print("[WARN] Model weakly distinguishes — may need more training data")
    else:
        print("[FAIL] Model does not distinguish — check training or export")

    # Check 3: custom sequence (optional)
    if args.seq_file:
        with open(args.seq_file) as f:
            custom_seq = [(int(s), int(c)) for s, c in json.load(f)]
        preds = run_sequence(custom_seq, W, num_skills, hidden_size)
        print(f"\n=== Custom sequence: {len(custom_seq)} steps ===")
        final_p = preds[-1]
        for idx in range(num_skills):
            cid = idx2concept.get(idx, idx)
            marker = " <- seen" if any(s == idx for s, _ in custom_seq) else ""
            print(f"  concept {cid}: {final_p[idx]:.3f}{marker}")

    # Optional: visualisation
    if args.plot:
        try:
            import matplotlib.pyplot as plt
            preds_over_time = np.array(
                run_sequence(good_seq[:min(50, len(good_seq))], W, num_skills, hidden_size)
            )  # [T, K]
            plt.figure(figsize=(10, 4))
            for k in range(min(5, num_skills)):
                plt.plot(preds_over_time[:, k], label=f"concept {idx2concept.get(k, k)}", alpha=0.8)
            plt.title(f"P(correct) over time — good student (course {args.course})")
            plt.xlabel("Step")
            plt.ylabel("P(correct)")
            plt.ylim(0, 1)
            plt.legend(fontsize=8)
            plt.tight_layout()
            out = MODELS_DIR / f"dkt_sanity_{args.course}.png"
            plt.savefig(out, dpi=120)
            print(f"\nPlot saved: {out}")
        except ImportError:
            print("matplotlib not installed — skipping plot")

    print("\nDeploy to container:")
    print(f"  docker cp models/dkt_weights_{args.course}.npz "
          f"adaptiveservice-adaptive-service-1:/app/models/")
    print(f"  docker cp models/dkt_skill_map_{args.course}.json "
          f"adaptiveservice-adaptive-service-1:/app/models/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify DKT NumPy export")
    parser.add_argument("--course", type=int, default=10)
    parser.add_argument("--seq-file", type=pathlib.Path, default=None,
                        help="JSON file with custom sequence [[skill_idx, correct], ...]")
    parser.add_argument("--plot", action="store_true", help="Save P(correct) over time plot")
    verify(parser.parse_args())
