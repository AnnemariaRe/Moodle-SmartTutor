import random
import time
from urllib.parse import urlparse, parse_qs

from selenium_common import (
    USERS, BASE_URL, create_driver, login, logout,
    enrol_to_course, open_course, get_course_modules, get_course_sections,
    open_random_sections
)

COURSE_ID = 4
MAX_MODULES_PER_USER = 10
MAX_SECTIONS_PER_USER = 3          # сколько секций открывает студент
QUIZ_ATTEMPTS_FRACTION = 2      # доля quiz-модулей, по которым делаем попытку

MODULE_VIEW_MIN_SEC = 1.0
MODULE_VIEW_MAX_SEC = 5.0

QUIZ_ATTEMPT_MIN_SEC = 1
QUIZ_ATTEMPT_MAX_SEC = 4.0

def browse_random_modules_and_attempts(driver, module_links):
    """Открываем несколько модулей, а затем делаем возвраты к уже посещённым, и для части quiz заходим на /attempt.php."""
    links = module_links.copy()
    random.shuffle(links)
    if MAX_MODULES_PER_USER is not None:
        links = links[:MAX_MODULES_PER_USER]

    visited = []
    quiz_views = []

    for href in links:
        print(f"Открываем модуль: {href}")
        driver.get(href)

        view_time = random.uniform(MODULE_VIEW_MIN_SEC, MODULE_VIEW_MAX_SEC)
        print(f"   Ждём внутри модуля ~{view_time:.1f} сек")
        time.sleep(view_time)

        visited.append(href)

        if "/mod/quiz/view.php" in href:
            quiz_views.append(href)

    back_steps = min(3, len(visited))
    for i in range(back_steps):
        back_href = random.choice(visited)
        print(f"Возврат к ранее открытому модулю: {back_href}")
        driver.get(back_href)

        back_view_time = random.uniform(MODULE_VIEW_MIN_SEC / 2, MODULE_VIEW_MAX_SEC / 2)
        print(f"Ждём при возврате ~{back_view_time:.1f} сек")
        time.sleep(back_view_time)

    attempts_count = int(len(quiz_views) * QUIZ_ATTEMPTS_FRACTION)
    if attempts_count <= 0:
        return

    random.shuffle(quiz_views)
    quiz_views = quiz_views[:attempts_count]

    for view_href in quiz_views:
        parsed = urlparse(view_href)
        params = parse_qs(parsed.query)
        cmid = params.get("id", [None])[0]
        if not cmid:
            continue
        attempt_url = f"{BASE_URL}/mod/quiz/attempt.php?cmid={cmid}"
        print(f"Открываем попытку теста: {attempt_url}")
        driver.get(attempt_url)

        attempt_time = random.uniform(QUIZ_ATTEMPT_MIN_SEC, QUIZ_ATTEMPT_MAX_SEC)
        print(f"   Ждём внутри попытки теста ~{attempt_time:.1f} сек")
        time.sleep(attempt_time)


def main():
    driver = create_driver()
    try:
        for username, password in random.sample(USERS, 5):
            print(f"\n=== Логин под {username} ===")
            login(driver, username, password)
            enrol_to_course(driver, COURSE_ID)
            open_course(driver, COURSE_ID)
            
            module_links = get_course_modules(driver)
            section_links = get_course_sections(driver)
            open_random_sections(driver, section_links, MAX_SECTIONS_PER_USER)
            browse_random_modules_and_attempts(driver, module_links)
            
            logout(driver)
            time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
