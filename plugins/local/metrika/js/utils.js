(function(window) {
    function getParam(href, name) {
        var match = href.match(new RegExp('[?&]' + name + '=([^&]+)'));
        return match ? decodeURIComponent(match[1]) : null;
    }

    function getPhpIds() {
        var M = window.M || {};
        var moodle = M.moodle || {};
        return {
            phpCourseId: moodle.courseId || null,
            phpModuleId: moodle.cmid || null
        };
    }

    function getCurrentCourseId(phpCourseId) {
        if (phpCourseId) {
            return String(phpCourseId);
        }
        try {
            var stored = localStorage.getItem('lastCourseId');
            if (stored) return stored;
        } catch (e) {}
        return null;
    }

    window.MetrikaUtils = {
        getParam: getParam,
        getPhpIds: getPhpIds,
        getCurrentCourseId: getCurrentCourseId
    };
})(window);
