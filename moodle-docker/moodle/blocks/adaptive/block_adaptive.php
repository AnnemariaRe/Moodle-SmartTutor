<?php
defined('MOODLE_INTERNAL') || die();

class block_adaptive extends block_base {

    public function init() {
        $this->title = get_string('pluginname', 'block_adaptive');
    }

    public function applicable_formats() {
        return [
            'course-view' => true,
            'mod'         => true,
            'my'          => false,
        ];
    }

    public function get_content() {
        global $PAGE, $USER, $COURSE;

        if ($this->content !== null) {
            return $this->content;
        }
        $this->content = new stdClass();
        $this->content->footer = '';

        // Skip for guests only
        if (!isloggedin() || isguestuser()) {
            $this->content->text = '';
            return $this->content;
        }

        $student_id = (int) $USER->id;
        $course_id  = (int) $COURSE->id;

        // Determine context: course page or module page
        $cmid = null;
        $cm   = $PAGE->cm;
        if ($cm) {
            $cmid = (int) $cm->id;
        }

        // Build map cmid → module name using Moodle's fast modinfo
        $cm_names = [];
        $cm_urls  = [];
        try {
            $modinfo = get_fast_modinfo($COURSE);
            foreach ($modinfo->cms as $cm_obj) {
                $cm_names[(int)$cm_obj->id] = $cm_obj->name;
                $cm_urls[(int)$cm_obj->id]  = $cm_obj->url ? $cm_obj->url->out(false) : null;
            }
        } catch (Exception $e) {
            // modinfo unavailable — fall back to concept names
        }

        $url = 'http://adaptive-service:8002/v1/recommendations'
             . '?student_id=' . $student_id
             . '&course_id='  . $course_id
             . ($cmid !== null ? '&cmid=' . $cmid : '');

        $data = $this->fetch_json($url);

        if ($data === null) {
            $this->content->text = '<p class="text-muted small">'
                . get_string('service_unavailable', 'block_adaptive') . '</p>';
            return $this->content;
        }

        // Hide block entirely when there are no recommendations and no context banner
        if (empty($data->recommendations) && empty($data->context)) {
            $this->content->text = '';
            return $this->content;
        }

        $this->content->text = $this->render_block($data, $cmid, $cm_names, $cm_urls);
        return $this->content;
    }

    // ── Rendering ────────────────────────────────────────────────────────────

    private function render_block(stdClass $data, ?int $cmid, array $cm_names, array $cm_urls): string {
        $html = '<div class="block-adaptive-inner">';

        // Context banner (module page only)
        if ($cmid !== null && !empty($data->context)) {
            $html .= $this->render_context_banner($data);
        }

        // Recommendations list
        if (!empty($data->recommendations)) {
            $html .= '<ul class="block-adaptive-list list-unstyled mb-0">';
            foreach ($data->recommendations as $rec) {
                $html .= $this->render_rec_item($rec, $cm_names, $cm_urls);
            }
            $html .= '</ul>';
        } else {
            $html .= '<p class="text-muted small mb-0">'
                   . get_string('no_recommendations', 'block_adaptive') . '</p>';
        }

        // Footer: method label
        $method_label = $this->method_label($data->method ?? 'rule_based');
        $html .= '<p class="text-muted" style="font-size:0.7rem;margin-top:6px;">'
               . $method_label . '</p>';

        $html .= '</div>';
        return $html;
    }

    private function render_context_banner(stdClass $data): string {
        $context         = $data->context ?? '';
        $context_message = htmlspecialchars($data->context_message ?? '', ENT_QUOTES);
        $mastery         = isset($data->current_mastery) ? round($data->current_mastery * 100) : null;
        $dkt             = isset($data->current_dkt_p_correct)
                           ? round($data->current_dkt_p_correct * 100) : null;

        $icon_map = [
            'fix_prerequisites'  => '⚠️',
            'review_current'     => '🔄',
            'progressing'        => '📈',
            'ready_to_continue'  => '✅',
        ];
        $icon = $icon_map[$context] ?? 'ℹ️';

        $alert_class_map = [
            'fix_prerequisites'  => 'alert-warning',
            'review_current'     => 'alert-warning',
            'progressing'        => 'alert-info',
            'ready_to_continue'  => 'alert-success',
        ];
        $alert_class = $alert_class_map[$context] ?? 'alert-secondary';

        $html  = '<div class="alert ' . $alert_class . ' py-1 px-2 mb-2" style="font-size:0.82rem;">';
        $html .= $icon . ' ' . $context_message;
        if ($mastery !== null) {
            $html .= '<br><small>';
            $html .= get_string('mastery_label', 'block_adaptive') . ': <strong>' . $mastery . '%</strong>';
            if ($dkt !== null) {
                $html .= ' &nbsp;|&nbsp; DKT: <strong>' . $dkt . '%</strong>';
            }
            $html .= '</small>';
        }
        $html .= '</div>';
        return $html;
    }

    private function render_rec_item(stdClass $rec, array $cm_names, array $cm_urls): string {
        $type_icons = [
            'quiz'   => '📝',
            'assign' => '📋',
            'lesson' => '📚',
            'page'   => '📄',
            'url'    => '🔗',
        ];
        $type  = $rec->type ?? 'page';
        $icon  = $type_icons[$type] ?? '📄';
        $cmid  = (int) ($rec->moodle_cmid ?? 0);

        // Use real Moodle module name; fall back to concept_name
        $label = isset($cm_names[$cmid]) && $cm_names[$cmid] !== ''
            ? htmlspecialchars($cm_names[$cmid], ENT_QUOTES)
            : htmlspecialchars($rec->concept_name ?? '', ENT_QUOTES);

        // Use real Moodle URL; fall back to generic /mod/{type}/view.php?id=
        $link = isset($cm_urls[$cmid]) && $cm_urls[$cmid] !== null
            ? $cm_urls[$cmid]
            : '/mod/' . urlencode($type) . '/view.php?id=' . $cmid;

        $reason = htmlspecialchars($rec->reason ?? '', ENT_QUOTES);

        $html  = '<li class="block-adaptive-item mb-1">';
        $html .= '<a href="' . $link . '" style="font-size:0.85rem;">'
               . $icon . ' ' . $label . '</a>';
        if ($reason) {
            $html .= '<br><span class="text-muted" style="font-size:0.72rem;">'
                   . $reason . '</span>';
        }
        $html .= '</li>';
        return $html;
    }

    private function method_label(string $method): string {
        $labels = [
            'lightfm_hybrid' => get_string('method_lightfm', 'block_adaptive'),
            'rule_based'     => get_string('method_rule_based', 'block_adaptive'),
        ];
        return $labels[$method] ?? $method;
    }

    // ── HTTP helper ──────────────────────────────────────────────────────────

    private function fetch_json(string $url): ?stdClass {
        $options = [
            'http' => [
                'method'        => 'GET',
                'timeout'       => 1.5,
                'ignore_errors' => true,
            ],
        ];
        $ctx  = stream_context_create($options);
        $body = @file_get_contents($url, false, $ctx);
        if ($body === false) {
            return null;
        }
        $decoded = @json_decode($body);
        return ($decoded instanceof stdClass) ? $decoded : null;
    }
}
