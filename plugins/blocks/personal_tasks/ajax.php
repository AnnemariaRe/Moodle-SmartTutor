<?php
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');
@set_time_limit(90);

require_login();
require_sesskey();

$action   = required_param('action', PARAM_ALPHA);
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

error_log("[PT ajax] action={$action} userid={$userid} courseid={$courseid} taskgen_url={$taskgen_url}");

header('Content-Type: application/json');

if ($action === 'generate') {
    $payload = json_encode([
        'student_id'           => $userid,
        'course_id'            => $courseid,
        'max_concepts'         => 2,
        'variants_per_concept' => 2,
        'mastery_threshold'    => 0.7,
    ]);

    $response = _pt_http_post($taskgen_url . '/v1/personalized-task', $payload);
    error_log("[PT ajax] generate response: " . ($response === false ? 'FALSE (connection failed)' : substr($response, 0, 300)));

    if ($response === false) {
        http_response_code(503);
        echo json_encode(['error' => get_string('service_unavailable', 'block_personal_tasks')]);
        die;
    }

    $decoded = json_decode($response, true);

    // TaskGenerator returns HTTP 200 with detail when all mastered
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
        'task_id' => $task_id,
        'answer'  => $answer,
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

http_response_code(400);
echo json_encode(['error' => 'Unknown action']);

function _pt_http_post(string $url, string $body) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $body,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json', 'Accept: application/json'],
        CURLOPT_TIMEOUT        => 60,
    ]);
    $response = curl_exec($ch);
    $errno    = curl_errno($ch);
    if ($errno) {
        error_log("[PT ajax] curl error {$errno}: " . curl_error($ch));
    }
    curl_close($ch);
    return $errno ? false : $response;
}
