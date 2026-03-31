# MoodleSmartTutor

Интеллектуальная обучающая система для Moodle: адаптивные рекомендации, генерация персонализированных заданий, AI-ассистент, аналитика курсов и трекинг событий.

## Обзор архитектуры

Система состоит из 5 бэкенд-микросервисов и 4 плагинов Moodle, которые связывают их с LMS.

![alt text](image.png)

### Сервисы

| Сервис | Описание |
|--------|----------|
| **TrackingService** | Принимает события Moodle по HTTP, сохраняет в PostgreSQL, публикует в RabbitMQ |
| **AdaptiveService** | Граф знаний, отслеживание уровня освоения (BKT), рекомендации (LightFM + правиловая модель), предсказания DKT |
| **AIAssist** | RAG-ассистент для ответов на вопросы по курсу (pgvector + OpenAI) |
| **TaskGenerator** | Генерация персонализированных тренировочных заданий на основе уровня освоения (OpenAI) |
| **CoursePortrait** | Аналитика курсов: тепловые карты, предсказание отвала (XGBoost), анализ сложности, интеграция с Яндекс Метрикой |

---

## Требования

- Docker и Docker Compose v2
- Работающий экземпляр Moodle (доступный из Docker-контейнеров)
- Токен Moodle REST API (создается через Администрирование > Плагины > Веб-сервисы)
- Ключ OpenAI API (для AIAssist и TaskGenerator)
- (Опционально) ID счетчика Яндекс Метрики и OAuth-токен (для аналитики CoursePortrait)

---

## Развертывание

### 1. Создание общих Docker-сетей

Эти сети должны существовать до запуска любого сервиса:

```bash
docker network create moodle_shared_net
docker network create trackingservice_internal
docker network create rabbitmq_shared_net
docker network create adaptive_shared_net
```

### 2. Настройка переменных окружения

Каждый сервис содержит файл `.env.example`. Скопируйте его в `.env` и заполните своими значениями:

```bash
cp .env.example .env
```

**Обязательные параметры для настройки:**

| Сервис | Переменная | Описание |
|--------|------------|----------|
| AdaptiveService | `MOODLE_TOKEN` | Токен Moodle REST API |
| AdaptiveService | `MOODLE_URL` | Базовый URL Moodle |
| AIAssist | `OPENAI_API_KEY` | Ключ OpenAI API для RAG |
| AIAssist | `MOODLE_TOKEN` | Токен Moodle REST API |
| TaskGenerator | `OPENAI_API_KEY` | Ключ OpenAI API для генерации заданий |
| CoursePortrait | `MOODLE_TOKEN` | Токен Moodle REST API |
| CoursePortrait | `METRIKA_COUNTER_ID` | ID счетчика Яндекс Метрики |
| CoursePortrait | `METRIKA_OAUTH_TOKEN` | OAuth-токен Яндекс Метрики |

### 3. Запуск сервисов

Запускайте сервисы в следующем порядке (важны зависимости):

1. TrackingService (создает RabbitMQ, который нужен AdaptiveService)
2. AdaptiveService (потребляет из RabbitMQ, предоставляет API для TaskGenerator)
3. Остальные сервисы: AIAssist, TaskGenerator, CoursePortrait

```bash
docker compose up -d --build
```

### 5. Инициализация графа знаний AdaptiveService

После первого запуска необходимо импортировать структуру курса:

```bash
# Извлечение концептов из содержимого курса
curl -X POST "http://localhost:8002/v1/admin/extract-concepts?course_id=ID_ВАШЕГО_КУРСА"

# Обучение рекомендательной модели LightFM
curl -X POST "http://localhost:8002/v1/admin/train-lightfm?course_id=ID_ВАШЕГО_КУРСА"
```

### 6. Инициализация базы знаний AIAssist

Индексация содержимого курса для RAG-ассистента:

```bash
curl -X POST "http://localhost:8003/v1/admin/index?course_id=ID_ВАШЕГО_КУРСА"
```

---

## Плагины Moodle

Плагины расположены в директории `plugins/` и должны быть установлены в Moodle.

### Типы плагинов и пути установки

| Плагин | Тип | Куда устанавливать | Назначение |
|--------|-----|-------------------|------------|
| `local/metrika` | local | `MOODLE_ROOT/local/metrika/` | Перехватывает события студентов и отправляет в TrackingService |
| `blocks/adaptive` | block | `MOODLE_ROOT/blocks/adaptive/` | Отображает адаптивные рекомендации из AdaptiveService |
| `blocks/aiassistant` | block | `MOODLE_ROOT/blocks/aiassistant/` | Виджет AI-чата, проксирует запросы в AIAssist |
| `blocks/personal_tasks` | block | `MOODLE_ROOT/blocks/personal_tasks/` | Персонализированные тренировочные задания из TaskGenerator |

### Установка

1. **Скопируйте плагины в Moodle:**

3. **Настройте `local_metrika`:**
   - Перейдите в `Администрирование > Плагины > Локальные плагины > Yandex Metrica integration`
   - Включите трекинг
   - Укажите ID счетчика Яндекс Метрики

4. **Настройте `block_personal_tasks`:**
   - Перейдите в `Администрирование > Плагины > Блоки > Personal Tasks`
   - Убедитесь, что URL TaskGenerator указан как `http://personalized-tasks:8004`

5. **Добавьте блоки на страницы курсов:**
   - Откройте страницу курса
   - Включите режим редактирования
   - Добавьте блоки: "Recommendations", "AI Assistant", "Personal Tasks"

### Связь плагинов с сервисами

**Важно:** Moodle должен находиться в той же Docker-сети `moodle_shared_net`, чтобы плагины могли обращаться к сервисам. Если Moodle запущен через собственный docker-compose, добавьте сеть:

```yaml
# В docker-compose.yml Moodle
services:
  moodle:
    networks:
      - moodle_shared_net

networks:
  moodle_shared_net:
    external: true
```

---

## Обучение ML-моделей CoursePortrait

Скрипты обучения находятся в `CoursePortrait/training/`. Для переобучения моделей предсказания отвала и сложности:

```bash
# Вариант 1: Экспорт реальных данных из TrackingService
python training/export_from_tracking.py --db-url postgresql://tracking:tracking@localhost:5435/tracking

# Вариант 2: Использование публичного датасета KDD Cup 2015
python training/prepare_kdd_dataset.py datasets/act-mooc datasets/kdd_prepared.csv

# Обучение моделей (результат сохраняется в models/)
python training/prep_and_train.py --mooc-data datasets/my_data.csv
```

Обученные модели (`.pkl`) загружаются CoursePortrait при запуске из директории `models/`.
