package ru.moodle.metrics

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import org.springframework.stereotype.Repository

@Repository
class MoodleDao(
    private val jdbc: NamedParameterJdbcTemplate
) {
    /**
     * Возвращает множества пользователей, завершивших каждую активность курса
     * по данным mdl_course_modules_completion (completionstate = 1).
     *
     * Map<courseModuleId (cm.id), Set<userId>>
     */
    fun getActivityCompletionByCourse(courseId: Long): Map<Long, Set<Long>> {
        val sql = """
        SELECT cmc.coursemoduleid AS cmid,
               cmc.userid        AS userid
        FROM m_course_modules_completion cmc
        JOIN m_course_modules cm
          ON cm.id = cmc.coursemoduleid
        WHERE cm.course = :courseId
          AND cmc.completionstate = 1
    """.trimIndent()

        val params = mapOf("courseId" to courseId)

        val rows: List<Pair<Long, Long>> = jdbc.query(sql, params) { rs, _ ->
            val cmid = rs.getLong("cmid")
            val userId = rs.getLong("userid")
            cmid to userId
        }

        return rows
            .groupBy({ it.first }, { it.second })
            .mapValues { (_, userIds) -> userIds.toSet() }
    }

}
