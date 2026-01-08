import random
import time
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium_common import (
    USERS, BASE_URL, create_driver, login, logout,
    enrol_to_course, open_course, get_course_modules
)

COURSE_ID = 5  # Курс "Marvellous media players"

# Настройки просмотра видео
VIDEO_PLAY_MIN_SEC = 3.0      # Минимальное время воспроизведения
VIDEO_PLAY_MAX_SEC = 15.0     # Максимальное время воспроизведения
PAUSE_PROBABILITY = 0.3       # Вероятность паузы (30%)
SEEK_PROBABILITY = 0.4       # Вероятность перемотки (40%)
SEEK_BACKWARD_PROBABILITY = 0.3  # Вероятность перемотки назад (30% от всех перемоток)
MAX_VIDEOS_PER_USER = 3      # Максимум видео на пользователя


def find_video_modules(driver):
    """Находит все модули с видео/аудио."""
    selectors = [
        ("url", "a[href*='/mod/url/view.php?id=']"),
        ("resource", "a[href*='/mod/resource/view.php?id=']"),
        ("page", "a[href*='/mod/page/view.php?id=']"),
    ]
    
    video_modules = []
    for module_type, selector in selectors:
        links = driver.find_elements(By.CSS_SELECTOR, selector)
        for link in links:
            href = link.get_attribute("href")
            if href:
                video_modules.append((module_type, href))
    
    print(f"Найдено {len(video_modules)} потенциальных модулей с медиа")
    return video_modules


def find_video_elements(driver):
    """Находит все видео/аудио элементы на странице."""
    time.sleep(2)
    videos = []
    found_elements = set()
    
    for tag in ['video', 'audio']:
        for elem in driver.find_elements(By.TAG_NAME, tag):
            elem_id = id(elem)
            if elem_id not in found_elements:
                videos.append(('native', elem))
                found_elements.add(elem_id)
    
    for selector in [".video-js", "video.video-js", "audio.video-js"]:
        try:
            for elem in driver.find_elements(By.CSS_SELECTOR, selector):
                elem_id = id(elem)
                if elem_id not in found_elements:
                    videos.append(('videojs', elem))
                    found_elements.add(elem_id)
        except:
            continue
    
    for iframe in driver.find_elements(By.CSS_SELECTOR, "iframe[src*='youtube.com'], iframe[src*='youtu.be']"):
        elem_id = id(iframe)
        if elem_id not in found_elements:
            videos.append(('youtube', iframe))
            found_elements.add(elem_id)
    
    print(f"Найдено {len(videos)} медиа элементов на странице")
    return videos


def play_video(driver, video_type, element):
    """Запускает воспроизведение видео."""
    try:
        if video_type == 'native':
            driver.execute_script("arguments[0].play().catch(function(e) {});", element)
            time.sleep(1)
        elif video_type == 'videojs':
            video_id = element.get_attribute("id")
            if not video_id:
                try:
                    parent = element.find_element(By.XPATH, "./ancestor::*[@class='video-js'][1]")
                    video_id = parent.get_attribute("id")
                except:
                    pass
            
            if video_id:
                driver.execute_script(f"""
                    if (window.videojs) {{
                        var player = window.videojs.getPlayer('{video_id}');
                        if (player) player.play();
                    }}
                """)
            else:
                try:
                    element.find_element(By.CSS_SELECTOR, ".vjs-big-play-button, .vjs-play-control").click()
                except:
                    driver.execute_script("arguments[0].play().catch(function(e) {});", element)
        elif video_type == 'youtube':
            try:
                ActionChains(driver).move_to_element(element).click().perform()
            except:
                pass
        
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"    Ошибка при запуске: {e}")
        return False


def pause_video(driver, video_type, element):
    """Ставит видео на паузу."""
    try:
        if video_type == 'native':
            driver.execute_script("arguments[0].pause();", element)
        elif video_type == 'videojs':
            video_id = element.get_attribute("id")
            if video_id:
                driver.execute_script(f"if (window.videojs) {{ var p = window.videojs.getPlayer('{video_id}'); if (p) p.pause(); }}")
            else:
                try:
                    element.find_element(By.CSS_SELECTOR, ".vjs-play-control").click()
                except:
                    driver.execute_script("arguments[0].pause();", element)
        elif video_type == 'youtube':
            try:
                element.click()
            except:
                pass
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"    Ошибка при паузе: {e}")
        return False


