import random
import time
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException


BASE_URL = "http://localhost:8000"
    
def create_driver(incognito: bool = True, start_maximized: bool = True):
    options = Options()
    if incognito:
        options.add_argument("--incognito")
    if start_maximized:
        options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver


def login(driver, username: str, password: str):
    driver.get(f"{BASE_URL}/login/index.php")
    user_input = driver.find_element(By.ID, "username")
    pass_input = driver.find_element(By.ID, "password")
    user_input.clear()
    pass_input.clear()
    user_input.send_keys(username)
    pass_input.send_keys(password)
    driver.find_element(By.ID, "loginbtn").click()
    time.sleep(2)


def logout(driver):
    driver.get(f"{BASE_URL}/login/logout.php")
    time.sleep(1)
    try:
        button = driver.find_element(
            By.CSS_SELECTOR,
            "button.btn.btn-primary[type='submit']"
        )
        print("Найдена кнопка logout:", button.get_attribute("id"))
        button.click()
        time.sleep(2)
    except NoSuchElementException:
        print("Кнопка подтверждения logout (btn-primary) не найдена")


def enrol_to_course(driver, course_id: int):
    """Самозапись на курс через /enrol/index.php?id=COURSE_ID."""
    url = f"{BASE_URL}/enrol/index.php?id={course_id}"
    print("Пробуем самозапись:", url)
    driver.get(url)
    time.sleep(2)

    try:
        button = driver.find_element(
            By.CSS_SELECTOR,
            "input.btn.btn-primary[type='submit'][id='id_submitbutton']"
        )
        label = button.get_attribute("value")
        print("Найдена кнопка Enrol me:", label)
        button.click()
        time.sleep(3)
    except NoSuchElementException:
        print("Кнопка Enrol me не найдена (возможно, студент уже записан)")


def open_course(driver, course_id: int):
    driver.get(f"{BASE_URL}/course/view.php?id={course_id}")
    time.sleep(2)


def get_course_modules(driver):
    """Собираем ссылки на модули /mod/.../view.php?id=..., исключая файлы."""
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/mod/'][href*='/view.php?id=']")
    hrefs = []
    for a in links:
        href = a.get_attribute("href")
        if not href:
            continue
        if "/mod/resource/" in href:
            continue
        if href not in hrefs:
            hrefs.append(href)
    print(f"Найдено {len(hrefs)} модулей (resource исключены)")
    return hrefs


def get_course_sections(driver):
    """Собираем ссылки на разделы /course/section.php?id=... (если есть)."""
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/course/section.php?id=']")
    hrefs = []
    for a in links:
        href = a.get_attribute("href")
        if href and href not in hrefs:
            hrefs.append(href)
    print(f"Найдено {len(hrefs)} секций курса")
    return hrefs


def open_random_sections(driver, section_links, max_sections_per_user: int):
    if not section_links:
        return
    links = section_links.copy()
    random.shuffle(links)
    links = links[:max_sections_per_user]
    for href in links:
        print(f"Открываем секцию: {href}")
        driver.get(href)
        time.sleep(random.uniform(3.0, 7.0))
