"""
Unit tests for prepare_lightfm_data().
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from app.lightfm_data import prepare_lightfm_data


def _mock_result(items: list):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _make_content_item(id, course_id, moodle_cmid, concept_id, type="page", difficulty=0.5, role="regular"):
    return SimpleNamespace(
        id=id, course_id=course_id, moodle_cmid=moodle_cmid,
        concept_id=concept_id, type=type, difficulty=difficulty, role=role,
    )


def _make_mastery(student_id, course_id, concept_id, mastery):
    return SimpleNamespace(
        student_id=student_id, course_id=course_id, concept_id=concept_id, mastery=mastery,
    )


def _make_stats(student_id, course_id, concept_id, num_attempts, num_correct):
    return SimpleNamespace(
        student_id=student_id, course_id=course_id, concept_id=concept_id,
        num_attempts=num_attempts, num_correct=num_correct,
    )


def _make_assessment_map(content_item_id, concept_id, weight):
    return SimpleNamespace(content_item_id=content_item_id, concept_id=concept_id, weight=weight)


def _make_db(*responses):
    """Mock DB where each execute() call returns the next response in sequence."""
    db = AsyncMock()
    db.execute.side_effect = list(responses)
    return db


@pytest.mark.asyncio
async def test_returns_none_when_no_content_items():
    db = _make_db(
        _mock_result([]),   # ContentItem query → empty
    )
    result = await prepare_lightfm_data(db, course_id=1)
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_when_no_student_data():
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    db = _make_db(
        _mock_result([item]),   # ContentItem
        _mock_result([]),       # AssessmentMap
        _mock_result([]),       # StudentConceptMastery → empty
        _mock_result([]),       # StudentConceptStats → empty
    )
    result = await prepare_lightfm_data(db, course_id=1)
    assert result is None


@pytest.mark.asyncio
async def test_basic_dataset_shapes():
    """1 student, 2 items, 1 concept → interaction matrix (1×2)."""
    item1 = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100, type="page", difficulty=0.3)
    item2 = _make_content_item(id=2, course_id=1, moodle_cmid=20, concept_id=100, type="quiz", difficulty=0.6)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.5)

    db = _make_db(
        _mock_result([item1, item2]),   # ContentItem
        _mock_result([]),               # AssessmentMap
        _mock_result([mastery]),        # StudentConceptMastery
        _mock_result([]),               # StudentConceptStats
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    assert dataset.interactions.shape == (1, 2)
    assert dataset.user_features.shape[0] == 1   # 1 user
    assert dataset.item_features.shape[0] == 2   # 2 items


@pytest.mark.asyncio
async def test_multiple_students():
    """2 students, 1 item, 1 concept → interaction matrix (2×1)."""
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    m1 = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.6)
    m2 = _make_mastery(student_id=2, course_id=1, concept_id=100, mastery=0.4)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([m1, m2]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    assert dataset.interactions.shape == (2, 1)


@pytest.mark.asyncio
async def test_interaction_weight_uses_stats_over_mastery():
    """When stats exist, weight = num_correct/num_attempts (not mastery)."""
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.9)
    stats = _make_stats(student_id=1, course_id=1, concept_id=100, num_attempts=5, num_correct=2)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([stats]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    # Weight should be 2/5=0.4, not mastery=0.9
    w = dataset.interactions[0, 0]
    assert float(w) == pytest.approx(0.4, abs=1e-4)


@pytest.mark.asyncio
async def test_interaction_weight_falls_back_to_mastery():
    """When no stats, weight = mastery value."""
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.7)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    w = dataset.interactions[0, 0]
    assert float(w) == pytest.approx(0.7, abs=1e-4)


@pytest.mark.asyncio
async def test_zero_weight_items_excluded():
    """Items with weight <= 0 are not added to the interaction matrix."""
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.0)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    # mastery=0 → weight=0 → interaction entry skipped → nnz=0
    result = await prepare_lightfm_data(db, course_id=1)
    assert result is None


@pytest.mark.asyncio
async def test_cmid_map_is_correct():
    """cmid_map must map content_item.id → moodle_cmid."""
    item = _make_content_item(id=7, course_id=1, moodle_cmid=42, concept_id=100)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.5)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    assert dataset.cmid_map[7] == 42


@pytest.mark.asyncio
async def test_assessment_map_adds_secondary_concept():
    """An assessment_map link adds a secondary concept column to item_features."""
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    am = _make_assessment_map(content_item_id=1, concept_id=200, weight=0.5)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.5)

    db = _make_db(
        _mock_result([item]),
        _mock_result([am]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    # concept_ids should include both primary (100) and secondary (200)
    assert 100 in dataset.concept_ids
    assert 200 in dataset.concept_ids


@pytest.mark.asyncio
async def test_item_features_column_count():
    """
    Item features = 5 type cols + 3 difficulty cols + n_concept cols.
    With 1 concept → n_item_features = 5 + 3 + 1 = 9.
    """
    item = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100)
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.5)

    db = _make_db(
        _mock_result([item]),
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    assert dataset.item_features.shape[1] == 9  # 5 types + 3 diff + 1 concept


@pytest.mark.asyncio
async def test_placement_items_included_in_data():
    """
    The prepare_lightfm_data query already filters role != 'placement' in the WHERE clause.
    This test confirms that when the DB returns no placement items,
    the dataset is built only from regular items.
    """
    regular = _make_content_item(id=1, course_id=1, moodle_cmid=10, concept_id=100, role="regular")
    mastery = _make_mastery(student_id=1, course_id=1, concept_id=100, mastery=0.5)

    db = _make_db(
        _mock_result([regular]),  # DB already filtered out placement; only regular returned
        _mock_result([]),
        _mock_result([mastery]),
        _mock_result([]),
    )
    dataset = await prepare_lightfm_data(db, course_id=1)

    assert dataset is not None
    assert dataset.interactions.shape == (1, 1)
