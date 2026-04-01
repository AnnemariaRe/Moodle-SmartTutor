<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('local_metrika', get_string('metrika_settings', 'local_metrika'));

    $settings->add(new admin_setting_configcheckbox(
        'local_metrika/enabled',
        get_string('metrika_enabled', 'local_metrika'),
        get_string('metrika_enabled_desc', 'local_metrika'),
        0
    ));

    $settings->add(new admin_setting_configtext(
        'local_metrika/counterid',
        get_string('metrika_counterid', 'local_metrika'),
        get_string('metrika_counterid_desc', 'local_metrika'),
        '',
        PARAM_RAW_TRIMMED
    ));

    $ADMIN->add('localplugins', $settings);
}
