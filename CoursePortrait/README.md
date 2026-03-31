# Course Portrait Service

Микросервис для анализа сложности курсов, выявления узких мест и генерации рекомендаций на основе данных из Yandex.Metrika и Moodle Web Services API.

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [API Endpoints](#api-endpoints)
- [Алгоритмы и логика](#алгоритмы-и-логика)
- [ML-модель: Dropout Risk Predictor](#ml-модель-dropout-risk-predictor)
- [Структура проекта](#структура-проекта)
- [Интеграция с Moodle](#интеграция-с-moodle)
- [Интеграция с Yandex.Metrika](#интеграция-с-yandexmetrika)
- [Dashboard](#dashboard)
- [Разработка](#разработка)

---

## Возможности

| Функция | Описание |
|---------|----------|
| **Heatmap сложностей** | Композитный индекс сложности каждого модуля курса с детальной разбивкой по метрикам |
| **Тип-специфичные метрики** | Отдельные калькуляторы сложности для видео, квизов, текстовых страниц и заданий |
| **Анализ отвалов** | Выявление модулей с высоким dropout rate и цепочек отвала (3-шаговые паттерны) |
| **Воронка прохождения** | Retention rate по шагам курса, среднее время сессий, обратная навигация |
| **Видеоаналитика** | Анализ просмотра видео: паузы, перемотки, «горячие» сегменты по квартилям |
| **Предсказание отвала** | XGBoost: вероятность того, что студент бросит курс после конкретного модуля |
| **Рекомендации** | Автоматические рекомендации по улучшению проблемных модулей |
| **Web Dashboard** | HTML-дашборд с Chart.js для визуализации всех метрик |
| **Redis-кэш** | TTL-кэширование всех endpoints (1–2 часа) |
| **Async I/O** | FastAPI + asyncpg + aiohttp — все операции неблокирующие |

---

## Архитектура

```
Moodle (плагин local/metrika)
        │
        ▼ отправляет события
Yandex.Metrika
        │
        ▼ REST API (pulls every request)
┌───────────────────────────────────┐
│        Course Portrait Service     │
│                                   │
│  FastAPI ──► MetrikaService       │
│              MoodleService  ──────┼──► Moodle Web Services API
│              MLPredictor          │
│              DifficultyCalculators│
│              MetricsCalculator    │
│                                   │
│  PostgreSQL (CourseMetrics,       │
│              SequencePath)        │
│  Redis (response cache)           │
└───────────────────────────────────┘
        │
        ▼
   REST API → Moodle-плагины, дашборд, сторонние клиенты
```

**Стек:**
- **Framework**: FastAPI 0.104+, Uvicorn (ASGI)
- **ORM / DB**: SQLAlchemy 2.0 (async), asyncpg, PostgreSQL 15
- **Cache**: Redis 7, aioredis 2.0
- **ML**: XGBoost 2.1, ONNX Runtime (inference)
- **HTTP-клиенты**: httpx 0.25 (async), aiohttp 3.9
- **Data**: pandas 2.2, numpy 1.26
- **Python**: 3.11+

---

## Быстрый старт

### Через Docker Compose (рекомендуется)

```bash
# 1. Настройте окружение
cp .env.example .env
# Заполните METRIKA_COUNTER_ID, METRIKA_OAUTH_TOKEN, MOODLE_URL, MOODLE_TOKEN

# 2. Обучите ML-модель (один раз)
docker compose build app
docker compose run --rm app python training/prep_and_train.py

# 3. Запустите все сервисы
docker compose up --build
```

Swagger UI: **http://app:8005/docs**
Dashboard: **http://app:8005/dashboard**

---

## Конфигурация

```env
# PostgreSQL
POSTGRES_USER=user
POSTGRES_PASSWORD=changeme
POSTGRES_DB=portrait
POSTGRES_PORT=5434
POSTGRES_EXTERNAL_PORT=5437

# Redis
REDIS_PORT=6379

# Yandex Metrika
METRIKA_COUNTER_ID=
METRIKA_OAUTH_TOKEN=

# Moodle
MOODLE_URL=http://localhost:8000
MOODLE_TOKEN=

# App
LOG_LEVEL=INFO
JWT_SECRET_KEY=change-this-secret-in-production
APP_PORT=8005
```

> Если `METRIKA_OAUTH_TOKEN` или `MOODLE_TOKEN` не заданы — сервис возвращает пустые результаты (без заглушек).

---

## API Endpoints

### Базовые

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Информация о сервисе |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/dashboard` | HTML-дашборд |

### Курсы

| Метод | Путь | Описание | Query-параметры |
|-------|------|----------|-----------------|
| GET | `/api/v1/courses` | Список всех курсов | — |
| GET | `/api/v1/courses/{course_id}/info` | Структура курса и модули | — |
| GET | `/api/v1/courses/{course_id}/heatmap` | Heatmap сложностей | `date_from`, `date_to` |
| GET | `/api/v1/courses/{course_id}/dropoff-points` | Точки отвала студентов | — |
| GET | `/api/v1/courses/{course_id}/funnel` | Воронка прохождения | `date_from`, `date_to` |
| GET | `/api/v1/courses/{course_id}/recommendations` | Рекомендации | — |
| GET | `/api/v1/courses/{course_id}/video-analytics` | Видеоаналитика | `date_from`, `date_to`, `module_id`, `media_id` |

### Примеры ответов

#### `GET /api/v1/courses/{course_id}/heatmap`

```json
{
  "courseId": 5,
  "modules": [
    {
      "moduleId": 63,
      "sectionId": 10,
      "moduleName": "Введение в алгоритмы",
      "moduleType": "video",
      "dropoutRisk": 0.72,
      "difficulty": "hard",
      "difficultyScore": 0.85,
      "difficultyDetails": {
        "metrics": [
          {"name": "watch_percent", "value": 0.34, "weight": 0.4, "contribution": 0.264, "interpretation": "Низкий процент просмотра"}
        ],
        "explanation": "Низкий процент просмотра указывает на сложный контент",
        "suggestions": ["Разбейте видео на части по 5–7 минут"]
      },
      "avgDurationMs": 45000,
      "watchPercent": 0.34,
      "engagementScore": 0.34,
      "studentCount": 40,
      "dropoutRate": 0.65
    }
  ],
  "totalModules": 20,
  "bottleneckModules": [63, 45],
  "generatedAt": "2024-01-15T10:30:00"
}
```

#### `GET /api/v1/courses/{course_id}/funnel`

```json
{
  "courseId": 5,
  "funnel": [
    {"step": 1, "moduleId": 10, "moduleName": "Введение", "studentsCount": 46, "retentionRate": 1.0},
    {"step": 2, "moduleId": 11, "moduleName": "Лекция 1",  "studentsCount": 40, "retentionRate": 0.87},
    {"step": 3, "moduleId": 12, "moduleName": "Квиз 1",    "studentsCount": 30, "retentionRate": 0.65}
  ],
  "totalStudents": 46,
  "finalRetentionRate": 0.65,
  "avgCourseCompletionTimeMs": 7200000,
  "avgSessionsPerUser": 4.2,
  "backwardNavigationRate": 0.15
}
```

---

## Алгоритмы и логика

### Расчёт индекса сложности

Сервис использует **тип-специфичные калькуляторы** (`app/services/difficulty_calculators.py`).

#### Видеомодули (`VideoDifficultyCalculator`)

| Метрика | Вес | Интерпретация |
|---------|-----|---------------|
| `watchPercent` | 0.40 | Чем меньше % просмотра — тем сложнее |
| `pauseCount` | 0.30 | Частые паузы = непонятный контент |
| `durationRatio` | 0.20 | Отношение длительности к медиане курса |
| `seekBackwardCount` | 0.10 | Перемотки назад = непонимание |

#### Квизы/задания с оценкой (`QuizDifficultyCalculator`)

| Метрика | Вес | Интерпретация |
|---------|-----|---------------|
| `avgScore` | 0.35 | Средний балл (инвертированный) |
| `attemptCount` | 0.25 | Число попыток = сложность задания |
| `completionRate` | 0.20 | Доля студентов, завершивших задание |
| `avgTimeSpent` | 0.20 | Время выполнения vs ожидаемое |

#### Текстовые страницы (`TextDifficultyCalculator`)

| Метрика | Вес | Интерпретация |
|---------|-----|---------------|
| `avgReadTime` | 0.40 | Время чтения vs ожидаемое (200 слов/мин) |
| `scrollDepth` | 0.30 | Глубина прокрутки (% страницы) |
| `returnVisits` | 0.30 | Повторные визиты = студент не разобрался |

#### Задания (`AssignmentDifficultyCalculator`)

| Метрика | Вес | Интерпретация |
|---------|-----|---------------|
| `submissionRate` | 0.30 | % студентов, сдавших работу |
| `avgGrade` | 0.30 | Средняя оценка (инвертированная) |
| `lateSubmissions` | 0.20 | Доля просроченных сдач |
| `resubmissions` | 0.20 | Частота пересдач |

**Базовая формула** (если тип-специфичные данные недоступны):
```
Difficulty = 0.4 × (avgDuration / medianDuration)
           + 0.3 × (1 - watchPercent)
           + 0.3 × dropoutRate
```

**Уровни сложности:**
```
easy:   score < 0.4
medium: 0.4 ≤ score < 0.7
hard:   score ≥ 0.7
```

### Выявление Bottleneck-модулей

Модуль считается узким местом, если одновременно:
```
difficulty_score > 0.35  AND  traffic_ratio > 0.1
```
где `traffic_ratio = studentCount / max_studentCount_in_course`.

### Анализ цепочек отвала

`analyze_dropoff_chains()` рассматривает только короткие последовательности (`len < 5` модулей — студент ушёл рано). Из них берёт последние 3 модуля каждой цепочки и считает частоту паттернов. Возвращает топ-5 наиболее частых троек.

### Воронка прохождения

- Шаги сортируются по полю `step` из Moodle (порядок в курсе).
- `retentionRate = studentsCount / totalStudents`, ограничен [0, 1].
- Модули с менее чем 25 студентами исключаются из воронки.
- `totalStudents` берётся из Moodle enrollment count (не из Метрики).

### Видеоаналитика

Видео делится на **4 квартила**: `0–25%`, `25–50%`, `50–75%`, `75–100%`.

Для каждого квартила:
- `avgWatchTime` — среднее время просмотра (секунды)
- `watchPercent` — % студентов, просмотревших квартил
- `pauseCount` — количество пауз в квартиле
- `isWellWatched` — watchPercent ≥ 90%
- `isLeastWatched` — наименее просматриваемый квартил

**Pause Hotspots** — квартилы, где студенты ставят паузу чаще всего.
**Seek Patterns** — направление перемотки (вперёд/назад) и частота по парам квартилов.

### Генерация рекомендаций

```
IF dropoutRate > 50% OR dropoutRisk > 70%:
    → "Add intermediate quizzes to check understanding"
    → "Simplify content or break into smaller parts"
    priority = HIGH

IF watchPercent < 30%:
    → "Add interactive elements (polls, assignments)"
    → "Review module duration and structure"
    priority = MEDIUM

IF difficultyScore > 70%:
    → "Add additional explanations and examples"
    → "Provide supplementary learning materials"
    priority = MEDIUM
```

---

## ML-модель: Dropout Risk Predictor

### Назначение

Модель предсказывает **вероятность того, что студент прекратит обучение после конкретного модуля** — dropout risk (0 до 1). Результат используется в Heatmap (поле `dropoutRisk`) и в расчёте рекомендаций.

Сложность модулей вычисляется независимо через детерминированные калькуляторы (`DifficultyCalculatorFactory`) — ML-модель на неё не влияет.

---

### Признаки модели (features)

Модель принимает вектор из **3 числовых признаков**:

| # | Признак | Тип | Описание |
|---|---------|-----|----------|
| 1 | `durationMs / 1000` | float | Длительность сессии в секундах. Слишком короткая (< 5 с) или слишком длинная (> 2 ч) — сигнал отвала. |
| 2 | `watchPercent` | float [0–1] | Доля просмотренного контента. 1.0 — модуль выполнен (есть событие сдачи). Иначе — `min(1.0, durationMs / 300000)`. |
| 3 | `step` | int | Порядковый номер модуля в курсе (ранг по первому визиту). Ранние шаги — ниже риск. |

Перед подачей в модель: `durationMs` делится на 1000 (перевод в секунды), остальные признаки — без изменений.

---

### Метка (target)

**`dropout = 1`** если выполнены оба условия одновременно:
1. Студент не активен в курсе более N дней (по умолчанию N=14, настраивается через `--dropout-days`)
2. Данный модуль входит в **последние 3 посещённых** студентом модуля в этом курсе

Иначе `dropout = 0`.

Такая постановка означает: *"это один из последних модулей, после которого студент бросил курс"*.

---

### Алгоритм обучения

**Модель**: XGBoost `binary:logistic`

```
n_estimators  = 100    (количество деревьев)
max_depth     = 6      (глубина каждого дерева)
learning_rate = 0.1    (шаг градиентного спуска)
random_state  = 42
```

Бинарная классификация: на каждом шаге строится новое дерево, которое корректирует ошибки предыдущих. Финальный результат — сигмоида от суммы вкладов всех деревьев → вероятность класса 1 (dropout).

---

### Источники обучающих данных

#### Вариант 1 — собственные данные из TrackingService (рекомендуется)

Скрипт `export_from_tracking.py` экспортирует реальные события студентов из PostgreSQL TrackingService и формирует CSV в нужном формате.

```bash
# Экспорт данных
python training/export_from_tracking.py \
    --db-url postgresql://tracking:tracking@tracking-service-postgres:5432/tracking \
    --dropout-days 14 \
    --min-events 2 \
    --output datasets/my_data.csv

# Обучение на своих данных
python training/prep_and_train.py --mooc-data datasets/my_data.csv
```

**Параметры экспорта:**

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--dropout-days` | 14 | Дней неактивности для признания студента дропнувшим |
| `--min-events` | 2 | Минимум событий в модуле для включения строки |
| `--course-id` | все | Экспортировать только один курс |
| `--output` | `datasets/my_data.csv` | Путь к выходному файлу |

**Алгоритм построения датасета в `export_from_tracking.py`:**

1. Из таблицы `events` TrackingService выбираются события: `course_module_viewed`, `lesson_page_view`, `lesson_started`, `lesson_answer_submitted`, `quiz_attempt_submitted`, `assign_submission_created`, `assign_submission_graded`.

2. Группировка по `(student_id, course_id, cmid)`.

3. Для каждой группы:
   - `durationMs` = (последний ts − первый ts) × 1000, минимум 1000 мс
   - `watchPercent` = 1.0 если есть событие завершения (`quiz_attempt_submitted` / `assign_*`), иначе `min(1.0, durationMs / 300000)` (5 минут = 100%)
   - `step` = ранг модуля по времени первого визита среди всех модулей студента в курсе

4. `dropout = 1` если:
   - Последнее событие студента в курсе было > N дней назад
   - И данный `cmid` входит в последние 3 модуля, которые студент посетил

5. Строки с `event_count < min_events` отфильтровываются.

#### Вариант 2 — KDD Cup 2015 MOOC Dataset

Публичный датасет взаимодействий студентов (Kaggle). Скрипт `prepare_kdd_dataset.py` преобразует его в нужный формат.

```bash
# Подготовка KDD-датасета
python training/prepare_kdd_dataset.py datasets/act-mooc/ datasets/kddcup_train_log.csv

# Обучение
python training/prep_and_train.py --mooc-data datasets/kddcup_train_log.csv
```

**Логика разметки dropout в KDD-датасете (`prepare_kdd_dataset.py`):**

- Если в датасете есть колонка `LABEL`: dropout = 1 если `LABEL.mean() ≥ 0.7` по сессии
- Иначе — эвристика по активности:
  - `total_events ≥ 15` AND `durationMs ≥ 60000` AND `watchPercent ≥ 0.5` → dropout = 0
  - `total_events < 5` OR `durationMs < 3000` OR `watchPercent < 0.2` → dropout = 1
  - Иначе: `dropout_score = 0.4*(1−watchPercent) + 0.3*(1−events/20) + 0.3*(1−duration/120000)`, dropout = 1 если score > 0.5

**Расчёт `watchPercent` из KDD-данных:**
- Видеособытия: `video_events / total_events * 0.7 + min(durationMs/300000, 1.0) * 0.3`
- Остальные: `min(durationMs/180000, 1.0) * 0.6 + min(total_events/20, 1.0) * 0.4`
- Добавляется шум ±5% для разнообразия

Сессия определяется разрывом > 30 минут между событиями.

---

### Сохранение и загрузка модели

После обучения модель сохраняется в двух форматах:

```
models/
├── dropout_predictor.pkl   — pickle (всегда)
└── dropout_predictor.onnx  — ONNX (если доступен skl2onnx)
```

> Примечание: `skl2onnx` не поддерживает прямую конвертацию XGBoost. Если ONNX экспорт не удался — используется pickle-файл, инференс через `model.predict_proba()`.

**Порядок загрузки при старте сервиса (`MLPredictor._load_models`):**

```
1. Проверяет models/dropout_predictor.onnx
   → если есть и onnxruntime доступен: загружает ONNX-сессию
   → иначе: пробует models/dropout_predictor.pkl

2. Если модель не найдена совсем:
   → fallback: возвращает 1.0 − watchPercent
```

---

### Инференс (предсказание в рантайме)

Вызывается из `MetricsCalculator.calculate_difficulty_scores()` для каждого модуля:

```python
features = [
    avg_duration_ms / 1000.0,   # длительность в секундах
    watch_percent,               # 0.0–1.0
    step                         # порядковый номер модуля
]
dropout_risk = predictor.predict_dropout(features)
```

**ONNX-инференс** (`dropout_sess.run`):
```python
input_name = session.get_inputs()[0].name
result = session.run(None, {input_name: np.array([features], dtype=np.float32)})
# result[0] — матрица вероятностей [[P(0), P(1)]]
dropout_risk = result[0][0][1]   # вероятность класса 1 (dropout)
```

**Pickle-инференс** (`model.predict_proba`):
```python
result = model.predict_proba(np.array([features], dtype=np.float32))[0]
dropout_risk = result[1]   # вероятность класса 1
```

**Fallback** (модель не загружена):
```python
dropout_risk = max(0.0, min(1.0, 1.0 - watch_percent))
```

---

### Рекомендуемые размеры обучающей выборки

| Размер датасета | Качество модели |
|----------------|-----------------|
| < 200 строк | Ненадёжное обучение, модель будет переобучаться |
| 200–1000 строк | Приемлемое качество для курса с 30–50 студентами |
| > 1000 строк | Хорошее качество, устойчивые предсказания |
| > 10000 строк | Автоматически берётся 10% выборка для скорости |

Доля `dropout=1` должна быть ≥ 5% для уверенного обучения. При < 5% модель будет предсказывать преимущественно 0.

---

### Полный цикл переобучения на реальных данных

```bash
# 1. Экспорт событий из TrackingService
python training/export_from_tracking.py \
    --dropout-days 7 \
    --output datasets/my_data.csv

# Выведет статистику:
# Строк итого: 2313
# Из них dropout=1: 67 (2.9%)
# Курсов: 5
# Уникальных модулей: 180

# 2. Обучение модели
python training/prep_and_train.py --mooc-data datasets/my_data.csv

# 3. Перезапуск сервиса (очистка Redis-кэша)
docker compose restart app
docker exec courseportrait-redis-1 redis-cli FLUSHDB
```

---

## Структура проекта

```
CoursePortrait/
├── app/
│   ├── main.py                       # FastAPI приложение, lifespan, CORS, роуты
│   ├── models.py                     # Pydantic response-модели
│   ├── database.py                   # SQLAlchemy: CourseMetrics, SequencePath
│   ├── api/
│   │   ├── heatmap.py                # GET /heatmap, /info, /courses
│   │   ├── dropoff.py                # GET /dropoff-points, /funnel, /recommendations
│   │   └── video.py                  # GET /video-analytics
│   └── services/
│       ├── metrika.py                # Yandex.Metrika API client
│       ├── moodle.py                 # Moodle Web Services client
│       ├── ml_predictor.py           # ONNX/pickle inference (dropout risk)
│       ├── difficulty_calculators.py # Тип-специфичные калькуляторы сложности
│       └── calculator.py             # Агрегация метрик, bottleneck-детекция
├── app/static/
│   ├── dashboard.html
│   ├── css/dashboard.css
│   └── js/dashboard.js
│
├── training/                         # Скрипты обучения ML-моделей
│   ├── prep_and_train.py             # Обучение XGBoost модели
│   ├── prepare_kdd_dataset.py        # Подготовка KDD Cup 2015 датасета
│   └── export_from_tracking.py       # Экспорт данных из TrackingService PostgreSQL
│
├── models/                           # ML-модели (создаются после обучения)
│   ├── dropout_predictor.pkl
│   └── difficulty_predictor.pkl
│
├── tests/
│   └── test_analytics.py             # Тесты аналитики
│
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Модели данных (SQLAlchemy)

**`CourseMetrics`** — агрегированные метрики модуля:
```python
courseId, moduleId, sectionId  # indexed
timestamp                       # indexed
avg_duration_ms
watch_percent
dropout_rate
student_count
pause_count_avg
difficulty_score
dropout_risk
```

**`SequencePath`** — путь студента по курсу:
```python
courseId, studentId, created_at  # indexed
step_path                         # JSON: список moduleId
ended_with_dropout                # 0 | 1
total_time_ms
```

---

## Интеграция с Moodle

Сервис подключается к Moodle через **Web Services REST API** для обогащения метрик реальными данными о структуре курса.

### Что получает сервис из Moodle

- Названия курсов и модулей
- Типы модулей (video, quiz, page, assign и др.)
- Видимость модулей — **скрытые модули фильтруются** из всех ответов
- Количество записанных студентов (используется как `totalStudents` в воронке)
- Порядок модулей (`step`) для корректной сортировки воронки

### Вызываемые Moodle API-функции

| Функция | Назначение |
|---------|-----------|
| `core_course_get_courses` | Список всех курсов |
| `core_course_get_contents` | Модули и секции курса |
| `core_enrol_get_enrolled_users` | Количество студентов |

### Настройка

1. В Moodle: **Site administration → Plugins → Web services → Manage tokens** — создайте токен
2. Разрешите пользователю функции выше
3. Установите переменные окружения:
   ```bash
   MOODLE_URL=http://moodle.local:8081
   MOODLE_TOKEN=your_token_here
   ```

### Docker networking

Сервис использует `extra_hosts` для доступа к Moodle на хост-машине:

```yaml
extra_hosts:
  - "moodle.local:host-gateway"
  - "localhost:host-gateway"
networks: [moodle_shared_net]
```

`moodle_shared_net` — внешняя Docker-сеть, общая со всеми сервисами системы.

---

## Интеграция с Yandex.Metrika

Данные поступают из плагина `local/metrika` Moodle через Yandex.Metrika API.

### Формат eventKey

```
courseId=5;moduleId=63;eventType=module_session;durationMs=120000
```

### Отслеживаемые события

| Тип события | Данные | Описание |
|-------------|--------|----------|
| `module_session` | `courseId`, `moduleId`, `durationMs` | Сессия в модуле |
| `module_view` | `courseId`, `moduleId`, `step` | Просмотр модуля |
| `module_attempt` | `courseId`, `moduleId`, `step` | Попытка выполнения |
| `video_watch` | `courseId`, `moduleId`, `mediaId`, `watchPercent` | Просмотр видео |
| `video_stats` | `courseId`, `moduleId`, `mediaId`, `finalPercent`, `totalWatchTime` | Итог просмотра |
| `video_pause` | `courseId`, `moduleId`, `mediaId`, `position`, `segment` | Пауза |
| `video_seek` | `courseId`, `moduleId`, `mediaId`, `fromPos`, `toPos`, `direction` | Перемотка |
| `course_session` | `courseId`, `durationMs` | Сессия в курсе |

### Эндпоинт Metrika API

```
GET https://api-metrika.yandex.net/stat/v1/data
    ?ids={counter_id}
    &metrics=ym:ep:eventsNumber
    &dimensions=ym:ep:eventParamsLevel1,...,ym:ep:eventParamsLevel5
    &filters=ym:ep:eventKey=@'eventType=module_session;courseId={id}'
```

Авторизация: `Authorization: OAuth {METRIKA_OAUTH_TOKEN}`.

Если токен не задан — endpoint возвращает пустой результат (без заглушек).

---

## Dashboard

Встроенный HTML-дашборд доступен по адресу `/dashboard`. Отображает:

- Список курсов (автозагрузка из Moodle)
- Heatmap сложности модулей (Chart.js бар-чарт)
- Воронка прохождения (retention rate)
- Список рекомендаций
- Видеоаналитика по квартилам

---

## Разработка

### Тестирование

```bash
pytest tests/ -v
# Или через Swagger UI: http://app:8005/docs
```

### Очистка кэша Redis

```bash
# Весь кэш
docker exec courseportrait-redis-1 redis-cli FLUSHDB

# Конкретный ключ
docker exec courseportrait-redis-1 redis-cli DEL "funnel:10:default:default"
```

### Отладочный режим

```bash
LOG_LEVEL=DEBUG docker compose up app
```

В DEBUG-режиме в логах видны все обращения к Metrika API, параметры запросов, количество найденных событий и причины фильтрации модулей.