def seek_video(driver, video_type, element, position_percent):
    """Перематывает видео на указанный процент."""
    try:
        if video_type == 'native':
            duration = driver.execute_script("return arguments[0].duration;", element)
            if duration and duration > 0:
                driver.execute_script(f"arguments[0].currentTime = {duration * position_percent / 100};", element)
        elif video_type == 'videojs':
            video_id = element.get_attribute("id")
            if video_id:
                driver.execute_script(f"""
                    if (window.videojs) {{
                        var p = window.videojs.getPlayer('{video_id}');
                        if (p) {{
                            var d = p.duration();
                            if (d) p.currentTime(d * {position_percent} / 100);
                        }}
                    }}
                """)
            else:
                try:
                    progress_bar = element.find_element(By.CSS_SELECTOR, ".vjs-progress-holder")
                    width = progress_bar.size['width']
                    ActionChains(driver).move_to_element(progress_bar).move_by_offset(
                        int(width * position_percent / 100) - width // 2, 0
                    ).click().perform()
                except:
                    pass
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"    Ошибка при перемотке: {e}")
        return False


def watch_video(driver, video_type, element, video_id=None):
    """Имитирует просмотр видео с паузами и перемотками."""
    print(f"  Просмотр {video_type} видео")
    
    # Запускаем видео
    if not play_video(driver, video_type, element):
        return
    
    # Время просмотра
    watch_duration = random.uniform(VIDEO_PLAY_MIN_SEC, VIDEO_PLAY_MAX_SEC)
    elapsed_time = 0
    last_position = 0
    
    while elapsed_time < watch_duration:
        # Решаем, делать ли паузу
        if random.random() < PAUSE_PROBABILITY and elapsed_time > 2:
            pause_time = random.uniform(1.0, 3.0)
            pause_video(driver, video_type, element)
            time.sleep(pause_time)
            play_video(driver, video_type, element)
            elapsed_time += pause_time
        
        # Решаем, делать ли перемотку
        if random.random() < SEEK_PROBABILITY and elapsed_time > 3:
            if random.random() < SEEK_BACKWARD_PROBABILITY:
                # Перемотка назад
                seek_percent = random.uniform(0, last_position * 0.8)
                seek_video(driver, video_type, element, seek_percent)
                last_position = seek_percent
            else:
                # Перемотка вперёд
                seek_percent = random.uniform(last_position, min(95, last_position + 20))
                seek_video(driver, video_type, element, seek_percent)
                last_position = seek_percent
        
        # Продолжаем просмотр
        chunk_time = random.uniform(2.0, 5.0)
        time.sleep(chunk_time)
        elapsed_time += chunk_time
        last_position = min(95, last_position + (chunk_time / 60 * 100))  # Примерный прогресс
    
    print(f"  Просмотр завершён (~{elapsed_time:.1f} сек)")


def process_video_module(driver, module_type, module_url):
    """Обрабатывает модуль с видео."""
    print(f"\nОткрываем модуль {module_type}: {module_url}")
    driver.get(module_url)
    time.sleep(2)  # Ждём загрузки страницы
    
    # Ищем видео элементы
    videos = find_video_elements(driver)
    
    if not videos:
        print("  Видео не найдено на странице")
        return
    
    # Обрабатываем каждое найденное видео
    for video_type, element in videos:
        try:
            watch_video(driver, video_type, element)
            time.sleep(1)  # Пауза между видео
        except Exception as e:
            print(f"  Ошибка при обработке видео: {e}")
            continue


def main():
    driver = create_driver()
    try:
        for username, password in random.sample(USERS, min(3, len(USERS))):
            print(f"\n{'='*60}\n=== Просмотр видео под {username} ===\n{'='*60}")
            login(driver, username, password)
            enrol_to_course(driver, COURSE_ID)
            open_course(driver, COURSE_ID)
            time.sleep(2)
            
            video_modules = find_video_modules(driver)
            if not video_modules:
                print("Модули с видео не найдены")
                logout(driver)
                continue
            
            random.shuffle(video_modules)
            for module_type, module_url in video_modules[:MAX_VIDEOS_PER_USER]:
                try:
                    process_video_module(driver, module_type, module_url)
                except Exception as e:
                    print(f"Ошибка при обработке модуля {module_url}: {e}")
            
            logout(driver)
            time.sleep(2)
    finally:
        driver.quit()
        print("\nТестирование завершено")


if __name__ == "__main__":
    main()
