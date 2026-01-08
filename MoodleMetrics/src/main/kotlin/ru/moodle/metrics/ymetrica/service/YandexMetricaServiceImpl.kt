package ru.moodle.metrics.ymetrica.service

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpEntity
import org.springframework.http.HttpHeaders
import org.springframework.http.HttpMethod
import org.springframework.stereotype.Service
import org.springframework.web.client.RestTemplate
import ru.moodle.metrics.MoodleService
import ru.moodle.metrics.ymetrica.vo.BacktrackedModule
import ru.moodle.metrics.ymetrica.vo.CourseEventDto
import ru.moodle.metrics.ymetrica.vo.CoursePathSummary
import ru.moodle.metrics.ymetrica.vo.CourseTime
import ru.moodle.metrics.ymetrica.vo.CourseVideoMetrics
import ru.moodle.metrics.ymetrica.vo.MetricaTableResponse
import ru.moodle.metrics.ymetrica.vo.ModuleProgress
import ru.moodle.metrics.ymetrica.vo.ModuleTime
import ru.moodle.metrics.ymetrica.vo.ParsedEventKey
import ru.moodle.metrics.ymetrica.vo.StudentPath
import ru.moodle.metrics.ymetrica.vo.StudentStep
import ru.moodle.metrics.ymetrica.vo.VideoModuleStats

