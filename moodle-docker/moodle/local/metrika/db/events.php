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
];