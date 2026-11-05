# -*- coding: utf-8 -*-
"""
ГОЛОСОВОЙ ВВОД 2.2 (офлайн, русский, Whisper)
============================================
Говорите в микрофон — текст вставляется туда, где стоит курсор.

  - только faster-whisper с моделью large-v3-turbo;
  - вся речь за нажатие распознаётся одним куском;
  - значок в трее: статус, переназначение клавиш, выход;
  - F11 открывает графическое окно переназначения клавиш.

Управление по умолчанию:
  УДЕРЖИВАТЬ F9  — записывать речь (отпустили — текст вставлен)
  F10            — вставить текст БЕЗ пробела перед ним
  F11            — переназначить клавиши
  Ctrl+Alt+Q     — выход

Запуск: ярлык «Голосовой ввод» на рабочем столе или автозапуск Windows
"""

import os
import sys
import time
import queue
import wave
import ctypes
import threading
import tempfile
import configparser

SAMPLE_RATE = 16000
WHISPER_MODEL = "large-v3-turbo"
WHISPER_DEVICE = "auto"       # auto | cuda | cpu

SETTINGS_FILE = "Голосовой_ввод.ini"
HOTKEY_REMAP = "f11"
HOTKEY_RECORD = "f9"
HOTKEY_INSERT_RAW = "f10"
HOTKEY_EXIT = "ctrl+alt+q"
ADD_SPACE_BEFORE = True

TRAY = None
TRAY_LOCK = threading.Lock()
STATUS_TEXT = "Загрузка..."
CONSOLE_VISIBLE = True
DLL_HANDLES = []


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _console_hwnd():
    try:
        return ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        return 0


def hide_console():
    global CONSOLE_VISIBLE
    hwnd = _console_hwnd()
    if hwnd:
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
            CONSOLE_VISIBLE = False
        except Exception:
            pass


def show_console():
    global CONSOLE_VISIBLE
    hwnd = _console_hwnd()
    if hwnd:
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 5)
            CONSOLE_VISIBLE = True
        except Exception:
            pass


def console_pause(msg="Нажмите Enter..."):
    show_console()
    try:
        input(msg)
    except EOFError:
        time.sleep(5)


def _draw_mic(color, dot=None):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([22, 8, 42, 34], radius=10, fill=color)
    d.arc([16, 12, 48, 46], start=0, end=180, fill=color, width=4)
    d.line([32, 46, 32, 54], fill=color, width=4)
    d.line([24, 54, 40, 54], fill=color, width=4)
    if dot:
        d.ellipse([46, 44, 60, 58], fill=dot)
    return img


def tray_update(text=None, state="idle"):
    global STATUS_TEXT
    if text is not None:
        STATUS_TEXT = text
    if TRAY is None:
        return
    try:
        colors = {"idle": ((120, 125, 140, 255), None),
                  "listen": ((80, 180, 90, 255), (220, 60, 60, 255)),
                  "error": ((220, 60, 60, 255), None)}
        color, dot = colors.get(state, colors["idle"])
        with TRAY_LOCK:
            TRAY.icon = _draw_mic(color, dot)
            TRAY.title = f"Голосовой ввод — {STATUS_TEXT}\n" \
                         f"Диктовка: удерживайте {HOTKEY_RECORD.upper()}"
            TRAY.update_menu()
    except Exception:
        pass


def tray_setup(quit_cb, remap_cb):
    global TRAY
    try:
        import pystray
    except ImportError:
        return False

    def status_item(item):
        return f"{STATUS_TEXT}  (держите {HOTKEY_RECORD.upper()} и говорите)"

    def open_folder_cb(icon, item):
        os.startfile(script_dir())

    menu = pystray.Menu(
        pystray.MenuItem(status_item, None, enabled=False),
        pystray.MenuItem("Переназначить клавиши", remap_cb),
        pystray.MenuItem("Открыть папку с настройками", open_folder_cb),
        pystray.MenuItem("Выход", quit_cb),
    )
    TRAY = pystray.Icon("voiceinput", _draw_mic((120, 125, 140, 255)),
                        "Голосовой ввод", menu)
    TRAY.run_detached()
    return True


