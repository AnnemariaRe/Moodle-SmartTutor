import random
import time
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium_common import (
    USERS,BASE_URL, create_driver, login, logout,
    enrol_to_course, open_course, get_course_modules,
)

COURSE_ID = 4
USERS_PER_RUN = 5 # сколько студентов полностью проходят курс за один запуск

MODULE_VIEW_MIN_SEC = 1.0
MODULE_VIEW_MAX_SEC = 3.0
QUIZ_ATTEMPT_MIN_SEC = 2.0
QUIZ_ATTEMPT_MAX_SEC = 4.0
BOOK_PAGE_VIEW_MIN_SEC = 0.2
BOOK_PAGE_VIEW_MAX_SEC = 1.5


def complete_book_module(driver, book_url):
    """Проходит все страницы Book модуля по стрелочке 'Next'."""
    print(f"  Проходим Book модуль: {book_url}")
    driver.get(book_url)
    time.sleep(1)
    
    page_count = 0
    max_pages = 100  # защита от бесконечного цикла
    visited_chapters = set()
    
    while page_count < max_pages:
        view_time = random.uniform(BOOK_PAGE_VIEW_MIN_SEC, BOOK_PAGE_VIEW_MAX_SEC)
        current_url = driver.current_url
        
        current_chapter = None
        if "chapterid=" in current_url:
            try:
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                current_chapter = int(params.get("chapterid", [0])[0])
            except (ValueError, KeyError):
                pass
        
        if current_chapter is None:
            try:
                first_chapter_link = driver.find_element(By.CSS_SELECTOR, "a[href*='chapterid=']")
                first_href = first_chapter_link.get_attribute("href")
                parsed = urlparse(first_href)
                params = parse_qs(parsed.query)
                first_chapter = int(params.get("chapterid", [0])[0])
                print(f"    Найдена первая глава (chapterid={first_chapter}), переходим")
                driver.get(first_href)
                time.sleep(1)
                page_count += 1
                continue
            except NoSuchElementException:
                print(f"    Не найдено глав в Book модуле")
                break
        
        if current_chapter in visited_chapters:
            print(f"    Уже были на chapterid={current_chapter}, завершаем")
            break
        visited_chapters.add(current_chapter)
        
        print(f"    Страница {page_count + 1} (chapterid={current_chapter}), ждём ~{view_time:.1f} сек")
        time.sleep(view_time)
        
        # Ищем кнопку "Next" для перехода на следующую страницу Book
        next_button = None
        next_chapter = current_chapter + 1 if current_chapter is not None else 1
        
        # Ищем кнопку "Next" - пробуем несколько способов
        selectors = [
            f"a[href*='chapterid={next_chapter}']",
            f"a.booknav[href*='chapterid={next_chapter}']",
        ]
        for selector in selectors:
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, selector)
                if next_button and next_button.is_displayed():
                    break
            except NoSuchElementException:
                next_button = None
        
        # Если не нашли, ищем по тексту "Next"
        if not next_button:
            try:
                nav_links = driver.find_elements(By.CSS_SELECTOR, "a.booknav")
                for link in nav_links:
                    title = (link.get_attribute("title") or "").lower()
                    href = link.get_attribute("href") or ""
                    if "next" in title and "chapterid=" in href:
                        try:
                            parsed = urlparse(href)
                            params = parse_qs(parsed.query)
                            href_chapter = int(params.get("chapterid", [0])[0])
                            if href_chapter > current_chapter:
                                next_button = link
                                break
                        except (ValueError, KeyError):
                            continue
            except NoSuchElementException:
                pass
        
        # Если нашли кнопку "Next", кликаем
        if next_button:
            try:
                next_href = next_button.get_attribute("href")
                print(f"    Переход на следующую страницу: {next_href}")
                next_button.click()
                time.sleep(1)
                page_count += 1
            except Exception as e:
                print(f"    Ошибка при клике на Next: {e}")
                break
        else:
            print(f"  Book модуль завершён, пройдено страниц: {page_count + 1}")
            break
    
    if page_count >= max_pages:
        print(f"  Достигнут лимит страниц ({max_pages}), остановка")


def complete_quiz(driver, quiz_url):
    """Проходит quiz: открывает, отвечает на вопросы и завершает попытку."""
    print(f"  Проходим Quiz: {quiz_url}")
    
    # Сначала открываем view.php чтобы увидеть информацию о квизе
    driver.get(quiz_url)
    time.sleep(1)
    
    parsed = urlparse(quiz_url)
    params = parse_qs(parsed.query)
    cmid = params.get("id", [None])[0]
    if not cmid:
        print(f"    Ошибка: не найден cmid в URL {quiz_url}")
        return
    
    attempt_url = f"{BASE_URL}/mod/quiz/attempt.php?cmid={cmid}"
    
    # Пробуем найти кнопку начала попытки
    try:
        attempt_button = driver.find_element(
            By.XPATH,
            "//input[@type='submit' and (contains(@value, 'Attempt') or contains(@value, 'Re-attempt'))]"
        )
        attempt_button.click()
        time.sleep(2)
    except NoSuchElementException:
        driver.get(attempt_url)
        time.sleep(2)
    
    try:
        driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='startattempt']").click()
        time.sleep(2)
    except NoSuchElementException:
        pass
    
    # Отвечаем на вопросы
    try:
        answered_count = 0
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox'], textarea, input[type='text']"):
            try:
                if not inp.is_displayed():
                    continue
                inp_type = inp.get_attribute("type")
                if inp_type in ["radio", "checkbox"]:
                    inp.click()
                elif inp_type in ["text"] or inp.tag_name == "textarea":
                    inp.send_keys("Test answer")
                answered_count += 1
            except:
                continue
        if answered_count > 0:
            time.sleep(random.uniform(QUIZ_ATTEMPT_MIN_SEC, QUIZ_ATTEMPT_MAX_SEC))
    except:
        pass
    
    # Завершаем попытку
    try:
        finish_btn = driver.find_element(
            By.XPATH,
            "//input[@type='submit' and (contains(@name, 'finish') or contains(@value, 'Finish') or contains(@value, 'Submit'))]"
        )
        finish_btn.click()
        time.sleep(2)
    except NoSuchElementException:
        pass


def complete_all_modules_and_quizzes(driver, module_links):
    """Линейно пройти все модули и все quiz-попытки."""
    print(f"\nНайдено модулей: {len(module_links)}")
    quiz_count = 0

    for href in module_links:
        if "/mod/book/view.php" in href:
            complete_book_module(driver, href)
        elif "/mod/quiz/view.php" in href:
            quiz_count += 1
            complete_quiz(driver, href)
        else:
            print(f"Открываем модуль: {href}")
            driver.get(href)
            time.sleep(random.uniform(MODULE_VIEW_MIN_SEC, MODULE_VIEW_MAX_SEC))

    if quiz_count:
        print(f"\nОбработано квизов: {quiz_count}")


def main():
    driver = create_driver()
    try:
        for username, password in random.sample(USERS, USERS_PER_RUN):
            print(f"\n=== Полное прохождение курса под {username} ===")
            login(driver, username, password)
            enrol_to_course(driver, COURSE_ID)
            open_course(driver, COURSE_ID)
            complete_all_modules_and_quizzes(driver, get_course_modules(driver))
            logout(driver)
            time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
