import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

MOODLE_URL   = os.getenv("MOODLE_URL", "http://localhost:8081")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")
TIMEOUT      = 20.0


def _rest_url(function: str) -> str:
    return (
        f"{MOODLE_URL}/webservice/rest/server.php"
        f"?wstoken={MOODLE_TOKEN}&wsfunction={function}&moodlewsrestformat=json"
    )


async def _get(function: str, params: Dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(_rest_url(function), params=params or {})
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict) and "exception" in data:
        raise RuntimeError(f"Moodle API error [{function}]: {data.get('message')}")
    return data


async def get_course_contents(course_id: int) -> List[Dict[str, Any]]:
    data = await _get("core_course_get_contents", {"courseid": course_id})
    return data if isinstance(data, list) else []


async def get_courses() -> List[Dict[str, Any]]:
    data = await _get("core_course_get_courses")
    return data if isinstance(data, list) else []


async def get_lesson_pages(lesson_id: int) -> List[Dict[str, Any]]:
    data = await _get("mod_lesson_get_pages", {"lessonid": lesson_id})
    return [item["page"] for item in data.get("pages", []) if "page" in item]


async def get_page_contents_by_course(course_id: int) -> Dict[int, str]:
    data = await _get("mod_page_get_pages_by_courses", {"courseids[0]": course_id})
    return {
        p["coursemodule"]: p.get("content", "") or p.get("intro", "")
        for p in data.get("pages", [])
    }


async def get_quiz_intros_by_course(course_id: int) -> Dict[int, str]:
    data = await _get("mod_quiz_get_quizzes_by_courses", {"courseids[0]": course_id})
    return {
        q["coursemodule"]: q.get("intro", "")
        for q in data.get("quizzes", [])
    }
