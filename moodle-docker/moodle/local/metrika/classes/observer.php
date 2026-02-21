<?php
namespace local_metrika;

defined('MOODLE_INTERNAL') || die();

class observer {
    
    public static function course_module_viewed($event) {
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