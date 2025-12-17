(function(window) {
    var key = 'metrikaPathState';

    function load() {
        try {
            var raw = localStorage.getItem(key);
            if (!raw) {
                return {
                    lastModuleId: null,
                    stepIndex: 0,
                    lastStepTimestamp: null
                };
            }
            var parsed = JSON.parse(raw);
            return {
                lastModuleId: parsed.lastModuleId || null,
                stepIndex: parsed.stepIndex || 0,
                lastStepTimestamp: parsed.lastStepTimestamp || null
            };
        } catch (e) {
            return {
                lastModuleId: null,
                stepIndex: 0,
                lastStepTimestamp: null
            };
        }
    }

    function save(state) {
        try {
            localStorage.setItem(key, JSON.stringify(state));
        } catch (e) {}
    }

    var state = load();

    window.MetrikaPath = {
        get: function() { return state; },
        update: function(mutator) {
            mutator(state);
            save(state);
        }
    };
})(window);
