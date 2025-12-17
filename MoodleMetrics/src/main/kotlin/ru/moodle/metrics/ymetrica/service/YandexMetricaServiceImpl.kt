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
import ru.moodle.metrics.ymetrica.vo.MetricaTableResponse
import ru.moodle.metrics.ymetrica.vo.ModuleProgress
import ru.moodle.metrics.ymetrica.vo.ModuleTime
import ru.moodle.metrics.ymetrica.vo.ParsedEventKey
import ru.moodle.metrics.ymetrica.vo.StudentPath
import ru.moodle.metrics.ymetrica.vo.StudentStep

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

        val completedRaw = moodleService.getActivityCompletionByCourse(courseId)

        val enrolledUsers: Long = moodleService.getEnrolledUsers(courseId).size.toLong()
        val moduleIds = (openedRaw.keys + completedRaw.keys).toSet()

        val courseContent = moodleService.getCourseContents(courseId)
        val modules = courseContent
            .flatMap { it.modules }
            .associateBy { it.id }

        return moduleIds
            .map { moduleId ->
                val openedUsersSet = openedRaw[moduleId].orEmpty()
                val completedUsersSet = completedRaw[moduleId].orEmpty()

                // считаем только тех, кто реально записан на курс
                val openedUsers = openedUsersSet.intersect(enrolledUserIds).size.toLong()
                val completedUsers = completedUsersSet.intersect(enrolledUserIds).size.toLong()
                val backMoves = backMovesByModule[moduleId] ?: 0L
                val module = modules[moduleId]
                val openedPercent = if (enrolledCount > 0) openedUsers.toDouble() * 100.0 / enrolledCount else 0.0
                val completedPercent = getCourseCompletionPercent(courseId)

                ModuleProgress(
                    moduleId = moduleId.toString(),
                    moduleName = module?.name,
                    openedUsers = openedUsers,
                    enrolledUsers = enrolledUsers,
                    openedPercent = openedPercent,
                    completedUsers = completedUsers,
                    completedPercent = completedPercent,
                    backMoves = backMoves
                )
            }
            .sortedBy { it.moduleId.toLongOrNull() ?: Long.MAX_VALUE }
    }

    fun getCourseCompletionPercent(courseId: Long): Double {
        val enrolled = moodleService.getEnrolledUsers(courseId)
        if (enrolled.isEmpty()) return 0.0

        val statuses = moodleService.getCourseCompletionStatuses(courseId)
        val completedCount = statuses.count { it.isCompleted }

        return completedCount.toDouble() * 100.0 / enrolled.size
    }

    private fun getBackMovesByModule(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): Map<String, Long> {

        val events = getCourseEvents(courseId, dateFrom, dateTo)

        // Берём только шаги пути с userId и moduleId
        val stepEvents = events.filter {
            val p = it.parsed
            p.step != null && p.moduleId != null && p.userId != null
        }

        if (stepEvents.isEmpty()) return emptyMap()

        // Группируем по пользователю и сортируем шаги
        val byUser = stepEvents.groupBy { it.parsed.userId }

        val backMoves = mutableMapOf<String, Long>()

        byUser.values.forEach { userEvents ->
            val sorted = userEvents.sortedBy { it.parsed.step }

            val visited = mutableSetOf<String>()
            sorted.forEach { e ->
                val p = e.parsed
                val mid = p.moduleId!!
                val movedBack = visited.contains(mid)   // модуль уже был ранее в пути
                if (movedBack) {
                    backMoves[mid] = (backMoves[mid] ?: 0L) + 1L
                }
                visited.add(mid)
            }
        }

        return backMoves
    }

    override fun getCourseEvents(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): List<CourseEventDto> {
        val url = StringBuilder("https://api-metrika.yandex.net/stat/v1/data")
            .append("?ids=$counterId")
            .append("&metrics=ym:s:users")
            .append("&dimensions=ym:s:paramsLevel1,ym:s:paramsLevel2")
            .append("&date1=$dateFrom")
            .append("&date2=$dateTo")
            .append("&limit=10000")
            .toString()

        val headers = HttpHeaders().apply {
            set("Authorization", "OAuth $oauthToken")
        }

        val entity = HttpEntity<Void>(headers)
        val response = restTemplate.exchange(
            url,
            HttpMethod.GET,
            entity,
            String::class.java
        )

        val body = response.body ?: return emptyList()
        val table: MetricaTableResponse = mapper.readValue(body)

        return table.data.mapNotNull { row ->
            val dim1 = row.dimensions.getOrNull(0)?.name
            val dim2 = row.dimensions.getOrNull(1)?.name

            if (dim1 != "eventKey" || dim2.isNullOrBlank()) return@mapNotNull null

            val parsed = parseEventKey(dim2)
            if (parsed.courseId != courseId) return@mapNotNull null

            val users = row.metrics.firstOrNull()?.toLong() ?: 0L
            CourseEventDto(
                eventKey = dim2,
                users = users,
                parsed = parsed
            )
        }
    }

    override fun getCourseTimeMetrics(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CourseTime {
        val events = getCourseEvents(courseId, dateFrom, dateTo)

        // 1. course_session: суммарное и среднее время в курсе
        val courseSessions = events.filter { it.parsed.eventType == "course_session" }

        val totalCourseTimeMs = courseSessions.sumOf { it.parsed.durationMs ?: 0L }

        // здесь users – это «кол-во уникальных посетителей с таким eventKey»
        val totalCourseUsers = courseSessions.sumOf { it.users }
        val avgCourseTimePerUserMs =
            if (totalCourseUsers > 0) totalCourseTimeMs / totalCourseUsers else null

        // 2. module_session: среднее время по каждому модулю
        val moduleSessions = events.filter {
            it.parsed.eventType == "module_session" && it.parsed.moduleId != null
        }

        val moduleTimeMap: Map<String, ModuleTime> =
            moduleSessions
                .groupBy { it.parsed.moduleId!! }
                .mapValues { (_, rows) ->
                    val totalDuration = rows.sumOf { it.parsed.durationMs ?: 0L }
                    val totalUsers = rows.sumOf { it.users }
                    val avg = if (totalUsers > 0) totalDuration / totalUsers else 0L
                    ModuleTime(
                        moduleId = rows.first().parsed.moduleId!!,
                        avgTimeMs = avg
                    )
                }

        // 3. first_activity_click: средняя задержка до первого клика
        val firstClicks = events.filter { it.parsed.eventType == "first_activity_click" }

        val totalDelay = firstClicks.sumOf { it.parsed.delayMs ?: 0L }
        val totalDelayUsers = firstClicks.sumOf { it.users }
        val avgFirstInteractionDelayMs =
            if (totalDelayUsers > 0) totalDelay / totalDelayUsers else null

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

        val url = StringBuilder("https://api-metrika.yandex.net/stat/v1/data")
            .append("?ids=$counterId")
            .append("&metrics=ym:s:users")
            .append("&dimensions=ym:s:paramsLevel1,ym:s:paramsLevel2")
            .append("&date1=$dateFrom")
            .append("&date2=$dateTo")
            .append("&limit=10000")
            .toString()

        val headers = HttpHeaders().apply {
            set("Authorization", "OAuth $oauthToken")
        }

        val entity = HttpEntity<Void>(headers)
        val response = restTemplate.exchange(
            url,
            HttpMethod.GET,
            entity,
            String::class.java
        )

        val body = response.body ?: return emptyMap()
        val table: MetricaTableResponse = mapper.readValue(body)

        // moduleId -> set of userIds
        val result = mutableMapOf<String, MutableSet<Long>>()

        table.data.forEach { row ->
            val dim1 = row.dimensions.getOrNull(0)?.name
            val dim2 = row.dimensions.getOrNull(1)?.name

            if (dim1 != "eventKey" || dim2.isNullOrBlank()) return@forEach

            val parsed = parseEventKey(dim2)

            if (parsed.courseId != courseId || parsed.activityType != activityType) return@forEach

            val moduleId = parsed.moduleId ?: return@forEach
            val userId = parsed.userId ?: return@forEach

            result.computeIfAbsent(moduleId) { mutableSetOf() }.add(userId)
        }

        return result
    }

    /**
     * Разбор eventKey="courseId=8;moduleId=32;activityType=view;eventType=section_view;sectionId=1"
     */
    private fun parseEventKey(value: String): ParsedEventKey {
        val parts = value.split(';')
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

        for (p in parts) {
            val kv = p.split('=', limit = 2)
            if (kv.size != 2) continue
            val key = kv[0]
            val v = kv[1]
            when (key) {
                "courseId" -> courseId = v.toLongOrNull()
                "moduleId" -> moduleId = v
                "activityType" -> activityType = v
                "eventType" -> eventType = v
                "durationMs" -> durationMs = v.toLongOrNull()
                "delayMs" -> delayMs = v.toLongOrNull()
                "step" -> step = v.toIntOrNull()
                "prevModuleId" -> prevModuleId = v
                "stepDurationMs" -> stepDurationMs = v.toLongOrNull()
                "userId" -> userId = v.toLongOrNull()
            }
        }
        return ParsedEventKey(
            courseId,
            moduleId,
            activityType,
            eventType,
            durationMs,
            delayMs,
            step,
            prevModuleId,
            stepDurationMs,
            userId
        )
    }

    override fun getCoursePathSummary(
        courseId: Long,
        dateFrom: String,
        dateTo: String
    ): CoursePathSummary {
        val events = getCourseEvents(courseId, dateFrom, dateTo)

        // Берём только шаги пути
        val stepEvents = events
            .filter { it.parsed.step != null && it.parsed.moduleId != null }

        if (stepEvents.isEmpty()) {
            return CoursePathSummary(courseId)
        }

        // Группируем по userId (если его нет, считаем всех в одной группе)
        val eventsByUser: Map<Long?, List<CourseEventDto>> =
            stepEvents.groupBy { it.parsed.userId }

        val studentPaths = mutableListOf<StudentPath>()

        eventsByUser.forEach { (userId, userEvents) ->
            val stepsForUser = userEvents
                .sortedBy { it.parsed.step }   // по step
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

}
