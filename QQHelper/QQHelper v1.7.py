import tkinter as tk
from tkinter import ttk
import pygetwindow as gw
import pyautogui
import time
import threading
import os
import psutil
import traceback

# === Константы ===
APP_TITLE = "QQPK"
APP_WIDTH = 400
APP_HEIGHT = 700
X_PAD_DEFAULT = 3
X_PAD_TIGHT = -21
Y_TOP = 0
RESTART_INTERVAL_SEC = 10800
INITIAL_DELAY_SEC = 2
FLASH_DURATION = 3000

TARGETS = {
    "Recording": {"title_keywords": ["Recording...", "Paused...", "Camtasia Recorder"], "x": 1034, "y": 910},
    "Utility":    {"title_keywords": ["QQPK – Утилита"], "x": 1518, "y": 0},
    "Holdem":     {"title_keywords": ["Holdem China Mini"], "x": 1418, "y": 942, "w": 724, "h": 370, "topmost": True},
    "OpenCV":     {"title_keywords": ["OpenCvServer"], "x": 1789, "y": 367, "w": 993, "h": 605, "topmost": False}
}

# === Глобальные переменные ===
auto_looping = False
loop_thread = None
progress_thread = None
monitor_thread = None
halt_event = threading.Event()
is_looping = False
remaining_time = RESTART_INTERVAL_SEC

# === Вспомогательные функции ===
def is_valid_app_window(win):
    return (
        APP_TITLE in win.title and win.visible and
        abs(win.width - APP_WIDTH) <= 10 and abs(win.height - APP_HEIGHT) <= 10
    )

def is_window_match(win, keywords):
    try:
        return any(k in win.title for k in keywords) and win.visible
    except:
        return False

def flash_message(text, duration=2500):
    flash = tk.Toplevel(root)
    flash.overrideredirect(True)
    flash.attributes("-topmost", True)
    flash.attributes("-alpha", 0.0)
    flash.configure(bg="#ff9800")

    width, height = 320, 60
    x = root.winfo_x() + root.winfo_width() // 2 - width // 2
    y = root.winfo_y() + root.winfo_height() // 2 - height // 2
    flash.geometry(f"{width}x{height}+{x}+{y}")

    label = tk.Label(flash, text=text, font=("Segoe UI", 12, "bold"), bg="#ff9800", fg="white")
    label.pack(expand=True, fill="both")

    def fade(step=0):
        alpha = step / 10
        flash.attributes("-alpha", alpha)
        if step < 10:
            flash.after(30, lambda: fade(step + 1))
        else:
            flash.after(duration, fade_out)

    def fade_out(step=10):
        alpha = step / 10
        flash.attributes("-alpha", alpha)
        if step > 0:
            flash.after(30, lambda: fade_out(step - 1))
        else:
            flash.destroy()

    fade()

def log(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())
    flash_message(text, duration=2500)

# === Расстановка окон ===
def align_windows(tight=False):
    log("🔄 Расстановка окон...")
    try:
        windows = [w for w in gw.getWindowsWithTitle(APP_TITLE) if is_valid_app_window(w)]
        windows = sorted(windows, key=lambda w: w.left)
        if not windows:
            return False
        x = 0
        padding = X_PAD_TIGHT if tight else X_PAD_DEFAULT
        for win in windows:
            try:
                win.restore()
                time.sleep(0.05)
                win.moveTo(x, Y_TOP)
                x += win.width + padding
            except Exception as e:
                log(f"[ERR] Ошибка при перемещении окна: {e}")
        return True
    except Exception as e:
        log(f"[ERR] Ошибка в align_windows: {e}")
        return False

def place_additional_windows():
    log("📐 Расстановка остального...")
    for label, cfg in TARGETS.items():
        for win in gw.getAllWindows():
            if is_window_match(win, cfg["title_keywords"]):
                try:
                    win.restore()
                    time.sleep(0.05)
                    if label == "Recording":
                        win.moveTo(cfg["x"], cfg["y"])
                        continue
                    if cfg.get("w") and cfg.get("h"):
                        if abs(win.width - cfg["w"]) > 5 or abs(win.height - cfg["h"]) > 5:
                            win.resizeTo(cfg["w"], cfg["h"])
                    win.moveTo(cfg["x"], cfg["y"])
                    if "topmost" in cfg:
                        win.alwaysOnTop = cfg["topmost"]
                except Exception as e:
                    log(f"[ERR] Не удалось переместить {label}: {e}")
                break

# === Проверки Camtasia и записи ===
def is_camtasia_active():
    return any("recorder" in p.info['name'].lower() and "cam" in p.info['name'].lower()
               for p in psutil.process_iter(attrs=['name']))

def is_recording_window_open():
    return any(x in title for title in gw.getAllTitles() for x in ["Recording...", "Paused..."])

# === Управление записью ===
def focus_camtasia():
    for win in gw.getWindowsWithTitle("Camtasia Recorder"):
        try:
            win.activate()
            time.sleep(0.3)
            return True
        except:
            continue
    return False

def trigger_start():
    global is_looping
    if not is_looping and is_camtasia_active():
        log("▶️ Запуск записи...")
        focus_camtasia()
        pyautogui.press("f9")
        time.sleep(1.5)
        if is_recording_window_open():
            is_looping = True
            log("✅ Запись началась")
        else:
            log("[WARN] Запись не началась")

