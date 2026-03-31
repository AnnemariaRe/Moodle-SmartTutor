# TrackingService

Микросервис трекинга событий Moodle. Принимает события от плагина `local_metrika`, сохраняет в PostgreSQL и публикует в RabbitMQ для потребления другими сервисами (AdaptiveService).

## Архитектура

```
Moodle (плагин local_metrika)
        | HTTP POST /v1/events
        v
TrackingService (порт 8001)
  - сохраняет событие в PostgreSQL (таблица events)
  - публикует в RabbitMQ exchange tracking.events (TOPIC, durable)
  - routing_key = event_type
        |
        v
AdaptiveService (потребитель)
  - queue: adaptive_student_events
  - binding keys: quiz_attempt_submitted, assign_submission_graded
```

### Стек технологий

| Компонент | Технология |
|-----------|-----------|
| API | FastAPI (async) |
| БД | PostgreSQL 16 + SQLAlchemy (asyncpg) |
| Очередь | RabbitMQ 3.13 (aio-pika) |

---

## API

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/v1/events` | Принять и сохранить событие |
| GET | `/health` | Health check |

### POST /v1/events

Принимает событие из Moodle, сохраняет в PostgreSQL, публикует в RabbitMQ.

**Тело запроса:**
```json
{
  "event_id": "unique-id",
  "ts": 1739610000,
  "student_id": 12,
  "course_id": 5,
  "event_type": "quiz_attempt_submitted",
  "object_type": "quiz_attempt",
  "object_id": 345,
  "cmid": 78,
  "payload": {
    "score": 0.67,
    "max_score": 1.0
  }
}
```

---

## Схема базы данных

```
events
├── id              (PK, bigint, autoincrement)
├── event_id        (varchar(255), unique, index)
├── ts              (bigint)          — UNIX timestamp события
├── student_id      (int, index)
├── course_id       (int, index)
├── event_type      (varchar(100), index)
├── object_type     (varchar(100))
├── object_id       (int)
├── cmid            (int, nullable)   — ID курс-модуля в Moodle
├── payload         (JSONB)           — произвольные данные события
└── received_at     (timestamp)       — время получения сервисом
```

Таблицы создаются автоматически при старте через `Base.metadata.create_all`.

---

## Запуск

```bash
cp .env.example .env
# Отредактируйте .env

docker compose up -d --build
```

---

## Конфигурация

Файл `.env.example`:

```env
POSTGRES_USER=tracking
POSTGRES_PASSWORD=changeme
POSTGRES_DB=tracking
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=changeme
TRACKING_PORT=8001
```

Все параметры подставляются в `docker-compose.yml` через переменные окружения.

---

## Docker-сети

| Сеть | Тип | Назначение |
|------|-----|-----------|
| `internal` | bridge | PostgreSQL, RabbitMQ (внутренние) |
| `moodle_shared_net` | external | Доступ от Moodle и других сервисов |

RabbitMQ также доступен через `rabbitmq_shared_net` для AdaptiveService.
