"""
launcher_gui.py — Панель управления Echelon с современным и выверенным UI/UX.
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser

from config import settings

try:
    import customtkinter as ctk
except ImportError:
    print("Ошибка: Библиотека customtkinter не найдена. Установите её: pip install customtkinter")
    sys.exit(1)


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_LABEL = ("Segoe UI", 14, "bold")
FONT_TEXT = ("Segoe UI Semibold", 14)
FONT_CAPTION = ("Segoe UI Semibold", 11)
FONT_MONO = ("Consolas", 13)


COLOR_BG = "#080B11"
COLOR_SIDEBAR = "#0F172A"
COLOR_CARD = "#1E293B"
COLOR_BORDER = "#334155"
COLOR_ACCENT = "#6366F1"
COLOR_ACCENT_HOVER = "#4F46E5"
COLOR_TEXT_MAIN = "#F3F4F6"
COLOR_TEXT_DIM = "#9CA3AF"
COLOR_SUCCESS = "#10B981"
COLOR_DANGER = "#EF4444"


class ActionButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            corner_radius=8,
            height=34,
            font=FONT_LABEL,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            **kwargs,
        )


class ModuleCard(ctk.CTkFrame):
    def __init__(self, master, title, command, **kwargs):
        super().__init__(
            master,
            fg_color=COLOR_CARD,
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
            height=90,
            **kwargs,
        )
        self.pack_propagate(False)

        self.info_container = ctk.CTkFrame(self, fg_color="transparent")
        self.info_container.pack(side="left", padx=20, pady=12, fill="y")

        self.label = ctk.CTkLabel(
            self.info_container, text=title, font=FONT_LABEL, text_color=COLOR_TEXT_MAIN
        )
        self.label.pack(anchor="w", pady=(0, 4))

        self.status_label = ctk.CTkLabel(
            self.info_container,
            text="●  OFFLINE",
            font=FONT_CAPTION,
            text_color=COLOR_DANGER,
        )
        self.status_label.pack(anchor="w")

        self.switch_var = ctk.StringVar(value="off")
        self.switch = ctk.CTkSwitch(
            self,
            text="",
            command=command,
            variable=self.switch_var,
            onvalue="on",
            offvalue="off",
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            progress_color=COLOR_ACCENT,
            switch_width=50,
            switch_height=26,
            width=50
        )
        self.switch.pack(side="right", padx=20, pady=28)

    def set_active(self, active: bool):
        if active:
            self.status_label.configure(text="●  ONLINE", text_color=COLOR_SUCCESS)
            self.switch_var.set("on")
        else:
            self.status_label.configure(text="●  OFFLINE", text_color=COLOR_DANGER)
            self.switch_var.set("off")


class ActionCard(ctk.CTkFrame):
    def __init__(self, master, title, description, button_text, command, **kwargs):
        super().__init__(
            master,
            fg_color=COLOR_CARD,
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
            height=90,
            **kwargs,
        )
        self.pack_propagate(False)

        self.info_container = ctk.CTkFrame(self, fg_color="transparent")
        self.info_container.pack(side="left", padx=20, pady=12, fill="y")

        self.label = ctk.CTkLabel(
            self.info_container, text=title, font=FONT_LABEL, text_color=COLOR_TEXT_MAIN
        )
        self.label.pack(anchor="w", pady=(0, 4))

        self.desc_label = ctk.CTkLabel(
            self.info_container,
            text=description,
            font=FONT_CAPTION,
            text_color=COLOR_TEXT_DIM,
        )
        self.desc_label.pack(anchor="w")

        self.btn = ActionButton(self, text=button_text, command=command, width=120)
        self.btn.pack(side="right", padx=20, pady=28)


class ClearDbDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_confirm):
        super().__init__(parent)
        self.parent = parent
        self.on_confirm = on_confirm

        self.title("Подтверждение действия")
        self.geometry("450x220")
        self.resizable(False, False)
        self.configure(fg_color="#0F172A") # COLOR_SIDEBAR equivalent

        # Center relative to parent
        self.center_on_parent(parent)

        # Make modal
        self.transient(parent)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # Layout
        self.title_label = ctk.CTkLabel(
            self,
            text="Внимание: сброс данных!",
            font=("Segoe UI", 18, "bold"),
            text_color="#EF4444" # COLOR_DANGER
        )
        self.title_label.pack(pady=(20, 10))

        self.desc_label = ctk.CTkLabel(
            self,
            text="Вы собираетесь полностью очистить базу данных.\nЭто действие удалит всех пользователей, историю цен и логов.\nМодели будут сброшены по умолчанию.",
            font=("Segoe UI Semibold", 12),
            text_color="#F3F4F6", # COLOR_TEXT_MAIN
            justify="center"
        )
        self.desc_label.pack(pady=(0, 20), padx=20)

        # Buttons Frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=40)

        # Cancel Button (Active immediately)
        self.cancel_btn = ctk.CTkButton(
            self.btn_frame,
            text="Отменить",
            fg_color="#334155", # COLOR_BORDER
            hover_color="#1E293B",
            font=("Segoe UI Semibold", 13),
            command=self.on_cancel,
            height=34,
            width=150
        )
        self.cancel_btn.pack(side="left", expand=True, padx=(0, 10))

        # Confirm Button (Countdown)
        self.countdown = 5
        self.confirm_btn = ctk.CTkButton(
            self.btn_frame,
            text=f"Подтвердить ({self.countdown})",
            state="disabled",
            fg_color="#475569", # Grayed out neutral
            text_color="#9CA3AF", # Dimmed text
            font=("Segoe UI Semibold", 13),
            command=self.on_confirm_click,
            height=34,
            width=150
        )
        self.confirm_btn.pack(side="right", expand=True, padx=(10, 0))

        # Start timer
        self.timer_id = self.after(1000, self.tick_timer)

    def center_on_parent(self, parent):
        parent.update_idletasks()
        p_width = parent.winfo_width()
        p_height = parent.winfo_height()
        p_x = parent.winfo_x()
        p_y = parent.winfo_y()

        # Dialog dimensions
        d_width = 450
        d_height = 220

        # Calculate coordinates
        x = p_x + (p_width - d_width) // 2
        y = p_y + (p_height - d_height) // 2

        self.geometry(f"{d_width}x{d_height}+{x}+{y}")

    def tick_timer(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.confirm_btn.configure(text=f"Подтвердить ({self.countdown})")
            self.timer_id = self.after(1000, self.tick_timer)
        else:
            self.timer_id = None
            self.confirm_btn.configure(
                text="Подтвердить",
                state="normal",
                fg_color="#EF4444", # COLOR_DANGER
                hover_color="#b91c1c",
                text_color="#F3F4F6"
            )

    def on_confirm_click(self):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.grab_release()
        self.on_confirm()
        self.destroy()

    def on_cancel(self):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.grab_release()
        self.destroy()


class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Панель управления Echelon")
        self.geometry("840x710")
        self.configure(fg_color=COLOR_BG)

        self.bot_process: subprocess.Popen | None = None
        self.dashboard_process: subprocess.Popen | None = None

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLOR_SIDEBAR)
        self.sidebar.pack(side="left", fill="y")

        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.pack(pady=(30, 20), padx=20, fill="x")

        self.brand = ctk.CTkLabel(
            self.brand_frame, text="ECHELON", font=FONT_TITLE, text_color="#ffffff"
        )
        self.brand.pack(anchor="w")

        self.brand_sub = ctk.CTkLabel(
            self.brand_frame,
            text="Панель управления",
            font=FONT_CAPTION,
            text_color=COLOR_TEXT_DIM,
        )
        self.brand_sub.pack(anchor="w", padx=2)

        self.divider = ctk.CTkFrame(self.sidebar, height=1, fg_color=COLOR_BORDER)
        self.divider.pack(fill="x", padx=16, pady=10)

        # Mode Selection Card
        self.mode_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#1E293B",
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
        )
        self.mode_card.pack(padx=16, pady=(0, 16), fill="x")

        self.mode_container = ctk.CTkFrame(self.mode_card, fg_color="transparent")
        self.mode_container.pack(padx=16, pady=16, fill="both")

        self.mode_title_label = ctk.CTkLabel(
            self.mode_container, text="Режим работы", font=FONT_CAPTION, text_color=COLOR_TEXT_DIM
        )
        self.mode_title_label.pack(anchor="w", pady=(0, 6))

        self.mode_var = ctk.StringVar(value=settings.MODE.lower())
        self.mode_selector = ctk.CTkSegmentedButton(
            self.mode_container,
            values=["demo", "avito"],
            command=self.change_mode,
            variable=self.mode_var,
            font=FONT_CAPTION,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
        )
        self.mode_selector.pack(fill="x", pady=(0, 6))

        self.headless_title_label = ctk.CTkLabel(
            self.mode_container, text="Браузер", font=FONT_CAPTION, text_color=COLOR_TEXT_DIM
        )
        self.headless_title_label.pack(anchor="w", pady=(10, 6))

        initial_headless_val = "Без окна" if settings.HEADLESS else "С окном"
        self.headless_var = ctk.StringVar(value=initial_headless_val)
        self.headless_selector = ctk.CTkSegmentedButton(
            self.mode_container,
            values=["Без окна", "С окном"],
            command=self.change_headless,
            variable=self.headless_var,
            font=FONT_CAPTION,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
        )
        self.headless_selector.pack(fill="x", pady=(0, 6))

        self.db_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#1E293B",
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
        )
        self.db_card.pack(padx=16, pady=(0, 16), fill="x")

        self.db_container = ctk.CTkFrame(self.db_card, fg_color="transparent")
        self.db_container.pack(padx=16, pady=16, fill="both")

        self.info_label = ctk.CTkLabel(
            self.db_container, text="База данных", font=FONT_CAPTION, text_color=COLOR_TEXT_DIM
        )
        self.info_label.pack(anchor="w", pady=(0, 6))

        db_name = os.path.basename(settings.DB_PATH)
        self.db_val = ctk.CTkLabel(
            self.db_container, text=db_name, font=FONT_TEXT, text_color=COLOR_TEXT_MAIN
        )
        self.db_val.pack(anchor="w", pady=(0, 10))

        db_exists = os.path.exists(settings.DB_PATH)
        db_status_color = COLOR_SUCCESS if db_exists else COLOR_DANGER
        db_status_text = "●  CONNECTED" if db_exists else "●  MISSING"

        self.db_status_label = ctk.CTkLabel(
            self.db_container,
            text=db_status_text,
            font=FONT_CAPTION,
            text_color=db_status_color,
        )
        self.db_status_label.pack(anchor="w")

        self.dash_link = ctk.CTkButton(
            self.sidebar,
            text="Открыть дашборд ↗",
            fg_color="transparent",
            text_color=COLOR_ACCENT,
            hover_color="#1E293B",
            anchor="w",
            font=FONT_LABEL,
            command=self.open_browser,
            height=36,
            corner_radius=8,
        )
        self.dash_link.pack(padx=16, pady=5, fill="x")

        # Кнопка очистки базы данных
        self.clear_db_btn = ctk.CTkButton(
            self.sidebar,
            text="Очистить базу данных",
            fg_color="transparent",
            text_color=COLOR_DANGER,
            hover_color="#3b1a1a",
            border_width=1,
            border_color=COLOR_DANGER,
            anchor="center",
            font=FONT_LABEL,
            command=self.confirm_clear_db,
            height=36,
            corner_radius=8,
        )
        self.clear_db_btn.pack(side="bottom", padx=16, pady=20, fill="x")

        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="right", fill="both", expand=True, padx=24, pady=24)

        self.bot_card = ModuleCard(self.main, "Telegram-бот", self.toggle_bot)
        self.bot_card.pack(fill="x", pady=(0, 16))

        self.dash_card = ModuleCard(self.main, "Веб-панель администратора", self.toggle_dashboard)
        self.dash_card.pack(fill="x", pady=(0, 16))

        self.session_card = ActionCard(
            self.main,
            title="Обход капчи",
            description="Ручной обход капчи и сохранение сессии",
            button_text="Запустить",
            command=self.run_save_session,
        )
        self.session_card.pack(fill="x", pady=(0, 20))

        self.console_header = ctk.CTkFrame(self.main, fg_color="transparent")
        self.console_header.pack(fill="x", pady=(0, 8), padx=5)

        self.console_title = ctk.CTkLabel(
            self.console_header,
            text="Консоль",
            font=FONT_CAPTION,
            text_color=COLOR_TEXT_DIM,
        )
        self.console_title.pack(side="left")

        self.clear_btn = ctk.CTkButton(
            self.console_header,
            text="Очистить",
            width=85,
            height=24,
            font=FONT_CAPTION,
            fg_color="transparent",
            text_color=COLOR_TEXT_DIM,
            hover_color="#1E293B",
            corner_radius=6,
            command=self.clear_logs,
        )
        self.clear_btn.pack(side="right")

        self.copy_btn = ctk.CTkButton(
            self.console_header,
            text="Копировать",
            width=95,
            height=24,
            font=FONT_CAPTION,
            fg_color="transparent",
            text_color=COLOR_TEXT_DIM,
            hover_color="#1E293B",
            corner_radius=6,
            command=self.copy_logs,
        )
        self.copy_btn.pack(side="right", padx=(0, 6))

        self.open_log_btn = ctk.CTkButton(
            self.console_header,
            text="Лог-файл",
            width=85,
            height=24,
            font=FONT_CAPTION,
            fg_color="transparent",
            text_color=COLOR_TEXT_DIM,
            hover_color="#1E293B",
            corner_radius=6,
            command=self.open_log_file,
        )
        self.open_log_btn.pack(side="right", padx=(0, 6))

        self.log_frame = ctk.CTkFrame(
            self.main,
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=12,
            fg_color="#060913",
        )
        self.log_frame.pack(fill="both", expand=True)

        self.textbox = ctk.CTkTextbox(
            self.log_frame,
            font=FONT_MONO,
            fg_color="transparent",
            border_width=0,
            text_color="#34D399",
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=16)
        self.textbox.configure(state="disabled")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.log("Готово.")

    def log(self, message: str):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"{time.strftime('%H:%M')} > {message}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear_logs(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.log("Консоль очищена.")

    def copy_logs(self):
        self.textbox.configure(state="normal")
        text = self.textbox.get("1.0", "end-1c")
        self.textbox.configure(state="disabled")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.log("Скопировано в буфер.")

    def open_log_file(self):
        log_path = "storage/logs/bot.log"
        if os.path.exists(log_path):
            try:
                os.startfile(log_path)
                self.log("Открываем bot.log...")
            except Exception as e:
                self.log(f"Не удалось открыть лог-файл: {e}")
        else:
            self.log("Лог-файл bot.log еще не создан.")

    def _get_python_exe(self) -> str:
        if getattr(sys, "frozen", False):
            return sys.executable
        venv_python = (
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "python.exe"
            )
            if os.name == "nt"
            else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
        )
        if os.path.exists(venv_python):
            return venv_python
        return sys.executable

    def toggle_bot(self):
        if self.bot_process is None:
            self.start_bot()
        else:
            self.stop_bot()

    def start_bot(self):
        python_exe = self._get_python_exe()
        args = [python_exe, "--bot"] if getattr(sys, "frozen", False) else [python_exe, "bot.py"]
        try:
            env = os.environ.copy()
            env["SCRAPER_MODE"] = self.mode_var.get()
            env["SCRAPER_HEADLESS"] = "True" if self.headless_var.get() == "Без окна" else "False"
            env["PYTHONIOENCODING"] = "utf-8"
            self.bot_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                env=env,
            )
            self.bot_card.set_active(True)
            threading.Thread(
                target=self.read_output, args=(self.bot_process, "Бот"), daemon=True
            ).start()
            self.log(f"Бот запущен (режим: {self.mode_var.get().upper()}).")
        except Exception as e:
            self.log(f"Ошибка: {e}")

    def stop_bot(self):
        if self.bot_process:
            self.bot_process.terminate()
            self.bot_process = None
            self.bot_card.set_active(False)
            self.log("Бот остановлен.")

    def toggle_dashboard(self):
        if self.dashboard_process is None:
            self.start_dashboard()
        else:
            self.stop_dashboard()

    def start_dashboard(self):
        python_exe = self._get_python_exe()
        args = (
            [python_exe, "--dashboard"]
            if getattr(sys, "frozen", False)
            else [python_exe, "admin_dashboard.py"]
        )
        try:
            env = os.environ.copy()
            env["SCRAPER_MODE"] = self.mode_var.get()
            env["SCRAPER_HEADLESS"] = "True" if self.headless_var.get() == "Без окна" else "False"
            env["PYTHONIOENCODING"] = "utf-8"
            self.dashboard_process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                env=env,
            )
            self.dash_card.set_active(True)
            threading.Thread(
                target=self.read_output, args=(self.dashboard_process, "Веб"), daemon=True
            ).start()
            self.log("Админка запущена на :8080")
        except Exception as e:
            self.log(f"Ошибка: {e}")

    def stop_dashboard(self):
        if self.dashboard_process:
            self.dashboard_process.terminate()
            self.dashboard_process = None
            self.dash_card.set_active(False)
            self.log("Админка остановлена.")

    def read_output(self, process, prefix):
        for line in iter(process.stdout.readline, ""):
            if line:
                self.log(f"[{prefix}] {line.strip()[:100]}")
        process.stdout.close()

    def run_save_session(self):
        python_exe = self._get_python_exe()
        args = [python_exe, "tools/save_session.py"]
        try:
            subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )
            self.log(
                "Браузер открыт. Решите капчу и нажмите Enter в консоли."
            )
        except Exception as e:
            self.log(f"Ошибка запуска сессии: {e}")

    def open_browser(self):
        webbrowser.open(f"http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")

    def change_mode(self, new_mode: str):
        settings.MODE = new_mode
        self.update_env_mode(new_mode)
        self.log(f"Режим изменен на: {new_mode.upper()}")
        if self.bot_process is not None:
            self.log("⚠️ Чтобы бот начал работать в новом режиме, выключите его (переключатель слева) и включите заново.")
        if self.dashboard_process is not None:
            self.log("⚠️ Чтобы режим применился для веб-панели, выключите её и включите заново.")

    def change_headless(self, new_val: str):
        headless_bool = (new_val == "Без окна")
        settings.HEADLESS = headless_bool
        self.update_env_headless(headless_bool)
        self.log(f"Браузер изменен на: {new_val.upper()}")
        if self.bot_process is not None:
            self.log("⚠️ Чтобы бот применил настройки браузера, выключите его и включите заново.")
        if self.dashboard_process is not None:
            self.log("⚠️ Чтобы веб-панель применила настройки браузера, выключите её и включите заново.")

    def update_env_mode(self, mode: str):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if not os.path.exists(env_path):
            self.log(f"Ошибка: файл .env не найден по пути {env_path}")
            return
        try:
            with open(env_path, encoding="utf-8") as f:
                lines = f.readlines()

            mode_found = False
            for i, line in enumerate(lines):
                if line.strip().startswith("SCRAPER_MODE="):
                    parts = line.split("=", 1)
                    comment = ""
                    if "#" in parts[1]:
                        comment_parts = parts[1].split("#", 1)
                        comment = f" #{comment_parts[1].rstrip()}"
                    lines[i] = f"SCRAPER_MODE={mode}{comment}\n"
                    mode_found = True
                    break

            if not mode_found:
                lines.append(f"\nSCRAPER_MODE={mode}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            self.log(f"Ошибка обновления файла .env: {e}")

    def update_env_headless(self, headless: bool):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if not os.path.exists(env_path):
            self.log(f"Ошибка: файл .env не найден по пути {env_path}")
            return
        try:
            with open(env_path, encoding="utf-8") as f:
                lines = f.readlines()

            headless_found = False
            for i, line in enumerate(lines):
                if line.strip().startswith("SCRAPER_HEADLESS="):
                    parts = line.split("=", 1)
                    comment = ""
                    if "#" in parts[1]:
                        comment_parts = parts[1].split("#", 1)
                        comment = f" #{comment_parts[1].rstrip()}"
                    lines[i] = f"SCRAPER_HEADLESS={headless}{comment}\n"
                    headless_found = True
                    break

            if not headless_found:
                lines.append(f"\nSCRAPER_HEADLESS={headless}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            self.log(f"Ошибка обновления файла .env: {e}")

    def confirm_clear_db(self):
        ClearDbDialog(self, on_confirm=self.perform_database_wipe)

    def perform_database_wipe(self):
        import asyncio

        import database as db
        self.log("Очистка базы данных...")
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(db.clear_database())
            self.log("[OK] База данных успешно очищена.")

            db_exists = os.path.exists(settings.DB_PATH)
            db_status_color = COLOR_SUCCESS if db_exists else COLOR_DANGER
            db_status_text = "●  CONNECTED" if db_exists else "●  MISSING"
            self.db_status_label.configure(text=db_status_text, text_color=db_status_color)
        except Exception as e:
            self.log(f"[ERR] Ошибка очистки базы данных: {e}")
        finally:
            loop.close()

    def on_closing(self):
        self.stop_bot()
        self.stop_dashboard()
        self.destroy()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--bot":
            import asyncio

            import bot

            try:
                asyncio.run(bot.main())
            except (KeyboardInterrupt, SystemExit):
                pass
        elif sys.argv[1] == "--dashboard":
            import admin_dashboard

            try:
                admin_dashboard.main()
            except (KeyboardInterrupt, SystemExit):
                pass
    else:
        app = LauncherApp()
        app.mainloop()
