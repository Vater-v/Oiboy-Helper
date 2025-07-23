import tkinter as tk
from tkinter import ttk
import pygetwindow as gw
import pyautogui
import threading
import time
import psutil
import os
import requests
import zipfile
import subprocess
import sys
import shutil
# --- Импорты для работы с процессами Windows ---
import win32gui
import win32process

# === Константы ===
APP_TITLE = "CGGHelper"
CURRENT_VERSION = "3.2"
TABLE_ASPECT = 557 / 424
LOBBY_ASPECT = 333 / 623
MIN_TABLE_SCALE = 0.75
TABLE_SIZE_REF = (557, 424)
LOBBY_SIZE_REF = (333, 623)
SLOTS = [
    (0, 0),      # Окно 1
    (280, 420),  # Окно 2
    (830, 0),    # Окно 3
    (1105, 425)  # Окно 4
]
LOBBY_POS = (1657, 143)
LOBBY_SIZE = (333, 623)
BOT_PLAYER_TITLE = "Holdem Desktop"
BOT_PLAYER_POS = (1386, 0)
BOT_PLAYER_SIZE = (701, 364)
CAMTASIA_POS = (1256, 836)
RESTART_INTERVAL = 4 * 60 * 60  # 4 часа в секундах
INITIAL_DELAY_SEC = 2
FLASH_DURATION = 2500
BLINK_TRIGGER_TIME = 25 * 60  # Мигание начинается за 25 минут до конца

# === Константы для автообновления ===
GITHUB_REPO = "Vater-v/Oiboy-Helper" # Укажите ваш репозиторий
UPDATE_DIR = "update_temp"
UPDATE_ARCHIVE = "update.zip"

# === Глобальные переменные ===
auto_recording = False
is_recording = False
blinking = False
halt_event = threading.Event()
remaining_time = RESTART_INTERVAL
# Потоки
recording_thread = None
progress_thread = None
monitor_thread = None

# --- Функции логирования и сообщений ---

def log(msg):
    """Выводит сообщение в консоль и показывает всплывающее уведомление."""
    try:
        print(msg)
        # Обновляем GUI в основном потоке, чтобы избежать ошибок
        if 'root' in globals() and root.winfo_exists():
            root.after(0, lambda: flash_message(msg))
    except Exception as e:
        print(f"Error in log: {e}")
        # Попытка вывести сообщение, даже если есть проблемы с кодировкой
        print(msg.encode("ascii", "replace").decode())

def flash_message(text, duration=FLASH_DURATION):
    """Показывает временное всплывающее сообщение по центру главного окна."""
    try:
        flash = tk.Toplevel(root)
        flash.overrideredirect(True)
        flash.attributes("-topmost", True)
        flash.attributes("-alpha", 0.0)
        flash.configure(bg="#ff9800")
        width, height = 320, 60
        x = root.winfo_x() + root.winfo_width() // 2 - width // 2
        y = root.winfo_y() + root.winfo_height() // 2 - height // 2
        flash.geometry(f"{width}x{height}+{x}+{y}")
        tk.Label(flash, text=text, font=("Segoe UI", 12, "bold"), bg="#ff9800", fg="white").pack(expand=True, fill="both")

        def fade_in(step=0):
            alpha = step / 10
            flash.attributes("-alpha", alpha)
            if step < 10:
                flash.after(30, lambda: fade_in(step + 1))
            else:
                flash.after(duration, fade_out)

        def fade_out(step=10):
            alpha = step / 10
            flash.attributes("-alpha", alpha)
            if step > 0:
                flash.after(30, lambda: fade_out(step - 1))
            else:
                flash.destroy()

        fade_in()
    except Exception as e:
        print(f"Failed to create flash message: {e}")


# --- Функции автообновления ---

