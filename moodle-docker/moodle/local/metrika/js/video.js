(function(window) {
    var Utils = window.MetrikaUtils;
    var WATCH_MILESTONES = [0, 25, 50, 75, 100];
    var TIMEUPDATE_THROTTLE = 1000;

    function normalizeSrc(url) {
        if (!url) return null;
        try {
            var a = document.createElement('a');
            a.href = url;
            return a.pathname || url.split('?')[0];
        } catch (e) {
            return url.split('?')[0];
        }
    }

    function resolveModuleIdForElement(element, fallbackModuleId) {
        if (fallbackModuleId) return String(fallbackModuleId);
        var el = element;
        while (el) {
            if (el.id && el.id.indexOf('module-') === 0) {
                return el.id.substring('module-'.length);
            }
            el = el.parentElement;
        }
        return null;
    }

    
    function VideoTracker(counterId, mediaId, mediaType, moduleId, courseId) {
        this.counterId = counterId;
        this.mediaId = mediaId;
        this.mediaType = mediaType;
        this.moduleId = moduleId;
        this.courseId = courseId;
        this.userId = window.M && window.M.moodle && window.M.moodle.userId;
        
        this.watchedMilestones = new Set();
        this.pauseCount = 0;
        this.seekCount = 0;
        this.seekBackwardCount = 0;
        this.lastTime = 0;
        this.totalWatchTime = 0;
        this.watchStartTime = null;
        this.lastTimeupdate = 0;
    }

    VideoTracker.prototype.getWatchPercent = function(currentTime, duration) {
        if (!duration || duration === 0) return 0;
        return Math.floor((currentTime / duration) * 100);
    };

    VideoTracker.prototype.sendEvent = function(eventType, params) {
        var parts = [];
        if (this.courseId) parts.push('courseId=' + this.courseId);
        if (this.moduleId) parts.push('moduleId=' + this.moduleId);
        parts.push('mediaId=' + this.mediaId);
        parts.push('mediaType=' + this.mediaType);
        parts.push('eventType=' + eventType);
        
        for (var key in params) {
            if (params[key] != null) parts.push(key + '=' + params[key]);
        }
        if (this.userId) parts.push('userId=' + this.userId);
        
        var eventKey = parts.join(';');
        console.log('[metrika]', this.mediaType, eventType + ':', eventKey);
        ym(this.counterId, 'params', { eventKey: eventKey });
    };

    VideoTracker.prototype.sendWatchEvent = function(percent, eventType) {
        if (this.watchedMilestones.has(percent)) return;
        this.watchedMilestones.add(percent);
        this.sendEvent('video_watch', {
            watchPercent: percent,
            event: eventType
        });
        ym(this.counterId, 'reachGoal', 'video_watch_' + percent);
    };

    VideoTracker.prototype.sendPauseEvent = function() {
        this.pauseCount++;
        this.sendEvent('video_pause', { pauseCount: this.pauseCount });
    };

    VideoTracker.prototype.sendSeekEvent = function(isBackward) {
        this.seekCount++;
        if (isBackward) this.seekBackwardCount++;
        this.sendEvent('video_seek', {
            seekCount: this.seekCount,
            seekBackward: isBackward ? 1 : 0
        });
    };

    VideoTracker.prototype.sendFinalStats = function(currentTime, duration) {
        var finalPercent = this.getWatchPercent(currentTime || 0, duration || 0);
        this.sendEvent('video_stats', {
            finalPercent: finalPercent,
            pauseCount: this.pauseCount,
            seekCount: this.seekCount,
            seekBackwardCount: this.seekBackwardCount,
            totalWatchTime: Math.round(this.totalWatchTime)
        });
    };

    VideoTracker.prototype.checkMilestones = function(currentTime, duration) {
        var percent = this.getWatchPercent(currentTime, duration);
        for (var i = 0; i < WATCH_MILESTONES.length; i++) {
            var milestone = WATCH_MILESTONES[i];
            if (percent >= milestone && !this.watchedMilestones.has(milestone)) {
                this.sendWatchEvent(milestone, 'milestone');
            }
        }
    };

    /**
     * Отслеживание VideoJS плеера
     */
    function trackVideoJS(counterId, element, moduleId, courseId) {
        var videojsPlayer = null;
        
        if (window.videojs && element) {
            try {
                var players = window.videojs.getPlayers();
                for (var playerId in players) {
                    var player = players[playerId];
                    if (player.el() === element || player.el().contains(element)) {
                        videojsPlayer = player;
                        break;
                    }
                }
                if (!videojsPlayer && element.id) {
                    videojsPlayer = window.videojs(element.id);
                }
            } catch (e) {}
        }
        
        if (videojsPlayer) {
            trackVideoJSPlayer(counterId, videojsPlayer, moduleId, courseId);
        } else {
            trackNativeMedia(counterId, element, moduleId, courseId);
        }
    }

    function trackVideoJSPlayer(counterId, player, moduleId, courseId) {
        var playerElement = player.el && player.el();
        var elementModuleId = resolveModuleIdForElement(playerElement || document.body, moduleId);
        
        var mediaSrc = null;
        try {
            if (player.currentSource && typeof player.currentSource === 'function') {
                var srcObj = player.currentSource();
                mediaSrc = srcObj && srcObj.src;
            }
        } catch (e) {}
        if (!mediaSrc && player.currentSrc && typeof player.currentSrc === 'function') {
            mediaSrc = player.currentSrc();
        }
        
        var mediaId = normalizeSrc(mediaSrc) || player.id() || 'videojs_unknown';
        var mediaType = 'videojs';
        var tracker = new VideoTracker(counterId, mediaId, mediaType, elementModuleId, courseId);
        
        console.log('[metrika] tracking VideoJS player:', mediaId);

        player.on('play', function() {
            tracker.watchStartTime = Date.now();
            var percent = tracker.getWatchPercent(player.currentTime(), player.duration());
            tracker.sendWatchEvent(percent, 'play');
        });

        player.on('pause', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                tracker.watchStartTime = null;
            }
            tracker.sendPauseEvent();
        });

        player.on('timeupdate', function() {
            var now = Date.now();
            if (now - tracker.lastTimeupdate < TIMEUPDATE_THROTTLE) return;
            tracker.lastTimeupdate = now;
            
            var duration = player.duration();
            if (!duration || duration === 0) return;
            tracker.checkMilestones(player.currentTime(), duration);
        });

        player.on('seeked', function() {
            var currentTime = player.currentTime();
            var isBackward = currentTime < tracker.lastTime;
            tracker.lastTime = currentTime;
            tracker.sendSeekEvent(isBackward);
        });

        player.on('ended', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                tracker.watchStartTime = null;
            }
            tracker.sendWatchEvent(100, 'ended');
            tracker.sendFinalStats(player.currentTime(), player.duration());
        });

        window.addEventListener('beforeunload', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
            }
            tracker.sendFinalStats(player.currentTime(), player.duration());
        });
    }

    /**
     * Отслеживание native HTML5 video/audio
     */
    function trackNativeMedia(counterId, element, moduleId, courseId) {
        if (!element || (element.tagName.toLowerCase() !== 'video' && element.tagName.toLowerCase() !== 'audio')) {
            return;
        }

        var elementModuleId = resolveModuleIdForElement(element, moduleId);
        var mediaSrc = element.currentSrc || element.src || null;
        if (!mediaSrc && element.querySelector) {
            var sourceEl = element.querySelector('source');
            if (sourceEl && sourceEl.src) mediaSrc = sourceEl.src;
        }
        
        var mediaId = normalizeSrc(mediaSrc) || element.id || 'unknown';
        var mediaType = element.tagName.toLowerCase();
        var tracker = new VideoTracker(counterId, mediaId, mediaType, elementModuleId, courseId);
        
        console.log('[metrika] tracking native media:', mediaId, mediaType);

        element.addEventListener('play', function() {
            tracker.watchStartTime = Date.now();
            var percent = tracker.getWatchPercent(element.currentTime, element.duration);
            tracker.sendWatchEvent(percent, 'play');
        });

        element.addEventListener('pause', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                tracker.watchStartTime = null;
            }
            tracker.sendPauseEvent();
        });

        element.addEventListener('timeupdate', function() {
            var now = Date.now();
            if (now - tracker.lastTimeupdate < TIMEUPDATE_THROTTLE) return;
            tracker.lastTimeupdate = now;
            
            if (!element.duration || element.duration === 0) return;
            tracker.checkMilestones(element.currentTime, element.duration);
        });

        element.addEventListener('seeked', function() {
            var currentTime = element.currentTime;
            var isBackward = currentTime < tracker.lastTime;
            tracker.lastTime = currentTime;
            tracker.sendSeekEvent(isBackward);
        });

        element.addEventListener('ended', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                tracker.watchStartTime = null;
            }
            tracker.sendWatchEvent(100, 'ended');
            tracker.sendFinalStats(element.currentTime, element.duration);
        });

        window.addEventListener('beforeunload', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
            }
            tracker.sendFinalStats(element.currentTime, element.duration);
        });
    }

    /**
     * Отслеживание YouTube через VideoJS события
     */
    function trackYouTube(counterId, iframe, moduleId, courseId) {
        if (!iframe || !iframe.src || (iframe.src.indexOf('youtube.com') === -1 && iframe.src.indexOf('youtu.be') === -1)) {
            return;
        }

        console.log('[metrika] tracking YouTube video');
        
        var elementModuleId = resolveModuleIdForElement(iframe, moduleId);
        var mediaId = normalizeSrc(iframe.src) || iframe.id || 'youtube_unknown';
        var tracker = new VideoTracker(counterId, mediaId, 'youtube', elementModuleId, courseId);
        
        // Ищем VideoJS player для этого iframe
        function findVideoJSPlayer() {
            if (!window.videojs) return null;
            try {
                var players = window.videojs.getPlayers();
                for (var playerId in players) {
                    var vjsPlayer = players[playerId];
                    var playerEl = vjsPlayer.el && vjsPlayer.el();
                    if (playerEl && (playerEl.contains(iframe) || playerEl.querySelector('iframe') === iframe)) {
                        return vjsPlayer;
                    }
                }
            } catch (e) {}
            return null;
        }
        
        // Ждём инициализации VideoJS player
        var attempts = 0;
        var checkInterval = setInterval(function() {
            attempts++;
            var vjsPlayer = findVideoJSPlayer();
            
            if (vjsPlayer) {
                clearInterval(checkInterval);
                console.log('[metrika] Found VideoJS YouTube player');
                
                // Отслеживаем через VideoJS события
                vjsPlayer.on('play', function() {
                    tracker.watchStartTime = Date.now();
                    tracker.sendWatchEvent(0, 'play');
                });
                
                vjsPlayer.on('pause', function() {
                    if (tracker.watchStartTime) {
                        tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                        tracker.watchStartTime = null;
                    }
                    tracker.sendPauseEvent();
                });
                
                vjsPlayer.on('timeupdate', function() {
                    var now = Date.now();
                    if (now - tracker.lastTimeupdate < TIMEUPDATE_THROTTLE) return;
                    tracker.lastTimeupdate = now;
                    
                    try {
                        var duration = vjsPlayer.duration && vjsPlayer.duration();
                        if (!duration || duration === 0) return;
                        tracker.checkMilestones(vjsPlayer.currentTime && vjsPlayer.currentTime() || 0, duration);
                    } catch (e) {}
                });
                
                vjsPlayer.on('seeked', function() {
                    try {
                        var currentTime = vjsPlayer.currentTime && vjsPlayer.currentTime() || 0;
                        var isBackward = currentTime < tracker.lastTime;
                        tracker.lastTime = currentTime;
                        tracker.sendSeekEvent(isBackward);
                    } catch (e) {}
                });
                
                vjsPlayer.on('ended', function() {
                    if (tracker.watchStartTime) {
                        tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
                        tracker.watchStartTime = null;
                    }
                    tracker.sendWatchEvent(100, 'ended');
                    try {
                        tracker.sendFinalStats(vjsPlayer.currentTime && vjsPlayer.currentTime() || 0, vjsPlayer.duration && vjsPlayer.duration() || 0);
                    } catch (e) {}
                });
            } else if (attempts >= 50) {
                clearInterval(checkInterval);
                console.log('[metrika] YouTube player not found, skipping');
            }
        }, 100);
        
        window.addEventListener('beforeunload', function() {
            if (tracker.watchStartTime) {
                tracker.totalWatchTime += (Date.now() - tracker.watchStartTime) / 1000;
            }
            tracker.sendFinalStats();
        });
    }


    function setupVideoTracking(counterId) {
        var ids = Utils.getPhpIds();
        var moduleId = ids.phpModuleId;
        var courseId = Utils.getCurrentCourseId(ids.phpCourseId);
        
        if (!moduleId) {
            var href = window.location.href;
            if (href.indexOf('/mod/') !== -1 && href.indexOf('/view.php') !== -1) {
                moduleId = Utils.getParam(href, 'id');
            }
        }

        console.log('[metrika] setting up video tracking, moduleId=', moduleId, 'courseId=', courseId);

        // Native video/audio
        var mediaElements = document.querySelectorAll('video, audio');
        for (var i = 0; i < mediaElements.length; i++) {
            trackVideoJS(counterId, mediaElements[i], moduleId, courseId);
        }

        // YouTube iframes
        var iframes = document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            var iframe = iframes[i];
            var src = iframe.src || '';
            if (src.indexOf('youtube.com') !== -1 || src.indexOf('youtu.be') !== -1) {
                trackYouTube(counterId, iframe, moduleId, courseId);
            }
        }

        // MutationObserver для динамически добавленных элементов
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;
                    
                    if (node.tagName && (node.tagName.toLowerCase() === 'video' || node.tagName.toLowerCase() === 'audio')) {
                        trackVideoJS(counterId, node, moduleId, courseId);
                    }
                    if (node.tagName && node.tagName.toLowerCase() === 'iframe') {
                        var src = node.src || '';
                        if (src.indexOf('youtube.com') !== -1 || src.indexOf('youtu.be') !== -1) {
                            trackYouTube(counterId, node, moduleId, courseId);
                        }
                    }
                    
                    var nested = node.querySelectorAll && node.querySelectorAll('video, audio, iframe');
                    if (nested) {
                        for (var i = 0; i < nested.length; i++) {
                            var elem = nested[i];
                            if (elem.tagName.toLowerCase() === 'video' || elem.tagName.toLowerCase() === 'audio') {
                                trackVideoJS(counterId, elem, moduleId, courseId);
                            } else if (elem.tagName.toLowerCase() === 'iframe') {
                                var src = elem.src || '';
                                if (src.indexOf('youtube.com') !== -1 || src.indexOf('youtu.be') !== -1) {
                                    trackYouTube(counterId, elem, moduleId, courseId);
                                }
                            }
                        }
                    }
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    window.MetrikaVideo = {
        setup: setupVideoTracking
    };
})(window);
