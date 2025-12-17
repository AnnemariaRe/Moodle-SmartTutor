(function(window) {
    var Utils = window.MetrikaUtils;

    function detectModule(href, phpCourseId, phpModuleId) {
        var moduleId = null;
        var activityType = null;

        var isModuleViewPage =
            href.indexOf('/mod/') !== -1 &&
            href.indexOf('/view.php') !== -1;

        var isQuizAttemptPage =
            href.indexOf('/mod/quiz/attempt.php') !== -1;

        if (phpModuleId) {
            moduleId = String(phpModuleId);
            if (isModuleViewPage) {
                activityType = 'view';
            } else if (isQuizAttemptPage) {
                activityType = 'attempt';
            }
        } else {
            if (isModuleViewPage) {
                moduleId = Utils.getParam(href, 'id');
                activityType = 'view';
            } else if (isQuizAttemptPage) {
                moduleId = Utils.getParam(href, 'cmid');
                activityType = 'attempt';
            }
        }

        var courseId = Utils.getCurrentCourseId(phpCourseId);

        return {
            moduleId: moduleId,
            activityType: activityType,
            courseId: courseId
        };
    }

    function trackModuleSession(counterId, moduleId, courseId) {
        if (!moduleId) return;

        var moduleSessionStart = Date.now();

        window.addEventListener('beforeunload', function() {
            if (!moduleSessionStart) return;
            var durationMs = Date.now() - moduleSessionStart;
            var parts = [];
            if (courseId) parts.push('courseId=' + courseId);
            parts.push('moduleId=' + moduleId);
            parts.push('eventType=module_session');
            parts.push('durationMs=' + durationMs);
            var eventKey = parts.join(';');

            ym(counterId, 'params', { eventKey: eventKey });
        });
    }

    // 1) courseId=2;moduleId=10;activityType=view;step=1;userId=1
    // 2) courseId=2;moduleId=11;activityType=view;step=2;prevModuleId=10;stepDurationMs=35000;userId=1
    // 3) courseId=2;moduleId=9;activityType=view;step=3;prevModuleId=11;stepDurationMs=42000;userId=1
    function trackModuleViewAttempt(counterId, moduleId, courseId, activityType) {
        if (!moduleId) return;
        var userId = window.M && window.M.moodle && window.M.moodle.userId;
    
        var state = MetrikaPath.get();
        var now = Date.now();
        var durationFromPrev = null;
        if (state.lastStepTimestamp != null) {
            durationFromPrev = now - state.lastStepTimestamp;
        }
    
        var prevModuleId = state.lastModuleId;
        var stepIndex = (state.stepIndex || 0) + 1;
    
        window.MetrikaPath.update(function(s) {
            s.lastStepTimestamp = now;
            s.lastModuleId = moduleId;
            s.stepIndex = stepIndex;
        });
    
        var parts = [];
        if (courseId) parts.push('courseId=' + courseId);
        parts.push('moduleId=' + moduleId);
        if (activityType) parts.push('activityType=' + activityType);
        parts.push('step=' + stepIndex);
        if (prevModuleId) parts.push('prevModuleId=' + prevModuleId);
        if (durationFromPrev != null) parts.push('stepDurationMs=' + durationFromPrev);
        if (userId) parts.push('userId=' + userId);
    
        var eventKeyModule = parts.join(';');
        console.log('[metrika] module eventKey =', eventKeyModule);
    
        ym(counterId, 'params', { eventKey: eventKeyModule });
        if (activityType === 'view') {
            ym(counterId, 'reachGoal', 'module_open');
        }
    }

    function setupModuleHandlers(counterId) {
        var href = window.location.href;
        var ids = Utils.getPhpIds();
        var phpCourseId = ids.phpCourseId;
        var phpModuleId = ids.phpModuleId;

        var info = detectModule(href, phpCourseId, phpModuleId);
        var moduleId = info.moduleId;
        var activityType = info.activityType;
        var courseId = info.courseId;

        trackModuleSession(counterId, moduleId, courseId);
        trackModuleViewAttempt(counterId, moduleId, courseId, activityType);
    }

    window.MetrikaModule = {
        setup: setupModuleHandlers
    };
})(window);
