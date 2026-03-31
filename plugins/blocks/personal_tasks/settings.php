<?php
defined('MOODLE_INTERNAL') || die();

if ($ADMIN->fulltree) {
    $settings->add(new admin_setting_configtext(
        'block_personal_tasks/taskgenerator_url',
        get_string('taskgenerator_url', 'block_personal_tasks'),
        get_string('taskgenerator_url_desc', 'block_personal_tasks'),
        'http://personalized-tasks:8004',
        PARAM_URL
    ));
}
