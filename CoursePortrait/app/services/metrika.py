import aiohttp
import os
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetrikaService:
    
    def __init__(self, counter_id: Optional[str] = None, oauth_token: Optional[str] = None):
        self.counter_id = counter_id or os.getenv("METRIKA_COUNTER_ID")
        self.oauth_token = oauth_token or os.getenv("METRIKA_OAUTH_TOKEN")
        self.base_url = "https://api-metrica.yandex.net/stat/v1/data"
    
    def _parse_event_key(self, event_key: str) -> Dict[str, str]:
        params = {}
        if not event_key:
            return params
        
        for pair in event_key.split(';'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key.strip()] = value.strip()
        
        return params
    
    async def pull_events(
        self,
        course_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Dict]:
        if not self.counter_id or not self.oauth_token:
            logger.warning("Metrika credentials not configured, returning mock data")
            return self._get_mock_metrics(course_id)
        
        if date_from is None:
            date_from = datetime.now() - timedelta(days=30)
        if date_to is None:
            date_to = datetime.now()
        
        try:
            events = await self._fetch_events_from_api(course_id, date_from, date_to)
            
            aggregated_metrics = self._aggregate_events_by_module(events, course_id)
            
            if not aggregated_metrics:
                return self._get_mock_metrics(course_id)
            
            return aggregated_metrics
        
        except Exception as e:
            logger.error(f"Error fetching Metrika data: {e}", exc_info=True)
            return self._get_mock_metrics(course_id)
    
    async def _fetch_events_from_api(
        self,
        course_id: int,
        date_from: datetime,
        date_to: datetime
    ) -> List[Dict]:
        all_events: List[Dict] = []
        
        try:
            params = {
                "ids": self.counter_id,
                "metrics": "ym:ep:eventsNumber",  
                "dimensions": "ym:ep:eventParamsLevel1,ym:ep:eventParamsLevel2,ym:ep:eventParamsLevel3,ym:ep:eventParamsLevel4,ym:ep:eventParamsLevel5",
                "date1": date_from.strftime("%Y-%m-%d"),
                "date2": date_to.strftime("%Y-%m-%d"),
                "limit": 10000,
            }
            
            headers = {
                "Authorization": f"OAuth {self.oauth_token}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        parsed_events = self._parse_api_response(data, course_id)
                        if parsed_events:
                            all_events.extend(parsed_events)
                    else:
                        error_text = await resp.text()
                        logger.warning(f"Metrika API error {resp.status}: {error_text}")
                        return []
        
        except Exception as e:
            logger.error(f"Error fetching events from API: {e}")
            return []
        
        return all_events

    async def pull_video_analytics(
        self,
        course_id: int,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        module_id: Optional[int] = None,
        media_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        - eventType=video_watch (watchPercent)
        - eventType=video_pause (pauseCount)
        - eventType=video_seek (seekCount, seekBackward=0/1)
        - eventType=video_stats (finalPercent, pauseCount, seekCount, seekBackwardCount, totalWatchTimeMs,
          segment_0_25_ms, segment_25_50_ms, segment_50_75_ms, segment_75_100_ms, ...)
        """
        if not self.counter_id or not self.oauth_token:
            logger.warning("Metrika credentials not configured, returning mock video analytics")
            return self._get_mock_video_analytics(course_id)

        if date_from is None:
            date_from = datetime.now() - timedelta(days=30)
        if date_to is None:
            date_to = datetime.now()

        try:
            events = await self._fetch_events_from_api(course_id, date_from, date_to)
            analytics = self._aggregate_video_analytics(events, course_id, module_id=module_id, media_id=media_id)
            if not analytics:
                return self._get_mock_video_analytics(course_id)
            return analytics
        except Exception as e:
            logger.error(f"Error fetching video analytics from Metrika: {e}", exc_info=True)
            return self._get_mock_video_analytics(course_id)

    @staticmethod
    def _get_segment_by_percent(percent: float) -> str:
        if percent < 25:
            return "0-25"
        elif percent < 50:
            return "25-50"
        elif percent < 75:
            return "50-75"
        else:
            return "75-100"

    def _aggregate_video_analytics(
        self,
        events: List[Dict],
        course_id: int,
        module_id: Optional[int] = None,
        media_id: Optional[str] = None,
    ) -> List[Dict]:
        logger.info(f"_aggregate_video_analytics: received {len(events)} events for course {course_id}")
        
        # Debug: log first few events to see their structure
        video_events_count = 0
        for ev in events[:10]:
            et = ev.get("eventType", "")
            if et.startswith("video_"):
                video_events_count += 1
                logger.debug(f"Video event sample: eventType={et}, moduleId={ev.get('moduleId')}, mediaId={ev.get('mediaId')[:50] if ev.get('mediaId') else None}...")
        logger.info(f"Found {video_events_count} video events in first 10 events")
        
        segment_keys = [
            ("0-25", "segment_0_25_ms"),
            ("25-50", "segment_25_50_ms"),
            ("50-75", "segment_50_75_ms"),
            ("75-100", "segment_75_100_ms"),
        ]
        segment_labels = [label for label, _ in segment_keys]

        per_media: Dict[str, Dict] = {}

        def _to_int(v, default=0):
            try:
                return int(float(v))
            except Exception:
                return default

        def _to_float(v, default=0.0):
            try:
                return float(v)
            except Exception:
                return default

        for ev in events:
            if module_id is not None:
                try:
                    if _to_int(ev.get("moduleId")) != int(module_id):
                        continue
                except Exception:
                    continue
            if media_id is not None:
                if str(ev.get("mediaId", "")) != str(media_id):
                    continue

            et = ev.get("eventType")
            if et not in {"video_watch", "video_pause", "video_seek", "video_stats"}:
                continue

            mid = str(ev.get("mediaId") or "")
            if not mid:
                continue

            rec = per_media.setdefault(
                mid,
                {
                    "courseId": course_id,
                    "moduleId": _to_int(ev.get("moduleId"), 0),
                    "mediaId": mid,
                    "mediaType": ev.get("mediaType", "video"),
                    "events": 0,
                    "uniqueUsers": set(),
                    # watch milestones
                    "watchPercents": [],
                    "finalPercents": [],
                    # pauses / seeks (aggregated)
                    "pauseCount": 0,
                    "seekCount": 0,
                    "seekBackwardCount": 0,
                    # segment watch times
                    "segments": {label: [] for (label, _) in segment_keys},
                    "totalWatchTimeMs": [],
                    "videoDurationMs": None,
                    "pausesBySegment": {label: {"count": 0, "times": []} for label in segment_labels},
                    "seekPatterns": {},  # (fromSeg, toSeg, isBackward) -> {count, fromTimes, toTimes}
                },
            )

            rec["events"] += _to_int(ev.get("_count"), 1)
            if ev.get("userId") is not None:
                rec["uniqueUsers"].add(str(ev.get("userId")))

            if et == "video_watch":
                rec["watchPercents"].append(_to_float(ev.get("watchPercent"), 0.0))
            elif et == "video_pause":
                rec["pauseCount"] = max(rec["pauseCount"], _to_int(ev.get("pauseCount"), 0))
                pause_percent = _to_float(ev.get("pausePercent"), -1)
                if pause_percent >= 0:
                    segment = self._get_segment_by_percent(pause_percent)
                    rec["pausesBySegment"][segment]["count"] += _to_int(ev.get("_count"), 1)
                    pause_time = _to_float(ev.get("pauseTimeMs"), 0)
                    if pause_time > 0:
                        rec["pausesBySegment"][segment]["times"].append(pause_time)
            elif et == "video_seek":
                logger.debug(f"video_seek event: keys={list(ev.keys())}, fromTimeMs={ev.get('fromTimeMs')}, toTimeMs={ev.get('toTimeMs')}, fromSegment={ev.get('fromSegment')}, toSegment={ev.get('toSegment')}, fromPercent={ev.get('fromPercent')}, toPercent={ev.get('toPercent')}")
                rec["seekCount"] = max(rec["seekCount"], _to_int(ev.get("seekCount"), 0))
                is_backward = _to_int(ev.get("seekBackward"), 0) == 1
                if is_backward:
                    rec["seekBackwardCount"] += _to_int(ev.get("_count"), 1)

                raw_from = ev.get("fromTimeMs")
                raw_to = ev.get("toTimeMs")
                from_time = _to_float(raw_from, -1)
                to_time = _to_float(raw_to, -1)

                from_seg = ev.get("fromSegment")
                to_seg = ev.get("toSegment")
                if not (from_seg and to_seg):
                    from_percent = _to_float(ev.get("fromPercent"), -1)
                    to_percent = _to_float(ev.get("toPercent"), -1)
                    if from_percent >= 0 and to_percent >= 0:
                        from_seg = self._get_segment_by_percent(from_percent)
                        to_seg = self._get_segment_by_percent(to_percent)

                if not (from_seg and to_seg) and rec["videoDurationMs"] and rec["videoDurationMs"] > 0:
                    duration = rec["videoDurationMs"]
                    if from_time >= 0:
                        from_pct = (from_time / duration) * 100
                        from_seg = self._get_segment_by_percent(from_pct)
                    if to_time >= 0:
                        to_pct = (to_time / duration) * 100
                        to_seg = self._get_segment_by_percent(to_pct)

                if from_seg and to_seg:
                    from_seg = from_seg.rstrip('%')
                    to_seg = to_seg.rstrip('%')
                    key = (from_seg, to_seg, is_backward)
                    pat = rec["seekPatterns"].setdefault(key, {"count": 0, "fromTimes": [], "toTimes": []})
                    pat["count"] += _to_int(ev.get("_count"), 1)
                    if from_time >= 0:
                        pat["fromTimes"].append(from_time)
                    if to_time >= 0:
                        pat["toTimes"].append(to_time)
                else:
                    logger.warning(f"video_seek event dropped (no segment info): {ev}")
            elif et == "video_stats":
                rec["finalPercents"].append(_to_float(ev.get("finalPercent"), 0.0))
                rec["pauseCount"] = max(rec["pauseCount"], _to_int(ev.get("pauseCount"), 0))
                rec["seekCount"] = max(rec["seekCount"], _to_int(ev.get("seekCount"), 0))
                rec["seekBackwardCount"] = max(rec["seekBackwardCount"], _to_int(ev.get("seekBackwardCount"), 0))
                rec["totalWatchTimeMs"].append(_to_float(ev.get("totalWatchTimeMs"), 0.0))
                duration = _to_float(ev.get("videoDurationMs"), 0)
                if duration > 0 and rec["videoDurationMs"] is None:
                    rec["videoDurationMs"] = duration
                for label, key in segment_keys:
                    rec["segments"][label].append(_to_float(ev.get(key), 0.0))

        result: List[Dict] = []
        for mid, rec in per_media.items():
            unique_users = rec.pop("uniqueUsers")
            pauses_by_segment = rec.pop("pausesBySegment")
            seek_patterns_raw = rec.pop("seekPatterns")
            video_duration = rec.pop("videoDurationMs")
            seg_stats = []

            seg_avgs = {}
            for label, _key in segment_keys:
                vals = rec["segments"][label]
                avg = (sum(vals) / len(vals)) if vals else 0.0
                seg_avgs[label] = avg
            total_seg_time = sum(seg_avgs.values()) or 1.0
            
            segment_duration = video_duration / 4 if video_duration else None

            for label in seg_avgs:
                avg_time = seg_avgs[label]
                share = avg_time / total_seg_time
                watch_percent = None
                if segment_duration and segment_duration > 0:
                    watch_percent = min(100.0, (avg_time / segment_duration) * 100)
                
                seg_stats.append(
                    {
                        "segment": label,
                        "avgWatchTime": avg_time,
                        "segmentDuration": segment_duration,
                        "watchPercent": watch_percent,
                        "watchShare": share,
                        "pauseCount": pauses_by_segment[label]["count"],
                        "isWellWatched": watch_percent is not None and watch_percent >= 90,
                        "isLeastWatched": False,
                    }
                )

            if seg_stats:
                sorted_segs = sorted(
                    seg_stats,
                    key=lambda x: x["watchPercent"] if x["watchPercent"] is not None else x["watchShare"] * 100
                )
                if sorted_segs and not sorted_segs[0]["isWellWatched"]:
                    sorted_segs[0]["isLeastWatched"] = True

            least_watched = [s["segment"] for s in sorted(seg_stats, key=lambda x: x["watchShare"])[:2]]
            most_watched = [s["segment"] for s in sorted(seg_stats, key=lambda x: x["watchShare"], reverse=True)[:2]]

            avg_final = (sum(rec["finalPercents"]) / len(rec["finalPercents"])) if rec["finalPercents"] else None
            avg_watch = (sum(rec["watchPercents"]) / len(rec["watchPercents"])) if rec["watchPercents"] else None
            avg_total_watch_time = (
                (sum(rec["totalWatchTimeMs"]) / len(rec["totalWatchTimeMs"])) if rec["totalWatchTimeMs"] else None
            )
            
            pause_hotspots = []
            for label in segment_labels:
                pause_data = pauses_by_segment[label]
                if pause_data["count"] > 0:
                    avg_pause_time = None
                    if pause_data["times"]:
                        avg_pause_time = sum(pause_data["times"]) / len(pause_data["times"])
                    pause_hotspots.append({
                        "segment": label,
                        "pauseCount": pause_data["count"],
                        "avgPauseTime": avg_pause_time,
                    })
            pause_hotspots.sort(key=lambda x: x["pauseCount"], reverse=True)
            
            seek_patterns = []
            for (from_seg, to_seg, is_backward), pat in seek_patterns_raw.items():
                logger.info(f"seekPattern aggregation: {from_seg}->{to_seg} backward={is_backward}, count={pat['count']}, fromTimes={pat['fromTimes']}, toTimes={pat['toTimes']}")
                entry = {
                    "fromSegment": from_seg,
                    "toSegment": to_seg,
                    "count": pat["count"],
                    "isBackward": is_backward,
                }
                if pat["fromTimes"]:
                    entry["avgFromTimeMs"] = sum(pat["fromTimes"]) / len(pat["fromTimes"])
                if pat["toTimes"]:
                    entry["avgToTimeMs"] = sum(pat["toTimes"]) / len(pat["toTimes"])

                avg_from = entry.get("avgFromTimeMs", 0)
                avg_to = entry.get("avgToTimeMs", 0)
                if avg_from == 0 and avg_to == 0:
                    logger.info(f"seekPattern skipped (both times 0): {entry}")
                    continue
                logger.info(f"seekPattern result entry: {entry}")
                seek_patterns.append(entry)
            seek_patterns.sort(key=lambda x: x["count"], reverse=True)

            result.append(
                {
                    "courseId": rec["courseId"],
                    "moduleId": rec["moduleId"],
                    "mediaId": rec["mediaId"],
                    "mediaType": rec["mediaType"],
                    "moduleName": None, 
                    "videoDurationMs": video_duration,
                    "uniqueUsers": len(unique_users),
                    "events": rec["events"],
                    "avgWatchPercent": avg_watch,
                    "avgFinalPercent": avg_final,
                    "pauseCount": rec["pauseCount"],
                    "seekCount": rec["seekCount"],
                    "seekBackwardCount": rec["seekBackwardCount"],
                    "avgTotalWatchTime": avg_total_watch_time,
                    "segments": seg_stats,
                    "leastWatchedSegments": least_watched,
                    "mostWatchedSegments": most_watched,
                    "pauseHotspots": pause_hotspots,
                    "seekPatterns": seek_patterns,
                }
            )

        result.sort(key=lambda x: (x.get("uniqueUsers", 0), x.get("events", 0)), reverse=True)
        return result

    def _get_mock_video_analytics(self, course_id: int) -> List[Dict]:
        import random
        videos = []
        labels = ["0-25", "25-50", "50-75", "75-100"]
        
        for i in range(random.randint(2, 5)):
            mid = f"/pluginfile.php/{course_id}/mod_resource/content/video_{i+1}.mp4"
            
            video_duration = random.uniform(120, 900)
            segment_duration = video_duration / 4
            
            segs = []
            shares = [random.uniform(0.1, 0.4) for _ in range(4)]
            total = sum(shares) or 1.0
            shares = [s / total for s in shares]
            
            for idx, (label, share) in enumerate(zip(labels, shares)):
                avg_watch_time = share * random.uniform(30, 180)
                watch_percent = min(100.0, (avg_watch_time / segment_duration) * 100) if segment_duration > 0 else None
                pause_count = random.randint(0, 5)
                
                segs.append({
                    "segment": label,
                    "avgWatchTime": avg_watch_time,
                    "segmentDuration": segment_duration,
                    "watchPercent": watch_percent,
                    "watchShare": share,
                    "pauseCount": pause_count,
                    "isWellWatched": watch_percent is not None and watch_percent >= 90,
                    "isLeastWatched": False,
                })
            
            sorted_segs = sorted(segs, key=lambda x: x["watchPercent"] if x["watchPercent"] else 0)
            if sorted_segs and not sorted_segs[0]["isWellWatched"]:
                sorted_segs[0]["isLeastWatched"] = True
            
            least = [s["segment"] for s in sorted(segs, key=lambda x: x["watchShare"])[:2]]
            most = [s["segment"] for s in sorted(segs, key=lambda x: x["watchShare"], reverse=True)[:2]]
            
            pause_hotspots = []
            for label in labels:
                if random.random() > 0.3: 
                    pause_hotspots.append({
                        "segment": label,
                        "pauseCount": random.randint(1, 15),
                        "avgPauseTime": random.uniform(5, 60),
                    })
            pause_hotspots.sort(key=lambda x: x["pauseCount"], reverse=True)
            
            seek_patterns = []
            possible_patterns = [
                ("50-75", "0-25", True), 
                ("75-100", "25-50", True), 
                ("25-50", "50-75", False), 
                ("0-25", "75-100", False), 
                ("50-75", "25-50", True),  
            ]
            for from_seg, to_seg, is_backward in possible_patterns:
                if random.random() > 0.4:
                    seek_patterns.append({
                        "fromSegment": from_seg,
                        "toSegment": to_seg,
                        "count": random.randint(1, 12),
                        "isBackward": is_backward,
                    })
            seek_patterns.sort(key=lambda x: x["count"], reverse=True)

            videos.append(
                {
                    "courseId": course_id,
                    "moduleId": random.randint(1, 20),
                    "mediaId": mid,
                    "mediaType": "video",
                    "moduleName": f"Ð’Ð¸Ð´ÐµÐ¾-Ð»ÐµÐºÑ†Ð¸Ñ {i+1}", 
                    "videoDurationMs": video_duration,
                    "uniqueUsers": random.randint(5, 25),
                    "events": random.randint(50, 300),
                    "avgWatchPercent": random.uniform(20, 95),
                    "avgFinalPercent": random.uniform(30, 100),
                    "pauseCount": random.randint(0, 10),
                    "seekCount": random.randint(0, 20),
                    "seekBackwardCount": random.randint(0, 10),
                    "avgTotalWatchTime": random.uniform(60, video_duration),
                    "segments": segs,
                    "leastWatchedSegments": least,
                    "mostWatchedSegments": most,
                    "pauseHotspots": pause_hotspots,
                    "seekPatterns": seek_patterns,
                }
            )
        return videos
    
    def _parse_api_response(self, data: Dict, course_id: int) -> List[Dict]:
        events = []
        
        if "data" not in data:
            logger.warning("_parse_api_response: no 'data' key in response")
            return events
        
        logger.info(f"_parse_api_response: processing {len(data.get('data', []))} items for course {course_id}")
        
        for item in data.get("data", []):
            dimensions = item.get("dimensions", [])
            metrics = item.get("metrics", [])
            
            if not dimensions:
                continue
            
            event_count = metrics[0] if metrics else 0
            event_params = {}
            
            for dim in dimensions:
                param_string = dim.get("name", "")
                if param_string:
                    parsed = self._parse_event_key(param_string)
                    event_params.update(parsed)
            
            event_course_id = event_params.get("courseId")
            if event_course_id:
                try:
                    if int(event_course_id) != course_id:
                        continue 
                except (ValueError, TypeError):
                    continue
            else:
                found_course_id = False
                for dim in dimensions:
                    param_string = dim.get("name", "")
                    if param_string and f"courseId={course_id}" in param_string:
                        found_course_id = True
                        break
                
                if not found_course_id:
                    continue
            
            if event_params:
                event_params["_count"] = event_count
                events.append(event_params)
            elif dimensions:
                event_params = {
                    "raw_params": [dim.get("name", "") for dim in dimensions],
                    "_count": event_count
                }
                events.append(event_params)
        
        return events
    
    def _aggregate_events_by_module(
        self,
        events: List[Dict],
        course_id: int
    ) -> List[Dict]:
        module_sessions = defaultdict(list)  # moduleId -> [durationMs, ...]
        module_views = defaultdict(int)  # moduleId -> count
        module_unique_students = defaultdict(set)  # moduleId -> {userId, ...}
        module_event_counts = defaultdict(int)  # moduleId -> total event count (fallback for studentCount)
        module_steps = {}  # moduleId -> step
        module_sequences = defaultdict(list)  # userId -> [moduleId, ...]
        video_watch_data = defaultdict(list)  # moduleId -> [watchPercent, ...]
        video_stats_data = defaultdict(list)  # moduleId -> [{finalPercent, pauseCount, ...}, ...]
        video_pause_counts = defaultdict(int)  # moduleId -> total_pause_count
        module_user_visits = defaultdict(lambda: defaultdict(int))  # moduleId -> {userId -> visitCount}
        
        for event in events:
            event_type = event.get("eventType", "")
            module_id = event.get("moduleId")
            
            if not module_id:
                module_id = event.get("cmid")
            
            if not module_id:
                continue
            
            try:
                module_id = int(module_id)
            except (ValueError, TypeError):
                continue
            
            user_id = event.get("userId")
            activity_type = event.get("activityType", "")
            is_view = activity_type == "view" or event_type in ("module_view", "module_attempt")

            if user_id:
                module_unique_students[module_id].add(str(user_id))
                if is_view or event_type == "":
                    module_sequences[user_id].append(module_id)

            event_count = event.get("_count", 1)
            module_event_counts[module_id] += event_count

            step = event.get("step")
            if step:
                try:
                    module_steps[module_id] = int(step)
                except (ValueError, TypeError):
                    pass

            duration_ms = event.get("durationMs") or event.get("stepDurationMs")
            if duration_ms:
                try:
                    module_sessions[module_id].append(float(duration_ms))
                except (ValueError, TypeError):
                    pass

            if is_view:
                module_views[module_id] += event.get("_count", 1)
                if user_id:
                    module_user_visits[module_id][str(user_id)] += event.get("_count", 1)
            
            elif event_type == "video_watch":
                watch_percent = event.get("watchPercent")
                if watch_percent:
                    try:
                        video_watch_data[module_id].append(float(watch_percent))
                    except (ValueError, TypeError):
                        pass
            
            elif event_type == "video_stats":
                stats = {
                    "finalPercent": float(event.get("finalPercent", 0)),
                    "pauseCount": int(event.get("pauseCount", 0)),
                    "seekCount": int(event.get("seekCount", 0)),
                    "totalWatchTimeMs": float(event.get("totalWatchTimeMs", 0))
                }
                video_stats_data[module_id].append(stats)
            
            elif event_type == "video_pause":
                pause_count = event.get("pauseCount")
                if pause_count:
                    try:
                        video_pause_counts[module_id] = max(
                            video_pause_counts[module_id],
                            int(pause_count)
                        )
                    except (ValueError, TypeError):
                        pass
        
        all_module_ids = set()
        all_module_ids.update(module_sessions.keys())
        all_module_ids.update(module_views.keys())
        all_module_ids.update(module_unique_students.keys())
        all_module_ids.update(module_event_counts.keys())
        all_module_ids.update(video_watch_data.keys())
        all_module_ids.update(video_stats_data.keys())
        all_module_ids.update(video_pause_counts.keys())
        
        aggregated_metrics = []
        
        for module_id in all_module_ids:
            sessions = module_sessions.get(module_id, [])
            avg_duration_ms = sum(sessions) / len(sessions) if sessions else 0.0
            
            unique_students = module_unique_students.get(module_id, set())
            if unique_students:
                student_count = len(unique_students)
            else:
                event_count = module_event_counts.get(module_id, 0)

                student_count = max(1, event_count // 2) if event_count > 0 else 0
            
            watch_percents = video_watch_data.get(module_id, [])
            stats_list = video_stats_data.get(module_id, [])
            
            final_percents = [s["finalPercent"] for s in stats_list]
            all_watch_percents = watch_percents + final_percents
            
            has_video = len(all_watch_percents) > 0 or len(stats_list) > 0
            
            if has_video:
                watch_percent = max(all_watch_percents) / 100.0 if all_watch_percents else 0.0
            else:
                if avg_duration_ms > 0:
                    watch_percent = min(1.0, avg_duration_ms / 60000.0)
                else:
                    watch_percent = 0.0
            
            pause_count = video_pause_counts.get(module_id, 0)
            if stats_list:
                avg_pause = sum(s["pauseCount"] for s in stats_list) / len(stats_list)
                pause_count = max(pause_count, int(avg_pause))
            
            
            step = module_steps.get(module_id, module_id)  
            
            dropout_rate = self._calculate_dropout_rate(module_id, module_sequences)

            user_visits = module_user_visits.get(module_id, {})
            if user_visits:
                avg_return_visits = sum(max(0, v - 1) for v in user_visits.values()) / len(user_visits)
            else:
                avg_return_visits = 0.0

            aggregated_metrics.append({
                "moduleId": module_id,
                "avgDurationMs": avg_duration_ms,
                "watchPercent": watch_percent,
                "dropoutRate": dropout_rate,
                "studentCount": student_count,
                "pauseCount": pause_count,
                "step": step,
                "returnVisits": avg_return_visits,
                "sectionId": None
            })
        
        aggregated_metrics.sort(key=lambda x: x.get("step", 0))
        
        return aggregated_metrics
    
    def _calculate_dropout_rate(
        self,
        module_id: int,
        module_sequences: Dict[str, List[int]]
    ) -> float:
        if not module_sequences:
            return 0.0
        
        total_students_with_module = 0
        students_dropped_after = 0
        
        for user_id, sequence in module_sequences.items():
            if module_id in sequence:
                total_students_with_module += 1
                if sequence[-1] == module_id:
                    students_dropped_after += 1
        
        if total_students_with_module == 0:
            return 0.0
        
        return students_dropped_after / total_students_with_module
    
    async def get_funnel_stats(self, course_id: int, date_from=None, date_to=None) -> Dict:
        if not self.counter_id or not self.oauth_token:
            return {"backwardNavigationRate": 0.0, "avgCourseCompletionTimeMs": 0, "avgSessionsPerUser": 0.0}

        if date_from is None:
            date_from = datetime.now() - timedelta(days=30)
        if date_to is None:
            date_to = datetime.now()

        try:
            events = await self._fetch_events_from_api(course_id, date_from, date_to)
        except Exception as e:
            logger.error(f"Error fetching events for funnel stats: {e}")
            return {"backwardNavigationRate": 0.0, "avgCourseCompletionTimeMs": 0, "avgSessionsPerUser": 0.0}

        total_navigations = 0
        backward_navigations = 0
        module_step_map = {}
        for ev in events:
            activity_type = ev.get("activityType", "")
            if activity_type == "view":
                mid = ev.get("moduleId")
                step = ev.get("step")
                if mid and step:
                    try:
                        module_step_map[int(mid)] = int(step)
                    except (ValueError, TypeError):
                        pass

        for ev in events:
            activity_type = ev.get("activityType", "")
            if activity_type != "view":
                continue
            mid = ev.get("moduleId")
            prev_mid = ev.get("prevModuleId")
            if not mid or not prev_mid:
                continue
            try:
                mid_int = int(mid)
                prev_int = int(prev_mid)
            except (ValueError, TypeError):
                continue

            cur_step = module_step_map.get(mid_int)
            prev_step = module_step_map.get(prev_int)
            if cur_step is not None and prev_step is not None and mid_int != prev_int:
                total_navigations += 1
                if cur_step < prev_step:
                    backward_navigations += 1

        backward_rate = backward_navigations / total_navigations if total_navigations > 0 else 0.0

        user_total_time = defaultdict(float)
        for ev in events:
            activity_type = ev.get("activityType", "")
            if activity_type == "view":
                user_id = ev.get("userId")
                duration = ev.get("stepDurationMs")
                if user_id and duration:
                    try:
                        user_total_time[str(user_id)] += float(duration)
                    except (ValueError, TypeError):
                        pass

        avg_completion_time = 0.0
        if user_total_time:
            avg_completion_time = sum(user_total_time.values()) / len(user_total_time)

        user_session_counts = defaultdict(int)
        course_session_count = 0
        for ev in events:
            event_type = ev.get("eventType", "")
            if event_type == "course_session":
                course_session_count += 1
                user_id = ev.get("userId")
                if user_id:
                    user_session_counts[str(user_id)] += 1

        if user_session_counts:
            avg_sessions = sum(user_session_counts.values()) / len(user_session_counts)
        elif course_session_count > 0 and user_total_time:
            avg_sessions = course_session_count / len(user_total_time)
        else:
            avg_sessions = 0.0

        return {
            "backwardNavigationRate": round(backward_rate, 3),
            "avgCourseCompletionTimeMs": round(avg_completion_time),
            "avgSessionsPerUser": round(avg_sessions, 1),
        }

    def _get_mock_metrics(self, course_id: int) -> List[Dict]:
        import random
        logger.info(f"Generating mock metrics for course {course_id}")
        
        num_modules = random.randint(10, 20)
        metrics = []
        
        total_students = random.randint(5, 25)
        
        for module_id in range(1, num_modules + 1):
            base_watch = random.uniform(0.2, 0.9)
            dropout_rate = random.uniform(0.3, 0.7) if base_watch < 0.5 else random.uniform(0.05, 0.3)
            
            retention_factor = max(0.3, 1.0 - (module_id / num_modules) * 0.5)
            module_students = max(1, int(total_students * retention_factor))
            
            metrics.append({
                "moduleId": module_id,
                "avgDurationMs": random.uniform(20000, 180010),
                "watchPercent": base_watch,
                "dropoutRate": dropout_rate,
                "studentCount": module_students,  
                "pauseCount": random.randint(0, 10),
                "step": module_id,
                "sectionId": (module_id - 1) // 5 + 1  
            })
        
        return metrics
    
    async def get_module_sequences(
        self,
        course_id: int,
        limit: int = 1000
    ) -> List[List[int]]:
        if not self.counter_id or not self.oauth_token:
            import random
            sequences = []
            for _ in range(min(limit, 100)):
                length = random.randint(3, 15)
                seq = list(range(1, length + 1))
                sequences.append(seq)
            return sequences
        
        try:
            date_from = datetime.now() - timedelta(days=30)
            date_to = datetime.now()
            
            events = await self._fetch_events_from_api(course_id, date_from, date_to)
            
            user_sequences = defaultdict(list)
            
            for event in events:
                if event.get("activityType") == "view" or event.get("eventType") in ["module_view", "module_attempt"]:
                    user_id = event.get("userId")
                    module_id = event.get("moduleId")
                    
                    if user_id and module_id:
                        try:
                            module_id = int(module_id)
                            if not user_sequences[user_id] or user_sequences[user_id][-1] != module_id:
                                user_sequences[user_id].append(module_id)
                        except (ValueError, TypeError):
                            pass
            
            sequences = list(user_sequences.values())[:limit]
            
            return sequences if sequences else self._get_mock_sequences(limit)
        
        except Exception as e:
            logger.error(f"Error getting module sequences: {e}")
            return self._get_mock_sequences(limit)
    
    def _get_mock_sequences(self, limit: int) -> List[List[int]]:
        import random
        sequences = []
        for _ in range(min(limit, 100)):
            length = random.randint(3, 15)
            seq = list(range(1, length + 1))
            sequences.append(seq)
        return sequences


_metrika_service: Optional[MetrikaService] = None


def get_metrika_service() -> MetrikaService:
    global _metrika_service
    if _metrika_service is None:
        _metrika_service = MetrikaService()
    return _metrika_service