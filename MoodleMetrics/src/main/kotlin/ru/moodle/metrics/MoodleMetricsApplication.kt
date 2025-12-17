package ru.moodle.metrics

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class MoodleMetricsApplication

fun main(args: Array<String>) {
    runApplication<MoodleMetricsApplication>(*args)
}