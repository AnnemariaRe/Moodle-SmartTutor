<?php
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');
@set_time_limit(300);

require_login();
require_sesskey();

$action   = required_param('action', PARAM_ALPHANUMEXT);
$courseid = required_param('courseid', PARAM_INT);
$userid   = required_param('userid', PARAM_INT);

$course  = get_course($courseid);
$context = context_course::instance($courseid);

require_login($course);
require_capability('block/personal_tasks:view', $context);

if ($userid !== (int)$USER->id) {
    throw new moodle_exception('invaliduserid');
}

$taskgen_url = rtrim(get_config('block_personal_tasks', 'taskgenerator_url'), '/');
if (!$taskgen_url) {
    $taskgen_url = 'http://personalized-tasks:8004';
}

error_log("[PT ajax] action={$action} userid={$userid} courseid={$courseid}");

header('Content-Type: application/json');

// ── Student actions ──────────────────────────────────────────────────────────

if ($action === 'generate') {
    $payload = json_encode([
        'student_id'           => $userid,
        'course_id'            => $courseid,
        'max_concepts'         => 2,
        'variants_per_concept' => 2,
        'mastery_threshold'    => 0.7,
    ]);

    $response = _pt_http_post($taskgen_url . '/v1/personalized-task', $payload);
    error_log("[PT ajax] generate response: " . ($response === false ? 'FALSE' : substr($response, 0, 300)));

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    $decoded = json_decode($response, true);
    if (isset($decoded['detail'])) {
        echo json_encode(['mastered' => true, 'message' => $decoded['detail']]);
        die;
    }

    echo $response;
    die;
}

if ($action === 'check') {
    $task_id = required_param('task_id', PARAM_INT);
    $raw     = required_param('answer', PARAM_RAW);
    $answer  = json_decode($raw, true);

    if (!is_array($answer)) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid answer format']);
        die;
    }

    $payload = json_encode([
        'task_id'    => $task_id,
        'student_id' => $userid,
        'answer'     => $answer,
    ]);

    $response = _pt_http_post($taskgen_url . '/v1/check-answer', $payload);

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    echo $response;
    die;
}

// ── Teacher / admin actions ───────────────────────────────────────────────────

require_capability('block/personal_tasks:managetasks', $context);

if ($action === 'generate_bank') {
    $instructions     = optional_param('teacher_instructions', '', PARAM_TEXT);
    $tasks_per_concept = optional_param('tasks_per_concept', 9, PARAM_INT);

    $payload = json_encode([
        'course_id'           => $courseid,
        'teacher_id'          => $userid,
        'teacher_instructions' => $instructions ?: null,
        'tasks_per_concept'   => max(1, min(30, $tasks_per_concept)),
        'difficulties'        => ['easy', 'medium', 'hard'],
    ]);

    $response = _pt_http_post($taskgen_url . '/v1/admin/generate-bank', $payload, 280);
    error_log("[PT ajax] generate_bank response: " . ($response === false ? 'FALSE' : substr($response, 0, 300)));

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    echo $response;
    die;
}

if ($action === 'list_bank') {
    $filter_status = optional_param('filter_status', '', PARAM_ALPHA);

    $url = $taskgen_url . '/v1/admin/bank?course_id=' . $courseid;
    if ($filter_status) {
        $url .= '&status=' . urlencode($filter_status);
    }

    $response = _pt_http_get($url);

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    echo $response;
    die;
}

if ($action === 'review_task') {
    $task_id      = required_param('task_id', PARAM_INT);
    $review_action = required_param('review_action', PARAM_ALPHA);
    $edited_raw   = optional_param('edited_spec', '', PARAM_RAW);
    $edited_spec  = $edited_raw ? json_decode($edited_raw, true) : null;

    $payload = json_encode(array_filter([
        'task_id'     => $task_id,
        'action'      => $review_action,
        'reviewed_by' => $userid,
        'edited_spec' => $edited_spec,
    ], function($v) { return $v !== null; }));

    $response = _pt_http_post($taskgen_url . '/v1/admin/review', $payload);

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    echo $response;
    die;
}

if ($action === 'review_bulk') {
    $task_ids_raw  = required_param('task_ids', PARAM_RAW);
    $review_action = required_param('review_action', PARAM_ALPHA);
    $task_ids      = json_decode($task_ids_raw, true);

    if (!is_array($task_ids) || empty($task_ids)) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid task_ids']);
        die;
    }

    $payload = json_encode([
        'task_ids'    => array_map('intval', $task_ids),
        'action'      => $review_action,
        'reviewed_by' => $userid,
    ]);

    $response = _pt_http_post($taskgen_url . '/v1/admin/review-bulk', $payload);

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    echo $response;
    die;
}

http_response_code(400);
echo json_encode(['error' => 'Unknown action']);

// ── HTTP helpers ──────────────────────────────────────────────────────────────

function _pt_http_post(string $url, string $body, int $timeout = 60) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $body,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json', 'Accept: application/json'],
        CURLOPT_TIMEOUT        => $timeout,
    ]);
    $response = curl_exec($ch);
    $errno    = curl_errno($ch);
    if ($errno) {
        error_log("[PT ajax] curl POST error {$errno}: " . curl_error($ch));
    }
    curl_close($ch);
    return $errno ? false : $response;
}

function _pt_http_get(string $url, int $timeout = 30) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ['Accept: application/json'],
        CURLOPT_TIMEOUT        => $timeout,
    ]);
    $response = curl_exec($ch);
    $errno    = curl_errno($ch);
    if ($errno) {
        error_log("[PT ajax] curl GET error {$errno}: " . curl_error($ch));
    }
    curl_close($ch);
    return $errno ? false : $response;
}
