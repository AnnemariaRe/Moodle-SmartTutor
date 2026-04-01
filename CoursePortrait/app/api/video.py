from fastapi import APIRouter, HTTPException
from typing import Optional, Dict
from datetime import datetime, timedelta
import logging

from app.database import get_redis
from app.models import VideoAnalyticsResponse, VideoMediaAnalytics
from app.services.metrika import get_metrika_service
from app.services.moodle import get_moodle_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["video"])


async def _get_module_names(course_id: int) -> Dict[int, str]:
    try:
        moodle_service = get_moodle_service()
        modules = await moodle_service.get_course_modules(course_id, include_hidden=True)
        
        module_names = {}
        for module in modules:
            module_id = module.get("moduleId")
            module_name = module.get("moduleName")
            if module_id and module_name:
                module_names[module_id] = module_name
        
        logger.info(f"Loaded {len(module_names)} module names from Moodle for course {course_id}")
        return module_names
    except Exception as e:
        logger.warning(f"Failed to load module names from Moodle: {e}")
        return {}


@router.get("/{course_id}/video-analytics", response_model=VideoAnalyticsResponse)
async def get_video_analytics(
    course_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    module_id: Optional[int] = None,
    media_id: Optional[str] = None,
):
    try:
        if date_from:
            date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
        else:
            date_from_dt = datetime.now() - timedelta(days=30)

        if date_to:
            date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
        else:
            date_to_dt = datetime.now()

        redis = await get_redis()
        cache_key = f"video:{course_id}:{module_id}:{media_id}:{date_from_dt.date()}:{date_to_dt.date()}"
        cached = await redis.get(cache_key)
        if cached:
            import json
            return VideoAnalyticsResponse(**json.loads(cached))

        metrika_service = get_metrika_service()
        items = await metrika_service.pull_video_analytics(
            course_id=course_id,
            date_from=date_from_dt,
            date_to=date_to_dt,
            module_id=module_id,
            media_id=media_id,
        )
        if not items:
            raise HTTPException(status_code=404, detail=f"Video analytics not found for course {course_id}")

        module_names = await _get_module_names(course_id)
        
        for item in items:
            video_module_id = item.get("moduleId")
            if video_module_id and video_module_id in module_names:
                item["moduleName"] = module_names[video_module_id]
            elif not item.get("moduleName"):
                item["moduleName"] = f"Module {video_module_id}" if video_module_id else None

        items = [x for x in items if x.get("videoDurationMs") and x["videoDurationMs"] > 0]
        videos = [VideoMediaAnalytics(**x) for x in items]

        response = VideoAnalyticsResponse(
            courseId=course_id,
            moduleId=module_id,
            mediaId=media_id,
            dateFrom=date_from,
            dateTo=date_to,
            videos=videos,
            totalVideos=len(videos),
        )

        await redis.setex(cache_key, 3600, response.model_dump_json())
        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating video analytics for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

