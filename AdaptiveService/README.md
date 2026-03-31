# AdaptiveService

Микросервис адаптивных рекомендаций для платформы Moodle. Отслеживает прогресс студентов, строит граф знаний курса и генерирует персонализированные рекомендации по учебным материалам.

## Содержание

- [Архитектура](#архитектура)
- [Схема базы данных](#схема-базы-данных)
- [Как работают рекомендации](#как-работают-рекомендации)
- [Обновление mastery](#обновление-mastery)
- [API](#api)
- [Запуск](#запуск)
- [Конфигурация](#конфигурация)

---

## Архитектура

```
Moodle (плагин local_metrika)
        │ HTTP events
        ▼
TrackingService (port 8001)
  - сохраняет события в PostgreSQL
  - публикует в RabbitMQ exchange tracking.events (TOPIC)
        │ routing_key = event_type
        ▼
AdaptiveService (port 8002)
  - queue: adaptive_student_events
  - binding keys: quiz_attempt_submitted, assign_submission_graded
  - обновляет mastery студента в своей БД
  - отвечает на запросы рекомендаций от плагина
```

### Стек технологий

| Компонент | Технология |
|-----------|-----------|
| API | FastAPI (async) |
| БД | PostgreSQL + SQLAlchemy (asyncpg) |
| Очередь | RabbitMQ (aio-pika) |
| Гибридные рекомендации | LightFM (WARP) |
| Знаниевое трассирование | DKT (LSTM, inference на NumPy) |

---

## Схема базы данных

```
concept
├── id, course_id, name, difficulty (0.0–1.0), is_approved
│
concept_prereq  (граф знаний)
├── concept_id → prereq_concept_id
│   "concept требует prereq_concept как пресеквизит"
│
content_item  (учебные модули Moodle)
├── id, course_id, moodle_cmid
├── concept_id  (главный концепт)
├── type: page | quiz | assign | book | lesson
├── difficulty (0.0–1.0)
└── role: regular | placement
│
assessment_map  (один модуль оценивает несколько концептов)
├── content_item_id, concept_id, weight (0.0–1.0)
│
student_concept_mastery  (текущий уровень знаний)
├── student_id, course_id, concept_id
└── mastery (0.0–1.0), updated_at
│
student_concept_stats  (статистика попыток)
├── student_id, course_id, concept_id
└── num_attempts, num_correct, last_attempt_at
```

### Роли ContentItem

- **regular** — обычный учебный материал
- **placement** — входной тест: результат записывается в mastery напрямую (без EMA), рекомендуется новым студентам без истории попыток

---

## Как работают рекомендации

Запрос от плагина Moodle:
```
GET /v1/recommendations?student_id=7&course_id=10&cmid=502
```

Алгоритм проходит по трём уровням последовательно. Если уровень возвращает результат — следующие не выполняются.

### Уровень 1 — Контекстные рекомендации (rule-based)

Выполняется если передан `cmid` (текущий модуль студента).

**Шаг 1.** Определяем состояние текущего модуля:

| Условие | Контекст | Сообщение |
|---------|----------|-----------|
| Новый студент (нет попыток) | `placement` | Рекомендуем входной тест |
| assign + нет оценки | `pending_grade` | "Задание ожидает проверки" |
| Слабые пресеквизиты (mastery < 0.5) | `fix_prerequisites` | "Сначала повтори: ..." |
| readiness < 0.4 | `review_current` | "Рекомендуем дополнительные материалы" |
| readiness ≥ 0.7 | `ready_to_continue` | "Материал освоен — можно идти дальше" |
| Иначе | `progressing` | "Хороший прогресс" |

`readiness` = DKT-предсказание (если модель загружена) или EMA mastery.

**Шаг 2.** Ищем ContentItems для целевых концептов:
1. Прямой запрос по `concept_id`
2. Fallback через `AssessmentMap` (для концептов без прямых ContentItems)
3. Исключаем текущий модуль (`moodle_cmid != cmid`) и placement-тесты
4. Сортируем по близости сложности: `|difficulty - mastery|`

Если нашли → возвращаем (`method = rule_based`). Если нет → идём к Уровню 2.

---

### Уровень 2 — LightFM (гибридная коллаборативная фильтрация)

```python
lightfm_recommend(course_id, student_id)  # → список cmid
```

Модель обучается на матрице взаимодействий студент×материал с признаками:
- **user features**: средний mastery, общий fail_rate
- **item features**: difficulty, тип модуля (quiz/page/assign)

Алгоритм WARP (Weighted Approximate-Rank Pairwise) оптимизирует ранжирование — на первое место выходят материалы, которые студент ещё не смотрел и которые окажутся наиболее полезными на основе опыта похожих студентов.

Минимум для обучения: 10 взаимодействий. Обучение запускается вручную:
```
POST /v1/admin/train-lightfm?course_id=10
```

---

### Уровень 3 — Rule-based fallback

Если LightFM не дал результат (модель не обучена или нет кандидатов):

```python
get_recommendations(db, student_id, course_id)
```

**Алгоритм:**

1. Загружаем все концепты курса и mastery студента
2. **Строгий фильтр кандидатов**: `mastery < 0.7` AND все пресеквизиты освоены (`mastery ≥ 0.7`)
3. Если кандидатов нет → **relaxed fallback**: любой неосвоенный концепт, пресеквизиты игнорируются
4. **Ранжирование по urgency**:
   ```
   urgency = (1 - mastery) × (1 + fail_rate)
   fail_rate = 1 - (correct / attempts)
   ```
   Концепты, где студент часто ошибается, имеют наибольший приоритет.
5. Для каждого концепта находим ContentItem с ближайшей сложностью:
   ```
   target_difficulty = min(1.0, mastery + 0.15)
   ```
6. Fallback через `AssessmentMap` если прямых ContentItems нет
7. Возвращаем до 3 рекомендаций

---

## Обновление mastery

Mastery обновляется при получении события из RabbitMQ.

### Поддерживаемые события

| Событие | Источник |
|---------|---------|
| `quiz_attempt_submitted` | Квиз Moodle |
| `assign_submission_graded` | Проверенное задание |
| `lesson_completed` | Завершённый урок |
| `lesson_answer_submitted` | Ответ на вопрос урока (вес 10%) |

### EMA (Exponential Moving Average)

Для обычных модулей mastery обновляется по формуле:

```
target = 0.8  если score ≥ 0.8
         0.5  если score ≥ 0.5
         0.2  иначе

new_mastery = mastery + weight × (target - mastery) × 0.5
```

`weight` = 1.0 для главного концепта, значение из `AssessmentMap.weight` для смежных.

Формула обеспечивает плавную сходимость: mastery движется к дискретному target, не делая резких скачков.

### Placement test

Для входного теста mastery записывается напрямую без EMA:
```
mastery = score × weight
```

### Какие концепты обновляются

Одно событие обновляет mastery сразу для нескольких концептов:
- Главный концепт (`ContentItem.concept_id`, weight = 1.0)
- Смежные концепты через `AssessmentMap` (weight из таблицы)

---

## API

### Публичные эндпоинты

| Метод | Путь | Описание |
|-------|------|---------|
| GET | `/v1/recommendations` | Получить рекомендации для студента |
| GET | `/v1/state` | Текущий mastery студента по всем концептам |
| GET | `/v1/content-items` | Список ContentItems курса |
| GET | `/v1/concepts` | Список концептов курса |
| POST | `/v1/concepts` | Создать концепт |
| POST | `/v1/concepts/prereqs` | Добавить пресеквизит |
| POST | `/v1/content-items` | Создать/обновить ContentItem |
| POST | `/v1/assessment-maps` | Добавить связь оценивания |

**GET /v1/recommendations** — пример ответа:
```json
{
  "student_id": 7,
  "course_id": 10,
  "method": "rule_based",
  "context": "fix_prerequisites",
  "context_message": "Для лучшего освоения повтори: Основы шифрования",
  "current_mastery": 0.1,
  "current_dkt_p_correct": 0.46,
  "weak_prerequisites": ["Основы шифрования"],
  "recommendations": [
    {
      "content_item_id": 42,
      "moodle_cmid": 115,
      "type": "quiz",
      "concept_id": 1243,
      "concept_name": "Основы шифрования",
      "difficulty": 0.3,
      "reason": "Изучите 'Основы шифрования' (уровень: 10%, попыток: 1, успех: 0%)"
    }
  ]
}
```

Поле `method`:
- `rule_based` — контекстный алгоритм или fallback
- `lightfm_hybrid` — гибридная модель LightFM

### Административные эндпоинты

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/v1/admin/graph/auto-extract` | Автоматически построить граф знаний из Moodle |
| GET | `/v1/admin/graph` | Просмотреть граф курса |
| POST | `/v1/admin/graph/import` | Импортировать граф из JSON |
| POST | `/v1/admin/concepts/approve-all` | Одобрить все черновые концепты курса |
| POST | `/v1/admin/concepts/{id}/approve` | Одобрить один концепт |
| POST | `/v1/admin/concepts/{id}/merge` | Объединить два концепта в один |
| POST | `/v1/admin/placement-test` | Назначить входной тест (`?course_id=&cmid=`) |
| GET | `/v1/admin/placement-test` | Получить текущий входной тест |
| DELETE | `/v1/admin/placement-test` | Снять статус входного теста |
| GET | `/v1/admin/model-stats` | Состояние ML-моделей и кол-во данных |
| POST | `/v1/admin/train-lightfm` | Обучить LightFM модель |

---

## Auto-extract (построение графа знаний)

```
POST /v1/admin/graph/auto-extract?course_id=10
```

**Процесс:**
1. Загружает список модулей курса из Moodle REST API
2. Извлекает текст каждого модуля (HTML → plain text, fallback на название модуля)
3. Батчами по 6 активностей отправляет запросы в OpenAI GPT-4o-mini
4. LLM возвращает JSON с 3–7 ключевыми концептами для каждой активности
5. Строит граф: `Concept → ContentItem → AssessmentMap → ConceptPrereq`
6. Новые концепты сохраняются как черновики (`is_approved = False`)

После auto-extract необходимо одобрить концепты:
```
POST /v1/admin/concepts/approve-all?course_id=10
```

---

## DKT (Deep Knowledge Tracing)

LSTM-модель предсказывает вероятность правильного ответа студента по следующему концепту на основе всей истории его попыток.

**Архитектура:** входной вектор (2 × num_skills) → LSTM → Linear → Sigmoid

Вход кодируется как one-hot по схеме:
- индексы `[0, num_skills)` — правильный ответ по концепту
- индексы `[num_skills, 2*num_skills)` — неправильный ответ

**Inference** выполняется на чистом NumPy без зависимости от PyTorch — LSTM-веса загружаются из `.npz` файлов, обученных отдельно в Jupyter notebook.

Файлы моделей: `models/dkt_weights_{course_id}.npz`, `models/dkt_skill_map_{course_id}.json`

DKT-предсказание используется как `readiness` при определении контекста рекомендаций.

---

## Запуск

```bash
# Запуск всех сервисов
docker compose up -d

# Пересборка после изменений в коде
docker compose up -d --build adaptive-service

# Просмотр логов
docker compose logs -f adaptive-service
```

### Первоначальная настройка курса

```bash
# 1. Построить граф знаний
curl -X POST "http://adaptive-service:8002/v1/admin/graph/auto-extract?course_id=10"

# 2. Одобрить концепты
curl -X POST "http://adaptive-service:8002/v1/admin/concepts/approve-all?course_id=10"

# 3. Назначить входной тест (cmid входного теста из Moodle)
curl -X POST "http://adaptive-service:8002/v1/admin/placement-test?course_id=10&cmid=123"

# 4. После накопления данных — обучить LightFM
curl -X POST "http://adaptive-service:8002/v1/admin/train-lightfm?course_id=10"
```

---

## Конфигурация

Файл `.env.example`:

```env
# PostgreSQL
POSTGRES_USER=adaptive
POSTGRES_PASSWORD=changeme
POSTGRES_DB=adaptive
POSTGRES_EXTERNAL_PORT=5434

# RabbitMQ
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=changeme

# Moodle REST API
MOODLE_URL=
MOODLE_TOKEN=

# Service port
ADAPTIVE_PORT=8002
```

### Ключевые параметры

| Параметр | Файл | Значение | Описание |
|----------|------|---------|---------|
| `MASTERY_THRESHOLD` | recommendations.py | 0.7 | Порог освоения концепта |
| `MAX_RECOMMENDATIONS` | recommendations.py | 3 | Максимум рекомендаций за запрос |
| `EXTRACTION_MODEL` | llm.py | gpt-4o-mini | Модель OpenAI для извлечения концептов |
| `BATCH_SIZE` | llm.py | 6 | Активностей в одном запросе к LLM |
| `TEXT_PER_ACTIVITY` | llm.py | 1500 | Символов текста на активность |
| `MIN_INTERACTIONS` | lightfm_model.py | 10 | Минимум взаимодействий для обучения LightFM |
