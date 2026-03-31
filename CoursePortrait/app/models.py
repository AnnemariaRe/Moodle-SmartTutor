from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum



class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"



class DifficultyMetricDetail(BaseModel):
    name: str = Field(description="Название метрики (для UI)")
    value: float = Field(description="Фактическое значение метрики")
    normalizedValue: float = Field(ge=0.0, le=1.0, description="Нормализованное значение (0-1)")
    weight: float = Field(ge=0.0, le=1.0, description="Вес метрики в формуле")
    contribution: float = Field(ge=0.0, le=1.0, description="Вклад в итоговый скор")
    interpretation: str = Field(description="Пояснение для преподавателя")


class DifficultyDetails(BaseModel):
    metrics: List[DifficultyMetricDetail] = Field(description="Детализация по метрикам")
    explanation: str = Field(description="Общее пояснение для преподавателя")
    suggestions: List[str] = Field(default_factory=list, description="Рекомендации по улучшению")



class ModuleHeatmap(BaseModel):
    moduleId: int
    sectionId: Optional[int] = None
    moduleName: Optional[str] = None
    moduleType: Optional[str] = Field(None, description="Тип модуля: video, text, quiz, assignment и т.д.")
    
    dropoutRisk: float = Field(ge=0.0, le=1.0, description="ML предсказание риска отвала (0-1)")
    difficulty: DifficultyLevel = Field(description="Уровень сложности (easy/medium/hard)")
    difficultyScore: float = Field(ge=0.0, le=1.0, description="Композитный индекс сложности (0-1)")
    
    difficultyDetails: Optional[DifficultyDetails] = Field(
        None,
        description="Детальная разбивка сложности по метрикам с пояснениями"
    )
    
    avgDurationMs: float = Field(description="Средняя длительность сессии в модуле (мс)")
    watchPercent: Optional[float] = Field(None, ge=0.0, le=1.0, description="Процент просмотра видео (только для видео, None для других)")
    engagementScore: float = Field(ge=0.0, le=1.0, description="Общий показатель вовлеченности (0-1)")
    studentCount: int = Field(description="Количество студентов, открывших модуль")
    dropoutRate: float = Field(ge=0.0, le=1.0, description="Процент отвала после модуля (0-1)")



class DropoffPoint(BaseModel):
    moduleId: int
    moduleName: Optional[str] = None
    moduleType: Optional[str] = Field(None, description="Тип модуля: quiz, page, video, assign и т.д.")
    step: int = Field(description="Порядковый номер модуля в курсе")
    studentsEntered: int = Field(description="Количество студентов, которые открыли этот модуль")
    studentsDropped: int = Field(description="Количество студентов, которые не перешли к следующим модулям")
    studentsContinued: int = Field(default=0, description="Количество студентов, которые продолжили к следующим модулям")
    dropoutRate: float = Field(ge=0.0, le=1.0, description="Процент отвала (0-1): доля студентов, не перешедших дальше")
    avgTimeBeforeDropout: Optional[float] = Field(None, description="Среднее время в модуле до отвала (миллисекунды)")



class FunnelStep(BaseModel):
    step: int = Field(description="Порядковый номер шага")
    moduleId: int
    moduleName: Optional[str] = None
    studentsCount: int = Field(description="Количество студентов на этом шаге")
    retentionRate: float = Field(ge=0.0, le=1.0, description="Процент студентов, дошедших до этого шага (0-1)")


class CourseHeatmapResponse(BaseModel):
    courseId: int
    modules: List[ModuleHeatmap] = Field(description="Список модулей с метриками")
    totalModules: int = Field(description="Общее количество модулей")
    bottleneckModules: List[int] = Field(description="ID модулей-узких мест (высокая сложность + высокий трафик)")
    generatedAt: datetime = Field(default_factory=datetime.now, description="Время генерации ответа")


class DropoffPointsResponse(BaseModel):
    courseId: int
    dropoffPoints: List[DropoffPoint] = Field(description="Список модулей с высоким отвалом (>30%)")
    topDropoffChains: List[List[int]] = Field(description="Топ-5 последовательностей модулей, заканчивающихся отвалом")
    totalEnrolled: int = Field(default=0, description="Всего студентов записано на курс")
    totalStarted: int = Field(default=0, description="Студентов начали курс (открыли хотя бы 1 модуль)")
    totalCompleted: int = Field(default=0, description="Студентов завершили курс")
    methodologyExplanation: str = Field(
        default="Процент отвала показывает долю студентов, которые открыли модуль, но не перешли к следующим модулям курса.",
        description="Пояснение методологии расчета отвала для отображения в UI"
    )
    generatedAt: datetime = Field(default_factory=datetime.now)


class FunnelResponse(BaseModel):
    courseId: int
    funnel: List[FunnelStep] = Field(description="Список шагов воронки")
    totalStudents: int = Field(description="Общее количество студентов, начавших курс")
    finalRetentionRate: float = Field(ge=0.0, le=1.0, description="Финальный процент удержания (0-1)")
    backwardNavigationRate: float = Field(default=0.0, ge=0.0, le=1.0, description="Доля навигаций назад к предыдущим модулям (0-1)")
    avgCourseCompletionTimeMs: float = Field(default=0.0, ge=0.0, description="Среднее суммарное время взаимодействия с курсом (мс)")
    avgSessionsPerUser: float = Field(default=0.0, ge=0.0, description="Среднее количество сессий на пользователя")
    generatedAt: datetime = Field(default_factory=datetime.now)


class SectionEngagement(BaseModel):
    sectionId: int
    sectionName: Optional[str] = None
    totalTimePercent: float = Field(ge=0.0, description="Суммарный % времени в секции")
    transitionsCount: int = Field(description="Количество переходов внутри секции")
    modules: List[int] = Field(description="ID модулей в секции")



