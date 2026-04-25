"""Minimal tests for study_history classifier."""

from app.study_history import _classify


def _row(cmid, event_type, payload=None):
    return {"cmid": cmid, "event_type": event_type, "payload": payload}


def test_passed_quiz_is_studied():
    rows = [_row(514, "quiz_attempt_submitted", {"score": 0.8, "max_score": 1.0})]
    assert _classify(rows, item_types={514: "quiz"}) == {514}


def test_failed_quiz_is_not_studied():
    """Score < 0.7 keeps the quiz recommendable for retry."""
    rows = [_row(514, "quiz_attempt_submitted", {"score": 0.3, "max_score": 1.0})]
    assert _classify(rows, item_types={514: "quiz"}) == set()


def test_failed_quiz_overrides_prior_view():
    """Even if a quiz was viewed, a subsequent failed attempt makes it eligible again."""
    rows = [
        _row(514, "course_module_viewed"),
        _row(514, "quiz_attempt_submitted", {"score": 0.0, "max_score": 1.0}),
    ]
    assert _classify(rows, item_types={514: "quiz"}) == set()


def test_lesson_view_alone_is_not_studied():
    """Opening a lesson without completing it doesn't make it 'studied' —
    student should be able to come back and finish it."""
    rows = [_row(513, "course_module_viewed")]
    assert _classify(rows, item_types={513: "lesson"}) == set()


def test_lesson_with_completion_is_studied():
    rows = [
        _row(513, "course_module_viewed"),
        _row(513, "lesson_completed"),
    ]
    assert _classify(rows, item_types={513: "lesson"}) == {513}


def test_page_view_counts_as_studied():
    """For page/book there's no completion event — a view counts."""
    rows = [_row(520, "course_module_viewed")]
    assert _classify(rows, item_types={520: "page"}) == {520}


def test_book_view_counts_as_studied():
    rows = [_row(521, "course_module_viewed")]
    assert _classify(rows, item_types={521: "book"}) == {521}


def test_quiz_view_alone_is_not_studied():
    """Viewing a quiz without attempting it shouldn't exclude it from recommendations."""
    rows = [_row(514, "course_module_viewed")]
    assert _classify(rows, item_types={514: "quiz"}) == set()


def test_lesson_completed_no_questions_is_studied():
    """A pure-content lesson (no questions) counts as studied on completion."""
    rows = [_row(513, "lesson_completed", {"num_questions": 0, "num_correct": 0})]
    assert _classify(rows, item_types={513: "lesson"}) == {513}


def test_lesson_completed_high_score_is_studied():
    rows = [_row(513, "lesson_completed", {"num_questions": 4, "num_correct": 4})]
    assert _classify(rows, item_types={513: "lesson"}) == {513}


def test_lesson_completed_low_score_is_not_studied():
    """1/4 correct on lesson questions → student didn't really master it."""
    rows = [_row(537, "lesson_completed", {"num_questions": 4, "num_correct": 1})]
    assert _classify(rows, item_types={537: "lesson"}) == set()


def test_lesson_completed_takes_best_of_multiple_attempts():
    rows = [
        _row(513, "lesson_completed", {"num_questions": 5, "num_correct": 0}),
        _row(513, "lesson_completed", {"num_questions": 5, "num_correct": 5}),
    ]
    assert _classify(rows, item_types={513: "lesson"}) == {513}


def test_quiz_takes_best_of_multiple_attempts():
    """First failed, second passed → studied."""
    rows = [
        _row(514, "quiz_attempt_submitted", {"score": 0.3, "max_score": 1.0}),
        _row(514, "quiz_attempt_submitted", {"score": 0.9, "max_score": 1.0}),
    ]
    assert _classify(rows, item_types={514: "quiz"}) == {514}


def test_passed_assign():
    rows = [_row(700, "assign_submission_graded", {"score": 9.0, "max_score": 10.0})]
    assert _classify(rows, item_types={700: "assign"}) == {700}


def test_payload_as_json_string():
    """asyncpg sometimes returns JSONB as str — classifier must handle it."""
    rows = [_row(514, "quiz_attempt_submitted", '{"score": 0.9, "max_score": 1.0}')]
    assert _classify(rows, item_types={514: "quiz"}) == {514}
