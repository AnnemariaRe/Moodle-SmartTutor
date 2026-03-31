# TaskGenerator

Микросервис персонализированной генерации заданий для платформы Moodle. На основе текущего уровня знаний студента запрашивает слабые концепты из AdaptiveService, выбирает оптимальную сложность через BKT + recent_avg и генерирует индивидуальные учебные задания через OpenAI GPT-4o-mini.

---

## Быстрый старт

```bash
cp .env.example .env
# Заполните OPENAI_API_KEY
docker compose up -d --build
```

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_USER` | `tasks` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `changeme` | Пароль PostgreSQL |
| `POSTGRES_DB` | `tasks` | Имя БД |
| `ADAPTIVE_URL` | `http://adaptive-service:8002` | Адрес AdaptiveService |
| `OPENAI_API_KEY` | — | Ключ OpenAI API (обязателен) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Модель эмбеддингов OpenAI |
| `TASKS_PORT` | `8004` | Порт сервиса |

---

## Выбор сложности (BKT)

Сложность определяется комбинацией Bayesian Knowledge Tracing и средних результатов последних 5 попыток:

| Сценарий | difficulty |
|----------|-----------|
| Нет истории (cold start) | easy |
| 3 неверных ответа подряд | easy |
| mastery < 0.2 | easy |
| Смешанные результаты (~0.5) | medium |
| 3 верных ответа подряд (>=0.8) | hard |

---

## API

### `POST /v1/personalized-task`

Генерирует задания для студента.

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

**Ответ:** список заданий с типом `mcq` (варианты ответа) или `open` (свободный ответ), сложностью и объяснением.

### `POST /v1/check-answer`

Проверяет ответ студента, сохраняет попытку в БД и обновляет mastery через AdaptiveService.

**Запрос (mcq):** `{ "task_id": 42, "answer": {"selected_index": 0} }`

**Запрос (open):** `{ "task_id": 43, "answer": {"text": "..."} }`

**Ответ:** `{ "score": 1.0, "correct": true, "explanation": "..." }`

---

## Зависимость от AdaptiveService

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/v1/state` | Получить mastery студента по концептам |
| POST | `/v1/internal/mastery-update` | Обновить mastery после проверки ответа |

---

## Тесты

```bash
pytest tests/test_predictor.py -v
```

Покрывают: BKT-обновления, пороги сложности, cold start, гибридное правило BKT + recent_avg.
