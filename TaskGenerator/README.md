# TaskGenerator

Микросервис генерации и управления банком учебных заданий. Преподаватель генерирует задания через LLM (GPT-4o-mini) **с опорой на реальные материалы курса** (RAG через AIAssist), проверяет и одобряет их. Студенты получают задания из готового банка без вызова LLM — выбор основан на адаптивной сложности через BKT. При первой ошибке студент видит подсказку и получает вторую попытку.

---

## Архитектура

```
Преподаватель                          Студент
     │                                      │
     │ POST /v1/admin/generate-bank         │
     │ + инструкции (опционально)           │
     ▼                                      │
 GPT-4o-mini генерирует задания             │
 по всем концептам курса                    │
 (easy / medium / hard)                     │
     │                                      │
     ▼                                      │
 Задания в статусе pending_review           │
     │                                      │
 GET /v1/admin/bank                         │
 POST /v1/admin/review                      │
 (редактирование, одобрение, отклонение)    │
     │                                      │
     ▼                                      │
 Банк одобренных заданий ◄──────── POST /v1/personalized-task
                                            │
                                    AdaptiveService → mastery
                                    BKT → целевая сложность
                                    SELECT из банка (без LLM)
                                    исключая успешно пройденные
                                            │
                                            ▼
                                    POST /v1/check-answer
                                    GPT-4o-mini проверяет ответ
                                    score >= 0.7 → задание пройдено
                                    score < 0.7 → можно повторить
```

---

## Быстрый старт

```bash
cp .env.example .env     # заполните OPENAI_API_KEY
docker compose up -d --build
```

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENAI_API_KEY` | — | Ключ OpenAI API (обязателен) |
| `OPENAI_BASE_URL` | — | Override base URL (для ProxyAPI / РФ) |
| `ADAPTIVE_URL` | `http://adaptive-service:8002` | Адрес AdaptiveService |
| `AIASSIST_URL` | `http://ai-assistant:8003` | Адрес AIAssist для RAG-контекста |
| `DATABASE_URL` | `postgresql+asyncpg://tasks:tasks@tasks-postgres:5432/tasks` | БД PostgreSQL |
| `TASKS_PORT` | `8004` | Порт сервиса |

---

## API преподавателя

Все эндпоинты с префиксом `/v1/admin`.

### `POST /v1/admin/generate-bank`

Генерация банка заданий по всем концептам курса. Концепты загружаются из AdaptiveService.

**RAG-контекст:** для каждого концепта запрашивается `POST /v1/internal/search` в AIAssist с расширенным запросом `"{concept_name}. Определение, примеры, применение"`. Топ-5 фрагментов из реальных материалов курса передаются в промпт. Если AIAssist недоступен — fallback на промпт без контекста (логируется WARNING).

Контекст кешируется на уровне концепта: один HTTP-запрос на концепт, не на каждый difficulty.

**Запрос:**
```json
{
  "course_id": 10,
  "teacher_id": 3,
  "teacher_instructions": "Сосредоточиться на практических примерах, избегать теоретических вопросов",
  "tasks_per_concept": 9,
  "difficulties": ["easy", "medium", "hard"]
}
```

- `tasks_per_concept` — общее число заданий на каждый концепт (по умолчанию 9, распределяются равномерно по сложностям: 3 easy + 3 medium + 3 hard)
- `teacher_instructions` — дополнительные указания для LLM (опционально)

**Ответ:**
```json
{
  "batch_id": "a1b2c3d4-...",
  "total_tasks": 135,
  "concepts_covered": 15
}
```

### `GET /v1/admin/bank`

Список заданий с фильтрами.

**Параметры:** `course_id` (обязательный), `status`, `concept_id`, `batch_id`

**Ответ:**
```json
{
  "tasks": [
    {
      "id": 1,
      "concept_id": 42,
      "concept_name": "Циклы for",
      "difficulty": "medium",
      "spec": {
        "type": "mcq",
        "difficulty": "medium",
        "question": "Что выведет цикл for i in range(3)?",
        "options": ["0 1 2", "1 2 3", "0 1 2 3"],
        "correct_index": 0,
        "correct_answer": null,
        "hint": "Вспомни, как работает range — со скольки начинает и какое число НЕ включает.",
        "explanation": "range(3) генерирует числа 0, 1, 2"
      },
      "status": "pending_review",
      "created_at": "2026-04-15T10:00:00Z"
    }
  ],
  "total": 135
}
```

### `POST /v1/admin/review`

Одобрить, отклонить или отредактировать задание.

**Запрос (одобрить):**
```json
{
  "task_id": 1,
  "action": "approve",
  "reviewed_by": 3
}
```

**Запрос (отредактировать и одобрить):**
```json
{
  "task_id": 1,
  "action": "approve",
  "reviewed_by": 3,
  "edited_spec": {
    "type": "mcq",
    "difficulty": "medium",
    "question": "Исправленный текст вопроса...",
    "options": ["0 1 2", "1 2 3", "0 1 2 3"],
    "correct_index": 0,
    "correct_answer": null,
    "explanation": "Исправленное объяснение..."
  }
}
```

### `POST /v1/admin/review-bulk`

Массовое одобрение или отклонение.

```json
{
  "task_ids": [1, 2, 3, 4, 5],
  "action": "approve",
  "reviewed_by": 3
}
```

### `DELETE /v1/admin/batch/{batch_id}`

Удалить весь батч заданий.

---

## API студента

### `POST /v1/personalized-task`

Выдаёт задания из банка одобренных заданий. LLM не вызывается.

