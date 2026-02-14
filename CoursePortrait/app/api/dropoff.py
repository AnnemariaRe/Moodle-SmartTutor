from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from app.models import (
    DropoffPointsResponse,
    DropoffPoint,
    FunnelResponse,
    FunnelStep,
    RecommendationsResponse,
    Recommendation
)
from app.services.metrika import get_metrika_service
from app.services.moodle import get_moodle_service
from app.services.calculator import MetricsCalculator
from app.database import get_redis
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["dropoff"])


@router.get("/{course_id}/dropoff-points", response_model=DropoffPointsResponse)
async def get_dropoff_points(
    course_id: int,
):
    try:
        redis = await get_redis()
        cache_key = f"dropoff:{course_id}"
        cached = await redis.get(cache_key)
        if cached:
            import json
            return DropoffPointsResponse(**json.loads(cached))
        
        metrika_service = get_metrika_service()
        metrics = await metrika_service.pull_events(course_id)
        sequences = await metrika_service.get_module_sequences(course_id)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Metrics not found for course {course_id}"
            )

        moodle_service = get_moodle_service()
        moodle_modules = {}
        visible_module_ids = set()
        total_enrolled = 0
        total_completed = 0

        try:
            moodle_data = await moodle_service.get_course_modules(course_id)
            moodle_modules = {mod.get('moduleId'): mod for mod in moodle_data}
            visible_module_ids = set(moodle_modules.keys())

            for m in metrics:
                module_id = m.get('moduleId')
                if module_id in moodle_modules:
                    moodle_mod = moodle_modules[module_id]
                    m['moduleName'] = moodle_mod.get('moduleName', m.get('moduleName'))
                    m['moduleType'] = moodle_mod.get('moduleType', '')
                    m['step'] = moodle_mod.get('step', m.get('step', 0))
        except Exception as e:
            logger.debug(f"Failed to get modules from Moodle: {e}")

        try:
            course_info = await moodle_service.get_course_full_info(course_id)
            total_enrolled = course_info.get('totalStudents', 0)
        except Exception as e:
            logger.debug(f"Failed to get course info from Moodle: {e}")
        
        if visible_module_ids:
            original_count = len(metrics)
            metrics = [m for m in metrics if m.get('moduleId') in visible_module_ids]
            filtered_count = original_count - len(metrics)
            if filtered_count > 0:
                logger.info(
                    "Dropoff: filtered out %d metrics for hidden modules, %d remaining",
                    filtered_count, len(metrics)
                )
            
            if sequences:
                sequences = [
                    [mid for mid in seq if mid in visible_module_ids]
                    for seq in sequences
                ]
                sequences = [seq for seq in sequences if seq]
        
        calculator = MetricsCalculator()
        top_chains = calculator.analyze_dropoff_chains(sequences)
        total_started = max((m.get("studentCount", 0) for m in metrics), default=0)
        
        dropoff_points = []
        for m in metrics:
            dropout_rate = m.get("dropoutRate", 0.0)
            if dropout_rate > 0.3:
                students_entered = m.get("studentCount", 0)
                students_dropped = int(students_entered * dropout_rate)
                students_continued = students_entered - students_dropped
                
                dropoff_points.append(DropoffPoint(
                    moduleId=m.get("moduleId"),
                    moduleName=m.get("moduleName"),
                    moduleType=m.get("moduleType"),
                    step=m.get("step", 1),
                    studentsEntered=students_entered,
                    studentsDropped=students_dropped,
                    studentsContinued=students_continued,
                    dropoutRate=dropout_rate,
                    avgTimeBeforeDropout=m.get("avgDurationMs", 0)
                ))
        
        dropoff_points.sort(key=lambda x: x.dropoutRate, reverse=True)
                
        response = DropoffPointsResponse(
            courseId=course_id,
            dropoffPoints=dropoff_points[:10],
            topDropoffChains=top_chains,
            totalEnrolled=total_enrolled,
            totalStarted=total_started,
            totalCompleted=total_completed,
            methodologyExplanation=(
                "Dropout rate shows the proportion of students who opened a module "
                "but did not proceed to the next modules. "
                "High dropout (>30%) may indicate issues with content or module difficulty."
            )
        )
        
        await redis.setex(cache_key, 7200, response.model_dump_json())

        return response

    except Exception as e:
        logger.error(f"Error getting dropoff points for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{course_id}/funnel", response_model=FunnelResponse)
