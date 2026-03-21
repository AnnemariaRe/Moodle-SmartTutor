<?php
defined('MOODLE_INTERNAL') || die();

$capabilities = [
    'block/aiassistant:myaddinstance' => [
        'captype'      => 'write',
        'contextlevel' => CONTEXT_SYSTEM,
        'archetypes'   => ['user' => CAP_ALLOW],
    ],
    'block/aiassistant:addinstance' => [
        'captype'      => 'write',
        'contextlevel' => CONTEXT_BLOCK,
        'archetypes'   => [
            'editingteacher' => CAP_ALLOW,
            'manager'        => CAP_ALLOW,
        ],
    ],
];
