import aiohttp
import os
import logging
from typing import Optional, Dict, List

from aiohttp import FormData

logger = logging.getLogger(__name__)


class MoodleService:
    
    def __init__(
        self,
        moodle_url: Optional[str] = None,
        moodle_token: Optional[str] = None
    ):
        self.moodle_url = (moodle_url or os.getenv("MOODLE_URL", "http://host.docker.internal:8081")).rstrip('/')
        self.moodle_token = moodle_token or os.getenv("MOODLE_TOKEN", "")
        self.api_url = f"{self.moodle_url}/webservice/rest/server.php"
        logger.warning("MoodleService init moodle_url=%r env=%r api_url=%r",
               self.moodle_url, os.getenv("MOODLE_URL"), self.api_url)
    
    async def get_course_info(self, course_id: int) -> Optional[Dict]:
        if not self.moodle_token:
            logger.warning("Moodle token not configured")
            return None
        
        try:
            form_data = FormData()
            form_data.add_field('wstoken', self.moodle_token)
            form_data.add_field('wsfunction', 'core_course_get_courses')
            form_data.add_field('moodlewsrestformat', 'json')
            form_data.add_field('options[ids][0]', str(course_id))
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    data=form_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    timeout=10
                ) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    logger.info(
                        "Moodle course info response -> status=%s reason=%s content_type=%s",
                        resp.status, resp.reason, content_type
                    )
                    raw = await resp.text()
                    logger.info(
                        "Moodle course info raw body (first 500 chars, len=%s): %s",
                        len(raw), raw[:500]
                    )

                    if resp.status != 200:
                        logger.warning("Moodle API returned non-200 status for course info: %s", resp.status)
                        return None

                    if 'json' not in content_type.lower():
                        logger.warning(
                            "Unexpected content-type for course info (expected json): %s",
                            content_type
                        )
                        return None

                    data = await resp.json()
                    
                    if isinstance(data, dict) and 'exception' in data:
                        logger.warning(f"Moodle API error: {data.get('message', 'Unknown error')}")
                        return None
                    
                    if isinstance(data, list) and len(data) > 0:
                        return data[0]
                    return None
        
        except Exception as e:
            logger.error(f"Error fetching course info from Moodle: {e}", exc_info=True)
            return None
    
    async def get_all_courses(self, include_hidden: bool = False) -> List[Dict]:
        if not self.moodle_token:
            logger.warning("Moodle token not configured")
            return []
        
        try:
            form_data = FormData()
            form_data.add_field('wstoken', self.moodle_token)
            form_data.add_field('wsfunction', 'core_course_get_courses')
            form_data.add_field('moodlewsrestformat', 'json')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    data=form_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    timeout=10
                ) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    logger.info(
                        "Moodle all courses response -> status=%s reason=%s content_type=%s",
                        resp.status, resp.reason, content_type
                    )
                    raw = await resp.text()
                    logger.info(
                        "Moodle all courses raw body (first 500 chars, len=%s): %s",
                        len(raw), raw[:500]
                    )

                    if resp.status != 200:
                        logger.warning("Moodle API returned non-200 status for all courses: %s", resp.status)
                        return []

                    if 'json' not in content_type.lower():
                        logger.warning(
                            "Unexpected content-type for all courses (expected json): %s",
                            content_type
                        )
                        return []

                    data = await resp.json()
                    
                    if isinstance(data, dict) and 'exception' in data:
                        logger.warning(f"Moodle API error: {data.get('message', 'Unknown error')}")
                        return []
                    
                    if not isinstance(data, list):
                        return []
                    
                    courses = []
                    hidden_count = 0
                    for course in data:
                        if course.get('id') == 1:
                            continue
                        
                        visible = course.get('visible', 1)
                        
                        if not include_hidden and visible == 0:
                            hidden_count += 1
                            continue
                        
                        courses.append({
                            'id': course.get('id'),
                            'fullname': course.get('fullname', ''),
                            'shortname': course.get('shortname', ''),
                            'visible': visible,
                            'categoryid': course.get('categoryid'),
                            'summary': course.get('summary', '')
                        })
                    
                    if hidden_count > 0:
                        logger.info(
                            "Filtered out %d hidden courses, returning %d visible courses",
                            hidden_count, len(courses)
                        )
                    
                    courses.sort(key=lambda x: x.get('fullname', '').lower())
                    
                    return courses
        
        except Exception as e:
            logger.error(f"Error fetching all courses from Moodle: {e}", exc_info=True)
            return []
    
    async def get_course_contents(self, course_id: int) -> List[Dict]:
        if not self.moodle_token:
            logger.warning("Moodle token not configured, returning empty list")
            return []

        logger.info(
            "Moodle connectivity check -> url=%s token_present=%s",
            self.api_url,
            bool(self.moodle_token)
        )
        
        try:
            form_data = FormData()
            form_data.add_field('wstoken', self.moodle_token)
            form_data.add_field('wsfunction', 'core_course_get_contents')
            form_data.add_field('moodlewsrestformat', 'json')
            form_data.add_field('courseid', str(course_id))
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    data=form_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    timeout=10
                ) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    logger.info(
                        "Moodle course contents response -> status=%s reason=%s content_type=%s",
                        resp.status, resp.reason, content_type
                    )
                    raw = await resp.text()
                    logger.info(
                        "Moodle course contents raw body (first 500 chars, len=%s): %s",
                        len(raw), raw[:500]
                    )

                    if resp.status != 200:
                        logger.warning("Moodle API returned non-200 status for course contents: %s", resp.status)
                        return []

                    if 'json' not in content_type.lower():
                        logger.warning(
                            "Unexpected content-type for course contents (expected json): %s",
                            content_type
                        )
                        return []

                    data = await resp.json()
                    
                    # Check for error
                    if isinstance(data, dict) and 'exception' in data:
                        logger.warning(f"Moodle API error: {data.get('message', 'Unknown error')}")
                        return []
                    
                    if isinstance(data, list):
                        return data
                    return []
        
        except Exception as e:
            logger.error(f"Error fetching course contents from Moodle: {e}", exc_info=True)
            return []
    
    async def get_course_modules(self, course_id: int, include_hidden: bool = False) -> List[Dict]:
        sections = await self.get_course_contents(course_id)
        
        modules = []
        hidden_count = 0
        step = 1
        for section in sections:
            section_id = section.get('id', 0)
            section_name = section.get('name', '')
            for module in section.get('modules', []):
                visible = module.get('visible', 1)
                
                if not include_hidden and visible == 0:
                    hidden_count += 1
                    continue
                
                modules.append({
                    'moduleId': module.get('id', 0),
                    'moduleName': module.get('name', ''),
                    'moduleType': module.get('modname', ''),
                    'sectionId': section_id,
                    'sectionName': section_name,
                    'visible': visible,
                    'url': module.get('url', ''),
                    'step': step
                })
                step += 1
        
        if hidden_count > 0:
            logger.info(
                "Course %s: filtered out %d hidden modules, returning %d visible modules",
                course_id, hidden_count, len(modules)
            )
        
        return modules
    
    async def get_enrolled_users(self, course_id: int) -> List[Dict]:
        if not self.moodle_token:
            logger.warning("Moodle token not configured, returning empty list")
            return []
        
        try:
            url = (
                f"{self.api_url}"
                f"?wstoken={self.moodle_token}"
                f"&wsfunction=core_enrol_get_enrolled_users"
                f"&moodlewsrestformat=json"
                f"&courseid={course_id}"
            )
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    content_type = resp.headers.get('Content-Type', '')
                    logger.info(
                        "Moodle enrolled users response -> status=%s reason=%s content_type=%s url=%s",
                        resp.status, resp.reason, content_type, url
                    )
                    raw = await resp.text()
                    logger.info(
                        "Moodle enrolled users raw body (first 500 chars, len=%s): %s",
                        len(raw), raw[:500]
                    )
                    
                    if resp.status != 200:
                        logger.warning("Moodle API returned non-200 status for enrolled users: %s", resp.status)
                        return []
                    
                    if 'json' not in content_type.lower():
                        logger.warning(
                            "Unexpected content-type for enrolled users (expected json): %s",
                            content_type
                        )
                        return []

                    data = await resp.json()
                    
                    if isinstance(data, dict) and 'exception' in data:
                        logger.warning(f"Moodle API error: {data.get('message', 'Unknown error')}")
                        return []
                    
                    if isinstance(data, list):
                        return data
                    return []
        
        except Exception as e:
            logger.error(f"Error fetching enrolled users from Moodle: {e}", exc_info=True)
            return []
    
    async def get_enrolled_users_count(self, course_id: int) -> int:
        users = await self.get_enrolled_users(course_id)
        return len(users)
    
    async def get_course_full_info(self, course_id: int, include_hidden: bool = False) -> Dict:
        course_info = await self.get_course_info(course_id)
        modules = await self.get_course_modules(course_id, include_hidden=include_hidden)
        students_count = await self.get_enrolled_users_count(course_id)
        
        return {
            'courseId': course_id,
            'courseName': course_info.get('fullname', f'Course {course_id}') if course_info else f'Course {course_id}',
            'courseShortName': course_info.get('shortname', '') if course_info else '',
            'courseSummary': course_info.get('summary', '') if course_info else '',
            'modules': modules,
            'totalModules': len(modules),
            'totalStudents': students_count
        }

_moodle_service: Optional[MoodleService] = None


def get_moodle_service() -> MoodleService:
    global _moodle_service
    if _moodle_service is None:
        _moodle_service = MoodleService()
    return _moodle_service
