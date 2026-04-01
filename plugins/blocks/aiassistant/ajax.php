<?php
/**
 * AJAX proxy: forwards student question to AI Assistant service.
 * Called by block JS via fetch('/blocks/aiassistant/ajax.php').
 */
define('AJAX_SCRIPT', true);
require_once(__DIR__ . '/../../config.php');

require_login();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

$body = file_get_contents('php://input');
$input = json_decode($body, true);

$course_id  = (int)  ($input['course_id']  ?? 0);
$student_id = (int)  ($input['student_id'] ?? 0);
$question   = trim(  ($input['question']   ?? ''));
$history    =         $input['history']    ?? [];

if (!$course_id || !$question) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing required fields']);
    exit;
}

$context = context_course::instance($course_id, IGNORE_MISSING);
if (!$context || !is_enrolled($context, $USER)) {
    http_response_code(403);
    echo json_encode(['error' => 'Access denied']);
    exit;
}

// Sanitize history: keep only role/content, last 20 messages
$clean_history = [];
foreach (array_slice((array)$history, -20) as $msg) {
    $role    = $msg['role']    ?? '';
    $content = $msg['content'] ?? '';
    if (in_array($role, ['user', 'assistant'], true) && strlen($content) > 0) {
        $clean_history[] = ['role' => $role, 'content' => mb_substr($content, 0, 4000)];
    }
}

$ai_url = 'http://ai-assistant:8003/v1/ask';
$payload = json_encode([
    'student_id' => $student_id,
    'course_id'  => $course_id,
    'question'   => $question,
    'history'    => $clean_history,
]);

$options = [
    'http' => [
        'method'        => 'POST',
        'header'        => "Content-Type: application/json\r\nAccept: application/json",
        'content'       => $payload,
        'timeout'       => 30,
        'ignore_errors' => true,
    ],
];
$ctx      = stream_context_create($options);
$response = @file_get_contents($ai_url, false, $ctx);

header('Content-Type: application/json');

if ($response === false) {
    http_response_code(502);
    echo json_encode(['error' => 'AI Assistant service unavailable']);
    exit;
}

// Pass response through as-is (already JSON)
echo $response;
