"""
export_from_tracking.py
-----------------------
Экспортирует данные из TrackingService PostgreSQL в формат обучающей выборки
для CoursePortrait ML-моделей (dropout_predictor, difficulty_predictor).

Выходной формат (совместим с prep_and_train.py):
    courseId, moduleId, durationMs, watchPercent, step, dropout

Запуск:
    python export_from_tracking.py
    python export_from_tracking.py --dropout-days 10 --min-events 2
    python export_from_tracking.py --db-url postgresql://tracking:tracking@localhost:5435/tracking
"""

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timezone

from pathlib import Path

import psycopg2
import psycopg2.extras

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = str(BASE_DIR / "datasets/my_data.csv")
DEFAULT_DB_URL = "postgresql://tracking:tracking@localhost:5435/tracking"
DEFAULT_DROPOUT_DAYS = 14
DEFAULT_MIN_EVENTS = 2   # минимум событий в модуле чтобы включить строку

# Какие события считаются "активностью в модуле"
MODULE_EVENTS = {
    "course_module_viewed",
    "lesson_page_view",
    "lesson_started",
    "lesson_answer_submitted",
    "quiz_attempt_submitted",
    "assign_submission_created",
    "assign_submission_graded",
}

# События завершения (submission/grade) — считаем как watchPercent = 1.0
COMPLETION_EVENTS = {
    "quiz_attempt_submitted",
    "assign_submission_created",
    "assign_submission_graded",
}


def connect(db_url: str):
    conn = psycopg2.connect(db_url)
    return conn


def fetch_events(conn, course_id: int | None = None) -> list[dict]:
    """Достаём все события из TrackingService."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if course_id:
        cur.execute(
            """
            SELECT student_id, course_id, event_type, cmid, ts, payload
            FROM events
            WHERE cmid IS NOT NULL
              AND event_type = ANY(%s)
              AND course_id = %s
            ORDER BY student_id, ts
            """,
            (list(MODULE_EVENTS), course_id),
        )
    else:
        cur.execute(
            """
            SELECT student_id, course_id, event_type, cmid, ts, payload
            FROM events
            WHERE cmid IS NOT NULL
              AND event_type = ANY(%s)
            ORDER BY student_id, ts
            """,
            (list(MODULE_EVENTS),),
        )
    return [dict(row) for row in cur.fetchall()]


def fetch_last_event_per_student(conn, course_id: int | None = None) -> dict[tuple, int]:
    """Возвращает {(student_id, course_id): last_ts}."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if course_id:
        cur.execute(
            """
            SELECT student_id, course_id, MAX(ts) AS last_ts
            FROM events
            WHERE course_id = %s
            GROUP BY student_id, course_id
            """,
            (course_id,),
        )
    else:
        cur.execute(
            """
            SELECT student_id, course_id, MAX(ts) AS last_ts
            FROM events
            GROUP BY student_id, course_id
            """
        )
    return {(row["student_id"], row["course_id"]): row["last_ts"] for row in cur.fetchall()}


def build_dataset(
    events: list[dict],
    last_ts_map: dict[tuple, int],
    dropout_days: int,
    min_events: int,
    now_ts: int,
) -> list[dict]:
    """
    Строит обучающую выборку: одна строка = студент × модуль.

    Алгоритм:
    1. Группируем события по (student_id, course_id, cmid).
    2. Для каждой группы считаем:
       - durationMs  = время между первым и последним событием в модуле
       - watchPercent = 1.0 если есть событие завершения, иначе по доле времени
       - step         = порядок первого визита среди всех модулей студента в курсе
    3. Dropout студента в курсе = его последнее событие >dropout_days дней назад.
    4. Метка dropout для строки:
       - 1 если студент — dropout И cmid входит в последние 3 модуля, которые он посетил
       - 0 иначе
    """
    # Группировка: (student_id, course_id, cmid) -> список ts
    groups: dict[tuple, dict] = defaultdict(lambda: {
        "ts_list": [],
        "has_completion": False,
        "event_count": 0,
    })

    for ev in events:
        key = (ev["student_id"], ev["course_id"], ev["cmid"])
        groups[key]["ts_list"].append(ev["ts"])
        groups[key]["event_count"] += 1
        if ev["event_type"] in COMPLETION_EVENTS:
            groups[key]["has_completion"] = True

    # Первый визит каждого модуля для каждого студента в курсе
    # -> нужен для вычисления step
    first_visit: dict[tuple, int] = {}  # (student_id, course_id, cmid) -> min_ts
    for key, data in groups.items():
        first_visit[key] = min(data["ts_list"])

    # Считаем step: ранг модуля по времени первого визита в рамках студент+курс
    student_course_modules: dict[tuple, list] = defaultdict(list)
    for (student_id, course_id, cmid), ts in first_visit.items():
        student_course_modules[(student_id, course_id)].append((ts, cmid))

    step_map: dict[tuple, int] = {}  # (student_id, course_id, cmid) -> step
    for (student_id, course_id), module_visits in student_course_modules.items():
        sorted_visits = sorted(module_visits, key=lambda x: x[0])
        for rank, (_, cmid) in enumerate(sorted_visits, start=1):
            step_map[(student_id, course_id, cmid)] = rank

    # Последние N модулей каждого студента в курсе (для dropout-метки)
    last_modules: dict[tuple, set] = {}
    for (student_id, course_id), module_visits in student_course_modules.items():
        sorted_visits = sorted(module_visits, key=lambda x: x[0], reverse=True)
        last_modules[(student_id, course_id)] = {cmid for _, cmid in sorted_visits[:3]}

    # Строим датасет
    rows = []
    dropout_threshold_sec = dropout_days * 86400

    for (student_id, course_id, cmid), data in groups.items():
        if data["event_count"] < min_events:
            continue

        ts_list = sorted(data["ts_list"])
        first_ts = ts_list[0]
        last_ts_module = ts_list[-1]

        # durationMs: время в модуле (мин. 1 сек)
        duration_ms = max((last_ts_module - first_ts) * 1000, 1000)

        # watchPercent
        if data["has_completion"]:
            watch_percent = 1.0
        else:
            # Приближение по времени: >5 мин = 1.0, иначе пропорционально
            watch_percent = min(1.0, duration_ms / 300_000)

        step = step_map.get((student_id, course_id, cmid), 1)

        # Dropout студента в курсе
        last_ts_course = last_ts_map.get((student_id, course_id), first_ts)
        student_is_dropout = (now_ts - last_ts_course) > dropout_threshold_sec

        # Dropout-метка для строки: дропнул ли после этого модуля
        is_last_module = cmid in last_modules.get((student_id, course_id), set())
        dropout = 1 if (student_is_dropout and is_last_module) else 0

        rows.append({
            "courseId": course_id,
            "moduleId": cmid,
            "durationMs": round(duration_ms),
            "watchPercent": round(watch_percent, 4),
            "step": step,
            "dropout": dropout,
        })

    return rows


