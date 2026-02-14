(function(window) {
    var Utils = window.MetrikaUtils;
    var WATCH_MILESTONES = [0, 25, 50, 75, 100];
    var TIMEUPDATE_THROTTLE = 500;
    var RETRY_INTERVALS = [500, 1000, 2000, 3000, 5000, 8000, 10000, 15000];

    var trackedNativeMedia = new Set();
    var trackedYouTubeIframes = new Set();

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

    function getSegmentIndex(percent) {
        if (percent < 25) return 0;
        if (percent < 50) return 1;
        if (percent < 75) return 2;
        return 3;
    }

    function getSegmentLabel(index) {
        var labels = ['0-25%', '25-50%', '50-75%', '75-100%'];
        return labels[index] || 'unknown';
    }

    function isVideoJSElement(element) {
        if (element.classList.contains('video-js') || element.classList.contains('vjs-tech')) {
            return true;
        }
        if (element.id && element.id.indexOf('videojs') !== -1) {
            return true;
        }
        if (element.closest && element.closest('.video-js')) {
            return true;
        }
        return false;
    }

    function isYouTubeUrl(src) {
        return src && (src.indexOf('youtube.com') !== -1 || src.indexOf('youtu.be') !== -1);
    }

    function isYouTubePlayer(playerEl) {
        return playerEl && (
            playerEl.classList.contains('vjs-youtube') ||
            (playerEl.querySelector && playerEl.querySelector('iframe[src*="youtube.com"]'))
        );
    }

    function getPlayerSource(player) {
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
        return mediaSrc;
    }

    function safeCall(fn, fallback) {
        try {
            return fn();
        } catch (e) {
            return fallback;
        }
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

        this.segmentWatchTime = [0, 0, 0, 0];
        this.currentSegment = -1;
        this.segmentStartTime = null;
    }

    VideoTracker.prototype.getWatchPercent = function(currentTime, duration) {
        if (!duration) return 0;
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
        this.sendEvent('video_watch', { watchPercent: percent, event: eventType });
        ym(this.counterId, 'reachGoal', 'video_watch_' + percent);
    };

    VideoTracker.prototype.sendPauseEvent = function(currentTime, duration) {
        this.pauseCount++;
        var pauseTimeMs = currentTime != null ? Math.round(currentTime * 1000) : null;
        var pausePercent = currentTime != null && duration ? this.getWatchPercent(currentTime, duration) : null;
        this.sendEvent('video_pause', {
            pauseCount: this.pauseCount,
            pauseTimeMs: pauseTimeMs,
            pausePercent: pausePercent
        });
    };

    VideoTracker.prototype.sendSeekEvent = function(isBackward, fromTime, toTime, duration) {
        this.seekCount++;
        if (isBackward) this.seekBackwardCount++;
        
        var fromPercent = this.getWatchPercent(fromTime, duration);
        var toPercent = this.getWatchPercent(toTime, duration);
        var fromSegment = getSegmentIndex(fromPercent);
        var toSegment = getSegmentIndex(toPercent);
        
        this.sendEvent('video_seek', {
            seekCount: this.seekCount,
            seekBackward: isBackward ? 1 : 0,
            fromSegment: getSegmentLabel(fromSegment),
            toSegment: getSegmentLabel(toSegment),
            fromTimeMs: Math.round(fromTime * 1000),
            toTimeMs: Math.round(toTime * 1000)
        });
    };

    VideoTracker.prototype.startSegmentTracking = function(currentTime, duration) {
        var percent = this.getWatchPercent(currentTime, duration);
        this.currentSegment = getSegmentIndex(percent);
        this.segmentStartTime = Date.now();
    };

    VideoTracker.prototype.stopSegmentTracking = function() {
        if (this.segmentStartTime !== null && this.currentSegment >= 0 && this.currentSegment < 4) {
            var elapsedMs = Date.now() - this.segmentStartTime;
            this.segmentWatchTime[this.currentSegment] += elapsedMs;
            this.totalWatchTime += elapsedMs;
        }
        this.segmentStartTime = null;
    };

    VideoTracker.prototype.updateSegmentTracking = function(currentTime, duration) {
        if (this.segmentStartTime === null) return;

        var percent = this.getWatchPercent(currentTime, duration);
        var newSegment = getSegmentIndex(percent);

        if (newSegment !== this.currentSegment) {
            this.stopSegmentTracking();
            this.currentSegment = newSegment;
            this.segmentStartTime = Date.now();
        }
    };

    VideoTracker.prototype.sendFinalStats = function(currentTime, duration) {
        this.stopSegmentTracking();
        var params = {
            finalPercent: this.getWatchPercent(currentTime || 0, duration || 0),
            pauseCount: this.pauseCount,
            seekCount: this.seekCount,
            seekBackwardCount: this.seekBackwardCount,
            totalWatchTimeMs: Math.round(this.totalWatchTime),
            segment_0_25_ms: Math.round(this.segmentWatchTime[0]),
            segment_25_50_ms: Math.round(this.segmentWatchTime[1]),
            segment_50_75_ms: Math.round(this.segmentWatchTime[2]),
            segment_75_100_ms: Math.round(this.segmentWatchTime[3])
        };
        if (duration && duration > 0) {
            params.videoDurationMs = Math.round(duration * 1000);
        }
        this.sendEvent('video_stats', params);
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

    VideoTracker.prototype.accumulateWatchTime = function() {
        if (this.watchStartTime) {
            this.totalWatchTime += Date.now() - this.watchStartTime;
            this.watchStartTime = null;
        }
    };

    function createMediaAccessor(source) {
        if (typeof source.currentTime === 'function') {
            return {
                getCurrentTime: function() { return safeCall(function() { return source.currentTime(); }, 0); },
                getDuration: function() { return safeCall(function() { return source.duration(); }, 0); }
            };
        }
        return {
            getCurrentTime: function() { return source.currentTime || 0; },
            getDuration: function() { return source.duration || 0; }
        };
    }

    function attachTrackingEvents(eventSource, tracker, mediaAccessor, useSegmentTracking) {
        var onPlay = function() {
            var currentTime = mediaAccessor.getCurrentTime();
            var duration = mediaAccessor.getDuration();

            if (useSegmentTracking) {
                tracker.startSegmentTracking(currentTime, duration);
            } else {
                tracker.watchStartTime = Date.now();
            }

            var percent = tracker.getWatchPercent(currentTime, duration);
            tracker.sendWatchEvent(percent, 'play');
        };

        var onPause = function() {
            var currentTime = mediaAccessor.getCurrentTime();
            var duration = mediaAccessor.getDuration();

            if (useSegmentTracking) {
                tracker.stopSegmentTracking();
            } else {
                tracker.accumulateWatchTime();
            }
            tracker.sendPauseEvent(currentTime, duration);
        };

        var onTimeupdate = function() {
            var now = Date.now();
            if (now - tracker.lastTimeupdate < TIMEUPDATE_THROTTLE) return;
            tracker.lastTimeupdate = now;

            var duration = mediaAccessor.getDuration();
            if (!duration) return;

            var currentTime = mediaAccessor.getCurrentTime();
            if (useSegmentTracking) {
                tracker.updateSegmentTracking(currentTime, duration);
            }
            tracker.checkMilestones(currentTime, duration);
        };

        var onSeeked = function() {
            var currentTime = mediaAccessor.getCurrentTime();
            var duration = mediaAccessor.getDuration();
            var fromTime = tracker.lastTime;
            var isBackward = currentTime < fromTime;
            tracker.lastTime = currentTime;
            tracker.sendSeekEvent(isBackward, fromTime, currentTime, duration);

            if (useSegmentTracking && tracker.segmentStartTime !== null) {
                tracker.stopSegmentTracking();
                tracker.startSegmentTracking(currentTime, duration);
            }
        };

        var onEnded = function() {
            if (useSegmentTracking) {
                tracker.stopSegmentTracking();
            } else {
                tracker.accumulateWatchTime();
            }
            tracker.sendWatchEvent(100, 'ended');
            tracker.sendFinalStats(mediaAccessor.getCurrentTime(), mediaAccessor.getDuration());
        };

        var onBeforeUnload = function() {
            if (!useSegmentTracking) {
                tracker.accumulateWatchTime();
            }
            tracker.sendFinalStats(mediaAccessor.getCurrentTime(), mediaAccessor.getDuration());
        };

        if (eventSource.on) {
            eventSource.on('play', onPlay);
            eventSource.on('pause', onPause);
            eventSource.on('timeupdate', onTimeupdate);
            eventSource.on('seeked', onSeeked);
            eventSource.on('ended', onEnded);
        } else {
            eventSource.addEventListener('play', onPlay);
            eventSource.addEventListener('pause', onPause);
            eventSource.addEventListener('timeupdate', onTimeupdate);
            eventSource.addEventListener('seeked', onSeeked);
            eventSource.addEventListener('ended', onEnded);
        }

        window.addEventListener('beforeunload', onBeforeUnload);
    }

    function trackVideoJSPlayer(counterId, player, moduleId, courseId) {
        var playerElement = player.el && player.el();
        var elementModuleId = resolveModuleIdForElement(playerElement || document.body, moduleId);
        var mediaSrc = getPlayerSource(player);
        var mediaId = normalizeSrc(mediaSrc) || player.id() || 'videojs_unknown';
        var tracker = new VideoTracker(counterId, mediaId, 'videojs', elementModuleId, courseId);
        var mediaAccessor = createMediaAccessor(player);

        attachTrackingEvents(player, tracker, mediaAccessor, true);
    }

    function trackNativeMedia(counterId, element, moduleId, courseId) {
        if (!element || (element.tagName !== 'VIDEO' && element.tagName !== 'AUDIO')) {
            return;
        }

        if (isVideoJSElement(element)) {
            return;
        }

        var elementKey = element.id || element.src || element.currentSrc;
        if (trackedNativeMedia.has(elementKey)) {
            return;
        }
        trackedNativeMedia.add(elementKey);

        var elementModuleId = resolveModuleIdForElement(element, moduleId);
        var mediaSrc = element.currentSrc || element.src;
        if (!mediaSrc && element.querySelector) {
            var sourceEl = element.querySelector('source');
            if (sourceEl) mediaSrc = sourceEl.src;
        }

        var mediaId = normalizeSrc(mediaSrc) || element.id || 'unknown';
        var mediaType = element.tagName.toLowerCase();
        var tracker = new VideoTracker(counterId, mediaId, mediaType, elementModuleId, courseId);
        var mediaAccessor = createMediaAccessor(element);

        attachTrackingEvents(element, tracker, mediaAccessor, true);
    }

    function trackVideoJSYouTube(counterId, player, moduleId, courseId) {
        var playerElement = player.el && player.el();
        var elementModuleId = resolveModuleIdForElement(playerElement || document.body, moduleId);
        var mediaSrc = getPlayerSource(player);
        var mediaId = normalizeSrc(mediaSrc) || player.id() || 'videojs_youtube_unknown';

        if (playerElement) {
            var youtubeIframe = playerElement.querySelector('iframe[src*="youtube.com"]');
            if (youtubeIframe) {
                trackedYouTubeIframes.add(youtubeIframe.id || youtubeIframe.src);
            }
        }

        var tracker = new VideoTracker(counterId, mediaId, 'videojs_youtube', elementModuleId, courseId);
        var mediaAccessor = createMediaAccessor(player);

        attachTrackingEvents(player, tracker, mediaAccessor, false);
    }

    function trackYouTube(counterId, iframe, moduleId, courseId) {
        if (!iframe || !isYouTubeUrl(iframe.src)) {
            return;
        }

        var iframeKey = iframe.id || iframe.src;
        if (trackedYouTubeIframes.has(iframeKey)) {
            return;
        }
        trackedYouTubeIframes.add(iframeKey);

        var elementModuleId = resolveModuleIdForElement(iframe, moduleId);
        var mediaId = normalizeSrc(iframe.src) || iframe.id || 'youtube_unknown';
        var tracker = new VideoTracker(counterId, mediaId, 'youtube', elementModuleId, courseId);

        var attempts = 0;
        var checkInterval = setInterval(function() {
            attempts++;
            var vjsPlayer = findVideoJSPlayerForIframe(iframe);

            if (vjsPlayer) {
                clearInterval(checkInterval);
                var mediaAccessor = createMediaAccessor(vjsPlayer);
                attachTrackingEvents(vjsPlayer, tracker, mediaAccessor, false);
            } else if (attempts >= 10) {
                clearInterval(checkInterval);
            }
        }, 100);

        window.addEventListener('beforeunload', function() {
            tracker.accumulateWatchTime();
            tracker.sendFinalStats(0, 0);
        });
    }

    function findVideoJSPlayerForIframe(iframe) {
        if (!window.videojs) return null;

        try {
            var players = window.videojs.getPlayers();

            for (var playerId in players) {
                var vjsPlayer = players[playerId];
                if (!vjsPlayer) continue;
                var playerEl = vjsPlayer.el && vjsPlayer.el();
                if (playerEl && (playerEl.contains(iframe) || playerEl.querySelector('iframe') === iframe)) {
                    return vjsPlayer;
                }
            }

            if (iframe.id && iframe.id.indexOf('_youtube_api') !== -1) {
                var playerIdMatch = iframe.id.match(/^(.+)_youtube_api$/);
                if (playerIdMatch && players[playerIdMatch[1]]) {
                    return players[playerIdMatch[1]];
                }
            }

            var parentVideoJS = iframe.closest('.video-js');
            if (parentVideoJS && parentVideoJS.id && players[parentVideoJS.id]) {
                return players[parentVideoJS.id];
            }

            var parentContainer = iframe.parentElement;
            if (parentContainer && parentContainer.parentElement) {
                var videoEl = parentContainer.parentElement.querySelector('video.video-js, video.vjs-tech');
                if (videoEl && videoEl.id && players[videoEl.id]) {
                    return players[videoEl.id];
                }
            }
        } catch (e) {}

        return null;
    }

    function getVideoJS() {
        if (window.videojs) return window.videojs;
        if (window.require && window.require.defined && window.require.defined('media_videojs/video-lazy')) {
            try {
                return window.require('media_videojs/video-lazy');
            } catch (e) {}
        }
        return null;
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

        var trackedPlayers = new Set();

        function trackAllVideoJSPlayers() {
            var videojs = getVideoJS();

            if (!videojs) {
                var vjsContainers = document.querySelectorAll('.video-js');
                for (var i = 0; i < vjsContainers.length; i++) {
                    var container = vjsContainers[i];
                    if (container.player && !trackedPlayers.has(container.id)) {
                        trackedPlayers.add(container.id);
                        var playerEl = container.player.el && container.player.el();
                        if (isYouTubePlayer(playerEl)) {
                            trackVideoJSYouTube(counterId, container.player, moduleId, courseId);
                        } else {
                            trackVideoJSPlayer(counterId, container.player, moduleId, courseId);
                        }
                    }
                }
                return;
            }

            var players = videojs.getPlayers ? videojs.getPlayers() : {};

            for (var playerId in players) {
                var player = players[playerId];
                if (!player || trackedPlayers.has(playerId)) continue;

                trackedPlayers.add(playerId);
                var playerEl = player.el && player.el();

                if (isYouTubePlayer(playerEl)) {
                    trackVideoJSYouTube(counterId, player, moduleId, courseId);
                } else {
                    trackVideoJSPlayer(counterId, player, moduleId, courseId);
                }
            }
        }

        function trackMediaElement(elem) {
            if (elem.tagName === 'VIDEO' || elem.tagName === 'AUDIO') {
                if (!isVideoJSElement(elem)) {
                    trackNativeMedia(counterId, elem, moduleId, courseId);
                }
            } else if (elem.tagName === 'IFRAME' && isYouTubeUrl(elem.src)) {
                trackYouTube(counterId, elem, moduleId, courseId);
            }
        }

        trackAllVideoJSPlayers();

        RETRY_INTERVALS.forEach(function(delay) {
            setTimeout(trackAllVideoJSPlayers, delay);
        });

        document.addEventListener('play', function(e) {
            if (e.target && (e.target.tagName === 'VIDEO' || e.target.tagName === 'AUDIO')) {
                setTimeout(trackAllVideoJSPlayers, 100);
            }
        }, true);

        var mediaElements = document.querySelectorAll('video, audio, iframe');
        for (var i = 0; i < mediaElements.length; i++) {
            trackMediaElement(mediaElements[i]);
        }

        var observer = new MutationObserver(function(mutations) {
            var needsVideoJSCheck = false;

            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;

                    if (node.classList && node.classList.contains('video-js')) {
                        needsVideoJSCheck = true;
                    }

                    if (node.tagName) {
                        trackMediaElement(node);
                    }

                    var nested = node.querySelectorAll && node.querySelectorAll('video, audio, iframe, .video-js');
                    if (nested) {
                        for (var i = 0; i < nested.length; i++) {
                            var elem = nested[i];
                            if (elem.classList && elem.classList.contains('video-js')) {
                                needsVideoJSCheck = true;
                            }
                            trackMediaElement(elem);
                        }
                    }
                });
            });

            if (needsVideoJSCheck) {
                setTimeout(trackAllVideoJSPlayers, 500);
            }
        });

        observer.observe(document.body, { childList: true, subtree: true });
    }

    window.MetrikaVideo = {
        setup: setupVideoTracking
    };
})(window);