def check_for_updates():
    """Проверяет наличие обновлений на GitHub в отдельном потоке."""
    def run_check():
        log("Проверка обновлений...")
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                release_info = response.json()
                latest_version = release_info["tag_name"].lstrip('v')
                
                if float(latest_version) > float(CURRENT_VERSION):
                    log(f"Доступна новая версия: {latest_version}. Скачиваю...")
                    asset = next((a for a in release_info["assets"] if a['name'].endswith('.zip')), None)
                    if asset:
                        download_url = asset["browser_download_url"]
                        download_and_update(download_url)
                    else:
                        log("Ошибка: в релизе не найден .zip архив.")
                else:
                    log("Вы используете последнюю версию.")
            else:
                log(f"Ошибка проверки обновлений: {response.status_code}")
        except Exception as e:
            log(f"Ошибка при проверке обновлений: {e}")
    
    threading.Thread(target=run_check, daemon=True).start()


def download_and_update(download_url):
    """Скачивает, распаковывает и устанавливает обновление."""
    try:
        current_exe_path = os.path.abspath(sys.executable)
        current_exe_name = os.path.basename(current_exe_path)
        base_dir = os.path.dirname(current_exe_path)
        archive_path = os.path.join(base_dir, UPDATE_ARCHIVE)
        extract_path = os.path.join(base_dir, UPDATE_DIR)
        updater_script_path = os.path.join(base_dir, "updater.bat")

        log("Скачивание архива...")
        response = requests.get(download_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(archive_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)
        
        log("Архив скачан. Распаковка...")
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)
        os.makedirs(extract_path)
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        
        # --- ОБНОВЛЕННЫЙ БЛОК ПОИСКА И ДИАГНОСТИКИ ---
        log("Пауза 2 сек перед поиском...")
        time.sleep(2) # Увеличена пауза до 2 секунд

        log(f"Поиск нового .exe в папке: {extract_path}")
        new_exe_location = None
        
        extracted_files = []
        for root_dir, _, files in os.walk(extract_path):
            for file in files:
                full_path = os.path.abspath(os.path.join(root_dir, file))
                extracted_files.append(full_path)
                if file.lower().endswith('.exe'):
                    new_exe_location = full_path
                    log(f"Найден новый .exe: {new_exe_location}")
                    break
            if new_exe_location:
                break
        
        if not new_exe_location:
            log("--- ДИАГНОСТИКА ОШИБКИ ---")
            log(f"Путь текущего файла: {current_exe_path}")
            log(f"Папка для распаковки: {extract_path}")
            log("Содержимое распакованного архива:")
            if extracted_files:
                for f in extracted_files:
                    log(f"- {f}")
            else:
                log("- Папка пуста или не удалось прочитать содержимое.")
            log("--- КОНЕЦ ДИАГНОСТИКИ ---")
            log("Критическая ошибка: .exe файл не найден в архиве. Проверьте логи антивируса.")
            shutil.rmtree(extract_path)
            os.remove(archive_path)
            return
        # --- КОНЕЦ ОБНОВЛЕННОГО БЛОКА ---

        log("Создание скрипта обновления (updater.bat)...")
        # Улучшенный bat-файл с принудительным завершением процесса
        bat_script_content = f"""@echo off
chcp 65001 > NUL
echo.
echo =========================
echo   CGGHelper Updater
echo =========================
echo.
echo [1/6] Завершение старого процесса (если он еще запущен)...
taskkill /F /IM "{current_exe_name}" > NUL 2>&1

echo [2/6] Ожидание закрытия старой версии (3 сек)...
timeout /t 3 /nobreak > NUL

echo [3/6] Переименование старого файла в .old...
ren "{current_exe_path}" "{current_exe_name}.old"

echo [4/6] Копирование нового файла...
copy /Y "{new_exe_location}" "{current_exe_path}"

echo [5/6] Очистка временных файлов...
rd /s /q "{extract_path}"
del "{archive_path}"

echo [6/6] Запуск новой версии...
start "" "{current_exe_path}"

echo.
echo Обновление завершено! Этот скрипт самоудалится.
(goto) 2>nul & del "%~f0"
"""
        with open(updater_script_path, "w", encoding="cp1251", errors='replace') as f:
            f.write(bat_script_content)

        log("Запуск обновления и выход...")
        subprocess.Popen([updater_script_path], shell=True, creationflags=subprocess.DETACHED_PROCESS)
        root.after(200, root.quit)

    except Exception as e:
        log(f"Критическая ошибка при обновлении: {e}")


