# quiz_answer_key.py
from __future__ import annotations

import html
import random
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional


def norm_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def el_text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


@dataclass
class QuestionKey:
    qtype: str
    name: str
    qtext_norm: str
    correct_choices_text: List[str]      # для multichoice/truefalse (normalized)
    correct_shortanswers: List[str]      # для shortanswer (original text)
    matching_pairs: Dict[str, str]       # для matching: subquestion_text -> correct_answer_text


def load_question_bank(xml_path: str) -> Dict[str, QuestionKey]:
    root = ET.parse(xml_path).getroot()
    out: Dict[str, QuestionKey] = {}

    for q in root.findall("question"):
        qtype = (q.get("type") or "").strip()
        if qtype == "category":
            continue

        name = el_text(q.find("name/text"))
        qtext_raw = el_text(q.find("questiontext/text"))
        qtext_norm = norm_text(qtext_raw)

        if not qtext_norm:
            continue

        correct_choices: List[str] = []
        correct_short: List[str] = []
        matching_pairs: Dict[str, str] = {}

        if qtype in ("multichoice", "truefalse"):
            for ans in q.findall("answer"):
                try:
                    frac = float(ans.get("fraction") or "0")
                except ValueError:
                    frac = 0.0
                if frac > 0:
                    correct_choices.append(norm_text(el_text(ans.find("text"))))

        elif qtype == "shortanswer":
            for ans in q.findall("answer"):
                try:
                    frac = float(ans.get("fraction") or "0")
                except ValueError:
                    frac = 0.0
                if frac > 0:
                    correct_short.append(el_text(ans.find("text")).strip())

        elif qtype == "matching":
            for sq in q.findall("subquestion"):
                sq_text = norm_text(el_text(sq.find("text")))
                ans_text = norm_text(el_text(sq.find("answer/text")))
                if sq_text and ans_text:
                    matching_pairs[sq_text] = ans_text

        else:
            pass

        out[qtext_norm] = QuestionKey(
            qtype=qtype,
            name=name,
            qtext_norm=qtext_norm,
            correct_choices_text=[c for c in correct_choices if c],
            correct_shortanswers=[c for c in correct_short if c],
            matching_pairs=matching_pairs,
        )

    return out


def pick_wrong_text() -> str:
    """Simple generator for 'wrong' answer text."""
    return random.choice(["Test answer", "42", "idk", "None", "???"])