def load_settings():
    global HOTKEY_RECORD, HOTKEY_INSERT_RAW, HOTKEY_EXIT, ADD_SPACE_BEFORE
    global WHISPER_MODEL, WHISPER_DEVICE
    path = os.path.join(script_dir(), SETTINGS_FILE)
    parser = configparser.ConfigParser(strict=False)
    if os.path.exists(path):
        parser.read(path, encoding="utf-8")
        sec = "Клавиши" if parser.has_section("Клавиши") else "Keys"
        if parser.has_section(sec):
            g = lambda k, d: parser.get(sec, k, fallback=d).strip().lower()
            HOTKEY_RECORD = g("запись", HOTKEY_RECORD)
            HOTKEY_INSERT_RAW = g("без_пробела", HOTKEY_INSERT_RAW)
            HOTKEY_EXIT = g("выход", HOTKEY_EXIT)
            ADD_SPACE_BEFORE = g("пробел_перед_текстом", "да") not in ("нет", "0", "no", "false")
        eng = "Движок" if parser.has_section("Движок") else "Engine"
        if parser.has_section(eng):
            g = lambda k, d: parser.get(eng, k, fallback=d).strip().lower()
            WHISPER_MODEL = g("модель", WHISPER_MODEL)
            WHISPER_DEVICE = g("устройство", WHISPER_DEVICE)
    else:
        save_settings()
    if HOTKEY_RECORD == HOTKEY_INSERT_RAW:
        show_console()
        print(f"ВНИМАНИЕ: в «{SETTINGS_FILE}» клавиши записи и вставки совпадают "
              f"({HOTKEY_RECORD}). Исправьте файл.")


