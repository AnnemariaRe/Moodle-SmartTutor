# AdaptiveService

Микросервис адаптивных рекомендаций для платформы Moodle. Отслеживает прогресс студентов, строит граф знаний курса и генерирует персонализированные рекомендации по учебным материалам.

---

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

### Первоначальная настройка курса

```bash
# 1. Построить граф знаний
curl -X POST "http://adaptive-service:8002/v1/admin/graph/auto-extract?course_id=10"

# 2. Одобрить концепты
curl -X POST "http://adaptive-service:8002/v1/admin/concepts/approve-all?course_id=10"

# 3. Назначить входной тест
curl -X POST "http://adaptive-service:8002/v1/admin/placement-test?course_id=10&cmid=123"

# 4. Обучить LightFM (после накопления данных)
curl -X POST "http://adaptive-service:8002/v1/admin/train-lightfm?course_id=10"
```

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_USER` | `adaptive` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `changeme` | Пароль PostgreSQL |
| `POSTGRES_DB` | `adaptive` | Имя БД |
| `RABBITMQ_USER` | `guest` | Пользователь RabbitMQ |
| `RABBITMQ_PASSWORD` | `changeme` | Пароль RabbitMQ |
| `MOODLE_URL` | — | URL Moodle-инстанса |
| `MOODLE_TOKEN` | — | Токен Moodle REST API |
| `ADAPTIVE_PORT` | `8002` | Порт сервиса |

---

## Как работают рекомендации

Запрос: `GET /v1/recommendations?student_id=7&course_id=10&cmid=502`

Алгоритм проходит по трём уровням последовательно:

**Уровень 1 — Контекстные (rule-based).** Если передан `cmid`: определяет контекст (`fix_prerequisites`, `review_current`, `ready_to_continue`, `progressing`), ищет подходящие материалы по близости сложности.

**Уровень 2 — LightFM (гибридная коллаборативная фильтрация).** Модель WARP на матрице студент*материал с user/item features. Минимум 10 взаимодействий.

**Уровень 3 — Rule-based fallback.** Фильтр: `mastery < 0.7` AND пресеквизиты освоены. Ранжирование по urgency: `(1 - mastery) * (1 + fail_rate)`. До 3 рекомендаций.

---

## Обновление mastery

Mastery обновляется при получении событий из RabbitMQ (`quiz_attempt_submitted`, `assign_submission_graded`, `lesson_completed`, `lesson_answer_submitted`) по формуле EMA:

```
new_mastery = mastery + weight * (target - mastery) * 0.5
```

Для placement-теста mastery записывается напрямую: `mastery = score * weight`.

---

## API

### Публичные

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/v1/recommendations` | Рекомендации для студента |
| GET | `/v1/state` | Mastery студента по всем концептам |
| GET | `/v1/content-items` | ContentItems курса |
| GET | `/v1/concepts` | Концепты курса |
| POST | `/v1/concepts` | Создать концепт |
| POST | `/v1/content-items` | Создать/обновить ContentItem |
| POST | `/v1/assessment-maps` | Добавить связь оценивания |

### Административные

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/v1/admin/graph/auto-extract` | Построить граф знаний из Moodle |
| GET | `/v1/admin/graph` | Просмотреть граф курса |
| POST | `/v1/admin/graph/import` | Импортировать граф из JSON |
| POST | `/v1/admin/concepts/approve-all` | Одобрить все концепты курса |
| POST | `/v1/admin/placement-test` | Назначить входной тест |
| POST | `/v1/admin/train-lightfm` | Обучить LightFM модель |
| GET | `/v1/admin/model-stats` | Состояние ML-моделей |

---

## DKT (Deep Knowledge Tracing)

LSTM-модель предсказывает вероятность правильного ответа студента на основе истории попыток. Inference на чистом NumPy (без PyTorch). Веса загружаются из `models/dkt_weights_{course_id}.npz`. Используется как `readiness` при определении контекста рекомендаций.