async def get_funnel(
    course_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    try:
        parsed_date_from = None
        parsed_date_to = None
        
        if date_from:
            try:
                parsed_date_from = datetime.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date_from format: {date_from}. Expected YYYY-MM-DD"
                )
        
        if date_to:
            try:
                parsed_date_to = datetime.strptime(date_to, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid date_to format: {date_to}. Expected YYYY-MM-DD"
                )
        
        redis = await get_redis()
        cache_key = f"funnel:{course_id}:{date_from or 'default'}:{date_to or 'default'}"
        cached = await redis.get(cache_key)
        
        if cached:
            import json
            return FunnelResponse(**json.loads(cached))
        
        metrika_service = get_metrika_service()
        metrics = await metrika_service.pull_events(
            course_id,
            date_from=parsed_date_from,
            date_to=parsed_date_to
        )
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Metrics not found for course {course_id}"
            )

        moodle_service = get_moodle_service()
        visible_module_ids = set()
        try:
            moodle_data = await moodle_service.get_course_modules(course_id)
            moodle_modules = {mod.get('moduleId'): mod for mod in moodle_data}
            visible_module_ids = set(moodle_modules.keys())
            for m in metrics:
                if m.get('moduleId') in moodle_modules:
                    moodle_mod = moodle_modules[m.get('moduleId')]
                    m['moduleName'] = moodle_mod.get('moduleName', m.get('moduleName'))
                    m['step'] = moodle_mod.get('step', m.get('step', m.get('moduleId')))
        except Exception as e:
            logger.debug(f"Failed to get modules from Moodle: {e}")
        
        if visible_module_ids:
            original_count = len(metrics)
            metrics = [m for m in metrics if m.get('moduleId') in visible_module_ids]
            filtered_count = original_count - len(metrics)
            if filtered_count > 0:
                logger.info(
                    "Funnel: filtered out %d metrics for hidden modules, %d remaining",
                    filtered_count, len(metrics)
                )
        
        total_students_from_moodle = None
        try:
            moodle_full_info = await moodle_service.get_course_full_info(course_id)
            total_students_from_moodle = moodle_full_info.get('totalStudents')
        except Exception as e:
            logger.debug(f"Failed to get totalStudents from Moodle: {e}")
        
        sorted_modules = sorted(metrics, key=lambda x: x.get("step", 0))
        if total_students_from_moodle is not None and total_students_from_moodle > 0:
            total_students = total_students_from_moodle
        else:
            total_students = max(m.get("studentCount", 0) for m in metrics) if metrics else 0
        
        funnel_steps = []
        for i, m in enumerate(sorted_modules):
            students_count = m.get("studentCount", 0)
            retention_rate = students_count / total_students if total_students > 0 else 0.0
            retention_rate = min(1.0, max(0.0, retention_rate))
            
            funnel_steps.append(FunnelStep(
                step=m.get("step", i + 1),
                moduleId=m.get("moduleId"),
                moduleName=m.get("moduleName"),
                studentsCount=students_count,
                retentionRate=retention_rate
            ))
        
        final_retention = funnel_steps[-1].retentionRate if funnel_steps else 0.0
        funnel_stats = await metrika_service.get_funnel_stats(
            course_id,
            date_from=parsed_date_from,
            date_to=parsed_date_to
        )

        response = FunnelResponse(
            courseId=course_id,
            funnel=funnel_steps,
            totalStudents=total_students,
            finalRetentionRate=final_retention,
            backwardNavigationRate=funnel_stats.get("backwardNavigationRate", 0.0),
            avgCourseCompletionTimeMs=funnel_stats.get("avgCourseCompletionTimeMs", 0.0),
            avgSessionsPerUser=funnel_stats.get("avgSessionsPerUser", 0.0),
        )
        
        await redis.setex(cache_key, 7200, response.model_dump_json())

        return response

    except Exception as e:
        logger.error(f"Error getting funnel for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{course_id}/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    course_id: int,
):
    try:
        redis = await get_redis()
        cache_key = f"recommendations:{course_id}"
        cached = await redis.get(cache_key)
        if cached:
            import json
            return RecommendationsResponse(**json.loads(cached))
        
        metrika_service = get_metrika_service()
        metrics = await metrika_service.pull_events(course_id)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"Metrics not found for course {course_id}"
            )

        moodle_service = get_moodle_service()
        visible_module_ids = set()
        try:
            moodle_data = await moodle_service.get_course_modules(course_id)
            moodle_modules = {mod.get('moduleId'): mod for mod in moodle_data}
            visible_module_ids = set(moodle_modules.keys())
            for m in metrics:
                if m.get('moduleId') in moodle_modules:
                    m['moduleName'] = moodle_modules[m.get('moduleId')].get('moduleName', m.get('moduleName'))
        except Exception as e:
            logger.debug(f"Failed to get modules from Moodle: {e}")
        
        if visible_module_ids:
            original_count = len(metrics)
            metrics = [m for m in metrics if m.get('moduleId') in visible_module_ids]
            filtered_count = original_count - len(metrics)
            if filtered_count > 0:
                logger.info(
                    "Recommendations: filtered out %d metrics for hidden modules, %d remaining",
                    filtered_count, len(metrics)
                )
        
        from app.services.ml_predictor import get_predictor
        predictor = get_predictor()
        calculator = MetricsCalculator()
        modules_with_scores = calculator.calculate_difficulty_scores(metrics, predictor)
        recs_data = calculator.generate_recommendations(modules_with_scores)
        
        recommendations = [Recommendation(**r) for r in recs_data]
        response = RecommendationsResponse(
            courseId=course_id,
            recommendations=recommendations
        )
        
        await redis.setex(cache_key, 3600, response.model_dump_json())
        
        return response
    
    except Exception as e:
        logger.error(f"Error getting recommendations for course {course_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
