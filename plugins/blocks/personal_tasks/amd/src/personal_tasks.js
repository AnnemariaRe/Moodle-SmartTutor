// AMD module for block_personal_tasks
define(['jquery', 'core/str'], function($, Str) {

    var config = {};

    var DIFFICULTY_BADGE = {
        easy:   'badge-success',
        medium: 'badge-warning',
        hard:   'badge-danger',
    };

    function difficultyLabel(diff) {
        var labels = {easy: 'Легко', medium: 'Средне', hard: 'Сложно'};
        return labels[diff] || diff;
    }

    function setStatus(msg) {
        $('#pt-status').text(msg);
    }

    function clearStatus() {
        $('#pt-status').text('');
    }

    function renderTasks(tasks) {
        var $container = $('#pt-tasks-container');
        $container.empty();

        if (!tasks || tasks.length === 0) {
            $container.html('<p class="text-muted small">Нет доступных заданий.</p>');
            return;
        }

        tasks.forEach(function(task) {
            var spec = task.spec;
            var badgeClass = DIFFICULTY_BADGE[spec.difficulty] || 'badge-secondary';
            var $card = $('<div class="card mb-2"></div>');
            var $body = $('<div class="card-body p-2"></div>');

            // Header: concept + difficulty badge
            $body.append(
                '<div class="d-flex justify-content-between align-items-start mb-1">' +
                '<small class="text-muted">' + $('<span>').text(task.concept_name).html() + '</small>' +
                '<span class="badge ' + badgeClass + '">' + difficultyLabel(spec.difficulty) + '</span>' +
                '</div>'
            );

            // Question
            $body.append('<p class="mb-2 font-weight-bold small">' + $('<span>').text(spec.question).html() + '</p>');

            // Answer input
            var $answerArea = $('<div class="pt-answer-area mb-2"></div>');

            if (spec.type === 'mcq' && Array.isArray(spec.options)) {
                spec.options.forEach(function(option, idx) {
                    var inputId = 'pt-opt-' + task.id + '-' + idx;
                    $answerArea.append(
                        '<div class="form-check">' +
                        '<input class="form-check-input" type="radio" name="pt-mcq-' + task.id + '" ' +
                        'id="' + inputId + '" value="' + idx + '">' +
                        '<label class="form-check-label small" for="' + inputId + '">' +
                        $('<span>').text(option).html() +
                        '</label></div>'
                    );
                });
            } else {
                $answerArea.append(
                    '<textarea class="form-control form-control-sm pt-open-answer" rows="3" ' +
                    'placeholder="Введите ответ..."></textarea>'
                );
            }

            $body.append($answerArea);

            // Check button
            var $btn = $('<button class="btn btn-secondary btn-sm check-answer w-100">Проверить</button>');
            $btn.data('task-id', task.id);
            $btn.data('task-type', spec.type);
            $body.append($btn);

            // Feedback area
            $body.append('<div class="pt-feedback mt-2" style="display:none;"></div>');

            $card.append($body);
            $container.append($card);
        });
    }

    function collectAnswer($card, taskType) {
        if (taskType === 'mcq') {
            var selected = $card.find('input[type="radio"]:checked').val();
            if (selected === undefined) return null;
            return {selected_index: parseInt(selected, 10)};
        } else {
            var text = $card.find('.pt-open-answer').val().trim();
            if (!text) return null;
            return {text: text};
        }
    }

    function showFeedback($card, data) {
        var $fb = $card.find('.pt-feedback');
        var correct = data.correct;
        var score = Math.round((data.score || 0) * 100);
        var explanation = data.explanation || '';

        var alertClass = correct ? 'alert-success' : 'alert-warning';
        var label = correct ? 'Верно' : 'Неверно';

        $fb.html(
            '<div class="alert ' + alertClass + ' p-2 small mb-0">' +
            '<strong>' + label + '</strong> (' + score + '%)<br>' +
            $('<span>').text(explanation).html() +
            '</div>'
        );
        $fb.show();
    }

    function doGenerate() {
        var $btn = $('#pt-generate');
        $btn.prop('disabled', true);
        setStatus('Загружаю задания...');
        $('#pt-tasks-container').empty();

        console.log('[PT] generate: config=', config);

        $.ajax({
            url: config.ajaxurl,
            method: 'GET',
            dataType: 'json',
            data: {
                action:   'generate',
                courseid: config.courseid,
                userid:   config.userid,
                sesskey:  config.sesskey,
            },
            timeout: 70000,
        }).done(function(data) {
            console.log('[PT] generate done:', data);
            clearStatus();
            if (data.error) {
                setStatus(data.error);
                return;
            }
            if (data.mastered) {
                setStatus(data.message || 'Все концепты освоены.');
                return;
            }
            renderTasks(data.tasks || []);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.error('[PT] generate fail:', jqXHR.status, textStatus, errorThrown);
            console.error('[PT] response text:', jqXHR.responseText);
            setStatus('Сервис недоступен. Попробуйте позже.');
        }).always(function() {
            $btn.prop('disabled', false);
        });
    }

    function doCheck($btn) {
        var $card = $btn.closest('.card');
        var taskId = $btn.data('task-id');
        var taskType = $btn.data('task-type');
        var answer = collectAnswer($card, taskType);

        if (!answer) {
            alert('Пожалуйста, введите ответ.');
            return;
        }

        $btn.prop('disabled', true).text('Проверяю...');
        $card.find('.pt-feedback').hide();

        $.ajax({
            url: config.ajaxurl,
            method: 'GET',
            dataType: 'json',
            data: {
                action:   'check',
                courseid: config.courseid,
                userid:   config.userid,
                sesskey:  config.sesskey,
                task_id:  taskId,
                answer:   JSON.stringify(answer),
            },
            timeout: 70000,
        }).done(function(data) {
            if (data.error) {
                $card.find('.pt-feedback')
                    .html('<div class="alert alert-danger p-2 small mb-0">' + data.error + '</div>')
                    .show();
                return;
            }
            showFeedback($card, data);
        }).fail(function() {
            $card.find('.pt-feedback')
                .html('<div class="alert alert-danger p-2 small mb-0">Сервис недоступен.</div>')
                .show();
        }).always(function() {
            $btn.prop('disabled', false).text('Проверить');
        });
    }

    return {
        init: function(cfg) {
            config = cfg;
            console.log('[PT] init config:', cfg);

            $(document).ready(function() {
                $('#pt-generate').on('click', function() {
                    doGenerate();
                });

                $('#pt-tasks-container').on('click', '.check-answer', function() {
                    doCheck($(this));
                });
            });
        }
    };
});
