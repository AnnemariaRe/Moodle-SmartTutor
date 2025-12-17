package ru.moodle.metrics.ymetrica.service

import ru.moodle.metrics.ymetrica.vo.CourseEventDto
import ru.moodle.metrics.ymetrica.vo.CoursePathSummary
import ru.moodle.metrics.ymetrica.vo.CourseTime
import ru.moodle.metrics.ymetrica.vo.ModuleProgress

interface YandexMetricaService {

    /**
     * Получить по API Метрики количество уникальных пользователей
     * для module_open и module_complete по каждому moduleId в рамках courseId.
     */
    fun getModuleProgress(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): List<ModuleProgress>

    fun getCourseEvents(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): List<CourseEventDto>

    fun getCourseTimeMetrics(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CourseTime

    fun getCoursePathSummary(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CoursePathSummary
}