# --- Функции для работы с окнами и записью ---

def is_aspect_match(w, h, ref_ratio, tol=0.03):
    return h != 0 and (ref_ratio * (1 - tol)) <= (w / h) <= (ref_ratio * (1 + tol))

def is_size_reasonable(w, h, ref_w, ref_h):
    return w >= ref_w * MIN_TABLE_SCALE and h >= ref_h * MIN_TABLE_SCALE

def is_valid_table_window(w):
    return (
        APP_TITLE not in w.title and
        w.visible and w.width > 0 and w.height > 0 and
        is_aspect_match(w.width, w.height, TABLE_ASPECT) and
        is_size_reasonable(w.width, w.height, *TABLE_SIZE_REF)
    )

def any_valid_tables_exist():
    return any(is_valid_table_window(w) for w in gw.getAllWindows())

def is_camtasia_active():
    return any("recorder" in p.info['name'].lower() for p in psutil.process_iter(attrs=['name']))

def is_recording_window_open():
    return any("Recording..." in t for t in gw.getAllTitles())

# --- Улучшенные функции для работы с Camtasia ---

def get_camtasia_hwnd():
    """Находит HWND главного окна Camtasia по PID процесса 'recorder'."""
    target_pid = None
    try:
        for p in psutil.process_iter(['name', 'pid']):
            if 'recorder' in p.info['name'].lower():
                target_pid = p.info['pid']
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None # Процесс мог исчезнуть во время итерации

    if not target_pid:
        return None

    hwnds = []
    def enum_windows_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
            return
        
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == target_pid and win32gui.GetParent(hwnd) == 0:
            hwnds.append(hwnd)
    
    try:
        win32gui.EnumWindows(enum_windows_callback, None)
    except win32gui.error:
        return None # Ошибка может возникнуть, если окно закрылось во время перебора
    
    return hwnds[0] if hwnds else None

def focus_camtasia():
    """Находит и активирует окно Camtasia с помощью его HWND."""
    hwnd = get_camtasia_hwnd()
    if hwnd:
        try:
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            return True
        except Exception as e:
            log(f"[ERR] Не удалось активировать окно Camtasia: {e}")
    return False

def start_recording():
    global is_recording
    if is_recording:
        return

    if is_camtasia_active():
        log("▶️ Запуск записи...")
        if focus_camtasia():
            pyautogui.press("f9")
            time.sleep(1.5)
            if is_recording_window_open():
                is_recording = True
                log("✅ Запись началась")
            else:
                log("[WARN] Запись не началась, повтор F9.")
                pyautogui.press("f9")
        else:
            log("[ERROR] Не удалось сфокусироваться на Camtasia.")
    else:
        log("[ERROR] Camtasia не активна.")

def stop_recording():
    global is_recording
    if is_recording and is_camtasia_active():
        log("⏹️ Остановка записи...")
        if focus_camtasia():
            pyautogui.press("f10")
            time.sleep(1.5)
            if not is_recording_window_open():
                is_recording = False
                log("✅ Запись остановлена")
            else:
                log("[WARN] Запись не остановилась, повтор F10.")
                pyautogui.press("f10")
    is_recording = False

# --- Основные циклы (в потоках) ---

def start_blinking_loop():
    """Цикл мигания фона. Управляется флагом `blinking`."""
    global blinking
    def _blink_loop():
        while blinking:
            if halt_event.is_set() or not auto_recording:
                break
            
            root.after(0, lambda: root.configure(bg="#ffcccc"))
            time.sleep(0.4)
            root.after(0, lambda: root.configure(bg="#ffffff"))
            time.sleep(0.4)
            root.after(0, lambda: root.configure(bg="#1e1e1e"))
            time.sleep(1)
        
        root.after(0, lambda: root.configure(bg="#1e1e1e"))

    blinking = True
    threading.Thread(target=_blink_loop, daemon=True).start()

