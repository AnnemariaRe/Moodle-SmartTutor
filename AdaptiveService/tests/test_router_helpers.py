"""
Unit tests for pure helper functions in router.py:
  - _make_rec_item: builds a RecommendationItem from a ContentItem ORM object
  - _dedupe_by_cmid: removes duplicate items by moodle_cmid, preserving order
"""
from types import SimpleNamespace

import pytest

from app.router import _dedupe_by_cmid, _make_rec_item
from app.schemas import RecommendationItem


def _make_item(id=1, moodle_cmid=10, type="quiz", concept_id=100, difficulty=0.5):
    return SimpleNamespace(
        id=id, moodle_cmid=moodle_cmid, type=type,
        concept_id=concept_id, difficulty=difficulty,
    )


class TestMakeRecItem:

    def test_builds_correct_recommendation_item(self):
        item = _make_item(id=5, moodle_cmid=42, type="quiz", concept_id=100, difficulty=0.6)
        rec = _make_rec_item(item, concept_name="Algebra", reason="Practice this")
        assert isinstance(rec, RecommendationItem)
        assert rec.content_item_id == 5
        assert rec.moodle_cmid == 42
        assert rec.type == "quiz"
        assert rec.concept_id == 100
        assert rec.concept_name == "Algebra"
        assert rec.difficulty == pytest.approx(0.6)
        assert rec.reason == "Practice this"

    def test_passes_through_all_item_types(self):
        for item_type in ("page", "assign", "lesson", "url"):
            item = _make_item(type=item_type)
            rec = _make_rec_item(item, concept_name="C", reason="R")
            assert rec.type == item_type

    def test_empty_concept_name_and_reason_allowed(self):
        item = _make_item()
        rec = _make_rec_item(item, concept_name="", reason="")
        assert rec.concept_name == ""
        assert rec.reason == ""

    def test_difficulty_preserved(self):
        item = _make_item(difficulty=0.0)
        rec = _make_rec_item(item, "C", "R")
        assert rec.difficulty == pytest.approx(0.0)

        item2 = _make_item(difficulty=1.0)
        rec2 = _make_rec_item(item2, "C", "R")
        assert rec2.difficulty == pytest.approx(1.0)


class TestDedupeByMoodle:

    def test_empty_list_returns_empty(self):
        assert _dedupe_by_cmid([]) == []

    def test_no_duplicates_unchanged(self):
        items = [_make_item(id=1, moodle_cmid=10), _make_item(id=2, moodle_cmid=20)]
        result = _dedupe_by_cmid(items)
        assert len(result) == 2
        assert result[0].id == 1
        assert result[1].id == 2

    def test_duplicate_cmid_keeps_first_occurrence(self):
        item1 = _make_item(id=1, moodle_cmid=10)
        item2 = _make_item(id=2, moodle_cmid=10)  # same cmid
        result = _dedupe_by_cmid([item1, item2])
        assert len(result) == 1
        assert result[0].id == 1

    def test_preserves_insertion_order(self):
        items = [
            _make_item(id=3, moodle_cmid=30),
            _make_item(id=1, moodle_cmid=10),
            _make_item(id=2, moodle_cmid=20),
        ]
        result = _dedupe_by_cmid(items)
        assert [i.id for i in result] == [3, 1, 2]

    def test_multiple_groups_of_duplicates(self):
        items = [
            _make_item(id=1, moodle_cmid=10),
            _make_item(id=2, moodle_cmid=20),
            _make_item(id=3, moodle_cmid=10),  # dup of id=1
            _make_item(id=4, moodle_cmid=20),  # dup of id=2
            _make_item(id=5, moodle_cmid=30),
        ]
        result = _dedupe_by_cmid(items)
        assert len(result) == 3
        assert [i.id for i in result] == [1, 2, 5]

    def test_all_same_cmid_keeps_one(self):
        items = [_make_item(id=i, moodle_cmid=99) for i in range(5)]
        result = _dedupe_by_cmid(items)
        assert len(result) == 1
        assert result[0].id == 0
