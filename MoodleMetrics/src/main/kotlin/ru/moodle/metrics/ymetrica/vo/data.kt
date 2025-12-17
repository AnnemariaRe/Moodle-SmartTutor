package ru.moodle.metrics.ymetrica.vo

import com.fasterxml.jackson.annotation.JsonIgnoreProperties

@JsonIgnoreProperties(ignoreUnknown = true)
data class MetricaTableResponse(
    val data: List<MetricaRow>
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class MetricaRow(
    val dimensions: List<MetricaDimension>,
    val metrics: List<Double>
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class MetricaDimension(
    val name: String?,
    val id: String?,
    val value: String?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class ModuleProgress(
    val moduleId: String,
    val moduleName: String?,
    val openedUsers: Long,
    val enrolledUsers: Long?,       // подтягиваешь из Moodle при необходимости
    val openedPercent: Double?,
    val completedUsers: Long,
    val completedPercent: Double?,
    val backMoves: Long?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class ParsedEventKey(
    val courseId: Long?,
    val moduleId: String?,
    val activityType: String?,
    val eventType: String?,
    val durationMs: Long?,
    val delayMs: Long?,
    val step: Int?,
    val prevModuleId: String?,
    val stepDurationMs: Long?,
    val userId: Long?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class CourseEventDto(
    val eventKey: String,
    val users: Long,
    val parsed: ParsedEventKey
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class CourseTime(
    val courseId: Long,
    val totalCourseTimeMs: Long,
    val avgCourseTimePerUserMs: Long?,
    val modules: List<ModuleTime>,
    val avgFirstInteractionDelayMs: Long?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class ModuleTime(
    val moduleId: String,
    val avgTimeMs: Long
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class StudentStep(
    val step: Int,
    val moduleId: String,
    val activityType: String?,
    val stepDurationMs: Long?,
    val movedBack: Boolean
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class StudentPath(
    val courseId: Long,
    val userId: String?,
    val steps: List<StudentStep>
)

/**
 * Агрегированные метрики по «пути студента» для всего курса.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
data class CoursePathSummary(
    val courseId: Long,
    val studentsCount: Int = 0,
    /** Среднее количество шагов (просмотров модулей) на одного студента. */
    val avgStepsPerStudent: Double = 0.0,
    /** Среднее время между шагами (по всем студентам и шагам), мс. */
    val avgStepDurationMs: Long? = null,
    /** Общее и среднее количество «возвратов назад» (movedBack=true). */
    val totalBackMoves: Long = 0,
    val avgBackMovesPerStudent: Double = 0.0,
    /** Модули, в которые чаще всего возвращаются (по числу back-переходов). */
    val topBacktrackedModules: List<BacktrackedModule> = emptyList()
)

/**
 * Информация о модуле, в который часто возвращаются студенты.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
data class BacktrackedModule(
    val moduleId: String,
    /** Сколько раз этот модуль встречался как цель шага movedBack=true. */
    val backMovesCount: Long
)
