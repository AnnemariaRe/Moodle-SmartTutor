<?php
$observers = [
    [
        'eventname' => '\core\event\course_module_viewed',
        'callback' => '\local_metrika\observer::course_module_viewed',
    ],
    [
        'eventname' => '\mod_quiz\event\attempt_submitted',
        'callback' => '\local_metrika\observer::quiz_attempt_submitted'
    ],
    [
        'eventname' => '\mod_assign\event\submission_created',
        'callback' => '\local_metrika\observer::assign_submission_created'
    ],
    [
        'eventname' => '\mod_assign\event\submission_graded',
        'callback' => '\local_metrika\observer::assign_submission_graded'
    ],
    [
        'eventname' => '\mod_lesson\event\lesson_started',
        'callback'  => '\local_metrika\observer::lesson_started',
    ],
    [
        'eventname' => '\mod_lesson\event\content_page_viewed',
        'callback'  => '\local_metrika\observer::lesson_page_viewed',
    ],
    [
        'eventname' => '\mod_lesson\event\question_viewed',
        'callback'  => '\local_metrika\observer::lesson_page_viewed',
    ],
    [
        'eventname' => '\mod_lesson\event\question_answered',
        'callback'  => '\local_metrika\observer::lesson_question_answered',
    ],
    [
        'eventname' => '\mod_lesson\event\lesson_ended',
        'callback'  => '\local_metrika\observer::lesson_ended',
    ],
];