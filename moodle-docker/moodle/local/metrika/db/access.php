<?php
defined('MOODLE_INTERNAL') || die();

$capabilities = [
    'local/metrika:manage' => [
        'captype' => 'write',
        'contextlevel' => CONTEXT_SYSTEM,
        'archetypes' => [
            'manager' => CAP_ALLOW,
            'admin'   => CAP_ALLOW,
        ],
    ],
];
