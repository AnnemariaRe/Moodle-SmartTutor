// AMD module for block_personal_tasks — teacher/admin view
define(['jquery'], function($) {

    var config = {};

    var DIFFICULTY_LABEL = {easy: 'Легко', medium: 'Средне', hard: 'Сложно'};
    var DIFFICULTY_BADGE = {easy: 'badge-success', medium: 'badge-warning', hard: 'badge-danger'};
    var STATUS_LABEL     = {pending_review: 'На проверке', approved: 'Одобрено', rejected: 'Отклонено'};
    var STATUS_BADGE     = {pending_review: 'badge-secondary', approved: 'badge-success', rejected: 'badge-danger'};

    function setStatus(msg) { $('#pt-teacher-status').text(msg); }
    function clearStatus()  { $('#pt-teacher-status').text(''); }

    // ── AJAX helpers ────────────────────────────────────────────────────────

    function doAjax(data, timeout) {
        return $.ajax({
            url:      config.ajaxurl,
            method:   'GET',
            dataType: 'json',
            data:     $.extend({courseid: config.courseid, userid: config.userid, sesskey: config.sesskey}, data),
            timeout:  timeout || 120000,
        });
    }

    // ── Generate bank ────────────────────────────────────────────────────────

    function generateBank() {
        var instructions   = $('#pt-teacher-instructions').val().trim();
        var tasksPerConcept = parseInt($('#pt-tasks-per-concept').val(), 10) || 9;

        $('#pt-generate-bank').prop('disabled', true);
        setStatus('Генерация заданий... Это может занять несколько минут.');
        $('#pt-bank-container').empty();
        $('#pt-bulk-actions').hide();

        doAjax({
            action:           'generate_bank',
            teacher_instructions: instructions,
            tasks_per_concept: tasksPerConcept,
        }, 300000).done(function(data) {
            clearStatus();
            if (data.error) { setStatus(data.error); return; }
            setStatus(
                'Сгенерировано ' + data.total_tasks + ' заданий по ' +
                data.concepts_covered + ' концептам. Batch: ' + data.batch_id
            );
            loadBank();
        }).fail(function() {
            setStatus('Ошибка при генерации. Попробуйте позже.');
        }).always(function() {
            $('#pt-generate-bank').prop('disabled', false);
        });
    }

    // ── Load & render bank ──────────────────────────────────────────────────

    function loadBank() {
        var filterStatus = $('#pt-filter-status').val();
        setStatus('Загружаю...');
        $('#pt-bank-container').empty();
        $('#pt-bulk-actions').hide();

        doAjax({action: 'list_bank', filter_status: filterStatus}).done(function(data) {
            clearStatus();
            if (data.error) { setStatus(data.error); return; }
            renderBank(data.tasks || []);
        }).fail(function() {
            setStatus('Не удалось загрузить банк заданий.');
        });
    }

    function renderBank(tasks) {
        var $container = $('#pt-bank-container');
        $container.empty();

        if (!tasks.length) {
            $container.html('<p class="text-muted small">' +
                'Банк заданий пуст. Нажмите «Сгенерировать банк заданий».' +
            '</p>');
            return;
        }

        $('#pt-bulk-actions').show();

        tasks.forEach(function(task) {
            $container.append(renderTaskCard(task));
        });
    }

    function renderTaskCard(task) {
        var spec        = task.spec;
        var diffBadge   = DIFFICULTY_BADGE[spec.difficulty] || 'badge-secondary';
        var diffLabel   = DIFFICULTY_LABEL[spec.difficulty] || spec.difficulty;
        var statusBadge = STATUS_BADGE[task.status] || 'badge-secondary';
        var statusLabel = STATUS_LABEL[task.status] || task.status;

        var $card = $('<div class="card mb-2" data-task-id="' + task.id + '"></div>');
        var $body = $('<div class="card-body p-2"></div>');

        // Header row
        $body.append(
            '<div class="d-flex justify-content-between align-items-start mb-1">' +
            '<small class="text-muted font-weight-bold">' + $('<span>').text(task.concept_name).html() + '</small>' +
            '<div>' +
            '<span class="badge ' + diffBadge + ' mr-1">' + diffLabel + '</span>' +
            '<span class="badge ' + statusBadge + '">' + statusLabel + '</span>' +
            '</div>' +
            '</div>'
        );

        // Question
        $body.append('<p class="small mb-1"><strong>Вопрос:</strong> ' + $('<span>').text(spec.question).html() + '</p>');

        // Options (mcq)
        if (spec.type === 'mcq' && Array.isArray(spec.options)) {
            var optHtml = '<ul class="small mb-1 pl-3">';
            spec.options.forEach(function(opt, idx) {
                var marker = (idx === spec.correct_index) ? ' ✓' : '';
                optHtml += '<li>' + $('<span>').text(opt).html() + '<em>' + marker + '</em></li>';
            });
            optHtml += '</ul>';
            $body.append(optHtml);
        } else if (spec.correct_answer) {
            $body.append('<p class="small mb-1"><strong>Ответ:</strong> ' + $('<span>').text(spec.correct_answer).html() + '</p>');
        }

        // Explanation
        $body.append('<p class="small text-muted mb-2"><em>' + $('<span>').text(spec.explanation).html() + '</em></p>');

        // Action buttons
        var $actions = $('<div class="d-flex flex-wrap" style="gap:4px;"></div>');
        if (task.status !== 'approved') {
            $actions.append('<button class="btn btn-success btn-sm pt-approve-btn">Одобрить</button>');
        }
        if (task.status !== 'rejected') {
            $actions.append('<button class="btn btn-danger btn-sm pt-reject-btn">Отклонить</button>');
        }
        $actions.append('<button class="btn btn-outline-secondary btn-sm pt-edit-btn">Редактировать</button>');
        $body.append($actions);

        // Edit form (hidden)
        $body.append(buildEditForm(task));

        $card.append($body);
        return $card;
    }

    function buildEditForm(task) {
        var spec = task.spec;
        var $form = $('<div class="pt-edit-form mt-2 border-top pt-2" style="display:none;"></div>');

        $form.append('<p class="small font-weight-bold mb-1">Редактирование</p>');
        $form.append(
            '<label class="small">Вопрос</label>' +
            '<textarea class="form-control form-control-sm mb-1 ef-question" rows="2">' +
            $('<span>').text(spec.question).html() +
            '</textarea>'
        );

        if (spec.type === 'mcq' && Array.isArray(spec.options)) {
            spec.options.forEach(function(opt, idx) {
                $form.append(
                    '<label class="small">Вариант ' + (idx + 1) + '</label>' +
                    '<input type="text" class="form-control form-control-sm mb-1 ef-option" data-idx="' + idx + '" value="' +
                    $('<span>').text(opt).html() + '">'
                );
            });
            $form.append(
                '<label class="small">Индекс правильного ответа (0-based)</label>' +
                '<input type="number" class="form-control form-control-sm mb-1 ef-correct-index" min="0" value="' +
                (spec.correct_index !== null && spec.correct_index !== undefined ? spec.correct_index : 0) + '">'
            );
        } else {
            $form.append(
                '<label class="small">Правильный ответ</label>' +
                '<input type="text" class="form-control form-control-sm mb-1 ef-correct-answer" value="' +
                $('<span>').text(spec.correct_answer || '').html() + '">'
            );
        }

        $form.append(
            '<label class="small">Объяснение</label>' +
            '<textarea class="form-control form-control-sm mb-2 ef-explanation" rows="2">' +
            $('<span>').text(spec.explanation).html() +
            '</textarea>'
        );
        $form.append(
            '<button class="btn btn-primary btn-sm pt-save-edit mr-1">Сохранить и одобрить</button>' +
            '<button class="btn btn-link btn-sm pt-cancel-edit">Отмена</button>'
        );
        return $form;
    }

    // ── Review helpers ──────────────────────────────────────────────────────

    function reviewTask(taskId, action, editedSpec) {
        var payload = {
            action:      'review_task',
            task_id:     taskId,
            review_action: action,
        };
        if (editedSpec) {
            payload.edited_spec = JSON.stringify(editedSpec);
        }
        return doAjax(payload);
    }

    function bulkReview(action) {
        var ids = [];
        $('#pt-bank-container .card').each(function() {
            ids.push(parseInt($(this).data('task-id'), 10));
        });
        if (!ids.length) return;

        setStatus('Обрабатываю...');
        doAjax({action: 'review_bulk', task_ids: JSON.stringify(ids), review_action: action})
            .done(function(data) {
                if (data.error) { setStatus(data.error); return; }
                clearStatus();
                loadBank();
            })
            .fail(function() { setStatus('Ошибка при массовом действии.'); });
    }

    function collectEditedSpec($card) {
        var $form = $card.find('.pt-edit-form');
        var spec  = {};
        spec.question    = $form.find('.ef-question').val();
        spec.explanation = $form.find('.ef-explanation').val();

        var $options = $form.find('.ef-option');
        if ($options.length) {
            spec.type    = 'mcq';
            spec.options = [];
            $options.each(function() { spec.options.push($(this).val()); });
            spec.correct_index  = parseInt($form.find('.ef-correct-index').val(), 10);
            spec.correct_answer = null;
        } else {
            spec.type          = 'open';
            spec.correct_answer = $form.find('.ef-correct-answer').val();
            spec.options        = null;
            spec.correct_index  = null;
        }
        // preserve difficulty from original card data
        var taskId = parseInt($card.data('task-id'), 10);
        var $badge = $card.find('.badge').first();
        spec.difficulty = 'medium'; // fallback; real value stays in DB
        return spec;
    }

    // ── Event wiring ────────────────────────────────────────────────────────

    return {
        init: function(cfg) {
            config = cfg;

            $(document).ready(function() {

                $('#pt-generate-bank').on('click', function() { generateBank(); });
                $('#pt-load-bank').on('click', function() { loadBank(); });
                $('#pt-approve-all').on('click', function() { bulkReview('approve'); });
                $('#pt-reject-all').on('click', function() { bulkReview('reject'); });

                // Approve
                $('#pt-bank-container').on('click', '.pt-approve-btn', function() {
                    var $card  = $(this).closest('.card');
                    var taskId = parseInt($card.data('task-id'), 10);
                    $(this).prop('disabled', true).text('...');
                    reviewTask(taskId, 'approve').done(function() { loadBank(); })
                        .fail(function() { setStatus('Ошибка одобрения задания #' + taskId); });
                });

                // Reject
                $('#pt-bank-container').on('click', '.pt-reject-btn', function() {
                    var $card  = $(this).closest('.card');
                    var taskId = parseInt($card.data('task-id'), 10);
                    $(this).prop('disabled', true).text('...');
                    reviewTask(taskId, 'reject').done(function() { loadBank(); })
                        .fail(function() { setStatus('Ошибка отклонения задания #' + taskId); });
                });

                // Toggle edit form
                $('#pt-bank-container').on('click', '.pt-edit-btn', function() {
                    $(this).closest('.card').find('.pt-edit-form').toggle();
                });

                // Cancel edit
                $('#pt-bank-container').on('click', '.pt-cancel-edit', function() {
                    $(this).closest('.pt-edit-form').hide();
                });

                // Save edit + approve
                $('#pt-bank-container').on('click', '.pt-save-edit', function() {
                    var $card     = $(this).closest('.card');
                    var taskId    = parseInt($card.data('task-id'), 10);
                    var editedSpec = collectEditedSpec($card);
                    $(this).prop('disabled', true).text('...');
                    reviewTask(taskId, 'approve', editedSpec)
                        .done(function() { loadBank(); })
                        .fail(function() { setStatus('Ошибка сохранения задания #' + taskId); });
                });
            });
        }
    };
});
