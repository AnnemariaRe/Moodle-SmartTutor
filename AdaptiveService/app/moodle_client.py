import asyncio
import logging
import os
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MOODLE_URL = os.getenv("MOODLE_URL", "http://moodle:8080")
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", "")
TEXT_MAX_CHARS = 4000  # truncate long texts before sending to LLM

SUPPORTED_TYPES = {"page", "quiz", "assign", "book", "lesson"}


@dataclass
class ActivityData:
    cmid: int
    course_id: int
    section: int
    position: int   # position within section (for prereq ordering)
    type: str       # page | quiz | assign | book
    name: str
    text: str
    visible: bool = True  # False if module is hidden from students in Moodle


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


class MoodleClient:
    def __init__(
        self,
        url: str = MOODLE_URL,
        token: str = MOODLE_TOKEN,
    ) -> None:
        self.base_url = url.rstrip("/") + "/webservice/rest/server.php"
        self.token = token

    async def _call(self, function: str, **params) -> dict | list:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                self.base_url,
                params={
                    "wstoken": self.token,
                    "wsfunction": function,
                    "moodlewsrestformat": "json",
                    **params,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "exception" in data:
                raise RuntimeError(
                    f"Moodle API error ({function}): {data.get('message', data)}"
                )
            return data

    async def get_course_info(self, course_id: int) -> dict:
        data = await self._call(
            "core_course_get_courses",
            **{"options[ids][0]": course_id},
        )
        return data[0] if data else {}

    async def get_course_contents(self, course_id: int) -> list[dict]:
        return await self._call("core_course_get_contents", courseid=course_id)

    # Per-module content
    async def _get_pages(self, course_id: int) -> dict[int, str]:
        """Return {cmid: plain_text}."""
        try:
            data = await self._call(
                "mod_page_get_pages_by_courses",
                **{"courseids[0]": course_id},
            )
            return {
                p["coursemodule"]: _strip_html(p.get("content", ""))
                for p in data.get("pages", [])
            }
        except Exception as exc:
            logger.warning("mod_page_get_pages_by_courses failed: %s", exc)
            return {}

    async def _get_quizzes(self, course_id: int) -> dict[int, str]:
        """Return {cmid: plain_text} from quiz intros."""
        try:
            data = await self._call(
                "mod_quiz_get_quizzes_by_courses",
                **{"courseids[0]": course_id},
            )
            return {
                q["coursemodule"]: _strip_html(q.get("intro", ""))
                for q in data.get("quizzes", [])
            }
        except Exception as exc:
            logger.warning("mod_quiz_get_quizzes_by_courses failed: %s", exc)
            return {}

    async def _get_assignments(self, course_id: int) -> dict[int, str]:
        """Return {cmid: plain_text} from assignment intros."""
        try:
            data = await self._call(
                "mod_assign_get_assignments",
                **{"courseids[0]": course_id},
            )
            assignments = []
            for course in data.get("courses", []):
                assignments.extend(course.get("assignments", []))
            return {
                a["cmid"]: _strip_html(a.get("intro", ""))
                for a in assignments
            }
        except Exception as exc:
            logger.warning("mod_assign_get_assignments failed: %s", exc)
            return {}

    async def _get_lessons(self, course_id: int) -> dict[int, str]:
        """Return {cmid: plain_text} from lesson intros."""
        try:
            data = await self._call(
                "mod_lesson_get_lessons_by_courses",
                **{"courseids[0]": course_id},
            )
            return {
                lesson["coursemodule"]: _strip_html(lesson.get("intro", ""))
                for lesson in data.get("lessons", [])
            }
        except Exception as exc:
            logger.warning("mod_lesson_get_lessons_by_courses failed: %s", exc)
            return {}

    # Main entry point
    async def fetch_activities(self, course_id: int) -> list[ActivityData]:
        """Fetch all supported activities with their text content."""
        sections, pages, quizzes, assigns, lessons = await asyncio.gather(
            self.get_course_contents(course_id),
            self._get_pages(course_id),
            self._get_quizzes(course_id),
            self._get_assignments(course_id),
            self._get_lessons(course_id),
        )

        activities: list[ActivityData] = []
        for section in sections:
            section_num = section.get("section", 0)
            for position, module in enumerate(section.get("modules", [])):
                cmid = module["id"]
                modname = module.get("modname", "")
                name = module.get("name", "")

                if modname not in SUPPORTED_TYPES:
                    continue

                if modname == "page":
                    text = pages.get(cmid, "")
                elif modname == "quiz":
                    text = quizzes.get(cmid, "")
                elif modname == "assign":
                    text = assigns.get(cmid, "")
                elif modname == "lesson":
                    text = lessons.get(cmid, "")
                elif modname == "book":
                    # book chapters not fetched separately — use module description
                    text = _strip_html(module.get("description", ""))
                else:
                    text = ""

                text = text.strip()
                if not text:
                    # Fall back to module name so the activity is still registered
                    # as a ContentItem (important for assign/quiz with no intro).
                    text = name.strip()
                if not text:
                    logger.debug("cmid=%s (%s) has empty text — skipping", cmid, modname)
                    continue

                # uservisible reflects student-facing visibility (hidden modules = False)
                visible = bool(module.get("uservisible", module.get("visible", 1)))

                activities.append(
                    ActivityData(
                        cmid=cmid,
                        course_id=course_id,
                        section=section_num,
                        position=position,
                        type=modname,
                        name=name,
                        text=text[:TEXT_MAX_CHARS],
                        visible=visible,
                    )
                )

        logger.info(
            "Fetched %d activities for course_id=%s", len(activities), course_id
        )
        return activities
