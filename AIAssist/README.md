# AI Assistant Service

Микросервис виртуального учебного ассистента для платформы Moodle.
Реализует **Advanced RAG** (Retrieval-Augmented Generation) с query rewriting и поддержкой многоходового диалога: переформулирует вопрос студента через LLM, выполняет мультизапросный поиск по векторному индексу курса и генерирует ответ через GPT-4o-mini с учётом всей истории разговора.

---

## Быстрый старт

```bash
cp .env.example .env
# Заполните OPENAI_API_KEY, MOODLE_URL, MOODLE_TOKEN

docker compose up -d

# Проиндексируйте курс
curl -X POST "http://ai-assistant:8003/v1/admin/reindex-course?course_id=10"
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
| `OPENAI_API_KEY` | — | API-ключ OpenAI |
| `CORS_ORIGINS` | `*` | Разрешённые CORS-источники |
| `AI_ASSIST_PORT` | `8003` | Порт сервиса |

---

## API

### `POST /v1/ask`

Задать вопрос ассистенту.

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
| `history` | array | нет | История диалога, до 20 сообщений |

**Ответ:**
```json
{
  "course_id": 10,
  "answer": "Шифр преобразует сам текст, а код заменяет слова условными обозначениями...",
  "sources": [
    { "cmid": 513, "title": "Лекция №2", "type": "lesson" },
    { "cmid": 520, "title": "Логические задачи", "type": "page" }
  ]
}
```

### Административные

| Метод | Путь | Описание |
|-------|------|---------|
| POST | `/v1/admin/reindex-course?course_id=X` | Переиндексация курса + генерация overview |
| GET | `/v1/admin/index-stats?course_id=X` | Статистика индекса (чанки, вопросы) |
| GET | `/v1/admin/logs?course_id=X&limit=50` | Последние диалоги по курсу |

---

## Пайплайн индексации

1. Загрузка структуры курса из Moodle API (`core_course_get_contents`)
2. Обогащение контента: `mod_lesson_get_pages`, `mod_page_get_pages_by_courses`, `mod_quiz_get_quizzes_by_courses`
3. HTML-очистка → `RecursiveCharacterTextSplitter` (chunk_size=1200, overlap=150) → чанки
4. Батчевое вычисление эмбеддингов (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dims) → атомарная замена в БД
5. GPT-4o-mini генерирует аннотацию курса → upsert в `course_overviews`

---

## Moodle-плагин

Блок `block_aiassistant`:
- Источник: `plugins/blocks/aiassistant/`
- Установка: `MOODLE_ROOT/blocks/aiassistant/`

Плагин реализует UI чата с пузырьками сообщений, историей в `sessionStorage` и PHP-прокси (`ajax.php`) для обращения к сервису.