def print_stats(rows: list[dict], dropout_days: int):
    total = len(rows)
    dropouts = sum(1 for r in rows if r["dropout"] == 1)
    courses = len(set(r["courseId"] for r in rows))
    students_modules = len(set((r["courseId"], r["moduleId"]) for r in rows))

    print(f"\n{'='*55}")
    print(f"  Экспорт завершён")
    print(f"{'='*55}")
    print(f"  Строк итого:          {total}")
    print(f"  Из них dropout=1:     {dropouts} ({dropouts/total*100:.1f}%)")
    print(f"  Курсов:               {courses}")
    print(f"  Уникальных модулей:   {students_modules}")
    print(f"  Порог dropout:        {dropout_days} дней неактивности")
    print(f"{'='*55}\n")

    if total < 200:
        print(f"  ⚠  Строк мало ({total}). Рекомендуется ≥500 для уверенного обучения.")
    if dropouts == 0:
        print("  ⚠  Нет dropout=1. Уменьши --dropout-days или подожди накопления данных.")
    elif dropouts / total < 0.05:
        print("  ⚠  Очень мало дропаутов (<5%). Модель может плохо их распознавать.")


def main():
    parser = argparse.ArgumentParser(
        description="Экспорт данных из TrackingService для обучения ML-моделей CoursePortrait",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("TRACKING_DB_URL", DEFAULT_DB_URL),
        help=f"PostgreSQL URL TrackingService (default: {DEFAULT_DB_URL})",
    )
    parser.add_argument(
        "--dropout-days",
        type=int,
        default=DEFAULT_DROPOUT_DAYS,
        help=f"Дней неактивности для метки dropout (default: {DEFAULT_DROPOUT_DAYS})",
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=DEFAULT_MIN_EVENTS,
        help=f"Минимум событий в модуле для включения строки (default: {DEFAULT_MIN_EVENTS})",
    )
    parser.add_argument(
        "--course-id",
        type=int,
        default=None,
        help="Экспортировать только один курс (default: все курсы)",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help=f"Путь к выходному CSV (default: {OUTPUT_FILE})",
    )
    args = parser.parse_args()

    print(f"Подключение к {args.db_url} ...")
    try:
        conn = connect(args.db_url)
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        print("Убедитесь что TrackingService запущен и порт проброшен (127.0.0.1:5435).")
        return

    print("Загрузка событий...")
    events = fetch_events(conn, course_id=args.course_id)
    print(f"  Загружено событий: {len(events)}")

    if not events:
        print("Нет событий. Проверьте что TrackingService накапливает данные.")
        conn.close()
        return

    print("Загрузка последних активностей студентов...")
    last_ts_map = fetch_last_event_per_student(conn, course_id=args.course_id)
    conn.close()

    now_ts = int(datetime.now(timezone.utc).timestamp())

    print(f"Построение датасета (dropout_days={args.dropout_days}, min_events={args.min_events})...")
    rows = build_dataset(events, last_ts_map, args.dropout_days, args.min_events, now_ts)

    if not rows:
        print("Датасет пустой после фильтрации. Попробуй уменьшить --min-events.")
        return

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    fieldnames = ["courseId", "moduleId", "durationMs", "watchPercent", "step", "dropout"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Сохранено в {args.output}")
    print_stats(rows, args.dropout_days)

    print("Следующий шаг — обучение моделей:")
    print(f"  python prep_and_train.py --mooc-data {args.output}")


if __name__ == "__main__":
    main()
