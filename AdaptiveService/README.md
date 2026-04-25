# AdaptiveService

Микросервис адаптивных рекомендаций для Moodle. Отслеживает прогресс студентов, строит граф знаний курса, фильтрует уже изученный контент и генерирует персонализированные рекомендации.

---

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build

# Создать таблицы при первом запуске (если не созданы автоматически)
docker compose exec adaptive-service python -c \
  "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

### Первоначальная настройка курса

```bash
# 1. Построить граф знаний из материалов Moodle через LLM
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
| `TRACKING_DB_URL` | — | DSN БД TrackingService для фильтрации studied-контента и hit-rate. Пример: `postgresql://tracking:tracking@trackingservice-postgres-1:5432/tracking` |
| `OPENAI_API_KEY` | — | Для извлечения концептов через LLM |
| `OPENAI_BASE_URL` | — | ProxyAPI base URL (для РФ-серверов) |
| `ADAPTIVE_PORT` | `8002` | Порт сервиса |

**Сети:** `internal`, `rabbitmq_shared_net`, `moodle_shared_net`, `adaptive_shared_net`, `tracking_shared_net`. Последняя нужна для доступа к БД TrackingService.

---

## Как работают рекомендации

Запрос: `GET /v1/recommendations?student_id=7&course_id=10&cmid=502`

### Этап 0 — Построение `studied_cmids`

При каждом запросе из БД TrackingService подтягивается история событий студента и вычисляется множество cmid'ов, которые уже считаются «освоены» (не предлагать снова):

| Тип контента | Считается studied когда |
|--------------|-------------------------|
| `quiz` / `assign` | best score / max_score ≥ 0.7 |
| `lesson` | `lesson_completed` event с `max(num_correct/num_questions, score_percent/100) ≥ 0.7` |
| `page` / `book` | любое `course_module_viewed` (нет другого сигнала) |

Failed-попытки сохраняют материал в выдаче для повторения. Lesson, открытая но не пройденная — тоже остаётся в выдаче.

### Этапы 1–3 — Поиск рекомендаций

**Этап 1 — Контекстные (rule-based).** Если передан `cmid`: определяется контекст (`fix_prerequisites`, `review_current`, `progressing`, `ready_to_continue`, `post_placement`, `completed`). Ищутся материалы целевых концептов.

**Этап 2 — LightFM.** WARP-модель на матрице студент×материал с user/item features. Использует implicit feedback (page_viewed, video_watched, lesson_answer_submitted) из TrackingService. Применяется как fallback когда rule-based не нашёл.

**Этап 3 — Rule-based fallback.** Кандидаты: концепты с `mastery < 0.7` И все prereq освоены (`mastery ≥ 0.5`). Ранжирование по urgency: `(1 - mastery) × (1 + fail_rate)`. До 3 рекомендаций.

`studied_cmids` фильтрует выдачу на каждом этапе.

---

## Mastery (EMA)

Mastery обновляется при scored events из RabbitMQ (`quiz_attempt_submitted`, `assign_submission_graded`, `lesson_completed`, `lesson_answer_submitted`).

```python
# Дискретные таргеты по rel_score
target = 0.8 if rel_score >= 0.8 else (0.5 if rel_score >= 0.5 else 0.2)

# Cold start: первая попытка сразу принимает target (без EMA dampening)
if old_mastery == 0.0:
    new_mastery = target * weight
# Все последующие — EMA half-step
else:
    new_mastery = old + weight * (target - old) * 0.5
```

Для placement-теста mastery записывается напрямую: `mastery = score × weight` (без EMA).

### Два порога

| Порог | Значение | Где используется |
|-------|----------|------------------|
| `MASTERY_THRESHOLD` | **0.7** | UI badge «Освоено», статус "ready_to_continue" |
| `PREREQ_UNLOCK_THRESHOLD` | **0.5** | Минимум для разблокировки зависимых концептов |

Это сделано чтобы низкие, но достаточные mastery (например 0.55) **открывали** дальнейший контент, при этом UI честно показывал «не освоено».

---

## API

### Публичные

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/v1/recommendations` | Рекомендации для студента (логируется в `recommendation_log`) |
| GET | `/v1/state` | Mastery студента по всем концептам |
| GET | `/v1/content-items` | ContentItems курса |
| GET | `/v1/concepts` | Концепты курса |
| POST | `/v1/concepts` | Создать концепт |
| POST | `/v1/content-items` | Создать/обновить ContentItem |
| POST | `/v1/assessment-maps` | Добавить связь оценивания |

### Административные

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/v1/admin/graph/auto-extract` | Построить граф знаний из Moodle через LLM |
| GET | `/v1/admin/graph` | Просмотреть граф курса |
| POST | `/v1/admin/graph/import` | Импортировать граф из JSON |
| POST | `/v1/admin/concepts/approve-all` | Одобрить все концепты курса |
| POST | `/v1/admin/concepts/{id}/merge` | Слить концепт в другой (переносит content_items и AM) |
| POST | `/v1/admin/placement-test` | Назначить входной тест |
| POST | `/v1/admin/train-lightfm` | Обучить LightFM модель |
| GET | `/v1/admin/evaluate-lightfm` | Метрики LightFM (precision@k, recall@k, AUC) с temporal split |
| GET | `/v1/admin/model-stats` | Состояние ML-моделей |
| GET | `/v1/admin/recommendations-stats` | **Hit-rate аналитика рекомендаций** |

### `/v1/admin/recommendations-stats`

Каждый ответ `/v1/recommendations` логируется в таблицу `recommendation_log`. Этот эндпоинт считает hit-rate: для каждой рекомендации проверяет, открыл ли студент рекомендованный cmid в течение `window_minutes` (по умолчанию 30) после показа.

```bash
curl "http://adaptive-service:8002/v1/admin/recommendations-stats?course_id=10&window_minutes=30" | jq
```

Возвращает hit-rate в целом и по методам (`rule_based` vs `lightfm_hybrid`) — позволяет оценить эффективность каждой модели.

---

## DKT (Deep Knowledge Tracing)

LSTM-модель предсказывает вероятность правильного ответа студента на основе истории попыток. Inference на чистом NumPy (без PyTorch). Веса загружаются из `models/dkt_weights_{course_id}.npz`.

В рекомендациях используется как `readiness` (более точная оценка, чем mastery): `readiness = dkt_p_correct OR current_mastery`. Это влияет на выбор контекста (`progressing` vs `ready_to_continue`).

---

## LightFM с implicit feedback

LightFM обучается на двух типах сигналов:
1. **Explicit:** mastery + успешные попытки (вес ≈ 1.0)
2. **Implicit:** просмотры страниц, видео, ответы на вопросы (вес 0.10–0.25)

Implicit-сигналы тянутся напрямую из БД TrackingService (через `TRACKING_DB_URL`), накладываются на explicit и хранятся с timestamps для temporal evaluation.

`evaluate-lightfm` использует **temporal split** (а не random) — последние 20% взаимодействий каждого студента в test set. Это даёт честные метрики предсказания будущего поведения.
