# AI Assistant Service

Микросервис виртуального учебного ассистента для платформы Moodle.
Реализует **Advanced RAG** (Retrieval-Augmented Generation) с query rewriting и поддержкой многоходового диалога: переформулирует вопрос студента через LLM, выполняет мультизапросный поиск по векторному индексу курса и генерирует ответ через GPT-4o-mini с учётом всей истории разговора.

---

## Содержание

- [Архитектура](#архитектура)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [API](#api)
- [Алгоритмы](#алгоритмы)
- [База данных](#база-данных)
- [Структура проекта](#структура-проекта)
- [Moodle-плагин](#moodle-плагин)
- [Зависимости](#зависимости)

---

## Архитектура

```
Студент (браузер)
      │  вопрос + история диалога (JS fetch)
      ▼
Moodle PHP (ajax.php)             ← проверяет доступ к курсу (can_access_course)
      │  POST /v1/ask { question, history[] }
      ▼
AI Assistant Service (8003)
      │
      ├─ Query Rewrite ───────►  GPT-4o-mini
      │   Multi-Query (×3)            ↓
      │   + HyDE document      QueryExpansion(queries, hyde_document)
      │
      ├─ embed_batch ─────────►  MiniLM-L12-v2 (384 dims, все варианты одним батчем)
      │
      ├─ kNN × N queries ─────►  PostgreSQL + pgvector (cosine, RETRIEVE_K=3 каждый)
      │   frequency rerank            ↓ top-5 по консенсусу
      │
      ├─ course_overview ─────►  course_overviews (PostgreSQL)
      │
      ├─ prompt ──────────────►  GPT-4o-mini
      │   [System] + [история: user/assistant × N] + [RAG context + вопрос]
      │
      └─ лог ─────────────────►  assistant_logs (PostgreSQL)

Преподаватель (admin)
      │  POST /v1/admin/reindex-course
      ▼
      ├─ Moodle API → lesson pages + page content + quiz intros
      ├─ LangChain RecursiveCharacterTextSplitter → chunks
      ├─ embed_batch → course_chunks (pgvector)
      └─ GPT-4o-mini → course_overviews
```

**Стек:**
- **Backend**: FastAPI 0.115, Uvicorn (ASGI)
- **ORM / DB**: SQLAlchemy 2.0 (async), asyncpg, PostgreSQL 16
- **Векторное хранилище**: pgvector (расширение PostgreSQL)
- **Эмбеддинги**: `sentence-transformers` — `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, multilingual)
- **LLM**: GPT-4o-mini через LangChain + OpenAI SDK (query rewriting, ответ, overview)
- **Чанкинг**: LangChain `RecursiveCharacterTextSplitter`
- **HTTP-клиент**: httpx (async)
- **Python**: 3.11+

---

## Быстрый старт

```bash
# 1. Настройте окружение
cp .env.example .env
# Заполните OPENAI_API_KEY, MOODLE_URL, MOODLE_TOKEN

# 2. Запустите сервисы
docker compose up -d

# 3. Проиндексируйте курс (+ автоматически сгенерируется course_overview)
curl -X POST "http://ai-assistant:8003/v1/admin/reindex-course?course_id=10"

# 4. Проверьте
curl "http://ai-assistant:8003/health"
curl "http://ai-assistant:8003/v1/admin/index-stats?course_id=10"
```

Swagger UI: **http://ai-assistant:8003/docs**

### Без Docker

```bash
pip install -r requirements.txt

# PostgreSQL с pgvector, примените init.sql
psql -U assistant -d assistant -f init.sql

uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_USER` | `assistant` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `changeme` | Пароль PostgreSQL |
| `POSTGRES_DB` | `assistant` | Имя БД PostgreSQL |
| `MOODLE_URL` | `http://moodle.local:8081` | URL Moodle-инстанса |
| `MOODLE_TOKEN` | — | Токен Web Services API Moodle |
| `OPENAI_API_KEY` | — | API-ключ OpenAI (query rewriting + ответ + overview) |
| `CORS_ORIGINS` | `*` | Разрешённые CORS-источники |
| `AI_ASSIST_PORT` | `8003` | Порт сервиса |

### Ключевые константы

| Константа | Файл | Значение | Описание |
|---|---|---|---|
| `EMBEDDING_DIM` | `models.py` | 384 | Размерность векторов MiniLM |
| `TOP_K` | `router.py` | 5 | Итоговых чанков в контексте LLM |
| `RETRIEVE_K` | `router.py` | 3 | Чанков на один запрос при мультипоиске |
| `MAX_CONTEXT_CHARS` | `router.py` | 6000 | Лимит символов контекста в промпте |
| `EMBED_BATCH_SIZE` | `ingestor.py` | 64 | Размер батча при индексации |
| `chunk_size` | `ingestor.py` | 1200 | Символов в чанке (~300 слов) |
| `chunk_overlap` | `ingestor.py` | 150 | Перекрытие чанков (12%) |

---

## API

### Основные

#### `POST /v1/ask`

Задать вопрос ассистенту. Внутри — полный Advanced RAG пайплайн с поддержкой истории диалога.

**Тело запроса:**
```json
{
  "course_id": 10,
  "student_id": 7,
  "question": "А чем шифр отличается от кода?",
  "history": [
    { "role": "user",      "content": "Что такое шифр?" },
    { "role": "assistant", "content": "Шифр — это алгоритм преобразования информации..." }
  ]
}
```

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `course_id` | int | да | ID курса в Moodle |
| `student_id` | int | нет | ID студента (для логов) |
| `question` | string | да | Вопрос, 1–2000 символов |
| `history` | array | нет | История диалога, до 20 сообщений. Каждый элемент: `{role: "user"/"assistant", content: string}` |

**Ответ `200 OK`:**
```json
{
  "course_id": 10,
  "answer": "Шифр преобразует сам текст, сохраняя смысл, а код заменяет слова или символы условными обозначениями...",
  "sources": [
    { "cmid": 513, "title": "Лекция №2", "type": "lesson" },
    { "cmid": 520, "title": "Логические задачи (продолжение)", "type": "page" }
  ]
}
```

Источники (`sources`) содержат только `lesson` и `page` — материалы с реальным учебным текстом. Задания (`assign`) и тесты (`quiz`) в источниках не отображаются.

**Ошибки:**

| Код | Причина |
|---|---|
| `400` | Пустой вопрос |
| `502` | Сбой LLM-вызова |

---

#### `GET /health`

```json
{ "status": "ok", "service": "ai-assistant" }
```

---

### Административные (`/v1/admin`)

#### `POST /v1/admin/reindex-course?course_id=X`

Полная переиндексация курса + генерация course overview.

1. `core_course_get_contents` — структура курса
2. `mod_lesson_get_pages` — полный HTML каждой страницы лекции (по одному запросу на лекцию)
3. `mod_page_get_pages_by_courses` — HTML страниц типа `page`
4. `mod_quiz_get_quizzes_by_courses` — intro текст тестов
5. HTML-очистка → `RecursiveCharacterTextSplitter` → чанки
6. Батчевое вычисление эмбеддингов → атомарная замена в БД
7. GPT-4o-mini генерирует аннотацию курса → upsert в `course_overviews`

**Ответ:**
```json
{
  "course_id": 10,
  "chunks_created": 163,
  "message": "Successfully indexed 163 chunks for course 10"
}
```

#### `GET /v1/admin/index-stats?course_id=X`

```json
{
  "course_id": 10,
  "chunks_indexed": 163,
  "total_questions_asked": 57
}
```

#### `GET /v1/admin/logs?course_id=X&limit=50`

Последние `limit` диалогов по курсу (для панели преподавателя).

```json
[
  {
    "id": 12,
    "ts": "2025-03-16T14:22:01",
    "student_id": 7,
    "question": "Что такое полиморфизм?",
    "answer": "Полиморфизм — это..."
  }
]
```

---

## Алгоритмы

### Advanced RAG — пайплайн запроса

```
Студент: "А чем отличается от кода?" (с историей из 2 сообщений)
         │
         ▼
1. QUERY REWRITING (GPT-4o-mini, structured_output)
   queries: [
     "Отличие шифра от кода в криптографии",
     "Шифр и код определение разница примеры",
     "Кодирование vs шифрование информации"
   ]
   hyde_document: "Шифр отличается от кода тем, что..."

         │  5 строк: original + 3 queries + hyde
         ▼
2. BATCH EMBEDDING (один вызов, float32[5, 384])

         │
         ▼
3. MULTI-QUERY kNN × 5 (cosine, RETRIEVE_K=3 каждый)
   → до 15 кандидатов → frequency rerank → top-5

         │
         ▼
4. СБОРКА ИСТОРИИ ДИАЛОГА (последние 10 сообщений)
   [HumanMessage("Что такое шифр?")]
   [AIMessage("Шифр — это...")]

         │
         ▼
5. ПРОМПТ
   [SystemMessage] Ты учебный AI-ассистент...
   [HumanMessage]  Что такое шифр?          ← история
   [AIMessage]     Шифр — это...            ← история
   [HumanMessage]  === О курсе ===          ← текущий запрос с RAG
                   <overview>
                   === Материалы курса ===
                   [1] Лекция №2 ...
                   === Вопрос студента ===
                   А чем отличается от кода?

         │
         ▼
6. GPT-4o-mini (temperature=0.2, max_tokens=1024) → answer

         │
         ▼
7. sources = deduplicate(chunks by cmid, exclude assign/quiz)
   INSERT INTO assistant_logs(...)
   return { answer, sources }
```

**Почему история работает правильно:**

LLM видит предыдущие реплики как полноценные сообщения в цепочке, а не склеенный текст. Это позволяет ей разрешать референции («он», «это», «как я сказал выше»), удерживать контекст нескольких ходов и не повторять объяснения.

**Почему Multi-Query + HyDE улучшают recall:**

| Техника | Проблема | Эффект |
|---|---|---|
| **Multi-Query** | Короткий вопрос даёт слабый эмбеддинг | 3 угла поиска → больше шанс найти нужный чанк |
| **HyDE** | Вопрос и ответ в разных частях embedding-пространства | Гипотетический документ-ответ ближе к чанкам |
| **Frequency rerank** | Случайные нерелевантные чанки из одного запроса | Чанки, найденные несколькими запросами, получают приоритет |

---

### Пайплайн индексации (reindex)

```
1. Moodle API: core_course_get_contents(course_id)
   → секции (name, section, modules[])

2. Обогащение контента (параллельно по типам):
   lesson  → mod_lesson_get_pages(instance_id)
              pages[].title + pages[].contents (HTML)
              один запрос на лекцию
   page    → mod_page_get_pages_by_courses(course_id)
              pages[].content или intro (HTML)
   quiz    → mod_quiz_get_quizzes_by_courses(course_id)
              quizzes[].intro (HTML)
   assign  → только описание из структуры (нет прав на API)

3. Приоритет текста: rich_content > base_description > title
   HTML очищается: strip tags → html.unescape → collapse whitespace

4. RecursiveCharacterTextSplitter(chunk_size=1200, overlap=150)
   separators: ["\n\n", "\n", ". ", " ", ""]
   метаданные модуля копируются в каждый чанк

5. embed_batch(тексты, batch=64) → float32[N, 384]

6. DELETE course_chunks WHERE course_id = :id  ← атомарная замена
   INSERT course_chunks(...)
   COMMIT

7. _build_course_structure(sections) → план курса в виде текста
   GPT-4o-mini: генерирует аннотацию 150–200 слов
   INSERT ... ON CONFLICT DO UPDATE  ← upsert в course_overviews
```

### Системный промпт ассистента

```
Ты учебный AI-ассистент курса.

Твои задачи:
- Отвечать на вопросы по содержанию курса, опираясь на предоставленные материалы.
- Разъяснять условия заданий, если студент не понимает, что от него требуется.
- Придумывать и показывать примеры, иллюстрации, аналогии.
- Помогать разобраться в теме шаг за шагом.

Правила:
- Используй предоставленные фрагменты как основной источник знаний.
- Если в материалах недостаточно информации — скажи об этом и помоги, насколько можешь.
- Никогда не решай задание за студента напрямую — направляй, объясняй, показывай похожий пример.
- Отвечай на русском языке, понятно и по существу.
```

### Эмбеддинг-модель

`paraphrase-multilingual-MiniLM-L12-v2` (`sentence-transformers`):
- 384-мерные L2-нормализованные векторы
- Поддержка русского и 50+ языков
- Загружается один раз при старте (lifespan FastAPI)
- Кешируется внутри Docker-образа при сборке

---

## База данных

### `course_chunks`

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK int | |
| `course_id` | int, index | ID курса в Moodle |
| `cmid` | int | ID курс-модуля в Moodle |
| `type` | varchar(50) | `page`, `lesson`, `assign`, `quiz`, `url` |
| `section` | int | Номер раздела курса |
| `title` | varchar(500) | Название модуля |
| `text` | text | Чистый текст фрагмента |
| `position_in_module` | int | Порядковый номер чанка внутри модуля (0, 1, 2…) |
| `embedding` | vector(384) | L2-нормализованный эмбеддинг |
| `created_at` | timestamp | Время индексации |

Рекомендуется IVFFlat-индекс после первой индексации:
```sql
CREATE INDEX ON course_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

### `course_overviews`

LLM-сгенерированная аннотация курса. Обновляется при каждом reindex.

| Поле | Тип | Описание |
|---|---|---|
| `course_id` | PK int | ID курса в Moodle |
| `overview` | text | Аннотация ~150–200 слов на русском |
| `generated_at` | timestamp | Время последней генерации |

### `assistant_logs`

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK int | |
| `ts` | timestamp, index | Время запроса |
| `student_id` | int, nullable | ID студента в Moodle |
| `course_id` | int, index | ID курса |
| `question` | text | Вопрос студента |
| `answer` | text | Ответ ассистента |
| `used_chunk_ids` | text | JSON-массив ID чанков, использованных в ответе |

---

## Структура проекта

```
AIAssist/
├── app/
│   ├── main.py            # FastAPI приложение, lifespan (таблицы, загрузка модели)
│   ├── database.py        # SQLAlchemy async engine + session factory
│   ├── models.py          # ORM: CourseChunk, CourseOverview, AssistantLog
│   ├── schemas.py         # Pydantic: AskRequest (+ history), AskResponse, HistoryMessage
│   ├── embedder.py        # Singleton SentenceTransformer: embed_one / embed_batch
│   ├── moodle_client.py   # Клиент Moodle WS API: структура курса, lesson/page/quiz контент
│   ├── ingestor.py        # Пайплайн индексации + генерация course_overview
│   ├── query_rewrite.py   # Multi-Query + HyDE через GPT-4o-mini (structured_output)
│   ├── llm.py             # Фабрика ChatOpenAI (singleton по параметрам)
│   ├── router.py          # POST /v1/ask (Advanced RAG + conversation history)
│   └── admin_router.py    # POST /v1/admin/reindex-course, GET /v1/admin/*
│
├── Dockerfile             # Предзагружает embedding-модель при сборке
├── docker-compose.yml     # ai-assistant + postgres-ai (pgvector/pgvector:pg16)
├── init.sql               # CREATE EXTENSION IF NOT EXISTS vector
└── requirements.txt
```

---

## Moodle-плагин

Блок `block_aiassistant` располагается в:
- Источник: `plugins/blocks/aiassistant/`
- Установка в Moodle: `MOODLE_ROOT/blocks/aiassistant/`

### Установка

1. Скопировать `block_aiassistant/` в `<moodle_root>/blocks/aiassistant/`
2. **Site administration → Notifications** — Moodle применит миграции
3. Добавить блок на страницу курса через «Режим редактирования»

### Структура

```
block_aiassistant/
├── block_aiassistant.php   # Класс блока, CSS + JS чата, рендеринг HTML
├── ajax.php                # PHP-прокси: проверяет доступ, передаёт history, проксирует
├── version.php             # v2.0.0
├── lang/en/block_aiassistant.php
└── db/access.php
```

### UI чата

- **Пузырьки сообщений**: вопросы студента — синие (справа), ответы — серые (слева)
- **Авто-resize** textarea: растёт по мере набора текста, `Shift+Enter` — перенос строки, `Enter` — отправка
- **Источники**: отображаются только `lesson` и `page`; каждый с новой строки с иконкой `↗`; оформлены блоком с левой серой полосой
- **История диалога**: хранится в `sessionStorage` — восстанавливается при перезагрузке в той же вкладке, сбрасывается при закрытии браузера
- **Кнопка «Clear chat»** — очищает визуально и в storage
- **Приветственное сообщение** при открытии блока

### Принцип работы

```
Студент вводит вопрос (Enter / кнопка Send)
      │
      │  JS:
      │  1. Собирает payload: { course_id, student_id, question, history[] }
      │  2. history[] — все реплики текущей сессии (из sessionStorage)
      │
      ▼
ajax.php:
  1. require_login()
  2. can_access_course($course, $USER)   ← студенты, учителя, admin
  3. Санитизация history: role/content, max 20 сообщений, max 4000 символов
  4. proxy → POST http://ai-assistant:8003/v1/ask
      │
      ▼
AI Assistant Service → { answer, sources }
      │
      ▼
JS:
  - Рендерит пузырёк с ответом
  - Добавляет источники (только lesson/page)
  - Сохраняет оба сообщения в sessionStorage
```

---

## Зависимости

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
pgvector==0.3.2
langchain-openai==0.3.9
langchain-core==0.3.51
langchain-text-splitters==0.3.8
sentence-transformers==3.2.1
numpy>=1.26
httpx==0.27.2
pydantic==2.9.2
```

Для работы pgvector необходим Docker-образ `pgvector/pgvector:pg16`.
