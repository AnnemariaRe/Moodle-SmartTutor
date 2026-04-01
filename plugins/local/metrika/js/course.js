(function(window) {
    var Utils = window.MetrikaUtils;

    function trackCourseSession(counterId, href, phpCourseId) {
        if (href.indexOf('/course/view.php') === -1) return;

        var cidFromUrl = Utils.getParam(href, 'id');
        var courseIdForStore = phpCourseId || cidFromUrl;
        if (courseIdForStore) {
            try {
                localStorage.setItem('lastCourseId', String(courseIdForStore));
            } catch (e) {}
        }

        // Сессия просмотра курса
        var courseSessionStart = Date.now();
        window.addEventListener('beforeunload', function() {
            if (!courseSessionStart) return;
            var durationMs = Date.now() - courseSessionStart;
            var currentCourseId = Utils.getCurrentCourseId(phpCourseId);
            var parts = [];
            if (currentCourseId) parts.push('courseId=' + currentCourseId);
            parts.push('eventType=course_session');
            parts.push('durationMs=' + durationMs);
            var eventKey = parts.join(';');
            ym(counterId, 'params', { eventKey: eventKey });
        });
    }

    function trackFirstActivityClick(counterId, phpCourseId) {
        var firstInteractionSent = false;
        var pageOpenAt = Date.now();
        var courseId = Utils.getCurrentCourseId(phpCourseId);

        document.addEventListener('click', function(e) {
            if (firstInteractionSent) return;
            var target = e.target;
            for (var i = 0; i < 5 && target; i++) {
                if (target.tagName === 'A' && target.href && target.href.indexOf('/mod/') !== -1) {
                    var delayMs = Date.now() - pageOpenAt;
                    var parts = [];
                    if (courseId) parts.push('courseId=' + courseId);
                    parts.push('eventType=first_activity_click');
                    parts.push('delayMs=' + delayMs);
                    var eventKey = parts.join(';');

                    ym(counterId, 'params', { eventKey: eventKey });
                    ym(counterId, 'reachGoal', 'first_activity_click');
                    firstInteractionSent = true;
                    break;
                }
                target = target.parentElement;
            }
        }, true);
    }

    function trackSectionView(counterId, href, phpCourseId) {
        if (href.indexOf('/course/section.php') === -1) return;

        var sectionId = Utils.getParam(href, 'id');
        var sectionCourseId = Utils.getCurrentCourseId(phpCourseId);

        var eventKeySection = [
            sectionCourseId ? 'courseId=' + sectionCourseId : null,
            sectionId ? 'sectionId=' + sectionId : null,
            'eventType=section_view'
        ].filter(Boolean).join(';');

        ym(counterId, 'params', { eventKey: eventKeySection });
        ym(counterId, 'reachGoal', 'section_open');
    }

    function trackEnrol(counterId, href, phpCourseId) {
        if (href.indexOf('/enrol/index.php') === -1) return;

        var courseId = Utils.getCurrentCourseId(phpCourseId);
        var enrollCourseId = phpCourseId || Utils.getParam(href, 'id') || courseId;

        document.addEventListener('click', function(e) {
            var target = e.target;
            for (var i = 0; i < 3 && target; i++) {
                if (target.tagName === 'BUTTON' || target.tagName === 'INPUT') break;
                target = target.parentElement;
            }
            if (!target) return;

            var label = (target.textContent || target.value || '').toLowerCase();
            var isEnrollButton =
                (target.tagName === 'BUTTON' || target.tagName === 'INPUT') &&
                (label.indexOf('enrol') !== -1 || label.indexOf('записаться') !== -1);

            if (!isEnrollButton) return;

            var eventKey = [
                enrollCourseId ? 'courseId=' + enrollCourseId : null,
                'eventType=enroll'
            ].filter(Boolean).join(';');

            ym(counterId, 'params', { eventKey: eventKey });
            ym(counterId, 'reachGoal', 'course_enroll');
        }, true);
    }

    function setupCourseHandlers(counterId) {
        var href = window.location.href;
        var ids = Utils.getPhpIds();
        var phpCourseId = ids.phpCourseId;

        trackCourseSession(counterId, href, phpCourseId);
        trackFirstActivityClick(counterId, phpCourseId);
        trackSectionView(counterId, href, phpCourseId);
        trackEnrol(counterId, href, phpCourseId);
    }

    window.MetrikaCourse = {
        setup: setupCourseHandlers
    };
})(window);
