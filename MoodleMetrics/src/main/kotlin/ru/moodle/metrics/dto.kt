package ru.moodle.metrics

import com.fasterxml.jackson.annotation.JsonIgnoreProperties

@JsonIgnoreProperties(ignoreUnknown = true)
data class MoodleCourse(
    val id: Long,
    val shortname: String?,
    val fullname: String?,
    val summary: String?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class MoodleModule(
    val id: Long,
    val name: String?,
    val modname: String?
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class MoodleSection(
    val id: Long,
    val name: String?,
    val summary: String?,
    val modules: List<MoodleModule> = emptyList()
)

data class CourseWithContents(
    val course: MoodleCourse,
    val sections: List<MoodleSection>
)

data class MoodleUser(
    val id: Long,
    val userName: String?
)

data class CourseCompletionStatus(
    val userId: Long,
    val isCompleted: Boolean
)