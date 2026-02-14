import random
import time
from urllib.parse import urlparse, parse_qs

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium_common import (
    USERS, create_driver, login, logout,
    enrol_to_course, open_course
)

COURSE_ID = 4
VIDEO_PLAY_MIN_SEC = 25.0      # Минимальное время воспроизведения
VIDEO_PLAY_MAX_SEC = 70.0     # Максимальное время воспроизведения
PAUSE_PROBABILITY = 0.3       # Вероятность паузы (30%)
SEEK_PROBABILITY = 0.8      # Вероятность перемотки (40%)
SEEK_BACKWARD_PROBABILITY = 0.3  # Вероятность перемотки назад (30% от всех перемоток)
MAX_VIDEOS_PER_USER = 5     # Максимум видео на пользователя
VIDEO_PLAYBACK_RATE = 2.0    # Скорость воспроизведения (1.0 = нормальная, 2.0 = x2)


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

def is_resource_view_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if not p.path.endswith("/mod/resource/view.php"):
            return False
        qs = parse_qs(p.query)
        return "id" in qs and len(qs["id"]) > 0 and qs["id"][0].isdigit()
    except Exception:
        return False

def find_video_elements(driver):
    """Находит все видео/аудио элементы на странице."""
    time.sleep(1)
    videos = []
    found_ids = set()
    
    # Инициализируем ленивые VideoJS плееры (data-setup-lazy)
    try:
        driver.execute_script("""
            // Инициализируем все ленивые VideoJS плееры
            if (window.videojs) {
                document.querySelectorAll('video[data-setup-lazy], audio[data-setup-lazy]').forEach(function(el) {
                    if (!el.player && el.id) {
                        try {
                            var setup = JSON.parse(el.getAttribute('data-setup-lazy') || '{}');
                            videojs(el.id, setup);
                            console.log('Initialized lazy player:', el.id);
                        } catch(e) {
                            console.log('Error initializing player:', e);
                        }
                    }
                });
            }
        """)
        time.sleep(2)  # Даём время на инициализацию
    except Exception as e:
        print(f"  Ошибка при инициализации ленивых плееров: {e}")
    
    # Сначала ищем VideoJS плееры (включая YouTube через VideoJS)
    # Используем JavaScript для получения всех VideoJS плееров
    # try:
    #     videojs_players = driver.execute_script("""
    #         if (window.videojs && window.videojs.getPlayers) {
    #             var players = window.videojs.getPlayers();
    #             var result = [];
    #             for (var id in players) {
    #                 if (players[id]) {
    #                     result.push(id);
    #                     console.log('Found VideoJS player:', id);
    #                 }
    #             }
    #             return result;
    #         }
    #         return [];
    #     """)
        
    #     print(f"  VideoJS плееры найдены: {videojs_players}")
        
    #     for player_id in (videojs_players or []):
    #         if player_id and player_id not in found_ids:
    #             try:
    #                 elem = driver.find_element(By.ID, player_id)
    #                 videos.append(('videojs', elem))
    #                 found_ids.add(player_id)
    #             except:
    #                 pass
    # except Exception as e:
    #     print(f"  Ошибка при поиске VideoJS плееров: {e}")
    
    # Ищем VideoJS контейнеры по классу (если не нашли через JS API)
    for selector in [".video-js", "video.video-js", "audio.video-js"]:
        try:
            for elem in driver.find_elements(By.CSS_SELECTOR, selector):
                elem_id = elem.get_attribute("id")
                if elem_id and elem_id not in found_ids:
                    videos.append(('videojs', elem))
                    found_ids.add(elem_id)
                    print(f"  Найден VideoJS по селектору: {elem_id}")
        except:
            continue

    
    # Ищем нативные video/audio элементы (не внутри VideoJS)
    # for tag in ['video', 'audio']:
    #     for elem in driver.find_elements(By.TAG_NAME, tag):
    #         elem_id = elem.get_attribute("id") or f"native_{id(elem)}"
    #         # Проверяем, что это не часть VideoJS
    #         elem_class = elem.get_attribute("class") or ""
    #         if "video-js" in elem_class or elem_id in found_ids:
    #             continue
            
    #         parent_class = ""
    #         try:
    #             parent = elem.find_element(By.XPATH, "./..")
    #             parent_class = parent.get_attribute("class") or ""
    #         except:
    #             pass
            
    #         if "video-js" not in parent_class:
    #             videos.append(('native', elem))
    #             found_ids.add(elem_id)
    
    if videos:
        print(f"  Найдено {len(videos)} медиа элементов на странице")
    else:
        print(f"  Медиа элементы не найдены")
    return videos


