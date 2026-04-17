# local_metrika — Плагин интеграции Moodle с Яндекс.Метрикой

Локальный плагин Moodle, который выполняет две функции:
1. **Серверная:** перехватывает события Moodle (quiz, assign, lesson) и отправляет их в TrackingService по HTTP
2. **Клиентская:** встраивает JavaScript-трекинг Яндекс.Метрики на все страницы Moodle для сбора поведенческой аналитики (сессии, видео, навигация)

## Архитектура

```
                  Moodle
    ┌──────────────┴──────────────┐
    │                             │
 PHP observer                JavaScript (browser)
    │                             │
    │ POST /v1/events             │ ym(counterId, ...)
    ▼                             ▼
TrackingService              Яндекс.Метрика API
 (port 8001)                      │
    │                             │
    ▼                             ▼
 PostgreSQL              CoursePortrait сервис
 + RabbitMQ               (pull_events, video)
    │
    ▼
AdaptiveService
 (mastery, BKT)
```

## Установка

1. Скопировать `plugins/local/metrika` в `<moodle>/local/metrika/`
2. Зайти в Moodle → Site administration → Notifications (запустится установка)
3. Настроить плагин: Site administration → Plugins → Local plugins → Yandex Metrica settings

## Настройки

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| **Enable tracking** (`enabled`) | Включить/выключить JS-трекинг Яндекс.Метрики | Выключен |
| **Counter ID** (`counterid`) | ID счётчика Яндекс.Метрики (число) | Пусто |

Настройки влияют **только на JS-часть** (клиентский трекинг). Серверная отправка событий в TrackingService работает всегда, независимо от этих настроек.

## Серверная часть — PHP Observer

### Отслеживаемые события

Плагин подписан на 9 событий Moodle через `db/events.php`:

| Событие Moodle | Тип в TrackingService | Payload |
|----------------|----------------------|---------|
| `course_module_viewed` | `course_module_viewed` | `module_name`, `time_spent_sec` |
| `quiz\attempt_submitted` | `quiz_attempt_submitted` | `score`, `max_score`, `attempt_no` |
| `assign\submission_created` | `assign_submission_created` | — |
| `assign\submission_graded` | `assign_submission_graded` | `grade` |
| `lesson\lesson_started` | `lesson_started` | — |
| `lesson\content_page_viewed` | `lesson_page_view` | `page_id` |
| `lesson\question_viewed` | `lesson_page_view` | `page_id` |
| `lesson\question_answered` | `lesson_answer_submitted` | `page_id`, `is_correct` |
| `lesson\lesson_ended` | `lesson_completed` | `num_questions`, `num_correct`, `score_percent`, `num_attempts` |

### Формат события

```json
{
  "event_id": "6605abcd12345.12345678",
  "ts": 1712000000,
  "student_id": 12,
  "course_id": 5,
  "event_type": "quiz_attempt_submitted",
  "object_type": "quiz_attempt",
  "object_id": 345,
  "cmid": 78,
  "payload": {
    "score": 8.0,
    "max_score": 10.0,
    "attempt_no": 1
  }
}
```

### Куда отправляются

`POST http://tracking-service:8001/v1/events` — неблокирующий вызов с таймаутом 0.3 сек.

### Фильтрация

Действия администраторов (`is_siteadmin()`) не отправляются — трекинг только для студентов.

## Клиентская часть — JavaScript

При включённом плагине (`enabled=1`, `counterid` задан) на каждую страницу Moodle подключается 7 JS-файлов.

### Глобальные переменные

PHP-хук `local_metrika_before_http_headers()` выставляет на каждой странице:

```javascript
window.M.metrika.counterId = "12345678";  // ID счётчика
window.M.moodle.courseId = 5;             // ID текущего курса
window.M.moodle.cmid = 78;               // ID текущего модуля
window.M.moodle.userId = 12;             // ID текущего пользователя
```

### Модули трекинга

#### `init.js` — Инициализация
Ожидает загрузки Яндекс.Метрики (`ym()`) и counterId, затем вызывает `setup()` у каждого модуля. Таймаут: 50 попыток по 100 мс (5 сек).

#### `utils.js` — Утилиты
- `getParam(href, name)` — извлечение параметра из URL
- `getPhpIds()` — получение courseId/cmid из `window.M.moodle`
- `getCurrentCourseId()` — текущий курс (PHP → localStorage fallback)

#### `course.js` — События уровня курса

| Событие | Условие | Данные |
|---------|---------|--------|
| `course_session` | При уходе со страницы `/course/view.php` | `durationMs` |
| `first_activity_click` | Первый клик по ссылке `/mod/*` | `delayMs` |
| `section_view` | Открытие `/course/section.php` | `sectionId` |
| `enroll` | Клик по кнопке записи на курс | `courseId` |

#### `module.js` — События уровня модуля

| Событие | Условие | Данные |
|---------|---------|--------|
| `module_session` | При уходе со страницы модуля | `moduleId`, `durationMs` |
| `module_open` | Открытие `/mod/*/view.php` | `moduleId`, `step`, `prevModuleId`, `stepDurationMs`, `userId` |

