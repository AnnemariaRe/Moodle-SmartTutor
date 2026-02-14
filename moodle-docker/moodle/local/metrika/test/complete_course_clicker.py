import random
import re
import time
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium_common import (
    USERS, BASE_URL, create_driver, login, logout,
    enrol_to_course, open_course, get_course_modules,
)
from quiz_answer_key import load_question_bank, norm_text
from video_viewer import process_page_videos

COURSE_ID = 4
USERS_PER_RUN = 10  # сколько студентов полностью проходят курс за один запуск

# Question bank configuration
QUESTION_BANK_XML = "questions-PFB1-Default-for-PFB1-20260131-1507.xml"
P_CORRECT = 0.9  # вероятность отвечать правильно на распознанный вопрос

MODULE_VIEW_MIN_SEC = 0.2
MODULE_VIEW_MAX_SEC = 0.6
QUIZ_ATTEMPT_MIN_SEC = 0.5
QUIZ_ATTEMPT_MAX_SEC = 1.0
BOOK_PAGE_VIEW_MIN_SEC = 0.2
BOOK_PAGE_VIEW_MAX_SEC = 0.5


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_qid_from_question_el(qel) -> int | None:
    try:
        h = qel.find_element(By.CSS_SELECTOR, "input.questionflagpostdata").get_attribute("value") or ""
        m = re.search(r"qid(\d+)", h)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _get_qtext_from_question_el(qel) -> str:
    try:
        return qel.find_element(By.CSS_SELECTOR, "div.qtext").text or ""
    except Exception:
        return ""


def _answer_multichoice_in_block(qel, key, p_correct: float) -> bool:
    inputs = qel.find_elements(By.CSS_SELECTOR, "div.answer input[type='radio'], div.answer input[type='checkbox']")
    if not inputs:
        return False

    options = []
    for inp in inputs:
        if not inp.is_displayed():
            continue
        labelledby = inp.get_attribute("aria-labelledby") or ""
        text = ""
        if labelledby:
            try:
                lab = qel.find_element(By.ID, labelledby)
                text = lab.text or ""
            except Exception:
                text = ""
        options.append((inp, _norm(text)))

    if not options:
        return False

    correct = set(key.correct_choices_text or [])
    do_correct = (random.random() < p_correct) and bool(correct)

    if do_correct:
        candidates = [inp for (inp, t) in options if t in correct]
        if candidates:
            random.choice(candidates).click()
            return True

    wrong = [inp for (inp, t) in options if t not in correct]
    random.choice(wrong or [inp for (inp, _) in options]).click()
    return True


def _answer_shortanswer_in_block(qel, key, p_correct: float) -> bool:
    try:
        inp = qel.find_element(By.CSS_SELECTOR, "input[type='text'], textarea")
    except NoSuchElementException:
        return False

    if not inp.is_displayed():
        return False

    if key.correct_shortanswers and random.random() < p_correct:
        text = random.choice(key.correct_shortanswers)
    else:
        if key.correct_shortanswers:
            text = random.choice(key.correct_shortanswers)[::-1]
        else:
            text = "Test answer"

    try:
        inp.clear()
    except Exception:
        pass
    inp.send_keys(text)
    return True


def _answer_matching_in_block(qel, key, p_correct: float) -> bool:
    rows = qel.find_elements(By.CSS_SELECTOR, "tr")
    if not rows:
        return False

    answered = False
    for row in rows:
        try:
            prompt_el = row.find_element(By.CSS_SELECTOR, "td.text")
            prompt_text = _norm(prompt_el.text or "")
        except NoSuchElementException:
            continue

        try:
            sel_el = row.find_element(By.CSS_SELECTOR, "select")
        except NoSuchElementException:
            continue

        sel = Select(sel_el)
        if len(sel.options) <= 1:
            continue

        correct_answer = key.matching_pairs.get(prompt_text) if key and key.matching_pairs else None

        do_correct = (random.random() < p_correct) and bool(correct_answer)

        if do_correct and correct_answer:
            for i, opt in enumerate(sel.options):
                if i == 0:  # Skip "Choose..." option
                    continue
                if _norm(opt.text) == correct_answer:
                    sel.select_by_index(i)
                    answered = True
                    break
            else:
                # Correct answer not found in options, select random
                sel.select_by_index(random.randint(1, len(sel.options) - 1))
                answered = True
        else:
            # Select wrong answer (not the correct one) or random
            wrong_indices = []
            for i, opt in enumerate(sel.options):
                if i == 0:
                    continue
                if correct_answer and _norm(opt.text) == correct_answer:
                    continue
                wrong_indices.append(i)

            if wrong_indices:
                sel.select_by_index(random.choice(wrong_indices))
            else:
                sel.select_by_index(random.randint(1, len(sel.options) - 1))
            answered = True

    return answered


def _answer_matching_random(qel) -> bool:
    selects = qel.find_elements(By.CSS_SELECTOR, "select")
    if not selects:
        return False
    for sel_el in selects:
        try:
            sel = Select(sel_el)
            # Skip option[0] "Choose..."
            if len(sel.options) > 1:
                sel.select_by_index(random.randint(1, len(sel.options) - 1))
        except Exception:
            continue
    return True


def click_mark_as_done(driver):
    try:
        # Ищем кнопку "Mark as done" в области activity-information
        mark_done_selectors = [
            "div[data-region='activity-information'] button:not([disabled])",
            "button.btn:not([disabled])",
        ]
        
        for selector in mark_done_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    btn_text = (btn.text or "").strip().lower()
                    if "mark as done" in btn_text and btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        print(f"    Нажата кнопка 'Mark as done'")
                        time.sleep(1)
                        return True
            except:
                continue
        
        return False
    except Exception as e:
        print(f"    Ошибка при нажатии 'Mark as done': {e}")
        return False


