from typing import List, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TaskAttempt


class BKT:
    """
    Bayesian Knowledge Tracing with standard posterior update.

    Parameters
    ----------
    p_l0 : float  Prior probability the student knows the concept at start.
    p_t  : float  Probability of learning the concept on each attempt (transition).
    p_s  : float  Probability of slipping — answering wrong despite knowing.
    p_g  : float  Probability of guessing — answering right without knowing.
    """

    def __init__(
        self,
        p_l0: float = 0.3,
        p_t: float = 0.15,
        p_s: float = 0.05,
        p_g: float = 0.2,
    ):
        self.p_t = p_t
        self.p_s = p_s
        self.p_g = p_g
        self.knowledge = p_l0  # P(L_0)

    def update(self, correct: bool) -> float:
        """
        Uses full Bayesian posterior:
            P(L | obs) = P(L) * P(obs | L=1) / P(obs)
        followed by the transition step:
            P(L_{t+1}) = P(L | obs) + (1 - P(L | obs)) * P(T)
        """
        if correct:
            p_obs_known = 1.0 - self.p_s   # P(correct | L=1)
            p_obs_unknown = self.p_g        # P(correct | L=0)
        else:
            p_obs_known = self.p_s          # P(wrong | L=1)
            p_obs_unknown = 1.0 - self.p_g  # P(wrong | L=0)

        p_obs = (
            self.knowledge * p_obs_known
            + (1.0 - self.knowledge) * p_obs_unknown
        )
        if p_obs > 0:
            posterior = self.knowledge * p_obs_known / p_obs
        else:
            posterior = self.knowledge

        # Transition step
        self.knowledge = posterior + (1.0 - posterior) * self.p_t

        # P(answer correctly on next question)
        p_correct = (
            self.knowledge * (1.0 - self.p_s)
            + (1.0 - self.knowledge) * self.p_g
        )
        return p_correct

    def predict_difficulty(self) -> str:
        if self.knowledge > 0.75:
            return "hard"
        elif self.knowledge > 0.45:
            return "medium"
        return "easy"


async def get_student_history(
    db: AsyncSession, student_id: int, concept_id: int
) -> List[Tuple[str, float]]:
    result = await db.execute(
        select(TaskAttempt)
        .where(
            TaskAttempt.student_id == student_id,
            TaskAttempt.concept_id == concept_id,
        )
        .order_by(TaskAttempt.created_at)
    )
    return [(a.difficulty, a.score) for a in result.scalars()]


def hybrid_bkt_recent(history: List[Tuple[str, float]]) -> str:
    if not history:
        return "easy"  # cold start

    # Recent average — last 5 scores capture current form
    recent_scores = [s for _, s in history[-5:]]
    recent_avg = float(np.mean(recent_scores))

    # BKT — run over full history for long-term knowledge estimate
    bkt = BKT()
    for _, score in history:
        bkt.update(score > 0.5)

    bkt_p = bkt.knowledge

    # Hybrid selection rule
    if recent_avg > 0.7 and bkt_p > 0.6:
        return "hard"
    elif bkt_p > 0.5 or recent_avg > 0.4:
        return "medium"
    return "easy"


async def select_optimal_difficulty(
    db: AsyncSession,
    student_id: int,
    concept_id: int,
    mastery: float,
) -> Tuple[str, float]:
    history = await get_student_history(db, student_id, concept_id)

    difficulty = hybrid_bkt_recent(history)

    # Hard override for absolute beginners regardless of BKT
    if mastery < 0.2:
        difficulty = "easy"

    # Rerun BKT to expose p_success to the prompt
    bkt = BKT()
    for _, score in history:
        bkt.update(score > 0.5)

    return difficulty, bkt.knowledge