**Запрос:**
```json
{
  "student_id": 7,
  "course_id": 10,
  "max_concepts": 2,
  "variants_per_concept": 2,
  "mastery_threshold": 0.7
}
```

**Логика выборки:**
1. Получает mastery студента из AdaptiveService (`GET /v1/state`)
2. Фильтрует слабые концепты (mastery < threshold)
3. Для каждого концепта определяет сложность через BKT + recent_avg
4. Выбирает из `generated_tasks` WHERE `status = 'approved'`, нужный `concept_id` и `difficulty`
5. Исключает задания, успешно пройденные этим студентом (есть `TaskAttempt` с `score >= 0.7`)
6. Если нет заданий нужной сложности — fallback на соседнюю (medium → easy → hard)
7. Задания, отвеченные неправильно (score < 0.7), могут быть выданы повторно

**Ответ:**
```json
{
  "tasks": [
    {
      "id": 42,
      "concept_id": 5,
      "concept_name": "Циклы for",
      "spec": { "type": "mcq", "difficulty": "medium", "question": "...", ... }
    }
  ]
}
```

### `POST /v1/check-answer`

Проверяет ответ студента через GPT-4o-mini, сохраняет попытку и обновляет mastery.

**Запрос:**
```json
{
  "task_id": 42,
  "student_id": 7,
  "answer": {"selected_index": 0}
}
```

**Ответ зависит от попытки и результата:**

Правильный ответ:
```json
{
  "score": 0.85, "correct": true, "attempt_no": 1,
  "can_retry": false, "hint": null,
  "explanation": "range(3) генерирует последовательность 0, 1, 2."
}
```

Первая ошибка — показывается **подсказка** (без правильного ответа), студент может попробовать снова:
```json
{
  "score": 0.2, "correct": false, "attempt_no": 1,
  "can_retry": true,
  "hint": "Вспомни, как работает range — со скольки начинает и какое число НЕ включает.",
  "explanation": null
}
```

Вторая ошибка — финал, показывается полное объяснение:
```json
{
  "score": 0.3, "correct": false, "attempt_no": 2,
  "can_retry": false, "hint": null,
  "explanation": "range(3) генерирует последовательность 0, 1, 2."
}
```

**Mastery обновляется только в финале цикла** (correct OR attempt_no >= MAX_ATTEMPTS=2) — нет двойного штрафа за промежуточную ошибку.

Задание остаётся в статусе `approved` и доступно другим студентам. Факт прохождения фиксируется через `TaskAttempt` (с полем `attempt_no`).

---

## Выбор сложности (BKT)

Адаптивная сложность определяется комбинацией Bayesian Knowledge Tracing и средних результатов последних 5 попыток студента:

| Сценарий | difficulty |
|----------|-----------|
| Нет истории (cold start) | easy |
| mastery < 0.2 (начинающий) | easy (принудительно) |
| recent_avg <= 0.4, bkt_p <= 0.5 | easy |
| bkt_p > 0.5 или recent_avg > 0.4 | medium |
| recent_avg > 0.7 и bkt_p > 0.6 | hard |

---

## Модель данных

### GeneratedTask

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `course_id` | int | ID курса |
| `concept_id` | int | ID концепта |
| `concept_name` | string | Название концепта |
| `difficulty` | string | easy / medium / hard |
| `json_spec` | json | Спецификация задания (TaskSpec) |
| `status` | string | `pending_review` / `approved` / `rejected` |
| `teacher_id` | int | Кто запустил генерацию |
| `teacher_instructions` | text | Инструкции преподавателя для LLM |
| `batch_id` | string | UUID группировки по запуску генерации |
| `reviewed_by` | int | Кто проверил задание |
| `reviewed_at` | datetime | Когда проверено |
| `created_at` | datetime | Когда создано |

### TaskAttempt

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | PK |
| `task_id` | int | FK → GeneratedTask |
| `student_id` | int | ID студента |
| `concept_id` | int | ID концепта |
| `difficulty` | string | easy / medium / hard |
| `score` | float | 0.0 - 1.0 |
| `attempt_no` | int | Номер попытки в текущем цикле (1 или 2). После правильного ответа цикл сбрасывается |
| `created_at` | datetime | Когда сделана попытка |

Задание считается **пройденным** для студента если есть TaskAttempt с `score >= 0.7`.

---

## Зависимость от AdaptiveService

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/v1/state` | Получить mastery студента по концептам |
| GET | `/v1/concepts` | Получить все концепты курса (для генерации банка) |
| POST | `/v1/internal/mastery-update` | Обновить mastery после проверки ответа |

---

## Moodle-плагин

Блок `personal_tasks` отображает разный интерфейс в зависимости от роли:

- **Преподаватель** (capability `managetasks`): форма генерации банка, список заданий с фильтрами, кнопки одобрения/отклонения/редактирования
- **Студент** (capability `view`): кнопка запроса заданий, карточки заданий, форма ответа с проверкой

---

## Тесты

```bash
pytest tests/ -v
```

- `test_predictor.py` — BKT-обновления, пороги сложности, cold start, гибридное правило
- `test_admin_router.py` — генерация банка, листинг, review, bulk review (mock LLM)
- `test_student_bank_selection.py` — выборка из банка, fallback по сложности, исключение успешно пройденных, повторная выдача при неправильном ответе
- `test_rag_context.py` — RAG-клиент к AIAssist + выбор промпта по наличию контекста
- `test_retry_hint.py` — retry-логика, счётчик попыток в цикле, fallback hint когда в spec нет hint
