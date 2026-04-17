<?php
defined('MOODLE_INTERNAL') || die();

class block_personal_tasks extends block_base {

    public function init() {
        $this->title = get_string('pluginname', 'block_personal_tasks');
    }

    public function applicable_formats() {
        return ['course-view' => true];
    }

    public function has_config() {
        return true;
    }

    public function get_content() {
        global $USER, $COURSE, $PAGE, $OUTPUT;

        if ($this->content !== null) {
            return $this->content;
        }

        $this->content = new stdClass();
        $this->content->footer = '';

        $context = context_course::instance($COURSE->id);

        if (!has_capability('block/personal_tasks:view', $context)) {
            $this->content->text = '';
            return $this->content;
        }

        $is_teacher = has_capability('block/personal_tasks:managetasks', $context);
        $ajaxurl    = (new moodle_url('/blocks/personal_tasks/ajax.php'))->out(false);

        if ($is_teacher) {
            $PAGE->requires->js_call_amd(
                'block_personal_tasks/teacher_tasks',
                'init',
                [[
                    'courseid'  => $COURSE->id,
                    'userid'    => $USER->id,
                    'sesskey'   => sesskey(),
                    'ajaxurl'   => $ajaxurl,
                ]]
            );
            $this->content->text = $OUTPUT->render_from_template(
                'block_personal_tasks/teacher_content',
                []
            );
        } else {
            $PAGE->requires->js_call_amd(
                'block_personal_tasks/personal_tasks',
                'init',
                [[
                    'courseid' => $COURSE->id,
                    'userid'   => $USER->id,
                    'sesskey'  => sesskey(),
                    'ajaxurl'  => $ajaxurl,
                ]]
            );
            $this->content->text = $OUTPUT->render_from_template(
                'block_personal_tasks/content',
                []
            );
        }

        return $this->content;
    }
}
