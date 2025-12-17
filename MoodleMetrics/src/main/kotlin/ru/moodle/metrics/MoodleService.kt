package ru.moodle.metrics

/**
 * @author arepenko
 * @since %CURRENT_VERSION%
 */
interface MoodleService {

    fun getCourseInfo(courseId: Long): List<MoodleCourse>

    fun getCourseContents(courseId: Long): List<MoodleSection>

    /** Возвращает список пользователей, записанных на курс. */
    fun getEnrolledUsers(courseId: Long): List<MoodleUser>

    fun getCourseCompletionStatuses(courseId: Long): List<CourseCompletionStatus>

    fun getActivityCompletionByCourse(courseId: Long): Map<Long, Set<Long>>
}