Модуль отслеживает **путь студента** через курс: каждый переход между модулями записывает номер шага (`step`), предыдущий модуль и время на предыдущем шаге.

#### `video.js` — Видеоаналитика

Самый сложный модуль. Трекает:
- HTML5 `<video>` и `<audio>` элементы
- VideoJS плееры (включая lazy-loaded через AMD)
- YouTube-iframe через VideoJS-YouTube плагин
- Динамически добавленные медиа (через MutationObserver)

| Событие | Когда | Данные |
|---------|-------|--------|
| `video_watch` | Достижение milestone (0%, 25%, 50%, 75%, 100%) | `watchPercent` |
| `video_pause` | Пауза | `pauseCount`, `pauseTimeMs`, `pausePercent` |
| `video_seek` | Перемотка | `seekCount`, `seekBackward`, `fromSegment`, `toSegment` |
| `video_stats` | Уход со страницы или конец видео | `finalPercent`, `pauseCount`, `seekCount`, `totalWatchTimeMs`, посегментное время (`segment_0_25_ms`, ...) |

Каждое видео разбивается на 4 сегмента (0–25%, 25–50%, 50–75%, 75–100%), для каждого считается время просмотра.

#### `path.js` — Навигационный путь

Хранит состояние навигации в `localStorage`:
- `lastModuleId` — последний просмотренный модуль
- `stepIndex` — порядковый номер шага
- `lastStepTimestamp` — время последнего перехода

Используется `module.js` для построения цепочки переходов.

#### `metrika.js` — Точка входа

Оркестрирует инициализацию: после загрузки Метрики вызывает `setup()` для `MetrikaCourse`, `MetrikaModule`, `MetrikaVideo`.

### Формат eventKey

Все JS-события отправляются через `ym(counterId, 'params', { eventKey: ... })` в формате:

```
courseId=5;moduleId=78;eventType=module_session;durationMs=45000;userId=12
```

Ключ-значение через `;`, парсится на стороне CoursePortrait (`metrika.py → _parse_event_key()`).

## Интеграция с CoursePortrait

CoursePortrait (`/CoursePortrait/app/services/metrika.py`) забирает данные из Яндекс.Метрики через REST API:

```
GET https://api-metrica.yandex.net/stat/v1/data
Headers: Authorization: OAuth <token>
```

Переменные окружения CoursePortrait:
- `METRIKA_COUNTER_ID` — ID счётчика
- `METRIKA_OAUTH_TOKEN` — OAuth-токен Яндекс.Метрики

### API-эндпоинты CoursePortrait, использующие Метрику

| Эндпоинт | Описание | Данные из Метрики |
|----------|----------|-------------------|
| `GET /courses/{id}/heatmap` | Тепловая карта курса | `pull_events()` → durationMs, watchPercent, studentCount |
| `GET /courses/{id}/dropoff-points` | Точки отвала студентов | `pull_events()` + `get_module_sequences()` |
| `GET /courses/{id}/funnel` | Воронка прохождения курса | `pull_events()` + `get_funnel_stats()` |
| `GET /courses/{id}/recommendations` | Рекомендации по улучшению | `pull_events()` + ML-предсказания |
| `GET /courses/{id}/video-analytics` | Видеоаналитика | `pull_video_analytics()` → сегменты, паузы, перемотки |

### Поток данных от JS до аналитики

```
1. Студент смотрит видео на странице модуля
2. video.js отправляет: ym(counter, 'params', {
     eventKey: "courseId=5;moduleId=78;mediaId=/video.mp4;eventType=video_stats;
                finalPercent=75;pauseCount=3;totalWatchTimeMs=120000;
                segment_0_25_ms=30000;segment_25_50_ms=45000;..."
   })
3. Яндекс.Метрика сохраняет в свою базу
4. CoursePortrait делает GET к API Метрики с фильтрами по courseId
5. metrika.py парсит eventKey, агрегирует по модулям
6. Фронтенд отображает тепловые карты и видеоаналитику
```

## Структура файлов

```
local/metrika/
├── version.php           # Метаданные плагина (v0.1, ALPHA)
├── settings.php          # Страница настроек (enabled, counterid)
├── lib.php               # Хук before_http_headers — инжект JS
├── metrika.js            # Точка входа JS
├── js/
│   ├── init.js           # Ожидание загрузки ym()
│   ├── utils.js          # Вспомогательные функции
│   ├── course.js         # Трекинг на уровне курса
│   ├── module.js         # Трекинг на уровне модуля
│   ├── video.js          # Видеоаналитика (HTML5, VideoJS, YouTube)
│   └── path.js           # Навигационный путь (localStorage)
├── classes/
│   └── observer.php      # Обработчик событий → TrackingService
├── db/
│   ├── events.php        # Подписка на 9 событий Moodle
│   └── access.php        # Capability local/metrika:manage
└── lang/
    ├── en/local_metrika.php
    └── ru/local_metrika.php
```

## Требования

- Moodle ≥ 4.1
- TrackingService запущен и доступен по `http://tracking-service:8001`
- Для JS-трекинга: счётчик Яндекс.Метрики с включённым сбором параметров визитов
- Для CoursePortrait: OAuth-токен Яндекс.Метрики с правами на чтение
