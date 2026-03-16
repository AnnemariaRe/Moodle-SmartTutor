<?php
namespace local_metrika;

defined('MOODLE_INTERNAL') || die();

class observer {
    
    private static function is_admin($userid): bool {
        return is_siteadmin($userid);
    }

    public static function course_module_viewed($event) {
        if (self::is_admin($event->userid)) return;
        global $CFG, $DB;
        
        $data = [
            'event_id' => uniqid('', true),
            'ts' => time(),
            'student_id' => $event->userid,
            'course_id' => $event->courseid,
            'event_type' => 'course_module_viewed',
            'object_type' => 'course_module',
            'object_id' => $event->objectid,
            'cmid' => $event->contextinstanceid,
            'payload' => [
                'module_name' => $event->other['modname'] ?? null,
                'time_spent_sec' => 0
            ]
        ];
        
        self::send_to_tracking($data);
    }

    public static function quiz_attempt_submitted($event) {
        if (self::is_admin($event->userid)) return;
        global $DB;

        $attempt = $DB->get_record('quiz_attempts', ['id' => $event->objectid]);
        $quiz    = $attempt ? $DB->get_record('quiz', ['id' => $attempt->quiz]) : null;

        $data = [
            'event_id' => uniqid('', true),
            'ts' => time(),
            'student_id' => $event->userid,
            'course_id' => $event->courseid,
            'event_type' => 'quiz_attempt_submitted',
            'object_type' => 'quiz_attempt',
            'object_id' => $event->objectid,
            'cmid' => $event->contextinstanceid,
            'payload' => [
                'quiz_id' => $event->other['quizid'] ?? null,
                'score' => $attempt ? (float) $attempt->sumgrades : 0,
                'max_score' => $quiz ? (float) $quiz->sumgrades : 1,
                'attempt_no' => $attempt ? (int) $attempt->attempt : 1,
            ]
        ];
        self::send_to_tracking($data);
    }
    
    public static function assign_submission_created($event) {
        if (self::is_admin($event->userid)) return;
        $data = [
            'event_id' => uniqid('', true),
            'ts' => time(),
            'student_id' => $event->userid,
            'course_id' => $event->courseid,
            'event_type' => 'assign_submission_created',
            'object_type' => 'assign_submission',
            'object_id' => $event->objectid,
            'cmid' => $event->contextinstanceid,
            'payload' => (object)[]
        ];
        self::send_to_tracking($data);
    }

    public static function assign_submission_graded($event) {
        if (self::is_admin($event->userid)) return;
        global $DB;

        $grade = $DB->get_record('assign_grades', ['id' => $event->objectid]);

        $data = [
            'event_id' => uniqid('', true),
            'ts' => time(),
            'student_id' => $event->userid,
            'course_id' => $event->courseid,
            'event_type' => 'assign_submission_graded',
            'object_type' => 'assign_submission',
            'object_id' => $event->objectid,
            'cmid' => $event->contextinstanceid,
            'payload' => [
                'grade' => $grade ? (float) $grade->grade : null,
            ]
        ];
        self::send_to_tracking($data);
    }
    
    public static function lesson_started($event) {
        if (self::is_admin($event->userid)) return;
        $data = [
            'event_id'    => uniqid('', true),
            'ts'          => time(),
            'student_id'  => $event->userid,
            'course_id'   => $event->courseid,
            'event_type'  => 'lesson_started',
            'object_type' => 'lesson',
            'object_id'   => $event->objectid,
            'cmid'        => $event->contextinstanceid,
            'payload'     => (object)[],
        ];
        self::send_to_tracking($data);
    }

    public static function lesson_page_viewed($event) {
        if (self::is_admin($event->userid)) return;
        $data = [
            'event_id'    => uniqid('', true),
            'ts'          => time(),
            'student_id'  => $event->userid,
            'course_id'   => $event->courseid,
            'event_type'  => 'lesson_page_view',
            'object_type' => 'lesson_page',
            'object_id'   => $event->objectid,
            'cmid'        => $event->contextinstanceid,
            'payload'     => [
                'page_id' => $event->objectid,
            ],
        ];
        self::send_to_tracking($data);
    }

    public static function lesson_question_answered($event) {
        $data = [
            'event_id'    => uniqid('', true),
            'ts'          => time(),
            'student_id'  => $event->userid,
            'course_id'   => $event->courseid,
            'event_type'  => 'lesson_answer_submitted',
            'object_type' => 'lesson_page',
            'object_id'   => $event->objectid,
            'cmid'        => $event->contextinstanceid,
            'payload'     => [
                'page_id'    => $event->objectid,
                'is_correct' => !empty($event->other['correct']),
            ],
        ];
        self::send_to_tracking($data);
    }

    public static function lesson_ended($event) {
        global $DB;

        $lessonid = $event->objectid;
        $userid   = $event->userid;

        // Final grade record (grade = percentage 0-100).
        $grade_record = $DB->get_record('lesson_grades', [
            'lessonid' => $lessonid,
            'userid'   => $userid,
        ]);

        // All page attempts for this user in this lesson.
        $attempts = $DB->get_records('lesson_attempts', [
            'lessonid' => $lessonid,
            'userid'   => $userid,
        ]);

        $num_questions = count($attempts);
        $num_correct   = 0;
        $retries       = [];
        foreach ($attempts as $a) {
            if (!empty($a->correct)) {
                $num_correct++;
            }
            $retries[$a->retry] = true;
        }

        $score_percent = $grade_record ? (float)$grade_record->grade : 0;
        $num_attempts  = count($retries) ?: 1;

        $data = [
            'event_id'    => uniqid('', true),
            'ts'          => time(),
            'student_id'  => $userid,
            'course_id'   => $event->courseid,
            'event_type'  => 'lesson_completed',
            'object_type' => 'lesson',
            'object_id'   => $lessonid,
            'cmid'        => $event->contextinstanceid,
            'payload'     => [
                'num_questions' => $num_questions,
                'num_correct'   => $num_correct,
                'score_percent' => $score_percent,
                'num_attempts'  => $num_attempts,
            ],
        ];
        self::send_to_tracking($data);
    }

    private static function send_to_tracking($data) {
        $url = 'http://tracking-service:8001/v1/events';
        $options = [
            'http' => [
                'method' => 'POST',
                'header' => 'Content-Type: application/json',
                'timeout' => 0.3,
                'ignore_errors' => true,
                'content' => json_encode($data)
            ]
        ];
        $context = stream_context_create($options);
        @file_get_contents($url, false, $context);
    }
}