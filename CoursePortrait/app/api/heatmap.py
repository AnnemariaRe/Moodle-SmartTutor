from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from app.models import (
    CourseHeatmapResponse,
    ModuleHeatmap,
    DifficultyLevel,
    CourseInfo,
    CoursesListResponse,
    CourseListItem
)
from app.services.metrika import get_metrika_service
from app.services.moodle import get_moodle_service
from app.services.ml_predictor import get_predictor
from app.services.calculator import MetricsCalculator
from app.database import get_redis
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["heatmap"])


@router.get("", response_model=CoursesListResponse)
async def get_all_courses():
    try:
        moodle_service = get_moodle_service()
        logger.info("Fetching all courses from Moodle...")
        courses_data = await moodle_service.get_all_courses()
        logger.info(f"Received {len(courses_data) if courses_data else 0} courses from Moodle")
        
        if not courses_data:
            logger.warning("No courses found in Moodle or Moodle is unavailable")
            return CoursesListResponse(
                courses=[],
                totalCourses=0
            )
        
        courses = [CourseListItem(**c) for c in courses_data]
        
        return CoursesListResponse(
            courses=courses,
            totalCourses=len(courses)
        )
    
    except Exception as e:
        logger.error(f"Error getting courses list: {e}", exc_info=True)
        return CoursesListResponse(
            courses=[],
            totalCourses=0
        )


@router.get("/{course_id}/heatmap", response_model=CourseHeatmapResponse)
async def get_heatmap(
    course_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
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
        cache_key = f"heatmap:{course_id}:{date_from_dt.date()}:{date_to_dt.date()}"
        cached = await redis.get(cache_key)
        
        if cached:
            import json
            logger.info(f"Cache hit for {cache_key}")
            return CourseHeatmapResponse(**json.loads(cached))
        
        metrika_service = get_metrika_service()
        metrics = await metrika_service.pull_events(course_id, date_from_dt, date_to_dt)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Metrics not found for course {course_id}"
            )
        
        moodle_service = get_moodle_service()
        moodle_modules = {}
        visible_module_ids = set()
        try:
            moodle_data = await moodle_service.get_course_modules(course_id)
            for mod in moodle_data:
                module_id = mod.get('moduleId')
                moodle_modules[module_id] = mod
                visible_module_ids.add(module_id)
        except Exception as e:
            logger.debug(f"Failed to get modules from Moodle: {e}")
        
        if visible_module_ids:
            original_count = len(metrics)
            metrics = [m for m in metrics if m.get('moduleId') in visible_module_ids]
            filtered_count = original_count - len(metrics)
            if filtered_count > 0:
                logger.info(
                    "Heatmap: filtered out %d metrics for hidden modules, %d remaining",
                    filtered_count, len(metrics)
                )
        
        for m in metrics:
            if m.get('moduleId') in moodle_modules:
                mod_info = moodle_modules[m.get('moduleId')]
                if not m.get('moduleName'):
                    m['moduleName'] = mod_info.get('moduleName', '')
                if not m.get('sectionId'):
                    m['sectionId'] = mod_info.get('sectionId')
                if not m.get('moduleType') and mod_info.get('moduleType'):
                    m['moduleType'] = mod_info.get('moduleType')
        
        predictor = get_predictor()
        calculator = MetricsCalculator()
        modules_with_scores = calculator.calculate_difficulty_scores(metrics, predictor)
        
        heatmap_modules = []
        for m in modules_with_scores:
            difficulty_str = m.get("difficultyLevel", "medium")
            
            moodle_module_type = m.get("moduleType")
            has_video = m.get("watchPercent") is not None and m.get("watchPercent", 0) > 0
            
            if moodle_module_type:
                module_type = moodle_module_type
            elif has_video:
                module_type = "video"
            else:
                module_type = "unknown"
            
            difficulty_details = None
            if m.get("difficultyDetails"):
                from app.models import DifficultyDetails, DifficultyMetricDetail
                details_data = m.get("difficultyDetails")
                difficulty_details = DifficultyDetails(
                    metrics=[
                        DifficultyMetricDetail(**metric_data)
                        for metric_data in details_data.get("metrics", [])
                    ],
                    explanation=details_data.get("explanation", ""),
                    suggestions=details_data.get("suggestions", [])
                )
            
            heatmap_modules.append(ModuleHeatmap(
                moduleId=m.get("moduleId"),
                sectionId=m.get("sectionId"),
                moduleName=m.get("moduleName"),
                moduleType=module_type,
                dropoutRisk=m.get("dropoutRisk", 0.0),
                difficulty=DifficultyLevel(difficulty_str),
                difficultyScore=m.get("difficultyScore", 0.0),
                difficultyDetails=difficulty_details,
                avgDurationMs=m.get("avgDurationMs", 0.0),
                watchPercent=m.get("watchPercent"),
                engagementScore=m.get("engagementScore", m.get("watchPercent", 0.5)),
                studentCount=m.get("studentCount", 0),
                dropoutRate=m.get("dropoutRate", 0.0)
            ))
        
        bottlenecks = calculator.identify_bottlenecks(modules_with_scores)
        
        total_modules_from_moodle = None
        try:
            moodle_full_info = await moodle_service.get_course_full_info(course_id)
            total_modules_from_moodle = moodle_full_info.get('totalModules')
        except Exception as e:
            logger.debug(f"Failed to get totalModules from Moodle: {e}")
        
        response = CourseHeatmapResponse(
            courseId=course_id,
            modules=heatmap_modules,
            totalModules=total_modules_from_moodle if total_modules_from_moodle is not None else len(heatmap_modules),
            bottleneckModules=bottlenecks
        )
        
        await redis.setex(cache_key, 3600, response.model_dump_json())
        
        return response
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Error generating heatmap for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{course_id}/info", response_model=CourseInfo)
async def get_course_info(
    course_id: int,
):
    try:
        moodle_service = get_moodle_service()
        moodle_data = await moodle_service.get_course_full_info(course_id)
        
        if moodle_data and moodle_data.get('modules'):
            modules_info = []
            for m in moodle_data['modules']:
                modules_info.append({
                    "moduleId": m.get("moduleId"),
                    "moduleName": m.get("moduleName") or f"Module {m.get('moduleId')}",
                    "moduleType": m.get("moduleType", "unknown"),
                    "sectionId": m.get("sectionId"),
                    "sectionName": m.get("sectionName"),
                    "step": 0
                })
            
            return CourseInfo(
                courseId=course_id,
                courseName=moodle_data.get('courseName', f'Course {course_id}'),
                modules=modules_info,
                totalModules=moodle_data.get('totalModules'),
                totalStudents=moodle_data.get('totalStudents')
            )
        
        logger.info(f"Moodle unavailable, using Metrika data for course {course_id}")
        metrika_service = get_metrika_service()
        metrics = await metrika_service.pull_events(course_id)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Metrics not found for course {course_id}"
            )
        
        modules_info = []
        for m in metrics:
            modules_info.append({
                "moduleId": m.get("moduleId"),
                "moduleName": m.get("moduleName") or f"Module {m.get('moduleId')}",
                "moduleType": m.get("moduleType", "unknown"),
                "sectionId": m.get("sectionId"),
                "step": m.get("step", 0)
            })
        
        modules_info.sort(key=lambda x: x.get("step", 0))
        
        return CourseInfo(
            courseId=course_id,
            courseName=f"Course {course_id}",
            modules=modules_info,
            totalModules=len(modules_info) if modules_info else None,
            totalStudents=None
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting course info for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
