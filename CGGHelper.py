#v1.8 maybe stable
import tkinter as tk
from tkinter import ttk
import pygetwindow as gw
import pyautogui
import threading
import time
import psutil
import subprocess

# === Константы ===
APP_TITLE = "CGGHelper"
TABLE_ASPECT = 557 / 424
LOBBY_ASPECT = 333 / 623
MIN_TABLE_SCALE = 0.75
TABLE_SIZE_REF = (557, 424)
LOBBY_SIZE_REF = (333, 623)
SLOTS = [(0, 0), (280, 420), (830, 0), (1105, 425)]
LOBBY_POS = (1622, 143)  # было 1642 — сдвиг на 20px влево
LOBBY_SIZE = (333, 623)
BOT_PLAYER_TITLE = "Holdem Desktop"
BOT_PLAYER_POS = (1386, 0)
BOT_PLAYER_SIZE = (701, 364)
CAMTASIA_TITLE = "Camtasia Recorder"
CAMTASIA_POS = (1256, 836)
RESTART_INTERVAL = 4 * 60 * 60
INITIAL_DELAY_SEC = 2
FLASH_DURATION = 2500

# === Глобальные переменные ===
auto_recording = False
is_looping = False
blinking = False
halt_event = threading.Event()
remaining_time = RESTART_INTERVAL
recording_thread = None
progress_thread = None
monitor_thread = None

# === Интерфейс ===
root = tk.Tk()
root.title(APP_TITLE + " v1.8")
root.geometry("420x290")
root.configure(bg="#1e1e1e")
root.resizable(False, False)
root.attributes("-topmost", True)
try: root.iconbitmap("icon.ico")
except: pass

status_label = tk.StringVar(value="Автозапись отключена")
label_time = tk.StringVar(value="След. перезапуск: --:--:--")
# === Уведомление + лог ===
def flash_message(text, duration=FLASH_DURATION):
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

    def fade(step=0):
        alpha = step / 10
        flash.attributes("-alpha", alpha)
        if step < 10: flash.after(30, lambda: fade(step + 1))
        else: flash.after(duration, fade_out)

    def fade_out(step=10):
        alpha = step / 10
        flash.attributes("-alpha", alpha)
        if step > 0: flash.after(30, lambda: fade_out(step - 1))
        else: flash.destroy()

    fade()

def log(msg):
    try: print(msg)
    except: print(msg.encode("ascii", "replace").decode())
    flash_message(msg)

# === Хелперы ===
def is_aspect_match(w, h, ref_ratio, tol=0.03):
    return h != 0 and (ref_ratio * (1 - tol)) <= (w / h) <= (ref_ratio * (1 + tol))

def is_size_reasonable(w, h, ref_w, ref_h):
    return w >= ref_w * MIN_TABLE_SCALE and h >= ref_h * MIN_TABLE_SCALE

def is_valid_table_window(w):
    return (
        APP_TITLE not in w.title and
        w.visible and
        is_aspect_match(w.width, w.height, TABLE_ASPECT) and
        is_size_reasonable(w.width, w.height, *TABLE_SIZE_REF)
    )

def any_valid_tables_exist():
    return any(is_valid_table_window(w) for w in gw.getAllWindows())

# === Расстановка столов ===
def place_tables():
    log("[CGG] Расстановка столов...")
    tables = [w for w in gw.getAllWindows() if is_valid_table_window(w)][:4]
    for i, (win, (x, y)) in enumerate(zip(tables, SLOTS), 1):
        try:
            win.restore(); time.sleep(0.1)
            win.moveTo(x, y)
            win.resizeTo(*TABLE_SIZE_REF)
            log(f"Стол {i} — {win.title}")
        except Exception as e:
            log(f"[ERR] Стол {i}: {e}")