def trigger_stop():
    global is_looping
    if is_looping and is_camtasia_active():
        log("⏹️ Остановка записи...")
        focus_camtasia()
        pyautogui.press("f10")
        time.sleep(1.5)
        if not is_recording_window_open():
            is_looping = False
            log("✅ Запись остановлена")
        else:
            log("[WARN] Запись не остановилась")

# === Прогресс бар ===
def update_progress():
    while auto_looping and not halt_event.is_set():
        minutes, seconds = divmod(remaining_time, 60)
        hours, minutes = divmod(minutes, 60)
        label_time.set(f"След. перезапуск: {hours:02}:{minutes:02}:{seconds:02}")
        progress_bar['value'] = 100 * (RESTART_INTERVAL_SEC - remaining_time) / RESTART_INTERVAL_SEC
        time.sleep(10)

# === Главный цикл автозаписи ===
def looping_cycle():
    global remaining_time
    status_loop.set("⏳ Подождите...")
    flash_message("⚙️ Подготовка автозаписи")
    trigger_stop()
    time.sleep(INITIAL_DELAY_SEC)
    status_loop.set("▶️ Запись начнётся")
    while not halt_event.is_set():
        trigger_start()
        remaining_time = RESTART_INTERVAL_SEC
        while remaining_time > 0:
            if halt_event.is_set():
                trigger_stop()
                return
            if not is_camtasia_active():
                log("❌ Camtasia закрыта. Автозапись отключена.")
                toggle_loop(force_off=True)
                return
            if any('Paused...' in title for title in gw.getAllTitles()):
                log("⏸️ Пауза в записи — перезапуск")
                trigger_stop()
                time.sleep(1)
                trigger_start()
            time.sleep(1)
            remaining_time -= 1
        trigger_stop()
        time.sleep(2)

# === Автовключение при наличии окна QQPK ===
def monitor_loop():
    global auto_looping
    while True:
        time.sleep(3)
        qqpk_windows = [
            w for w in gw.getAllWindows()
            if APP_TITLE in w.title and abs(w.width - APP_WIDTH) <= 10 and abs(w.height - APP_HEIGHT) <= 10
        ]
        if qqpk_windows and not auto_looping:
            log("🧠 Найдено окно QQPK — автозапись включается")
            toggle_loop(force_on=True)

# === Переключатель автозаписи ===
def toggle_loop(force_on=False, force_off=False):
    global auto_looping, loop_thread, progress_thread
    if auto_looping or force_off:
        halt_event.set()
        auto_looping = False
        trigger_stop()
        loop_btn.config(text="Автозапись: ВЫКЛ", bg="#555")
        status_loop.set("Автозапись отключена.")
    elif force_on or not auto_looping:
        if not is_camtasia_active():
            status_loop.set("❗ Camtasia не запущена")
            return
        halt_event.clear()
        auto_looping = True
        loop_thread = threading.Thread(target=looping_cycle, daemon=True)
        loop_thread.start()
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        loop_btn.config(text="Автозапись: ВКЛ", bg="#4CAF50")
        status_loop.set("Автозапись включена.")

# === GUI ===
root = tk.Tk()
root.title("QQPK – Утилита")
root.geometry("400x330")
root.configure(bg="#1e1e1e")
root.resizable(False, False)
root.attributes("-topmost", True)

try: root.iconbitmap("icon.ico")
except: pass

status_loop = tk.StringVar(value="Автозапись отключена.")
label_time = tk.StringVar(value="След. перезапуск: --:--:--")

tk.Label(root, text="QQPK – Панель управления", font=("Segoe UI", 13, "bold"),
         fg="white", bg="#1e1e1e").pack(pady=(12, 6))

button_frame = tk.Frame(root, bg="#1e1e1e")
button_frame.pack(padx=16, fill="x")

btn1 = tk.Button(button_frame, text="🧩 Расставить", font=("Segoe UI", 11),
                 bg="#4CAF50", fg="white", command=lambda: align_windows(False))
btn2 = tk.Button(button_frame, text="↔ Для 5 окон", font=("Segoe UI", 11),
                 bg="#2196F3", fg="white", command=lambda: align_windows(True))
btn3 = tk.Button(button_frame, text="Автозапись: ВЫКЛ", font=("Segoe UI", 11),
                 bg="#555", fg="white", command=toggle_loop)
btn4 = tk.Button(button_frame, text="📐 Расставить остальное", font=("Segoe UI", 11),
                 bg="#FFC107", fg="black", command=place_additional_windows)

loop_btn = btn3
for i, btn in enumerate((btn1, btn2, btn3, btn4)):
    btn.grid(row=i, column=0, sticky="ew", pady=4)
    button_frame.grid_rowconfigure(i, weight=1)
button_frame.grid_columnconfigure(0, weight=1)

ttk.Style().configure("TProgressbar", troughcolor="#333", background="#76d275", thickness=12)
progress_bar = ttk.Progressbar(root, orient="horizontal", length=320, mode="determinate")
progress_bar.pack(pady=(14, 4))
tk.Label(root, textvariable=label_time, font=("Segoe UI", 9), fg="lightgray", bg="#1e1e1e").pack()
tk.Label(root, textvariable=status_loop, font=("Segoe UI", 8), fg="gray", bg="#1e1e1e").pack()

# Запуск фонового мониторинга
monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
monitor_thread.start()

root.mainloop()
