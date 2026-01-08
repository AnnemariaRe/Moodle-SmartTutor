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
    val userId: Long?,
    // Video metrics
    val mediaId: String? = null,
    val mediaType: String? = null,
    val watchPercent: Int? = null,
    val pauseCount: Int? = null,
    val seekCount: Int? = null,
    val seekBackward: Int? = null,
    val totalWatchTime: Long? = null,
    val segment025Time: Long? = null,
    val segment2550Time: Long? = null,
    val segment5075Time: Long? = null,
    val segment75100Time: Long? = null,
    val finalPercent: Int? = null
) {
    companion object {
        /**
         * Парсит строку eventKey и создает ParsedEventKey используя билдер.
         */
        fun parse(value: String): ParsedEventKey {
            val builder = ParsedEventKeyBuilder()
            
            value.split(';').forEach { part ->
                val kv = part.split('=', limit = 2)
                if (kv.size != 2) return@forEach
                
                val (key, v) = kv[0] to kv[1]
                when (key) {
                    "courseId" -> builder.courseId = v.toLongOrNull()
                    "moduleId" -> builder.moduleId = v
                    "activityType" -> builder.activityType = v
                    "eventType" -> builder.eventType = v
                    "durationMs" -> builder.durationMs = v.toLongOrNull()
                    "delayMs" -> builder.delayMs = v.toLongOrNull()
                    "step" -> builder.step = v.toIntOrNull()
                    "prevModuleId" -> builder.prevModuleId = v
                    "stepDurationMs" -> builder.stepDurationMs = v.toLongOrNull()
                    "userId" -> builder.userId = v.toLongOrNull()
                    "mediaId" -> builder.mediaId = v
                    "mediaType" -> builder.mediaType = v
                    "watchPercent" -> builder.watchPercent = v.toIntOrNull()
                    "pauseCount" -> builder.pauseCount = v.toIntOrNull()
                    "seekCount" -> builder.seekCount = v.toIntOrNull()
                    "seekBackward" -> builder.seekBackward = v.toIntOrNull()
                    "totalWatchTime" -> builder.totalWatchTime = v.toLongOrNull()
                    "segment_0_25_time" -> builder.segment025Time = v.toLongOrNull()
                    "segment_25_50_time" -> builder.segment2550Time = v.toLongOrNull()
                    "segment_50_75_time" -> builder.segment5075Time = v.toLongOrNull()
                    "segment_75_100_time" -> builder.segment75100Time = v.toLongOrNull()
                    "finalPercent" -> builder.finalPercent = v.toIntOrNull()
                }
            }
            
            return builder.build()
        }
    }
    
    /**
     * Внутренний билдер для создания ParsedEventKey.
     */
    private class ParsedEventKeyBuilder {
        var courseId: Long? = null
        var moduleId: String? = null
        var activityType: String? = null
        var eventType: String? = null
        var durationMs: Long? = null
        var delayMs: Long? = null
        var step: Int? = null
        var prevModuleId: String? = null
        var stepDurationMs: Long? = null
        var userId: Long? = null
        var mediaId: String? = null
        var mediaType: String? = null
        var watchPercent: Int? = null
        var pauseCount: Int? = null
        var seekCount: Int? = null
        var seekBackward: Int? = null
        var totalWatchTime: Long? = null
        var segment025Time: Long? = null
        var segment2550Time: Long? = null
        var segment5075Time: Long? = null
        var segment75100Time: Long? = null
        var finalPercent: Int? = null
        
        fun build() = ParsedEventKey(
            courseId, moduleId, activityType, eventType, durationMs, delayMs,
            step, prevModuleId, stepDurationMs, userId,
            mediaId, mediaType, watchPercent, pauseCount, seekCount, seekBackward,
            totalWatchTime, segment025Time, segment2550Time, segment5075Time, segment75100Time, finalPercent
        )
    }
}

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

/**
 * Статистика по видео/аудио для модуля.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
data class VideoModuleStats(
    val moduleId: String,
    val moduleName: String?,
    val mediaId: String?,
    val mediaType: String?,
    /** Количество пользователей, которые начали просмотр (watchPercent >= 0). */
    val startedUsers: Long = 0,
    /** Количество пользователей, которые досмотрели до 25%. */
    val watched25Users: Long = 0,
    /** Количество пользователей, которые досмотрели до 50%. */
    val watched50Users: Long = 0,
    /** Количество пользователей, которые досмотрели до 75%. */
    val watched75Users: Long = 0,
    /** Количество пользователей, которые досмотрели до 100%. */
    val watched100Users: Long = 0,
    /** Средний процент досмотра. */
    val avgWatchPercent: Double? = null,
    /** Среднее количество пауз. */
    val avgPauseCount: Double? = null,
    /** Среднее количество перемоток. */
    val avgSeekCount: Double? = null,
    /** Среднее количество возвратов назад. */
    val avgSeekBackwardCount: Double? = null,
    /** Среднее время просмотра (мс). */
    val avgWatchTimeMs: Long? = null,
    /** Среднее время просмотра по сегментам (мс). */
    val avgSegment025TimeMs: Long? = null,
    val avgSegment2550TimeMs: Long? = null,
    val avgSegment5075TimeMs: Long? = null,
    val avgSegment75100TimeMs: Long? = null
)

/**
 * Агрегированные видео-метрики для курса.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
data class CourseVideoMetrics(
    val courseId: Long,
    /** Статистика по каждому модулю с видео/аудио. */
    val modules: List<VideoModuleStats> = emptyList(),
    /** Общее количество модулей с видео/аудио. */
    val totalVideoModules: Int = 0,
    /** Общее количество пользователей, которые просматривали видео. */
    val totalVideoViewers: Long = 0
)