# === Расстановка плеера, лобби, Camtasia ===
def place_lobby_bot_rec():
    log("[CGG] Расстановка окон...")

    # Плеер
    for win in gw.getAllWindows():
        try:
            if BOT_PLAYER_TITLE in win.title:
                win.restore()
                win.moveTo(*BOT_PLAYER_POS)
                win.resizeTo(*BOT_PLAYER_SIZE)
                win.alwaysOnTop = False
                log("✅ Бот-плеер размещён")
                break
        except Exception as e:
            log(f"[ERR] Плеер: {e}")

    # Лобби (поверх плеера)
    for win in gw.getAllWindows():
        try:
            if is_aspect_match(win.width, win.height, LOBBY_ASPECT):
                win.restore()
                win.moveTo(*LOBBY_POS)
                win.resizeTo(*LOBBY_SIZE)
                win.alwaysOnTop = True
                log("✅ Лобби размещено")
                break
        except Exception as e:
            log(f"[ERR] Лобби: {e}")

    # Camtasia (поверх всех)
    for win in gw.getAllWindows():
        try:
            if "Recording" in win.title:
                win.restore()
                win.moveTo(*CAMTASIA_POS)
                win.alwaysOnTop = True
                log("✅ Camtasia размещена")
                break
        except Exception as e:
            log(f"[ERR] Camtasia: {e}")
# === Camtasia: позиция ===
def move_camtasia_home():
    for win in gw.getWindowsWithTitle(CAMTASIA_TITLE):
        try:
            win.moveTo(*CAMTASIA_POS)
            log("↩️ Camtasia возвращена")
        except:
            pass

# === Camtasia: состояния ===
def is_camtasia_active():
    return any("recorder" in p.info['name'].lower() for p in psutil.process_iter(attrs=['name']))

def is_recording_window_open():
    return any("Recording..." in t for t in gw.getAllTitles())

def focus_camtasia():
    for w in gw.getWindowsWithTitle(CAMTASIA_TITLE):
        try:
            w.activate()
            time.sleep(0.3)
            return True
        except:
            continue
    return False

# === Запуск записи ===
def start_recording():
    global is_looping
    if not is_looping and is_camtasia_active():
        log("▶️ Старт записи")
        focus_camtasia()
        pyautogui.press("f9")
        time.sleep(1.5)
        if not is_recording_window_open():
            log("⚠️ Повтор F9")
            pyautogui.press("f9")
            time.sleep(1.5)
        if is_recording_window_open():
            is_looping = True
            log("✅ Запись началась")
            move_camtasia_home()
        else:
            log("[WARN] Camtasia не стартанула")

# === Остановка записи ===
def stop_recording():
    global is_looping, blinking
    blinking = False
    if is_looping and is_camtasia_active():
        log("⏹️ Остановка записи")
        focus_camtasia()
        pyautogui.press("f10")
        time.sleep(1.5)
        if not is_recording_window_open():
            is_looping = False
            log("✅ Запись остановлена")
            move_camtasia_home()
        else:
            log("[WARN] F10 не сработал")

# === Мигание окна ===
def start_blinking_loop():
    def _blink():
        global blinking
        while blinking and remaining_time > 0:
            if not any_valid_tables_exist() or not is_camtasia_active():
                blinking = False
                root.configure(bg="#1e1e1e")
                return
            root.configure(bg="#ff0000"); time.sleep(0.4)
            root.configure(bg="#ffffff"); time.sleep(0.4)
    threading.Thread(target=_blink, daemon=True).start()
# === Обновление прогресс-бара с цветом ===
def update_progress():
    global blinking, is_looping
    while auto_recording and not halt_event.is_set():
        mins, secs = divmod(remaining_time, 60)
        hrs, mins = divmod(mins, 60)
        label_time.set(f"След. перезапуск: {hrs:02}:{mins:02}:{secs:02}")

        percent = (RESTART_INTERVAL - remaining_time) / RESTART_INTERVAL
        progress['value'] = percent * 100

        # Цвет прогресс-бара
        if percent < 0.33:
            color = "#F44336"  # Красный
        elif percent < 0.66:
            color = "#FFC107"  # Жёлтый
        else:
            color = "#4CAF50"  # Зелёный

        style = ttk.Style()
        style.configure("TProgressbar", troughcolor="#333", background=color)

        # Защита от падения записи
        if is_looping and not is_recording_window_open():
            log("⚠️ Camtasia крашнулась. Перезапуск...")
            stop_recording(); time.sleep(2); start_recording()
        time.sleep(10)

