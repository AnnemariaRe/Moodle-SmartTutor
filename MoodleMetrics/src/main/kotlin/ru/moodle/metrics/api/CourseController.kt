package ru.moodle.metrics.api

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RestController
import ru.moodle.metrics.CourseWithContents
import ru.moodle.metrics.MoodleServiceImpl

@RestController
class CourseController(
    private val moodleServiceImpl: MoodleServiceImpl
) {

    @GetMapping("/api/courses/{id}")
    fun getCourse(@PathVariable id: Long): CourseWithContents {
        val course = moodleServiceImpl.getCourseInfo(id).first()
        val sections = moodleServiceImpl.getCourseContents(id)
        return CourseWithContents(course, sections)
    }
}