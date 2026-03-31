# Course Portrait Service

Микросервис аналитики курсов для платформы Moodle: тепловые карты сложности, предсказание отвала (XGBoost), анализ видео, воронка прохождения и рекомендации на основе данных из Yandex.Metrika и Moodle Web Services API.

---

## Быстрый старт

```bash
cp .env.example .env
# Заполните METRIKA_COUNTER_ID, METRIKA_OAUTH_TOKEN, MOODLE_URL, MOODLE_TOKEN

# Обучите ML-модель (один раз)
docker compose run --rm app python training/prep_and_train.py

# Запустите сервисы
docker compose up -d --build
```

Dashboard: `http://app:8005/dashboard`

---

## Конфигурация

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_USER` | `user` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `changeme` | Пароль PostgreSQL |
| `POSTGRES_DB` | `portrait` | Имя БД |
| `METRIKA_COUNTER_ID` | — | ID счётчика Яндекс Метрики |
| `METRIKA_OAUTH_TOKEN` | — | OAuth-токен Метрики |
| `MOODLE_URL` | — | URL Moodle-инстанса |
| `MOODLE_TOKEN` | — | Токен Moodle REST API |
| `JWT_SECRET_KEY` | — | Секрет для JWT |
| `APP_PORT` | `8005` | Порт сервиса |

Если токены Метрики или Moodle не заданы — сервис возвращает пустые результаты.

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v1/courses` | Список всех курсов |
| GET | `/api/v1/courses/{id}/info` | Структура курса и модули |
| GET | `/api/v1/courses/{id}/heatmap` | Heatmap сложностей |
| GET | `/api/v1/courses/{id}/dropoff-points` | Точки отвала студентов |
| GET | `/api/v1/courses/{id}/funnel` | Воронка прохождения |
| GET | `/api/v1/courses/{id}/recommendations` | Рекомендации |
| GET | `/api/v1/courses/{id}/video-analytics` | Видеоаналитика |
| GET | `/dashboard` | HTML-дашборд (Chart.js) |

---

## Расчёт сложности

Тип-специфичные калькуляторы:

- **Видео**: watchPercent (0.4), pauseCount (0.3), durationRatio (0.2), seekBackward (0.1)
- **Квизы**: avgScore (0.35), attemptCount (0.25), completionRate (0.2), avgTimeSpent (0.2)
- **Текст**: avgReadTime (0.4), scrollDepth (0.3), returnVisits (0.3)
- **Задания**: submissionRate (0.3), avgGrade (0.3), lateSubmissions (0.2), resubmissions (0.2)

Уровни: easy (< 0.4), medium (0.4–0.7), hard (>= 0.7).

---

## ML-модель: Dropout Risk Predictor

XGBoost (`binary:logistic`) предсказывает вероятность отвала студента после модуля.

**Признаки:** `durationMs/1000` (секунды), `watchPercent` (0–1), `step` (порядковый номер модуля).

### Обучение

```bash
# Экспорт реальных данных из TrackingService
python training/export_from_tracking.py --output datasets/my_data.csv

# Или использование KDD Cup 2015 датасета
python training/prepare_kdd_dataset.py datasets/act-mooc/ datasets/kdd_prepared.csv

# Обучение
python training/prep_and_train.py --mooc-data datasets/my_data.csv
```

Обученная модель (`models/dropout_predictor.pkl`) загружается при старте сервиса. Если модель не найдена — fallback: `dropout_risk = 1.0 - watchPercent`.