@Service
class YandexMetricaServiceImpl(
    @Value("\${metrica.counter-id}") private val counterId: Long,
    @Value("\${metrica.oauth-token}") private val oauthToken: String,
    private val restTemplate: RestTemplate,
    private val moodleService: MoodleService,
) : YandexMetricaService {

    private val mapper = jacksonObjectMapper()

    override fun getModuleProgress(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): List<ModuleProgress> {
        val enrolledUsersList = moodleService.getEnrolledUsers(courseId)
        val enrolledUserIds: Set<Long> = enrolledUsersList.map { it.id }.toSet()
        val enrolledCount = enrolledUserIds.size.toLong()

        // activityType = view  -> открытие модуля
        // activityType = complete (добавишь в JS) -> завершение модуля
        val openedRaw = getUsersByModuleRaw(
            courseId = courseId,
            activityType = "view",
            dateFrom = dateFrom,
            dateTo = dateTo
        )

        val backMovesByModule = getBackMovesByModule(
            courseId = courseId,
            dateFrom = dateFrom,
            dateTo = dateTo
        )

        val completedRaw: Map<String, Set<Long>> =
            moodleService.getActivityCompletionByCourse(courseId)
                .entries
                .associate { (cmId, userIds) -> cmId.toString() to userIds }

        val enrolledUsers: Long = moodleService.getEnrolledUsers(courseId).size.toLong()
        val moduleIds = (openedRaw.keys + completedRaw.keys).toSet()
        val modules = moodleService.getCourseContents(courseId)
            .flatMap { it.modules }
            .associateBy { it.id }

        fun calculatePercent(count: Long) = if (enrolledCount > 0) count.toDouble() * 100.0 / enrolledCount else 0.0

        return moduleIds
            .map { moduleId ->
                val openedUsersSet = openedRaw[moduleId].orEmpty()
                val completedUsersSet = completedRaw[moduleId].orEmpty()
                val openedUsers = openedUsersSet.intersect(enrolledUserIds).size.toLong()
                val completedUsers = completedUsersSet.intersect(enrolledUserIds).size.toLong()
                val module = modules[moduleId.toLong()]

                ModuleProgress(
                    moduleId = moduleId.toString(),
                    moduleName = module?.name,
                    openedUsers = openedUsers,
                    enrolledUsers = enrolledUsers,
                    openedPercent = calculatePercent(openedUsers),
                    completedUsers = completedUsers,
                    completedPercent = calculatePercent(completedUsers),
                    backMoves = backMovesByModule[moduleId] ?: 0L
                )
            }
            .sortedBy { it.moduleId.toLongOrNull() ?: Long.MAX_VALUE }
    }

    private fun getBackMovesByModule(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): Map<String, Long> {
        val stepEvents = getCourseEvents(courseId, dateFrom, dateTo)
            .filter { it.parsed.step != null && it.parsed.moduleId != null && it.parsed.userId != null }

        if (stepEvents.isEmpty()) return emptyMap()

        val backMoves = mutableMapOf<String, Long>()
        stepEvents.groupBy { it.parsed.userId }.values.forEach { userEvents ->
            val visited = mutableSetOf<String>()
            userEvents.sortedBy { it.parsed.step }.forEach { event ->
                val moduleId = event.parsed.moduleId!!
                if (visited.contains(moduleId)) {
                    backMoves[moduleId] = (backMoves[moduleId] ?: 0L) + 1L
                }
                visited.add(moduleId)
            }
        }
        return backMoves
    }

    override fun getCourseEvents(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): List<CourseEventDto> {
        val table = fetchMetricaData(dateFrom, dateTo) ?: return emptyList()

        return table.data.mapNotNull { row ->
            val dim1 = row.dimensions.getOrNull(0)?.name
            val dim2 = row.dimensions.getOrNull(1)?.name
            if (dim1 != "eventKey" || dim2.isNullOrBlank()) return@mapNotNull null

            val parsed = parseEventKey(dim2)
            if (parsed.courseId != courseId) return@mapNotNull null

            CourseEventDto(
                eventKey = dim2,
                users = row.metrics.firstOrNull()?.toLong() ?: 0L,
                parsed = parsed
            )
        }
    }

    private fun fetchMetricaData(dateFrom: String, dateTo: String): MetricaTableResponse? {
        val url = "https://api-metrika.yandex.net/stat/v1/data" +
                "?ids=$counterId" +
                "&metrics=ym:s:users" +
                "&dimensions=ym:s:paramsLevel1,ym:s:paramsLevel2" +
                "&date1=$dateFrom" +
                "&date2=$dateTo" +
                "&limit=10000"

        val headers = HttpHeaders().apply { set("Authorization", "OAuth $oauthToken") }
        val response = restTemplate.exchange(
            url, HttpMethod.GET, HttpEntity<Void>(headers), String::class.java
        )

        return response.body?.let { mapper.readValue<MetricaTableResponse>(it) }
    }

    override fun getCourseTimeMetrics(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CourseTime {
        val events = getCourseEvents(courseId, dateFrom, dateTo)

        fun filterByEventType(type: String) = events.filter { it.parsed.eventType == type }
        fun calculateAvgTime(sessions: List<CourseEventDto>): Long? {
            val totalTime = sessions.sumOf { it.parsed.durationMs ?: 0L }
            val totalUsers = sessions.sumOf { it.users }
            return if (totalUsers > 0) totalTime / totalUsers else null
        }

        val courseSessions = filterByEventType("course_session")
        val totalCourseTimeMs = courseSessions.sumOf { it.parsed.durationMs ?: 0L }

        val totalCourseUsers = courseSessions.sumOf { it.users }
        val avgCourseTimePerUserMs = if (totalCourseUsers > 0) totalCourseTimeMs / totalCourseUsers else null

        val moduleTimeMap = filterByEventType("module_session")
            .filter { it.parsed.moduleId != null }
            .groupBy { it.parsed.moduleId!! }
            .mapValues { (moduleId, rows) ->
                val avg = calculateAvgTime(rows) ?: 0L
                ModuleTime(moduleId = moduleId, avgTimeMs = avg)
            }

        val firstClicks = filterByEventType("first_activity_click")
        val avgFirstInteractionDelayMs = calculateAvgTime(firstClicks)

        return CourseTime(
            courseId = courseId,
            totalCourseTimeMs = totalCourseTimeMs,
            avgCourseTimePerUserMs = avgCourseTimePerUserMs,
            modules = moduleTimeMap.values.toList(),
            avgFirstInteractionDelayMs = avgFirstInteractionDelayMs
        )
    }


    /**
     * Возвращает Map<moduleId, usersCount> для заданного courseId и activityType.
     *
     * JS пишет:
     *   eventKey = "courseId=8;moduleId=32;activityType=view"
     *   или      "courseId=8;moduleId=32;activityType=attempt"
     */
    private fun getUsersByModuleRaw(
        courseId: Long,
        activityType: String,
        dateFrom: String,
        dateTo: String
    ): Map<String, Set<Long>> {
        val table = fetchMetricaData(dateFrom, dateTo) ?: return emptyMap()
        val result = mutableMapOf<String, MutableSet<Long>>()

        table.data.forEach { row ->
            val dim1 = row.dimensions.getOrNull(0)?.name
            val dim2 = row.dimensions.getOrNull(1)?.name
            if (dim1 != "eventKey" || dim2.isNullOrBlank()) return@forEach

            val parsed = parseEventKey(dim2)
            if (parsed.courseId != courseId || parsed.activityType != activityType) return@forEach

            val moduleId = parsed.moduleId ?: return@forEach
            val userId = parsed.userId ?: return@forEach

            result.getOrPut(moduleId) { mutableSetOf() }.add(userId)
        }

        return result
    }

    /**
     * Разбор eventKey="courseId=8;moduleId=32;activityType=view;eventType=section_view;sectionId=1"
     * или "courseId=8;moduleId=32;mediaId=123;mediaType=video;eventType=video_watch;watchPercent=50"
     */
    private fun parseEventKey(value: String): ParsedEventKey = ParsedEventKey.parse(value)

    override fun getCoursePathSummary(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CoursePathSummary {
        val events = getCourseEvents(courseId, dateFrom, dateTo)

        val stepEvents = events.filter { it.parsed.step != null && it.parsed.moduleId != null }

        if (stepEvents.isEmpty()) {
            return CoursePathSummary(courseId)
        }

        // Группируем по userId (если его нет, считаем всех в одной группе)
        val eventsByUser: Map<Long?, List<CourseEventDto>> =
            stepEvents.groupBy { it.parsed.userId }

        val studentPaths = mutableListOf<StudentPath>()

        eventsByUser.forEach { (userId, userEvents) ->
            val stepsForUser = userEvents
                .sortedBy { it.parsed.step }
                .map { event ->
                    val p = event.parsed
                    val movedBack = p.prevModuleId != null && p.prevModuleId != p.moduleId
                    StudentStep(
                        step = p.step!!,
                        moduleId = p.moduleId!!,
                        activityType = p.activityType,
                        stepDurationMs = p.stepDurationMs,
                        movedBack = movedBack
                    )
                }

            if (stepsForUser.isNotEmpty()) {
                studentPaths += StudentPath(
                    courseId = courseId,
                    userId = userId?.toString(),
                    steps = stepsForUser
                )
            }
        }

        val studentsCount = studentPaths.size
        if (studentsCount == 0) {
            return CoursePathSummary(courseId)
        }

        val allSteps = studentPaths.flatMap { it.steps }
        val totalSteps = allSteps.size.toLong()
        val avgStepsPerStudent = totalSteps.toDouble() / studentsCount

        val durations = allSteps.mapNotNull { it.stepDurationMs }
        val totalDuration = durations.sum()
        val avgStepDurationMs = if (durations.isNotEmpty()) totalDuration / durations.size else null

        val totalBackMoves = allSteps.count { it.movedBack }.toLong()
        val avgBackMovesPerStudent = totalBackMoves.toDouble() / studentsCount

        val backtrackedModules = allSteps
            .filter { it.movedBack }
            .groupBy { it.moduleId }
            .map { (moduleId, list) ->
                BacktrackedModule(
                    moduleId = moduleId,
                    backMovesCount = list.size.toLong()
                )
            }
            .sortedByDescending { it.backMovesCount }

        return CoursePathSummary(
            courseId = courseId,
            studentsCount = studentsCount,
            avgStepsPerStudent = avgStepsPerStudent,
            avgStepDurationMs = avgStepDurationMs,
            totalBackMoves = totalBackMoves,
            avgBackMovesPerStudent = avgBackMovesPerStudent,
            topBacktrackedModules = backtrackedModules
        )
    }

    override fun getCourseVideoMetrics(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CourseVideoMetrics {
        val events = getCourseEvents(courseId, dateFrom, dateTo)

        // Фильтруем только видео-события
        val videoEvents = events.filter {
            val eventType = it.parsed.eventType
            eventType != null && eventType.startsWith("video_")
        }

        if (videoEvents.isEmpty()) {
            return CourseVideoMetrics(courseId)
        }

        val courseContent = moodleService.getCourseContents(courseId)
        val modules = courseContent
            .flatMap { it.modules }
            .associateBy { it.id }

        val isValidModuleId: (String?) -> Boolean = { it?.toLongOrNull() != null }
        val eventsByModuleAndMedia = videoEvents
            .filter { isValidModuleId(it.parsed.moduleId) }
            .groupBy { Pair(it.parsed.moduleId!!, it.parsed.mediaId ?: "") }

        val moduleStats = mutableListOf<VideoModuleStats>()

        eventsByModuleAndMedia.forEach { (moduleMediaPair, moduleEvents) ->
            val moduleId = moduleMediaPair.first
            val mediaId = moduleMediaPair.second

            val uniqueUsers = moduleEvents
                .mapNotNull { it.parsed.userId }
                .toSet()

            // События video_watch с watchPercent
            val watchEvents = moduleEvents.filter {
                it.parsed.eventType == "video_watch" && it.parsed.watchPercent != null
            }

            // События video_stats с финальной статистикой
            val statsEvents = moduleEvents.filter {
                it.parsed.eventType == "video_stats"
            }

            // События video_pause
            val pauseEvents = moduleEvents.filter {
                it.parsed.eventType == "video_pause"
            }

            // События video_seek
            val seekEvents = moduleEvents.filter {
                it.parsed.eventType == "video_seek"
            }

            // Подсчитываем пользователей по milestone'ам
            fun countUsersByPercent(percent: Int): Long {
                val users = if (watchEvents.isNotEmpty()) {
                    watchEvents.filter { it.parsed.watchPercent != null && it.parsed.watchPercent!! >= percent }
                        .mapNotNull { it.parsed.userId }.toSet()
                } else if (percent == 100) {
                    statsEvents.filter { it.parsed.finalPercent != null && it.parsed.finalPercent!! >= 100 }
                        .mapNotNull { it.parsed.userId }.toSet()
                } else {
                    emptySet()
                }
                return users.size.toLong()
            }

            val startedUsers = if (watchEvents.isNotEmpty()) {
                countUsersByPercent(0)
            } else {
                statsEvents.mapNotNull { it.parsed.userId }.toSet().size.toLong()
            }
            val watched25Users = countUsersByPercent(25)
            val watched50Users = countUsersByPercent(50)
            val watched75Users = countUsersByPercent(75)
            val watched100Users = countUsersByPercent(100)

            fun <T : Number> averageFromStats(extractor: (ParsedEventKey) -> T?): Double? {
                val values = statsEvents.mapNotNull { extractor(it.parsed) }
                return if (values.isNotEmpty()) values.map { it.toDouble() }.average() else null
            }

            fun <T : Number> averageFromStatsAsLong(extractor: (ParsedEventKey) -> T?): Long? {
                return averageFromStats(extractor)?.toLong()
            }

            fun fallbackAverage(statsValues: List<Double>, eventCount: Int): Double? {
                return if (statsValues.isNotEmpty()) {
                    statsValues.average()
                } else if (eventCount > 0 && uniqueUsers.isNotEmpty()) {
                    eventCount.toDouble() / uniqueUsers.size
                } else null
            }

            val avgWatchPercent = averageFromStats { it.finalPercent }
                ?: watchEvents.mapNotNull { it.parsed.watchPercent }.takeIf { it.isNotEmpty() }?.average()

            val avgPauseCount = fallbackAverage(
                statsEvents.mapNotNull { it.parsed.pauseCount?.toDouble() },
                pauseEvents.size
            )

            val avgSeekCount = fallbackAverage(
                statsEvents.mapNotNull { it.parsed.seekCount?.toDouble() },
                seekEvents.size
            )

            val avgSeekBackwardCount = fallbackAverage(
                statsEvents.mapNotNull { it.parsed.seekBackward?.toDouble() },
                seekEvents.count { it.parsed.seekBackward == 1 }
            )

            val avgWatchTimeMs = averageFromStatsAsLong { it.totalWatchTime }
            val avgSegment025TimeMs = averageFromStatsAsLong { it.segment025Time }
            val avgSegment2550TimeMs = averageFromStatsAsLong { it.segment2550Time }
            val avgSegment5075TimeMs = averageFromStatsAsLong { it.segment5075Time }
            val avgSegment75100TimeMs = averageFromStatsAsLong { it.segment75100Time }

            val module = moduleId.toLongOrNull()?.let { modules[it] }
            moduleStats.add(
                VideoModuleStats(
                    moduleId = moduleId,
                    moduleName = module?.name,
                    mediaId = mediaId.takeIf { it.isNotEmpty() },
                    mediaType = moduleEvents.firstOrNull()?.parsed?.mediaType,
                    startedUsers = if (startedUsers > 0) startedUsers else uniqueUsers.size.toLong(),
                    watched25Users = watched25Users,
                    watched50Users = watched50Users,
                    watched75Users = watched75Users,
                    watched100Users = watched100Users,
                    avgWatchPercent = avgWatchPercent,
                    avgPauseCount = avgPauseCount,
                    avgSeekCount = avgSeekCount,
                    avgSeekBackwardCount = avgSeekBackwardCount,
                    avgWatchTimeMs = avgWatchTimeMs,
                    avgSegment025TimeMs = avgSegment025TimeMs,
                    avgSegment2550TimeMs = avgSegment2550TimeMs,
                    avgSegment5075TimeMs = avgSegment5075TimeMs,
                    avgSegment75100TimeMs = avgSegment75100TimeMs
                )
            )
        }

        val validModuleStats = moduleStats.filter { it.moduleId.toLongOrNull() != null }
        val validVideoEvents = videoEvents.filter { isValidModuleId(it.parsed.moduleId) }
        val totalVideoViewers = validVideoEvents.mapNotNull { it.parsed.userId }.toSet().size.toLong()

        return CourseVideoMetrics(
            courseId = courseId,
            modules = validModuleStats.sortedBy { it.moduleId.toLongOrNull() ?: Long.MAX_VALUE },
            totalVideoModules = validModuleStats.size,
            totalVideoViewers = totalVideoViewers
        )
    }

}
