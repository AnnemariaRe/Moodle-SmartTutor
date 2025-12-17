(function(window) {
    function initMetrikaOnce(initFn) {
        var attempts = 0;
        var maxAttempts = 50; // ~5 секунд

        var timer = setInterval(function() {
            attempts++;
            var M = window.M || {};
            var counterId = M.metrika && M.metrika.counterId;
            if (counterId && typeof ym === 'function') {
                console.log('[metrika] initMetrika success, counterId=', counterId);
                try { initFn(counterId); } catch (e) { console.error(e); }
                clearInterval(timer);
            } else if (attempts >= maxAttempts) {
                console.log('[metrika] initMetrika failed, giving up');
                clearInterval(timer);
            }
        }, 100);
    }

    window.MetrikaInit = {
        initOnce: initMetrikaOnce
    };
})(window);
