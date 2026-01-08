package ru.moodle.metrics.api

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import ru.moodle.metrics.ymetrica.service.YandexMetricaService
import ru.moodle.metrics.ymetrica.vo.CourseEventDto
import ru.moodle.metrics.ymetrica.vo.CoursePathSummary
import ru.moodle.metrics.ymetrica.vo.CourseTime
import ru.moodle.metrics.ymetrica.vo.CourseVideoMetrics
import ru.moodle.metrics.ymetrica.vo.ModuleProgress

@RestController
class ProgressController(
    private val metricaService: YandexMetricaService
) {

    /**
     * Возвращает агрегированный прогресс по модулям выбранного курса за указанный период.
     *
     * Для каждого модуля курса рассчитывается число уникальных пользователей,
     * которые открывали модуль (activityType=view) и завершали модуль (activityType=complete).
     *
     * @param courseId идентификатор курса в Moodle
     * @param dateFrom начало периода в формате, поддерживаемом API Яндекс.Метрики
     * @param dateTo конец периода
     * @return список объектов {@link ModuleProgress}, по одному на каждый модуль курса
     */
    @GetMapping("/api/courses/{courseId}/modules/progress")
    fun getModulesProgress(
        @PathVariable courseId: Long,
        @RequestParam(defaultValue = "30daysAgo") dateFrom: String,
        @RequestParam(defaultValue = "today") dateTo: String
    ): List<ModuleProgress> {
        return metricaService.getModuleProgress(courseId, dateFrom, dateTo)
    }

    /**
     * Возвращает «сырые» события курса за указанный период в том виде,
     * как они были собраны из Яндекс.Метрики и распарсены из параметра eventKey.
     *
     * Каждый элемент результата содержит исходный eventKey, агрегированное
     * количество уникальных пользователей для этого события и структурированное
     * представление разобранных полей (courseId, moduleId, activityType,
     * eventType, durationMs, delayMs).
     *
     * @param courseId идентификатор курса в Moodle
     * @param dateFrom начало периода выборки событий
     * @param dateTo конец периода выборки событий
     * @return список объектов {@link CourseEventDto}, описывающих события курса
     */
    @GetMapping("/api/courses/{courseId}/events")
    fun getCourseEvents(
        @PathVariable courseId: Long,
        @RequestParam(defaultValue = "30daysAgo") dateFrom: String,
        @RequestParam(defaultValue = "today") dateTo: String
    ): List<CourseEventDto> {
        return metricaService.getCourseEvents(courseId, dateFrom, dateTo)
    }

    /**
     * Возвращает временные метрики по выбранному курсу за указанный период.
     *
     * В ответе содержатся агрегаты по времени в курсе и модулях:
     * суммарное время, среднее время в курсе на пользователя, среднее время
     * просмотра по каждому модулю, а также средняя задержка до первого
     * взаимодействия с активностями курса.
     *
     * @param courseId идентификатор курса в Moodle
     * @param dateFrom начало периода, за который считаются метрики
     * @param dateTo конец периода, за который считаются метрики
     * @return объект {@link CourseTime}, содержащий сводные временные метрики курса
     */
    @GetMapping("/api/courses/{courseId}/time")
    fun getCourseTimeMetrics(
        @PathVariable courseId: Long,
        @RequestParam(defaultValue = "30daysAgo") dateFrom: String,
        @RequestParam(defaultValue = "today") dateTo: String
    ): CourseTime {
        return metricaService.getCourseTimeMetrics(courseId, dateFrom, dateTo)
    }

    @GetMapping("/api/courses/{courseId}/path")
    fun getCoursePathSummary(
        @PathVariable courseId: Long,
        @RequestParam(defaultValue = "30daysAgo") dateFrom: String,
        @RequestParam(defaultValue = "today") dateTo: String
    ): CoursePathSummary {
        return metricaService.getCoursePathSummary(courseId, dateFrom, dateTo)
    }

    /**
     * Возвращает видео-метрики для выбранного курса за указанный период.
     *
     * В ответе содержатся агрегированные метрики по просмотру видео/аудио:
     * процент досмотра по milestone'ам (25%, 50%, 75%, 100%), статистика по паузам,
     * перемоткам, времени просмотра по сегментам для каждого модуля с медиа-контентом.
     *
     * @param courseId идентификатор курса в Moodle
     * @param dateFrom начало периода, за который считаются метрики
     * @param dateTo конец периода, за который считаются метрики
     * @return объект {@link CourseVideoMetrics}, содержащий сводные видео-метрики курса
     */
    @GetMapping("/api/courses/{courseId}/video")
    fun getCourseVideoMetrics(
        @PathVariable courseId: Long,
        @RequestParam(defaultValue = "30daysAgo") dateFrom: String,
        @RequestParam(defaultValue = "today") dateTo: String
    ): CourseVideoMetrics {
        return metricaService.getCourseVideoMetrics(courseId, dateFrom, dateTo)
    }

}