def save_settings():
    lines = [
        "; НАСТРОЙКИ ГОЛОСОВОГО ВВОДА",
        "; Меняйте значения после = и перезапускайте программу.",
        "; Названия клавиш: f1-f12, a-z, 0-9, space, insert, home, pause...",
        "; Комбинации через плюс, например: ctrl+f9",
        "",
        "[Клавиши]",
        f"запись = {HOTKEY_RECORD}",
        f"без_пробела = {HOTKEY_INSERT_RAW}",
        f"выход = {HOTKEY_EXIT}",
        f"пробел_перед_текстом = {'да' if ADD_SPACE_BEFORE else 'нет'}",
        "",
        "; Движок Whisper:",
        "[Движок]",
        f"модель = {WHISPER_MODEL}",
        "; устройство: auto (GPU, если получилось) | cuda | cpu",
        f"устройство = {WHISPER_DEVICE}",
        "",
    ]
    path = os.path.join(script_dir(), SETTINGS_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def say(msg):
    print(msg, flush=True)


def remap_hotkeys():
    try:
        import tkinter as tk
    except ImportError:
        ctypes.windll.user32.MessageBoxW(
            None, "Для переназначения клавиш нужен компонент Tkinter в Python.",
            "Голосовой ввод", 0x10)
        return

    captured = []
    root = tk.Tk()
    root.title("Голосовой ввод — переназначение клавиш")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    width, height = 480, 310
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    title = tk.Label(root, text="Переназначение клавиш", font=("Segoe UI", 16, "bold"))
    title.pack(pady=(18, 10))
    prompt = tk.Label(
        root,
        text=f"1/2. Нажмите новую клавишу ДИКТОВКИ\n(сейчас: {HOTKEY_RECORD.upper()})",
        font=("Segoe UI", 12), justify="center")
    prompt.pack(pady=8)
    current = tk.Label(root, text="", font=("Segoe UI", 12, "bold"), fg="#355070", justify="center")
    current.pack(pady=5)
    error = tk.Label(root, text="", font=("Segoe UI", 10), fg="#b3261e")
    error.pack()

    def confirm_selection():
        global HOTKEY_RECORD, HOTKEY_INSERT_RAW
        if len(captured) != 2:
            return
        HOTKEY_RECORD, HOTKEY_INSERT_RAW = captured
        save_settings()
        root.destroy()

    buttons = tk.Frame(root)
    buttons.pack(pady=12)
    confirm_button = tk.Button(
        buttons, text="Подтвердить", width=14, state=tk.DISABLED,
        command=confirm_selection)
    confirm_button.pack(side="left", padx=6)
    cancel_button = tk.Button(buttons, text="Отмена", width=14, command=root.destroy)
    cancel_button.pack(side="left", padx=6)
    hint = tk.Label(root, text="Esc — отмена без изменений", font=("Segoe UI", 10), fg="#666666")
    hint.pack()

    aliases = {
        "return": "enter", "prior": "page up", "next": "page down",
        "control_l": "ctrl", "control_r": "ctrl", "shift_l": "shift",
        "shift_r": "shift", "alt_l": "alt", "alt_r": "alt",
        "caps_lock": "caps lock", "num_lock": "num lock", "scroll_lock": "scroll lock",
    }

    def on_key(event):
        keycode = int(event.keycode)
        name = event.keysym.lower()
        if keycode == 27 or name == "escape":
            root.destroy()
            return
        if 112 <= keycode <= 123:
            name = f"f{keycode - 111}"
        name = aliases.get(name, name)
        if len(captured) == 2:
            return
        error.config(text="")
        if not captured:
            captured.append(name)
            current.config(text=f"Диктовка: {name.upper()}")
            prompt.config(
                text=f"2/2. Нажмите клавишу ВСТАВКИ БЕЗ ПРОБЕЛА\n(сейчас: {HOTKEY_INSERT_RAW.upper()})")
            return
        if name == captured[0] or name == HOTKEY_EXIT:
            error.config(text="Клавиши должны различаться и не совпадать с выходом.")
            return
        captured.append(name)
        current.config(
            text=f"Диктовка: {captured[0].upper()}\nБез пробела: {captured[1].upper()}")
        prompt.config(text="Проверьте клавиши и нажмите «Подтвердить»")
        confirm_button.config(state=tk.NORMAL)
        confirm_button.focus_set()

    root.bind_all("<Key>", on_key)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.focus_force()
    root.mainloop()
    tray_update("Готов", "idle")


def _register_cuda_dirs():
    """Добавляет DLL из pip-пакетов NVIDIA до загрузки ctranslate2."""
    try:
        import site
        for base in site.getsitepackages():
            for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
                d = os.path.join(base, sub)
                if os.path.isdir(d):
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                    DLL_HANDLES.append(os.add_dll_directory(d))
    except Exception:
        pass


def load_libs():
    global sd, keyboard, pyperclip, WhisperModel
    WhisperModel = None
    missing = []
    for mod, name in (("sounddevice", "sounddevice"),
                      ("keyboard", "keyboard"),
                      ("pyperclip", "pyperclip")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(name)
    if missing:
        say("Не установлены библиотеки: " + ", ".join(missing))
        say("Выполни в командной строке:")
        say("  pip install " + " ".join(missing))
        console_pause()
        sys.exit(1)
    import sounddevice as sd
    import keyboard
    import pyperclip
    _register_cuda_dirs()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        WhisperModel = None


def init_whisper():
    if WhisperModel is None:
        return None
    device = WHISPER_DEVICE
    if device == "auto":
        device = "cuda" if _cuda_available() else "cpu"
    compute = "int8_float16" if device == "cuda" else "int8"
    models_dir = os.path.join(script_dir(), "models")
    os.makedirs(models_dir, exist_ok=True)
    try:
        return WhisperModel(WHISPER_MODEL, device=device, compute_type=compute,
                            download_root=models_dir)
    except Exception as e:
        say(f"Whisper на {device} не завёлся ({e}); пробую CPU…")
        try:
            return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8",
                                download_root=models_dir)
        except Exception as e2:
            say(f"Whisper недоступен: {e2}")
            return None


def _cuda_available():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def recognize_whisper(model, frames):
    if not frames:
        return ""
    tmp = os.path.join(tempfile.gettempdir(), "voice_input_session.wav")
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    segments, _info = model.transcribe(tmp, language="ru", beam_size=5,
                                       vad_filter=True, initial_prompt="Диктовка сообщения на русском языке.")
    return " ".join(seg.text.strip() for seg in segments).strip()


def paste_text(text, add_space=True):
    text = text.strip()
    if not text:
        return
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?…":
        text += "."

    old_clip = None
    try:
        old_clip = pyperclip.paste()
    except Exception:
        old_clip = None

    try:
        pyperclip.copy((" " if add_space else "") + text)
    except Exception as e:
        say(f"Не удалось записать в буфер обмена: {e}")
        tray_update("Ошибка буфера обмена", "error")
        return

    time.sleep(0.15)
    keyboard.send("ctrl+v")
    time.sleep(0.35)

    if isinstance(old_clip, str) and old_clip:
        try:
            pyperclip.copy(old_clip)
        except Exception:
            pass


def main():
    global TRAY

    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "VoiceInput_2_0_SingleInstance")
    if ctypes.windll.kernel32.WaitForSingleObject(mutex, 0) == 0x102:
        ctypes.windll.user32.MessageBoxW(
            None, "Голосовой ввод уже запущен.\nЗначок у часов — правый клик покажет меню.",
            "Голосовой ввод", 0x40)
        sys.exit(0)

    say("=" * 50)
    say("  ГОЛОСОВОЙ ВВОД 2.2 — WHISPER")
    say("=" * 50)

    load_libs()
    load_settings()
    remap_request = threading.Event()
    tray_ok = tray_setup(quit_cb=lambda icon, item: os._exit(0),
                         remap_cb=lambda icon, item: remap_request.set())

    say(f"Загрузка Whisper ({WHISPER_MODEL})…")
    tray_update("Загрузка Whisper…", "idle")
    model = init_whisper()
    if model is None:
        show_console()
        print("Не удалось загрузить Whisper. Запустите install.bat для восстановления.")
        console_pause()
        sys.exit(1)
    say("Модель загружена.")
    tray_update("Готов", "idle")

    try:
        dev = sd.query_devices(kind="input")
        say(f"Микрофон: {dev['name']}")
    except Exception as e:
        say(f"Микрофон не найден: {e}")
        tray_update("Микрофон не найден", "error")
        console_pause()
        sys.exit(1)

    audio_q = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_q.put(bytes(indata))

    try:
        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
            channels=1, callback=callback)
        stream.start()
    except Exception as e:
        say(f"Не удалось открыть микрофон: {e}")
        tray_update("Микрофон занят другой программой?", "error")
        console_pause()
        sys.exit(1)

    if tray_ok:
        hide_console()
    else:
        say("")
        say("  УДЕРЖИВАЙТЕ  " + HOTKEY_RECORD.upper() + "  и говорите")
        say("  отпустили   — текст вставлен в окно")
        say("  " + HOTKEY_INSERT_RAW.upper() + " — вставить без пробела")
        say("  " + HOTKEY_REMAP.upper() + " — поменять клавиши")
        say("  " + HOTKEY_EXIT.upper() + " — выход")
        say("")
        say("Готов. Говорите!")

    def request_remap(_event=None):
        say(f"Получен запрос переназначения: {HOTKEY_REMAP}")
        remap_request.set()
    keyboard.on_press_key(HOTKEY_REMAP, request_remap)
    say(f"Клавиша переназначения зарегистрирована: {HOTKEY_REMAP}")

    no_space_once = False
    try:
        while True:
            if keyboard.is_pressed(HOTKEY_EXIT):
                break

            if remap_request.is_set():
                remap_request.clear()
                time.sleep(0.3)
                remap_hotkeys()

            if keyboard.is_pressed(HOTKEY_INSERT_RAW):
                no_space_once = True
                time.sleep(0.3)

            if keyboard.is_pressed(HOTKEY_RECORD):
                tray_update("Слушаю... отпустите клавишу", "listen")
                if not tray_ok:
                    say("● слушаю...")
                rec_frames = []
                while keyboard.is_pressed(HOTKEY_RECORD):
                    try:
                        rec_frames.append(audio_q.get(timeout=0.1))
                    except queue.Empty:
                        continue
                drain_until = time.monotonic() + 0.65
                while time.monotonic() < drain_until:
                    try:
                        rec_frames.append(audio_q.get(timeout=max(0.01, drain_until - time.monotonic())))
                    except queue.Empty:
                        break

                tray_update("Распознаю…", "listen")
                try:
                    text = recognize_whisper(model, rec_frames)
                except Exception as e:
                    say(f"Ошибка Whisper: {e}")
                    tray_update("Ошибка распознавания", "error")
                    text = ""

                if text:
                    say(f"  -> {text}")
                    tray_update(f"Вставлено: {text[:45]}", "idle")
                    paste_text(text, add_space=(ADD_SPACE_BEFORE and not no_space_once))
                else:
                    tray_update("Ничего не распознано, повторите", "idle")
                    if not tray_ok:
                        say("  (ничего не распознано)")
                no_space_once = False
                time.sleep(0.3)
            else:
                try:
                    audio_q.get(timeout=0.1)
                except queue.Empty:
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        tray_update("Выход...", "idle")
        stream.stop()
        stream.close()
        if TRAY is not None:
            try:
                TRAY.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
