<?php
defined('MOODLE_INTERNAL') || die();

$capabilities = [
    'block/adaptive:addinstance' => [
        'riskbitmask' => RISK_SPAM | RISK_XSS,
        'captype'     => 'write',
        'contextlevel' => CONTEXT_BLOCK,
        'archetypes'   => [
            'editingteacher' => CAP_ALLOW,
            'manager'        => CAP_ALLOW,
        ],
        'clonepermissionsfrom' => 'moodle/site:manageblocks',
    ],
    'block/adaptive:myaddinstance' => [
        'captype'      => 'write',
        'contextlevel' => CONTEXT_SYSTEM,
        'archetypes'   => [
            'user' => CAP_ALLOW,
        ],
    ],
];