def complete_book_module(driver, book_url):
    print(f"  Проходим Book модуль: {book_url}")
    driver.get(book_url)
    time.sleep(1)
    
    page_count = 0
    max_pages = 100
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
        
        print(f"    Страница {page_count + 1} (chapterid={current_chapter})")
        
        if process_page_videos(driver):
            print(f"    Видео на странице обработано")
        else:
            time.sleep(view_time)
        
        click_mark_as_done(driver)
        
        next_button = None
        next_chapter = current_chapter + 1 if current_chapter is not None else 1
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


def complete_quiz(driver, quiz_url, qbank_by_qtext: dict):
    print(f"  Проходим Quiz: {quiz_url}")
    driver.get(quiz_url)
    time.sleep(1)

    parsed = urlparse(quiz_url)
    cmid = parse_qs(parsed.query).get("id", [None])[0]
    if not cmid:
        print(f"    Ошибка: не найден cmid в URL {quiz_url}")
        return

    started = False
    for xp in [
        "//input[@type='submit' and (contains(@value,'Attempt') or contains(@value,'Re-attempt') or contains(@value,'Attempt quiz'))]",
        "//button[contains(.,'Attempt') or contains(.,'Re-attempt') or contains(.,'Attempt quiz')]",
    ]:
        try:
            driver.find_element(By.XPATH, xp).click()
            started = True
            time.sleep(2)
            break
        except NoSuchElementException:
            pass

    try:
        driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='startattempt']").click()
        started = True
        time.sleep(2)
    except NoSuchElementException:
        pass

    max_pages = 20
    for _ in range(max_pages):
        time.sleep(random.uniform(QUIZ_ATTEMPT_MIN_SEC, QUIZ_ATTEMPT_MAX_SEC))

        questions = driver.find_elements(By.CSS_SELECTOR, "div.que")
        if not questions:
            break

        for qel in questions:
            qid = _get_qid_from_question_el(qel)
            qtext = _get_qtext_from_question_el(qel)
            qtext_norm = norm_text(qtext)

            # Match by question text
            key = qbank_by_qtext.get(qtext_norm)
            cls = (qel.get_attribute("class") or "").lower()

            try:
                if key and key.qtype in ("multichoice", "truefalse"):
                    _answer_multichoice_in_block(qel, key, P_CORRECT)
                elif key and key.qtype == "shortanswer":
                    _answer_shortanswer_in_block(qel, key, P_CORRECT)
                elif key and key.qtype == "matching":
                    _answer_matching_in_block(qel, key, P_CORRECT)
                elif "match" in cls:
                    # Fallback for matching without key
                    _answer_matching_random(qel)
                else:
                    radios = qel.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    if radios:
                        random.choice(radios).click()
                    else:
                        cbs = qel.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                        if cbs:
                            random.choice(cbs).click()
                        else:
                            selects = qel.find_elements(By.CSS_SELECTOR, "select")
                            if selects:
                                _answer_matching_random(qel)
                            else:
                                txts = qel.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
                                if txts:
                                    txts[0].send_keys("Test answer")
            except Exception:
                continue

        try:
            btn_next = driver.find_element(By.CSS_SELECTOR, "input[type='submit'][name='next']")
            btn_next.click()
            time.sleep(2)
        except NoSuchElementException:
            break

        if "summary.php" in driver.current_url:
            break

    submit_clicked = False
    submit_selectors = [
        "input[type='submit'][name='submitallandfinish']",
        "button[type='submit'][id^='single_button']",
        "button.btn-primary[type='submit']",
    ]
    for selector in submit_selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed() and "submit all" in (btn.text or btn.get_attribute("value") or "").lower():
                btn.click()
                submit_clicked = True
                time.sleep(1)
                break
        except NoSuchElementException:
            continue
    
    if submit_clicked:
        try:
            # Wait for modal to appear and click the confirm button
            modal_confirm = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.modal-footer button[data-action='save']"))
            )
            modal_confirm.click()
            time.sleep(2)
        except Exception:
            # Try alternative selector for modal confirm button
            try:
                modal_btn = driver.find_element(By.CSS_SELECTOR, "div.modal-content button.btn-primary[data-action='save']")
                if modal_btn.is_displayed():
                    modal_btn.click()
                    time.sleep(2)
            except NoSuchElementException:
                pass


def complete_all_modules_and_quizzes(driver, module_links, qbank_by_qtext):
    print(f"\nНайдено модулей: {len(module_links)}")
    quiz_count = 0
    video_count = 0

    for href in module_links:
        if "/mod/book/view.php" in href:
            complete_book_module(driver, href)
        elif "/mod/quiz/view.php" in href:
            quiz_count += 1
            complete_quiz(driver, href, qbank_by_qtext)
        else:
            print(f"Открываем модуль: {href}")
            driver.get(href)
            time.sleep(random.uniform(MODULE_VIEW_MIN_SEC, MODULE_VIEW_MAX_SEC))
            
            if process_page_videos(driver):
                video_count += 1
            
            click_mark_as_done(driver)

    if quiz_count:
        print(f"\nОбработано квизов: {quiz_count}")
    if video_count:
        print(f"Обработано модулей с видео: {video_count}")


def main():
    driver = create_driver()
    qbank_by_qtext = load_question_bank(QUESTION_BANK_XML)

    try:
        for username, password in random.sample(USERS, USERS_PER_RUN):
            print(f"\n=== Полное прохождение курса под {username} ===")
            login(driver, username, password)
            enrol_to_course(driver, COURSE_ID)
            open_course(driver, COURSE_ID)
            complete_all_modules_and_quizzes(driver, get_course_modules(driver), qbank_by_qtext)
            logout(driver)
            time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
