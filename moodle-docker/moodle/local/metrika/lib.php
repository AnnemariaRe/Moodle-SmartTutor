<?php
defined('MOODLE_INTERNAL') || die();

function local_metrika_before_http_headers() {
    global $PAGE, $USER;

    $enabled   = get_config('local_metrika', 'enabled');
    $counterid = get_config('local_metrika', 'counterid');

    if (empty($enabled) || empty($counterid)) {
        return;
    }

    $PAGE->requires->js_init_code(
        "console.log('[metrika] hook, counterId=$counterid');"
    );

    $PAGE->requires->js_init_code(
        "window.M = window.M || {}; window.M.metrika = {counterId: '$counterid'};"
    );

    $courseid = !empty($PAGE->course) ? (int)$PAGE->course->id : null;
    $cmid     = !empty($PAGE->cm) ? (int)$PAGE->cm->id : null;
    $userid   = !empty($USER) && !empty($USER->id) ? (int)$USER->id : null;

    $js = [];
    $js[] = "window.M = window.M || {};";
    $js[] = "window.M.moodle = window.M.moodle || {};";
    if ($courseid) {
        $js[] = "window.M.moodle.courseId = $courseid;";
    }
    if ($cmid) {
        $js[] = "window.M.moodle.cmid = $cmid;";
    }
    if ($userid) {
        $js[] = "window.M.moodle.userId = $userid;";
    }

    $PAGE->requires->js_init_code(implode("\n", $js));

    $version = '2026020905';
    $PAGE->requires->js(new moodle_url('/local/metrika/js/utils.js', ['v' => $version]));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/path.js', ['v' => $version]));  // path должен быть перед module
    $PAGE->requires->js(new moodle_url('/local/metrika/js/course.js', ['v' => $version]));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/module.js', ['v' => $version]));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/video.js', ['v' => $version]));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/init.js', ['v' => $version]));
    $PAGE->requires->js(new moodle_url('/local/metrika/metrika.js', ['v' => $version]));
}
