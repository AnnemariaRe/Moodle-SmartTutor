(function(window) {
    if (!window.MetrikaInit || !window.MetrikaUtils) {
        console.error('[metrika] helpers not loaded');
        return;
    }

    window.MetrikaInit.initOnce(function(counterId) {
        console.log('[metrika] init with counterId=', counterId);

        if (window.MetrikaCourse) {
            window.MetrikaCourse.setup(counterId);
        }
        if (window.MetrikaModule) {
            window.MetrikaModule.setup(counterId);
        }
    });
})(window);