def set_playback_rate(driver, video_type, element, rate=VIDEO_PLAYBACK_RATE):
    """Устанавливает скорость воспроизведения видео."""
    try:
        if video_type == 'native':
            driver.execute_script(f"arguments[0].playbackRate = {rate};", element)
        elif video_type == 'videojs':
            video_id = element.get_attribute("id")
            if not video_id:
                try:
                    parent = element.find_element(By.XPATH, "./ancestor::*[contains(@class,'video-js')][1]")
                    video_id = parent.get_attribute("id")
                except:
                    pass
            
            if video_id:
                # Для VideoJS (включая YouTube tech) используем playbackRate()
                # Нужно дождаться готовности плеера
                result = driver.execute_script(f"""
                    if (window.videojs) {{
                        var player = window.videojs.getPlayer('{video_id}');
                        if (player) {{
                            // Пробуем установить скорость напрямую
                            try {{
                                player.playbackRate({rate});
                                console.log('VideoJS playbackRate set to {rate}');
                                return 'set';
                            }} catch(e) {{
                                console.log('Error setting playbackRate:', e);
                            }}
                            
                            // Для YouTube tech пробуем через tech
                            try {{
                                var tech = player.tech(true);
                                if (tech && tech.ytPlayer && tech.ytPlayer.setPlaybackRate) {{
                                    tech.ytPlayer.setPlaybackRate({rate});
                                    console.log('YouTube playbackRate set to {rate}');
                                    return 'youtube';
                                }}
                            }} catch(e) {{
                                console.log('Error setting YouTube playbackRate:', e);
                            }}
                        }}
                    }}
                    return 'failed';
                """)
                print(f"    Установка скорости {rate}x: {result}")
            else:
                driver.execute_script(f"arguments[0].playbackRate = {rate};", element)
        elif video_type == 'youtube':
            pass
        return True
    except Exception as e:
        print(f"    Ошибка при установке скорости: {e}")
        return False


def play_video(driver, video_type, element):
    """Запускает воспроизведение видео и устанавливает скорость."""
    try:
        video_id = element.get_attribute("id")
        
        if video_type == 'native':
            driver.execute_script("arguments[0].play().catch(function(e) {});", element)
            time.sleep(1)
        elif video_type == 'videojs':
            if not video_id:
                try:
                    parent = element.find_element(By.XPATH, "./ancestor::*[contains(@class,'video-js')][1]")
                    video_id = parent.get_attribute("id")
                except:
                    pass
            
            played = False
            if video_id:
                # Пробуем запустить через VideoJS API и сразу установить скорость
                result = driver.execute_script(f"""
                    if (window.videojs) {{
                        var player = window.videojs.getPlayer('{video_id}');
                        if (player) {{
                            // Запускаем воспроизведение
                            player.play();
                            
                            // Ждём готовности и устанавливаем скорость
                            player.ready(function() {{
                                setTimeout(function() {{
                                    try {{
                                        player.playbackRate({VIDEO_PLAYBACK_RATE});
                                        console.log('Playback rate set to {VIDEO_PLAYBACK_RATE}');
                                    }} catch(e) {{
                                        console.log('Error setting playback rate:', e);
                                    }}
                                }}, 1000);
                            }});
                            
                            return 'played';
                        }}
                    }}
                    return 'no_player';
                """)
                played = (result == 'played')
                print(f"    VideoJS play result: {result}")
            
            if not played:
                # Пробуем кликнуть по кнопке воспроизведения
                try:
                    # Сначала пробуем большую кнопку play
                    big_play = element.find_element(By.CSS_SELECTOR, ".vjs-big-play-button")
                    if big_play.is_displayed():
                        big_play.click()
                        played = True
                        print("    Clicked big play button")
                except:
                    pass
                
                if not played:
                    try:
                        # Пробуем кнопку play в контролах
                        play_control = element.find_element(By.CSS_SELECTOR, ".vjs-play-control")
                        if play_control.is_displayed():
                            play_control.click()
                            played = True
                            print("    Clicked play control")
                    except:
                        pass
                
                if not played:
                    # Последняя попытка - клик по самому элементу
                    try:
                        ActionChains(driver).move_to_element(element).click().perform()
                        print("    Clicked on element")
                    except:
                        pass
                        
        elif video_type == 'youtube':
            try:
                ActionChains(driver).move_to_element(element).click().perform()
            except:
                pass
        
        time.sleep(2)  # Даём время на загрузку и начало воспроизведения
        
        # Повторно пробуем установить скорость (для YouTube через VideoJS)
        if video_type == 'videojs' and video_id:
            driver.execute_script(f"""
                if (window.videojs) {{
                    var player = window.videojs.getPlayer('{video_id}');
                    if (player) {{
                        try {{
                            player.playbackRate({VIDEO_PLAYBACK_RATE});
                            console.log('Retry: Playback rate set to {VIDEO_PLAYBACK_RATE}');
                        }} catch(e) {{
                            console.log('Retry error:', e);
                        }}
                    }}
                }}
            """)
        else:
            # Устанавливаем скорость воспроизведения для других типов
            set_playback_rate(driver, video_type, element)
        
        time.sleep(1)
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
            pause_time = random.uniform(0.5, 2.0)
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
        chunk_time = random.uniform(0.5, 2.0)
        time.sleep(chunk_time)
        elapsed_time += chunk_time
        last_position = min(95, last_position + (chunk_time / 60 * 100))  # Примерный прогресс
    
    print(f"  Просмотр завершён (~{elapsed_time:.1f} сек)")


def process_page_videos(driver):
    """Обрабатывает все видео на текущей странице (без перехода по URL)."""
    videos = find_video_elements(driver)
    
    if not videos:
        return False
    
    # Обрабатываем каждое найденное видео
    for video_type, element in videos:
        try:
            watch_video(driver, video_type, element)
            time.sleep(1)  # Пауза между видео
        except Exception as e:
            print(f"  Ошибка при обработке видео: {e}")
            continue
    
    return True


def process_video_module(driver, module_type, module_url):
    """Обрабатывает модуль с видео."""
    print(f"\nОткрываем модуль {module_type}: {module_url}")
    driver.get(module_url)
    time.sleep(2)  # Ждём загрузки страницы
    
    # Используем общую функцию для обработки видео на странице
    if not process_page_videos(driver):
        print("  Видео не найдено на странице")


def main():
    driver = create_driver()
    try:
        for username, password in random.sample(USERS, min(5, len(USERS))):
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
