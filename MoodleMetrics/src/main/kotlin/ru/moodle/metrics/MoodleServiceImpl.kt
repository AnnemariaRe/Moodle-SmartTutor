package ru.moodle.metrics

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import org.springframework.beans.factory.annotation.Value
import org.springframework.http.HttpEntity
import org.springframework.http.HttpHeaders
import org.springframework.http.MediaType
import org.springframework.stereotype.Service
import org.springframework.util.LinkedMultiValueMap
import org.springframework.web.client.RestTemplate

@Service
class MoodleServiceImpl(
    private val restTemplate: RestTemplate,
    private val moodleDao: MoodleDao,
    @Value("\${moodle.base-url}") private val baseUrl: String,
    @Value("\${moodle.token}") private val token: String
) : MoodleService {

    override fun getCourseInfo(courseId: Long): List<MoodleCourse> {
        val url = "$baseUrl/webservice/rest/server.php"
        val params = LinkedMultiValueMap<String, String>().apply {
            add("wstoken", token)
            add("wsfunction", "core_course_get_courses")
            add("moodlewsrestformat", "json")
            add("options[ids][0]", courseId.toString())
        }
        val headers = HttpHeaders().apply {
            contentType = MediaType.APPLICATION_FORM_URLENCODED
            accept = listOf(MediaType.APPLICATION_JSON)
        }

        val entity = HttpEntity(params, headers)

        val raw = restTemplate.postForObject(url, entity, String::class.java)
        println("Moodle response: $raw")

        val mapper = jacksonObjectMapper()
        val courses: Array<MoodleCourse> = mapper.readValue(raw)
        return courses.toList()
    }

    override fun getCourseContents(courseId: Long): List<MoodleSection> {
        val url = "$baseUrl/webservice/rest/server.php"
        val params = LinkedMultiValueMap<String, String>().apply {
            add("wstoken", token)
            add("wsfunction", "core_course_get_contents")
            add("moodlewsrestformat", "json")
            add("courseid", courseId.toString())
        }
        val headers = HttpHeaders().apply {
            contentType = MediaType.APPLICATION_FORM_URLENCODED
            accept = listOf(MediaType.APPLICATION_JSON)
        }

        val entity = HttpEntity(params, headers)

        val raw = restTemplate.postForObject(url, entity, String::class.java)
        println("Moodle response: $raw")

        val mapper = jacksonObjectMapper()
        val courses: Array<MoodleSection> = mapper.readValue(raw)
        return courses.toList()
    }

    override fun getEnrolledUsers(courseId: Long): List<MoodleUser> {
        val url = StringBuilder()
            .append(baseUrl)
            .append("/webservice/rest/server.php")
            .append("?wstoken=").append(token)
            .append("&wsfunction=core_enrol_get_enrolled_users")
            .append("&moodlewsrestformat=json")
            .append("&courseid=").append(courseId)
            .toString()

        val response = restTemplate.getForEntity(url, String::class.java)
        val body = response.body ?: return emptyList()

        // Ожидается массив пользователей
        val nodes: List<Map<String, Any?>> = mapper.readValue(body)

        return nodes.mapNotNull { node ->
            val id = (node["id"] as? Number)?.toLong() ?: return@mapNotNull null
            val userName = node["fullname"] as? String
            MoodleUser(id = id, userName = userName)
        }
    }

    override fun getCourseCompletionStatuses(courseId: Long): List<CourseCompletionStatus> {
        val users = getEnrolledUsers(courseId)

        return users.map { user ->
            val url = "$baseUrl/webservice/rest/server.php"

            val params = mapOf(
                "wstoken" to token,
                "wsfunction" to "core_completion_get_course_completion_status",
                "moodlewsrestformat" to "json",
                "courseid" to courseId.toString(),
                "userid" to user.id.toString()
            )

            val response = restTemplate.postForEntity(url, LinkedMultiValueMap<String, String>().apply {
                params.forEach { (k, v) -> add(k, v) }
            }, String::class.java)

            val node = mapper.readTree(response.body)

            val completed = node["completionstatus"]?.get("completed")?.asBoolean(false) == true

            CourseCompletionStatus(
                userId = user.id,
                isCompleted = completed
            )
        }
    }

    override fun getActivityCompletionByCourse(courseId: Long): Map<Long, Set<Long>> {
        return moodleDao.getActivityCompletionByCourse(courseId)
    }

    private companion object {
        private val mapper = jacksonObjectMapper()
    }
}
