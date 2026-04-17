<?php
defined('MOODLE_INTERNAL') || die();

function local_metrika_before_http_headers() {
    global $PAGE, $USER;

    $enabled   = get_config('local_metrika', 'enabled');
    $counterid = get_config('local_metrika', 'counterid');

    if (empty($enabled) || empty($counterid)) {
        return;
    }

    // Log to confirm the hook fired
    $PAGE->requires->js_init_code(
        "console.log('[metrika] hook, counterId=$counterid');"
    );

    // Expose counterId on every page
    $PAGE->requires->js_init_code(
        "window.M = window.M || {}; window.M.metrika = {counterId: '$counterid'};"
    );

    // Expose courseId, cmid, and userId
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

    $PAGE->requires->js(new moodle_url('/local/metrika/js/utils.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/init.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/course.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/module.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/video.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/metrika.js'));
    $PAGE->requires->js(new moodle_url('/local/metrika/js/path.js'));
}
