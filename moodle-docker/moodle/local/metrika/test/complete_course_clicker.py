import random
import time
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium_common import (
    BASE_URL, create_driver, login, logout,
    enrol_to_course, open_course, get_course_modules,
)

COURSE_ID = 3
USERS = [
    ("student01", "Test123!"),
    ("student02", "Test123!"),
    ("student03", "Test123!"),
    ("student04", "Test123!"),
    ("student05", "Test123!"),
    ("student06", "Test123!"),
    ("student07", "Test123!"),
    ("student08", "Test123!"),
    ("student09", "Test123!"),
    ("student10", "Test123!"),
    ("student11", "Test123!"),
    ("student12", "Test123!"),
    ("student13", "Test123!"),
    ("student14", "Test123!"),
    ("student15", "Test123!"),
    ("student16", "Test123!"),
    ("student17", "Test123!"),
    ("student18", "Test123!"),
    ("student19", "Test123!"),
    ("student20", "Test123!"),
]

# сколько студентов полностью проходят курс за один запуск
USERS_PER_RUN = 1

MODULE_VIEW_MIN_SEC = 1.0
MODULE_VIEW_MAX_SEC = 3.0
QUIZ_ATTEMPT_MIN_SEC = 2.0
QUIZ_ATTEMPT_MAX_SEC = 4.0


def complete_all_modules_and_quizzes(driver, module_links):
    """Линейно пройти все модули и все quiz-попытки, имитируя завершение курса."""
    quiz_views = []

    for href in module_links:
        print(f"Открываем модуль: {href}")
        driver.get(href)

        view_time = random.uniform(MODULE_VIEW_MIN_SEC, MODULE_VIEW_MAX_SEC)
        print(f"   Ждём внутри модуля ~{view_time:.1f} сек")
        time.sleep(view_time)

        if "/mod/quiz/view.php" in href:
            quiz_views.append(href)

    # Для всех тестов запускаем attempt.php (QUIZ_ATTEMPTS_FRACTION = 1)
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

        # здесь можно дополнительно нажать кнопку завершения попытки, если нужно
        try:
            finish_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='finishattempt']")
            finish_btn.click()
            time.sleep(2)
        except NoSuchElementException:
            pass


def main():
    driver = create_driver()
    try:
        users_sample = random.sample(USERS, USERS_PER_RUN)

        for username, password in users_sample:
            print(f"\n=== Полное прохождение курса под {username} ===")
            login(driver, username, password)

            enrol_to_course(driver, COURSE_ID)

            open_course(driver, COURSE_ID)
            module_links = get_course_modules(driver)

            # полный линейный проход по модулю + все квизы
            complete_all_modules_and_quizzes(driver, module_links)

            logout(driver)
            time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