class Recommendation(BaseModel):
    moduleId: int
    moduleName: Optional[str] = None
    issue: str = Field(description="Выявленная проблема (например: 'Высокий отвал (75%)')")
    recommendation: str = Field(description="Рекомендация по улучшению (например: 'Добавить промежуточные quiz')")
    priority: str = Field(description="Приоритет: high/medium/low")


class RecommendationsResponse(BaseModel):
    courseId: int
    recommendations: List[Recommendation] = Field(description="Список рекомендаций, отсортированный по приоритету")
    generatedAt: datetime = Field(default_factory=datetime.now)



class CourseListItem(BaseModel):
    id: int = Field(description="ID курса в Moodle")
    fullname: str = Field(description="Полное название курса")
    shortname: str = Field(description="Короткое название курса")
    visible: int = Field(description="Видимость курса (1=видим, 0=скрыт)")
    categoryid: Optional[int] = Field(None, description="ID категории курса")


class CoursesListResponse(BaseModel):
    courses: List[CourseListItem] = Field(description="Список курсов")
    totalCourses: int = Field(description="Общее количество курсов")
    generatedAt: datetime = Field(default_factory=datetime.now)


class CourseInfo(BaseModel):
    courseId: int
    courseName: Optional[str] = Field(None, description="Название курса")
    modules: List[Dict] = Field(description="Список модулей с названиями и метаданными")
    totalModules: Optional[int] = Field(None, description="Общее количество модулей в курсе (из Moodle)")
    totalStudents: Optional[int] = Field(None, description="Общее количество студентов на курсе (из Moodle)")
    generatedAt: datetime = Field(default_factory=datetime.now)



class VideoSegmentAnalytics(BaseModel):
    segment: str = Field(description="Сегмент видео: 0-25, 25-50, 50-75, 75-100")
    avgWatchTime: float = Field(ge=0.0, description="Среднее время просмотра сегмента (секунды)")
    segmentDuration: Optional[float] = Field(None, ge=0.0, description="Длительность сегмента (секунды), если известна")
    watchPercent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Процент просмотра сегмента (0-100)")
    watchShare: float = Field(ge=0.0, le=1.0, description="Доля сегмента в суммарном времени просмотра (0-1)")
    pauseCount: int = Field(default=0, ge=0, description="Количество пауз в этом сегменте")
    isWellWatched: bool = Field(default=False, description="True если watchPercent >= 90")
    isLeastWatched: bool = Field(default=False, description="True если это минимально просмотренный сегмент")


class VideoPauseHotspot(BaseModel):
    segment: str = Field(description="Сегмент где ставят паузу: 0-25, 25-50, 50-75, 75-100")
    pauseCount: int = Field(ge=0, description="Количество пауз в этом сегменте")
    avgPauseTime: Optional[float] = Field(None, ge=0.0, description="Среднее время паузы в секундах (внутри сегмента)")


class VideoSeekPattern(BaseModel):
    fromSegment: str = Field(description="Откуда перематывают: 0-25, 25-50, 50-75, 75-100")
    toSegment: str = Field(description="Куда перематывают: 0-25, 25-50, 50-75, 75-100")
    count: int = Field(ge=0, description="Количество таких перемоток")
    isBackward: bool = Field(description="True если перемотка назад")
    avgFromTimeMs: Optional[float] = Field(None, description="Среднее время начала перемотки (мс)")
    avgToTimeMs: Optional[float] = Field(None, description="Среднее время конца перемотки (мс)")


class VideoMediaAnalytics(BaseModel):
    courseId: int
    moduleId: int
    mediaId: str
    mediaType: str = Field(description="Тип медиа: video или audio")
    
    moduleName: Optional[str] = Field(None, description="Название модуля из Moodle")
    videoDurationMs: Optional[float] = Field(None, ge=0.0, description="Общая длительность видео (милисекунды)")

    uniqueUsers: int = Field(ge=0, description="Количество уникальных студентов, взаимодействовавших с видео")
    events: int = Field(ge=0, description="Количество событий (агрегировано)")

    avgWatchPercent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Средний процент просмотра (0-100)")
    avgFinalPercent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Средний финальный процент (0-100)")
    avgTotalWatchTime: Optional[float] = Field(None, ge=0.0, description="Среднее суммарное время просмотра (милисекунды)")

    pauseCount: int = Field(ge=0, description="Количество пауз (агрегировано)")
    seekCount: int = Field(ge=0, description="Количество перемоток (агрегировано)")
    seekBackwardCount: int = Field(ge=0, description="Количество перемоток назад (агрегировано)")

    segments: List[VideoSegmentAnalytics] = Field(description="Статистика по сегментам видео")
    leastWatchedSegments: List[str] = Field(description="Сегменты, которые смотрят меньше всего")
    mostWatchedSegments: List[str] = Field(description="Сегменты, которые смотрят больше всего")
    
    pauseHotspots: List[VideoPauseHotspot] = Field(default_factory=list, description="Точки частых пауз по сегментам")
    seekPatterns: List[VideoSeekPattern] = Field(default_factory=list, description="Паттерны перемоток")


class VideoAnalyticsResponse(BaseModel):
    courseId: int
    moduleId: Optional[int] = Field(None, description="Если задано — фильтр по модулю")
    mediaId: Optional[str] = Field(None, description="Если задано — фильтр по конкретному видео")
    dateFrom: Optional[str] = Field(None, description="Параметр запроса date_from (YYYY-MM-DD)")
    dateTo: Optional[str] = Field(None, description="Параметр запроса date_to (YYYY-MM-DD)")

    videos: List[VideoMediaAnalytics]
    totalVideos: int
    generatedAt: datetime = Field(default_factory=datetime.now)
