# TrackingService

Микросервис трекинга событий Moodle. Принимает события от плагина `local_metrika`, сохраняет в PostgreSQL и публикует в RabbitMQ для потребления другими сервисами (AdaptiveService).

---

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_USER` | `tracking` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `changeme` | Пароль PostgreSQL |
| `POSTGRES_DB` | `tracking` | Имя БД |
| `RABBITMQ_USER` | `guest` | Пользователь RabbitMQ |
| `RABBITMQ_PASSWORD` | `changeme` | Пароль RabbitMQ |
| `TRACKING_PORT` | `8001` | Порт сервиса |

---

## Сети и интеграция

PostgreSQL TrackingService подключён к двум сетям:
- `internal` — для самого `tracking-service`
- `tracking_shared_net` — **для прямого доступа из AdaptiveService** (фильтрация уже изученного контента + LightFM implicit feedback + hit-rate аналитика)

RabbitMQ дополнительно на сети `rabbitmq_shared_net` — для подписки AdaptiveService на события.

Перед запуском убедитесь что внешние сети созданы:
```bash
docker network create tracking_shared_net
docker network create rabbitmq_shared_net
docker network create moodle_shared_net
```

---

## API

### `POST /v1/events`

Принимает событие из Moodle, сохраняет в PostgreSQL, публикует в RabbitMQ.

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
  "payload": { "score": 0.67, "max_score": 1.0 }
}
```