def update_progress():
    """Обновляет прогресс-бар и таймер каждую секунду."""
    while auto_recording and not halt_event.is_set():
        if remaining_time >= 0:
            mins, secs = divmod(remaining_time, 60)
            hrs, mins = divmod(mins, 60)
            
            root.after(0, lambda: label_time.set(f"След. перезапуск: {hrs:02}:{mins:02}:{secs:02}"))
            root.after(0, lambda: progress.config(value=100 * (RESTART_INTERVAL - remaining_time) / RESTART_INTERVAL))
        
        time.sleep(1)

def recording_cycle():
    """Основной цикл записи. Автоматически перезапускается каждые 4 часа."""
    global remaining_time, blinking

    while auto_recording and not halt_event.is_set():
        root.after(0, lambda: status_label.set("⏳ Подготовка..."))
        stop_recording()
        time.sleep(INITIAL_DELAY_SEC)
        
        if halt_event.is_set(): return
        
        start_recording()
        
        if not is_recording:
            log("Не удалось начать запись. Попытка через 10 сек.")
            time.sleep(10)
            continue

        remaining_time = RESTART_INTERVAL
        
        while remaining_time > 0:
            if halt_event.is_set():
                stop_recording()
                return

            if not is_camtasia_active():
                log("❌ Camtasia закрыта. Запись остановлена.")
                root.after(0, lambda: toggle_auto(force_state=False))
                return

            if any('Paused...' in t for t in gw.getAllTitles()):
                log("⏸️ Запись на паузе — перезапуск...")
                stop_recording()
                time.sleep(1)
                start_recording()

            if remaining_time <= BLINK_TRIGGER_TIME and not blinking:
                start_blinking_loop()

            time.sleep(1)
            remaining_time -= 1
        
        log("⏰ 4-часовой цикл завершен. Перезапуск записи...")
        if blinking:
            blinking = False
        
        stop_recording()
        time.sleep(5)

def monitor_loop():
    """Постоянно проверяет, не появились ли столы, чтобы запустить автозапись."""
    while not halt_event.is_set():
        time.sleep(3)
        if not auto_recording and any_valid_tables_exist():
            log("🧠 Найден стол — запуск автозаписи")
            root.after(0, lambda: toggle_auto(force_state=True))

# --- Функции управления и GUI ---

def toggle_auto(force_state=None):
    """Переключение режима автозаписи."""
    global auto_recording, recording_thread, progress_thread, blinking
    
    should_be_on = not auto_recording if force_state is None else force_state

    if not should_be_on: # Выключаем
        if auto_recording:
            log("Автозапись выключается...")
            halt_event.set()
            blinking = False
            auto_recording = False
            stop_recording()
            toggle_btn.config(text="Автозапись: ВЫКЛ", bg="#555")
            status_label.set("Автозапись отключена")
            label_time.set("След. перезапуск: --:--:--")
            progress.config(value=0)
    else: # Включаем
        if not auto_recording:
            if not is_camtasia_active():
                status_label.set("❗ Camtasia не запущена")
                return
            log("Автозапись включается...")
            halt_event.clear()
            auto_recording = True
            blinking = False
            
            recording_thread = threading.Thread(target=recording_cycle, daemon=True)
            progress_thread = threading.Thread(target=update_progress, daemon=True)
            
            recording_thread.start()
            progress_thread.start()
            
            toggle_btn.config(text="Автозапись: ВКЛ", bg="#4CAF50")
            status_label.set("Автозапись включена")

def place_tables():
    log("[CGG] Расстановка столов...")
    tables = [w for w in gw.getAllWindows() if is_valid_table_window(w)][:4]
    if not tables:
        log("Не найдено валидных столов.")
        return
    for i, (win, (x, y)) in enumerate(zip(tables, SLOTS), 1):
        try:
            win.restore()
            time.sleep(0.1)
            win.moveTo(x, y)
            win.resizeTo(*TABLE_SIZE_REF)
            log(f"Стол {i} — {win.title}")
        except Exception as e:
            log(f"[ERR] Стол {i}: {e}")