# === Цикл записи ===
def recording_cycle():
    global remaining_time, blinking
    status_label.set("⏳ Подготовка...")
    flash_message("⚙️ Подготовка записи")
    stop_recording(); time.sleep(INITIAL_DELAY_SEC)
    start_recording()
    remaining_time = RESTART_INTERVAL
    status_label.set("▶️ Запись активна")

    while remaining_time > 0:
        if halt_event.is_set(): stop_recording(); return
        if not is_camtasia_active():
            log("❌ Camtasia закрыта"); toggle_auto(force_off=True); return
        if any('Paused...' in t for t in gw.getAllTitles()):
            log("⏸️ Пауза — перезапуск"); stop_recording(); time.sleep(1); start_recording()
        if remaining_time <= 1500 and not blinking:
            blinking = True
            start_blinking_loop()
        time.sleep(1)
        remaining_time -= 1
    stop_recording(); time.sleep(2)

# === Переключение автозаписи ===
def toggle_auto(force_on=False, force_off=False):
    global auto_recording, recording_thread, progress_thread, blinking
    blinking = False
    if auto_recording or force_off:
        halt_event.set(); auto_recording = False
        stop_recording()
        toggle_btn.config(text="Автозапись: ВЫКЛ", bg="#555")
        status_label.set("Автозапись отключена")
    elif force_on or not auto_recording:
        if not is_camtasia_active():
            status_label.set("❗ Camtasia не запущена"); return
        halt_event.clear(); auto_recording = True
        recording_thread = threading.Thread(target=recording_cycle, daemon=True)
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        recording_thread.start(); progress_thread.start()
        toggle_btn.config(text="Автозапись: ВКЛ", bg="#4CAF50")
        status_label.set("Автозапись включена")

# === Мониторинг: автостарт при появлении стола ===
def monitor_loop():
    while True:
        time.sleep(3)
        if not auto_recording and any_valid_tables_exist():
            log("🧠 Найден стол — автозапись включается")
            toggle_auto(force_on=True)

# === Интерфейс ===
tk.Label(root, text="ClubGG – Панель управления", font=("Segoe UI", 13, "bold"), fg="white", bg="#1e1e1e").pack(pady=(12, 6))
frame = tk.Frame(root, bg="#1e1e1e"); frame.pack(padx=16, fill="x")

btn1 = tk.Button(frame, text="🃏 Расставить столы", font=("Segoe UI", 11), bg="#4CAF50", fg="white", command=place_tables)
btn2 = tk.Button(frame, text="📐 Остальное", font=("Segoe UI", 11), bg="#FFC107", fg="black", command=place_lobby_bot_rec)
toggle_btn = tk.Button(frame, text="Автозапись: ВЫКЛ", font=("Segoe UI", 11), bg="#555", fg="white", command=toggle_auto)

for i, btn in enumerate((btn1, btn2, toggle_btn)):
    btn.grid(row=i, column=0, sticky="ew", pady=5)
    frame.grid_rowconfigure(i, weight=1)
frame.grid_columnconfigure(0, weight=1)

progress = ttk.Progressbar(root, orient="horizontal", length=320, mode="determinate", style="TProgressbar")
progress.pack(pady=(14, 4))
tk.Label(root, textvariable=label_time, font=("Segoe UI", 9), fg="lightgray", bg="#1e1e1e").pack()
tk.Label(root, textvariable=status_label, font=("Segoe UI", 8), fg="gray", bg="#1e1e1e").pack()

# === Запуск ===
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()
root.mainloop()
