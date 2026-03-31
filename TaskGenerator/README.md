# TaskGenerator — Personalized Tasks Service

Микросервис персонализированной генерации заданий для платформы Moodle. На основе текущего уровня знаний студента запрашивает слабые концепты из AdaptiveService, выбирает оптимальную сложность через BKT + recent_avg и генерирует индивидуальные учебные задания через LangChain + OpenAI GPT-4o-mini.

## Содержание

- [Архитектура](#архитектура)
- [Схема базы данных](#схема-базы-данных)
- [Выбор сложности (BKT)](#выбор-сложности-bkt)
- [Как работает генерация](#как-работает-генерация)
- [Проверка ответов](#проверка-ответов)
- [API](#api)
- [Тесты](#тесты)
- [Запуск](#запуск)
- [Конфигурация](#конфигурация)

---

## Архитектура

```
Moodle (block_personal_tasks)
        │ HTTP POST
        ▼
TaskGenerator (port 8004)
  - запрашивает mastery студента у AdaptiveService
  - выбирает слабые концепты (mastery < threshold)
  - определяет сложность через BKT + recent_avg
  - генерирует задания через LangChain + GPT-4o-mini
  - сохраняет задания и историю попыток в PostgreSQL
  - при проверке ответа обновляет mastery через AdaptiveService
        │ HTTP GET /v1/state
        │ HTTP POST /v1/internal/mastery-update
        ▼
AdaptiveService (port 8002)
```

**Стек технологий**

| Компонент        | Технология                            |
|------------------|---------------------------------------|
| API              | FastAPI (async)                       |
| БД               | PostgreSQL + SQLAlchemy (asyncpg)     |
| LLM              | OpenAI GPT-4o-mini (через LangChain)  |
| Предиктор        | BKT + recent_avg (NumPy)              |
| Клиент           | httpx (async)                         |

---

## Схема базы данных

```
generated_tasks
├── id              (PK)
├── student_id      (int, index)
├── course_id       (int, index)
├── concept_id      (int)        — ID концепта из AdaptiveService
├── concept_name    (str)
├── json_spec       (JSON)       — полная спецификация задания (TaskSpec)
├── status          (str)        — draft | approved | used
└── created_at      (datetime)

task_attempts                    — история попыток, вход для BKT
├── id              (PK)
├── task_id         (FK → generated_tasks.id, nullable)
├── student_id      (int, index)
├── concept_id      (int, index)
├── difficulty      (str)        — easy | medium | hard
├── score           (float)      — 0.0 – 1.0
└── created_at      (datetime)
```

`json_spec` хранит структуру `TaskSpec`:

| Поле             | Тип                | Описание                              |
|------------------|--------------------|---------------------------------------|
| `type`           | `mcq` \| `open`    | Тип задания                           |
| `difficulty`     | `easy/medium/hard` | Сложность                             |
| `question`       | str                | Текст вопроса                         |
| `options`        | list[str] \| null  | Варианты ответа (только для mcq)      |
| `correct_index`  | int \| null        | Индекс правильного варианта (mcq)     |
| `correct_answer` | str \| null        | Правильный ответ текстом (open)       |
| `explanation`    | str                | Объяснение правильного ответа         |

---

## Выбор сложности (BKT)

Сложность задания определяется не простым порогом по mastery, а комбинацией двух сигналов.

### Bayesian Knowledge Tracing (Corbett & Anderson, 1995)

BKT моделирует скрытое знание студента через вероятностную модель с 4 параметрами:

| Параметр | Значение | Описание                                       |
|----------|----------|------------------------------------------------|
| `P(L₀)`  | 0.30     | Априорная вероятность знания концепта          |
| `P(T)`   | 0.15     | Вероятность выучить концепт на одной попытке   |
| `P(S)`   | 0.05     | Вероятность ошибиться при знании (slip)        |
| `P(G)`   | 0.20     | Вероятность угадать без знания (guess)         |

**Формулы обновления (полный Байесовский posterior):**

```
P(L | obs=correct) = P(L) × (1 − P_s) / P(obs)
P(L | obs=wrong)   = P(L) × P_s        / P(obs)
P(L_{t+1})         = P(L | obs) + (1 − P(L | obs)) × P(T)
P(next_correct)    = P(L) × (1 − P_s) + (1 − P(L)) × P_g
```

Ключевое свойство: неверный ответ **снижает** оценку знания, верный — повышает.

### Hybrid rule: BKT + recent_avg

```python
recent_avg = mean(scores[-5:])   # текущая «форма» студента
bkt_p      = bkt.knowledge       # долгосрочная оценка знания

if recent_avg > 0.7 and bkt_p > 0.6:  → "hard"
elif bkt_p > 0.5 or recent_avg > 0.4: → "medium"
else:                                  → "easy"
```

Дополнительный override: если `mastery < 0.2` (абсолютный новичок по данным AdaptiveService) — сложность принудительно `"easy"`.

### Поведение по сценариям

| Сценарий                          | difficulty |
|-----------------------------------|------------|
| Нет истории (cold start)          | easy       |
| 3 неверных ответа подряд          | easy       |
| Смешанные результаты (≈0.5)       | medium     |
| 3 верных ответа подряд (≥0.8)     | hard       |
| mastery < 0.2 (любая история)     | easy       |

---

## Как работает генерация

`POST /v1/personalized-task`:

1. Запрашивает `GET /v1/state` у AdaptiveService — список концептов с mastery студента.
2. Фильтрует концепты с `mastery < mastery_threshold` (по умолчанию `0.7`), берёт первые `max_concepts` (по умолчанию `2`).
3. Для каждого слабого концепта:
   - Запрашивает историю попыток из `task_attempts`.
   - Вычисляет `difficulty` и `p_success` через BKT + recent_avg (`predictor.py`).
   - Вызывает LangChain `task_chain` (GPT-4o-mini): генерирует `variants_per_concept` уникальных заданий. В промпт передаются `mastery`, `p_success` и `difficulty` для контекстно-точной генерации.
4. Сохраняет задания в `generated_tasks` со статусом `draft`.

---

## Проверка ответов

`POST /v1/check-answer`:

1. Достаёт задание из `generated_tasks` по `task_id`.
2. Отправляет спецификацию задания и ответ студента в LangChain `check_chain` (GPT-4o-mini).
3. Получает `score` (0–1), `correct` (bool), `explanation`.
4. Помечает задание как `used` в БД.
5. Сохраняет запись в `task_attempts` — пополняет историю для BKT.
6. Вызывает `POST /v1/internal/mastery-update` на AdaptiveService — обновляет mastery концепта по EMA-формуле.

---

## API

### `POST /v1/personalized-task`

Генерирует персонализированные задания для студента.

**Тело запроса:**
```json
{
  "student_id": 7,
  "course_id": 10,
  "max_concepts": 2,
  "variants_per_concept": 2,
  "mastery_threshold": 0.7
}
```

**Пример ответа:**
```json
{
  "tasks": [
    {
      "id": 42,
      "concept_id": 15,
      "concept_name": "Основы шифрования",
      "spec": {
        "type": "mcq",
        "difficulty": "medium",
        "question": "Что такое симметричное шифрование?",
        "options": [
          "Один ключ для шифрования и расшифрования",
          "Разные ключи для шифрования и расшифрования",
          "Шифрование без ключа",
          "Шифрование с публичным ключом"
        ],
        "correct_index": 0,
        "correct_answer": null,
        "explanation": "При симметричном шифровании один и тот же ключ используется для шифрования и расшифрования данных."
      }
    }
  ]
}
```

---

### `POST /v1/check-answer`

Проверяет ответ студента, сохраняет попытку и обновляет mastery.

**Тело запроса (mcq):**
```json
{
  "task_id": 42,
  "answer": {"selected_index": 0}
}
```

**Тело запроса (open):**
```json
{
  "task_id": 43,
  "answer": {"text": "Алгоритм RSA использует пару ключей..."}
}
```

**Пример ответа:**
```json
{
  "score": 1.0,
  "correct": true,
  "explanation": "Верно! Симметричное шифрование использует единый ключ для обеих операций."
}
```

---

### `GET /health`

```json
{"status": "healthy"}
```

---

## Тесты

```bash
# Внутри контейнера или локально (с установленными зависимостями)
pytest tests/test_predictor.py -v
```

Тесты покрывают:

| Тест                                     | Что проверяется                                   |
|------------------------------------------|---------------------------------------------------|
| `test_bkt_update_wrong`                  | Неверный ответ снижает оценку знания              |
| `test_bkt_update_correct`                | Верный ответ повышает оценку знания               |
| `test_bkt_sequential_wrong_then_correct` | Последовательное обновление (P(correct) ≈ 0.629)  |
| `test_bkt_knowledge_monotone_correct`    | 5 верных ответов — knowledge монотонно растёт     |
| `test_bkt_knowledge_decreases_on_wrong`  | Байесовский posterior снижает knowledge           |
| `test_bkt_predict_difficulty`            | Пороги предсказания сложности                     |
| `test_hybrid_cold_start`                 | Нет истории → easy                                |
| `test_hybrid_three_wrong`                | 3 неверных → easy                                 |
| `test_hybrid_three_correct`              | 3 верных → hard                                   |
| `test_hybrid_medium_performance`         | Средние результаты → medium                       |
| `test_hybrid_recent_window_is_five`      | recent_avg учитывает только последние 5 попыток   |

---

## Запуск

### 1. Создать общую Docker-сеть (один раз)

```bash
docker network create adaptive_shared_net
```

### 2. Пересобрать AdaptiveService (добавлена сеть + внутренний эндпоинт)

```bash
cd AdaptiveService
docker compose up -d --build adaptive-service
```

### 3. Запустить TaskGenerator

```bash
cd TaskGenerator
cp .env.example .env
# Вставить OPENAI_API_KEY в .env
docker compose up -d --build
```

Сервис будет доступен на `http://personalized-tasks:8004`.

---

## Конфигурация

Файл `.env.example`:

```env
# PostgreSQL
POSTGRES_USER=tasks
POSTGRES_PASSWORD=changeme
POSTGRES_DB=tasks
POSTGRES_EXTERNAL_PORT=5439

# Adaptive Service
ADAPTIVE_URL=http://adaptive-service:8002

# OpenAI API
OPENAI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small

# Service port
TASKS_PORT=8004
```

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

## Зависимость от AdaptiveService

TaskGenerator использует два эндпоинта AdaptiveService:

| Метод  | Путь                          | Назначение                              |
|--------|-------------------------------|-----------------------------------------|
| `GET`  | `/v1/state`                   | Получить mastery студента по концептам  |
| `POST` | `/v1/internal/mastery-update` | Обновить mastery после проверки ответа  |

`/v1/internal/mastery-update` — внутренний эндпоинт, добавленный в AdaptiveService специально для TaskGenerator. Принимает:
```json
{
  "student_id": 7,
  "course_id": 10,
  "concept_id": 15,
  "score": 0.85
}
```
Обновляет mastery по EMA-формуле AdaptiveService (без привязки к Moodle cmid).