def place_lobby_bot_rec():
    log("[CGG] Расстановка остального...")
    
    # 1. Размещаем Camtasia с помощью win32 (надежно)
    camtasia_hwnd = get_camtasia_hwnd()
    if camtasia_hwnd:
        try:
            # Флаги для SetWindowPos: NOZORDER | NOSIZE
            win32gui.SetWindowPos(camtasia_hwnd, 0, CAMTASIA_POS[0], CAMTASIA_POS[1], 0, 0, 0x0001 | 0x0004)
            log("✅ Camtasia размещена")
        except Exception as e:
            log(f"[ERR] Не удалось разместить Camtasia: {e}")
    
    # 2. Размещаем остальные окна с помощью pygetwindow
    for win in gw.getAllWindows():
        try:
            # Пропускаем Camtasia, так как мы ее уже обработали
            if camtasia_hwnd and win.title == win32gui.GetWindowText(camtasia_hwnd):
                continue
            
            if BOT_PLAYER_TITLE in win.title:
                win.restore()
                win.moveTo(*BOT_PLAYER_POS)
                win.resizeTo(*BOT_PLAYER_SIZE)
                log("✅ Бот-плеер размещён")
            elif is_aspect_match(win.width, win.height, LOBBY_ASPECT, tol=0.02) and win.width > 300:
                win.restore()
                win.moveTo(*LOBBY_POS)
                win.resizeTo(*LOBBY_SIZE)
                win.alwaysOnTop = True
                log("✅ Лобби размещено")
        except Exception as e:
            log(f"[ERR] Ошибка размещения окна '{win.title}': {e}")

# === Инициализация и запуск ===
if __name__ == "__main__":
    root = tk.Tk()
    root.title(f"CGGHelper – Утилита v{CURRENT_VERSION}")
    root.geometry("420x290")
    root.configure(bg="#1e1e1e")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    try:
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(__file__)
        icon_path = os.path.join(base_path, "icon.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception as e:
        print(f"Не удалось загрузить иконку: {e}")

    status_label = tk.StringVar(value="Готов к работе")
    label_time = tk.StringVar(value="След. перезапуск: --:--:--")

    # --- GUI виджеты ---
    tk.Label(root, text="ClubGG – Панель управления", font=("Segoe UI", 13, "bold"), fg="white", bg="#1e1e1e").pack(pady=(12, 6))
    frame = tk.Frame(root, bg="#1e1e1e")
    frame.pack(padx=16, fill="x")

    btn1 = tk.Button(frame, text="🃏 Расставить столы", font=("Segoe UI", 11), bg="#4CAF50", fg="white", command=place_tables)
    btn2 = tk.Button(frame, text="📐 Остальное", font=("Segoe UI", 11), bg="#FFC107", fg="black", command=place_lobby_bot_rec)
    toggle_btn = tk.Button(frame, text="Автозапись: ВЫКЛ", font=("Segoe UI", 11), bg="#555", fg="white", command=toggle_auto)
    
    for i, btn in enumerate((btn1, btn2, toggle_btn)):
        btn.grid(row=i, column=0, sticky="ew", pady=5)
        frame.grid_rowconfigure(i, weight=1)
    frame.grid_columnconfigure(0, weight=1)

    ttk.Style().configure("TProgressbar", troughcolor="#333", background="#76d275", thickness=12)
    progress = ttk.Progressbar(root, orient="horizontal", length=320, mode="determinate")
    progress.pack(pady=(14, 4))
    
    tk.Label(root, textvariable=label_time, font=("Segoe UI", 9), fg="lightgray", bg="#1e1e1e").pack()
    tk.Label(root, textvariable=status_label, font=("Segoe UI", 8), fg="gray", bg="#1e1e1e").pack()

    # --- Запуск фоновых процессов ---
    root.after(1000, check_for_updates)

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    
    root.mainloop()

