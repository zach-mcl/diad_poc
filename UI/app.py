from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import pandas as pd

try:
    from PIL import Image, ImageTk
except ImportError:  # Pillow is optional.
    Image = None
    ImageTk = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # Drag/drop is nice to have, but the app should still run without it.
    DND_FILES = None
    TkinterDnD = None

from UI.controller import Controller
from UI.state import AppState


_ALLOWED_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx *.json"),
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx"),
    ("JSON files", "*.json"),
]
_ALLOWED_SUFFIXES = {".csv", ".xlsx", ".json"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

APP_BG = "#151216"
SURFACE = "#211D24"
SURFACE_2 = "#121114"
SURFACE_3 = "#302832"
SURFACE_4 = "#44323D"
SURFACE_5 = "#523B49"
BORDER = "#6E444D"
BORDER_SOFT = "#3A2931"
TEXT = "#FFF3F5"
MUTED = "#D3B8BE"
MUTED_2 = "#A8848D"
ACCENT = "#F52D35"
ACCENT_HOVER = "#D9212B"
ACCENT_SOFT = "#421F28"
ACCENT_TEXT = "#FFFFFF"
SUCCESS = "#40C983"
WARNING = "#F3B562"
ERROR = "#FF6B73"
DANGER = "#B91C1C"
DANGER_HOVER = "#991B1B"

FONT_FAMILY = "Courier New"


def app_font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def tk_app_font(size: int = 12, weight: str = "normal") -> tuple[str, int, str]:
    return (FONT_FAMILY, size, weight)


def glass_panel(parent, **kwargs):
    defaults = {
        "fg_color": SURFACE,
        "border_width": 1,
        "border_color": BORDER_SOFT,
        "corner_radius": 18,
    }
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def section_title(parent, text: str):
    return ctk.CTkLabel(
        parent,
        text=text,
        font=app_font(18, "bold"),
        text_color=TEXT,
    )


def section_subtitle(parent, text: str, wraplength: int = 320):
    return ctk.CTkLabel(
        parent,
        text=text,
        font=app_font(13),
        text_color=MUTED,
        wraplength=wraplength,
        justify="left",
    )


def small_button(parent, text: str, command=None, width: int | None = None):
    return ctk.CTkButton(
        parent,
        text=text,
        width=width or 120,
        height=34,
        corner_radius=10,
        fg_color=SURFACE_3,
        hover_color=SURFACE_4,
        text_color=TEXT,
        font=app_font(12, "bold"),
        command=command,
    )


def primary_button(parent, text: str, command=None, width: int | None = None):
    return ctk.CTkButton(
        parent,
        text=text,
        width=width or 120,
        height=40,
        corner_radius=12,
        fg_color=ACCENT,
        hover_color=ACCENT_HOVER,
        text_color=ACCENT_TEXT,
        font=app_font(13, "bold"),
        command=command,
    )


def danger_button(parent, text: str, command=None, width: int | None = None):
    return ctk.CTkButton(
        parent,
        text=text,
        width=width or 120,
        height=40,
        corner_radius=12,
        fg_color=DANGER,
        hover_color=DANGER_HOVER,
        text_color=ACCENT_TEXT,
        font=app_font(13, "bold"),
        command=command,
    )


class ToolTip:
    def __init__(self, widget, text: str, wraplength: int = 360):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None) -> None:
        if self.tip is not None:
            return

        x = self.widget.winfo_pointerx() + 14
        y = self.widget.winfo_pointery() + 14

        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        self.tip.configure(bg=SURFACE_2)

        frame = tk.Frame(
            self.tip,
            bg=SURFACE_2,
            highlightbackground=ACCENT_HOVER,
            highlightthickness=1,
            bd=0,
        )
        frame.pack()

        label = tk.Label(
            frame,
            text=self.text,
            bg=SURFACE_2,
            fg=TEXT,
            justify="left",
            padx=10,
            pady=8,
            wraplength=self.wraplength,
            font=tk_app_font(11),
        )
        label.pack()

    def hide(self, event=None) -> None:
        if self.tip:
            self.tip.destroy()
        self.tip = None


def add_corner_help(parent, text: str, x: int = -10, y: int = 10):
    try:
        parent_bg = parent.cget("fg_color")
        if isinstance(parent_bg, tuple):
            parent_bg = parent_bg[0]
    except Exception:
        parent_bg = SURFACE

    badge = tk.Label(
        parent,
        text="?",
        font=tk_app_font(20, "bold"),
        fg=ACCENT_HOVER,
        bg=parent_bg,
        activeforeground=ACCENT,
        activebackground=parent_bg,
        cursor="question_arrow",
        bd=0,
        highlightthickness=0,
        padx=3,
        pady=1,
    )
    badge.place(relx=1.0, rely=0.0, anchor="ne", x=x, y=y)
    ToolTip(badge, text)
    return badge


def clear_children(parent):
    for child in list(parent.winfo_children()):
        try:
            child.destroy()
        except (tk.TclError, AttributeError):
            pass


def resolve_logo_path() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent.parent / "DIADlogo.png",
        Path.cwd() / "DIADlogo.png",
        Path(__file__).resolve().parent / "DIADlogo.png",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


if TkinterDnD is not None:

    class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

else:

    class DnDCTk(ctk.CTk):
        pass


class TkApp(DnDCTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title("DIAD")
        self.geometry("1440x880")
        self.minsize(1180, 760)
        self.configure(fg_color=APP_BG)

        self.logo_path = resolve_logo_path()
        self.logo_image_large = self._load_logo_image((190, 105))
        self.logo_image_medium = self._load_logo_image((144, 80))
        self.logo_image_small = self._load_logo_image((86, 48))
        self._window_icon = None
        self._set_window_icon()

        self.app_state = AppState()
        self._render_pending = False
        self.controller = Controller(self.app_state, self.request_render)

        self._configure_ttk_styles()

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=14, pady=14)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.pages: dict[type[ctk.CTkFrame], ctk.CTkFrame] = {}
        for page_cls in (UploadPage, MainPage):
            page = page_cls(self.container, self)
            self.pages[page_cls] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.controller.refresh_projects()
        self.show_page(UploadPage)
        self.render()

    def _configure_ttk_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass

        style.configure(
            "Dark.Treeview",
            background=SURFACE_2,
            fieldbackground=SURFACE_2,
            foreground=TEXT,
            rowheight=30,
            font=tk_app_font(11),
            bordercolor=BORDER_SOFT,
            borderwidth=0,
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", ACCENT_SOFT)],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=SURFACE,
            foreground=TEXT,
            font=tk_app_font(11, "bold"),
            relief="flat",
        )
        style.map("Dark.Treeview.Heading", background=[("active", SURFACE_3)])

    def _prepare_logo_pil(self, square: bool = False):
        if not self.logo_path or Image is None:
            return None

        try:
            img = Image.open(self.logo_path).convert("RGBA")
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)

            if square:
                side = max(img.width, img.height)
                pad = max(24, int(side * 0.10))
                canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), "#FFFFFF")
                x = (canvas.width - img.width) // 2
                y = (canvas.height - img.height) // 2
                canvas.alpha_composite(img, (x, y))
                return canvas

            pad_x = max(18, int(img.width * 0.04))
            pad_y = max(14, int(img.height * 0.08))
            canvas = Image.new("RGBA", (img.width + pad_x * 2, img.height + pad_y * 2), "#FFFFFF")
            canvas.alpha_composite(img, (pad_x, pad_y))
            return canvas
        except Exception:
            return None

    def _load_logo_image(self, size: tuple[int, int]):
        logo = self._prepare_logo_pil(square=False)
        if logo is None:
            return None
        try:
            return ctk.CTkImage(light_image=logo, dark_image=logo, size=size)
        except Exception:
            return None

    def _set_window_icon(self):
        if not self.logo_path:
            return
        try:
            if Image is not None and ImageTk is not None:
                icon_img = self._prepare_logo_pil(square=True)
                if icon_img is not None:
                    icon_img = icon_img.resize((256, 256), Image.Resampling.LANCZOS)
                    self._window_icon = ImageTk.PhotoImage(icon_img)
                    self.iconphoto(False, self._window_icon)
                    return
            self._window_icon = tk.PhotoImage(file=str(self.logo_path))
            self.iconphoto(False, self._window_icon)
        except Exception:
            self._window_icon = None

    def show_page(self, page_class):
        self.pages[page_class].tkraise()
        self.render()

    def request_render(self):
        if self._render_pending:
            return
        self._render_pending = True
        try:
            self.after(0, self._run_requested_render)
        except tk.TclError:
            self._render_pending = False

    def _run_requested_render(self):
        self._render_pending = False
        self.render()

    def render(self):
        for page in self.pages.values():
            try:
                page.render()
            except tk.TclError:
                pass


class UploadPage(ctk.CTkFrame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.pending_files: list[Path] = []
        self.project_records: list[dict] = []
        self.selected_project_var = tk.StringVar(value="")
        self._progress_running = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 18))
        header.grid_columnconfigure(1, weight=1)

        if self.app.logo_image_large is not None:
            holder = ctk.CTkFrame(header, fg_color="#FFFFFF", corner_radius=16, width=214, height=118)
            holder.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 16))
            holder.grid_propagate(False)
            ctk.CTkLabel(holder, text="", image=self.app.logo_image_large, fg_color="#FFFFFF").place(
                relx=0.5, rely=0.5, anchor="center"
            )
            brand_col = 1
        else:
            brand_col = 0

        brand_text = ctk.CTkFrame(header, fg_color="transparent")
        brand_text.grid(row=0, column=brand_col, sticky="ew")
        brand_text.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(brand_text, text="DIAD", font=app_font(30, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            brand_text,
            text="Create a project, add your files, and start chatting with your data.",
            font=app_font(14),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.create_frame = glass_panel(body)
        self.create_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.create_frame.grid_columnconfigure(0, weight=1)
        self.create_frame.grid_rowconfigure(5, weight=1)
        add_corner_help(
            self.create_frame,
            "Start by naming the project, then add CSV, XLSX, or JSON files. DIAD copies those files into the project and loads each sheet/file as a table you can query.",
        )

        section_title(self.create_frame, "New Project").grid(row=0, column=0, sticky="w", padx=22, pady=(22, 4))
        section_subtitle(
            self.create_frame,
            "Drop files here or choose them manually. DIAD will load each file as a table.",
            440,
        ).grid(row=1, column=0, sticky="w", padx=22, pady=(0, 16))

        self.project_name_entry = ctk.CTkEntry(
            self.create_frame,
            height=42,
            corner_radius=12,
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Project name",
            placeholder_text_color=MUTED_2,
            font=app_font(13),
        )
        self.project_name_entry.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))

        action_row = ctk.CTkFrame(self.create_frame, fg_color="transparent")
        action_row.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 12))
        action_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_pick_files = small_button(action_row, "Add Files", self.on_pick_files)
        self.btn_pick_files.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.btn_clear_files = small_button(action_row, "Clear", self.on_clear_files)
        self.btn_clear_files.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.pending_frame = ctk.CTkScrollableFrame(
            self.create_frame,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
        )
        self.pending_frame.grid(row=5, column=0, sticky="nsew", padx=22, pady=(0, 14))
        self._enable_drop_target(self.pending_frame, self.on_files_drop)

        bottom_row = ctk.CTkFrame(self.create_frame, fg_color="transparent")
        bottom_row.grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 22))
        bottom_row.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(bottom_row, text="", text_color=MUTED, anchor="w", font=app_font(12))
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.btn_create_project = primary_button(bottom_row, "Create Project", self.on_create_project, width=150)
        self.btn_create_project.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            bottom_row,
            height=8,
            corner_radius=8,
            mode="indeterminate",
            fg_color=SURFACE_3,
            progress_color=ACCENT,
        )
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.progress_bar.grid_remove()

        self.projects_frame = glass_panel(body)
        self.projects_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.projects_frame.grid_columnconfigure(0, weight=1)
        self.projects_frame.grid_rowconfigure(3, weight=1)
        add_corner_help(
            self.projects_frame,
            "Pick a saved project to reload its files, schema, table names, and chat-ready data context. Use Refresh if a project does not show up yet.",
        )

        section_title(self.projects_frame, "Existing Projects").grid(row=0, column=0, sticky="w", padx=22, pady=(22, 4))
        section_subtitle(self.projects_frame, "Pick a project to continue where you left off.", 440).grid(
            row=1, column=0, sticky="w", padx=22, pady=(0, 16)
        )

        project_actions = ctk.CTkFrame(self.projects_frame, fg_color="transparent")
        project_actions.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        project_actions.grid_columnconfigure(0, weight=1)
        self.project_count_label = ctk.CTkLabel(project_actions, text="0 available", text_color=MUTED, anchor="w", font=app_font(12))
        self.project_count_label.grid(row=0, column=0, sticky="ew")
        self.btn_refresh_projects = small_button(project_actions, "Refresh", self.on_refresh_projects, width=100)
        self.btn_refresh_projects.grid(row=0, column=1, padx=(8, 0))

        self.projects_scroll = ctk.CTkScrollableFrame(
            self.projects_frame,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
        )
        self.projects_scroll.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 14))

        open_row = ctk.CTkFrame(self.projects_frame, fg_color="transparent")
        open_row.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 22))
        open_row.grid_columnconfigure(0, weight=1)
        self.btn_open_project = primary_button(open_row, "Open Project", self.on_open_project, width=150)
        self.btn_open_project.grid(row=0, column=1, sticky="e")

        self._enable_drop_target(self.create_frame, self.on_files_drop)

    def _enable_drop_target(self, widget, callback):
        if DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", callback)
        except Exception:
            pass

    def _parse_drop_paths(self, event) -> list[str]:
        try:
            return list(self.tk.splitlist(event.data))
        except Exception:
            return []

    def _file_badge_text(self, path: Path) -> str:
        return path.suffix.replace(".", "").upper() or "FILE"

    def _add_pending_files(self, raw_paths: list[str | Path]):
        existing = {p.resolve() for p in self.pending_files}
        for raw in raw_paths:
            p = Path(raw).expanduser().resolve()
            if not p.exists() or not p.is_file():
                continue
            if p.suffix.lower() not in _ALLOWED_SUFFIXES:
                continue
            if p.resolve() in existing:
                continue
            self.pending_files.append(p)
            existing.add(p.resolve())
        self.render()

    def _render_pending_files(self):
        clear_children(self.pending_frame)
        if not self.pending_files:
            ctk.CTkLabel(
                self.pending_frame,
                text="No files selected yet.\nDrop CSV/XLSX/JSON files here.",
                text_color=MUTED,
                font=app_font(13),
                justify="left",
                wraplength=420,
            ).pack(anchor="w", padx=12, pady=14)
            return

        for path in self.pending_files:
            card = ctk.CTkFrame(self.pending_frame, fg_color=SURFACE_3, corner_radius=12)
            card.pack(fill="x", padx=4, pady=5)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                card,
                text=self._file_badge_text(path),
                width=54,
                height=26,
                fg_color=ACCENT_SOFT,
                corner_radius=8,
                text_color=TEXT,
                font=app_font(12, "bold"),
            ).grid(row=0, column=0, rowspan=2, padx=10, pady=10)
            ctk.CTkLabel(card, text=path.name, text_color=TEXT, anchor="w", font=app_font(13)).grid(
                row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0)
            )
            ctk.CTkLabel(card, text=str(path.parent), text_color=MUTED_2, anchor="w", font=app_font(11)).grid(
                row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10)
            )

    def _render_projects(self):
        clear_children(self.projects_scroll)
        self.project_count_label.configure(text=f"{len(self.project_records)} available")
        if not self.project_records:
            ctk.CTkLabel(self.projects_scroll, text="No projects yet.", text_color=MUTED, font=app_font(13)).pack(
                anchor="w", padx=8, pady=8
            )
            return

        selected = self.selected_project_var.get()
        for item in self.project_records:
            path = str(item.get("path") or "")
            selected_now = path == selected
            card = ctk.CTkFrame(
                self.projects_scroll,
                fg_color=SURFACE_3 if selected_now else SURFACE,
                border_width=1,
                border_color=ACCENT if selected_now else BORDER_SOFT,
                corner_radius=14,
            )
            card.pack(fill="x", padx=4, pady=5)
            card.grid_columnconfigure(1, weight=1)
            card.grid_columnconfigure(2, weight=0)

            radio = ctk.CTkRadioButton(
                card,
                text="",
                variable=self.selected_project_var,
                value=path,
                radiobutton_width=18,
                radiobutton_height=18,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                border_color=MUTED,
                command=self.render,
            )
            radio.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=12, sticky="n")

            created = self._format_created_at(item.get("created_at"))
            meta = f'{item.get("file_count", 0)} file(s) • {created}'
            name_label = ctk.CTkLabel(
                card,
                text=item.get("name", "(unnamed)"),
                font=app_font(15, "bold"),
                text_color=TEXT,
                anchor="w",
            )
            name_label.grid(row=0, column=1, sticky="ew", pady=(10, 2), padx=(0, 10))
            meta_label = ctk.CTkLabel(card, text=meta, text_color=MUTED, anchor="w", font=app_font(12))
            meta_label.grid(row=1, column=1, sticky="ew", pady=(0, 10), padx=(0, 10))

            delete_btn = danger_button(card, "Delete", lambda p=path: self.on_delete_project(p), width=72)
            delete_btn.configure(height=28, corner_radius=10, font=app_font(11, "bold"))
            delete_btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 10), pady=10)

            self._bind_project_card([card, radio, name_label, meta_label], path)

    def _bind_project_card(self, widgets, path: str):
        for widget in widgets:
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass
            widget.bind("<Button-1>", lambda _e, p=path: self._select_project(p), add="+")
            widget.bind("<Double-Button-1>", lambda _e, p=path: self._open_project_path(p), add="+")

    def _select_project(self, path: str):
        self.selected_project_var.set(path)
        self.render()

    def _open_project_path(self, path: str):
        if path:
            self.app.controller.open_project(path)
            self.after(120, self.check_transition)

    def on_pick_files(self):
        paths = filedialog.askopenfilenames(title="Select CSV/XLSX/JSON files", filetypes=_ALLOWED_FILE_TYPES)
        if paths:
            self._add_pending_files(list(paths))

    def on_clear_files(self):
        self.pending_files = []
        self.render()

    def on_files_drop(self, event):
        self._add_pending_files(self._parse_drop_paths(event))

    def on_create_project(self):
        project_name = self.project_name_entry.get().strip()
        if not project_name:
            messagebox.showinfo("Create Project", "Enter a project name first.")
            return
        if not self.pending_files:
            messagebox.showinfo("Create Project", "Add at least one CSV, XLSX, or JSON file.")
            return
        self.app.controller.create_project(project_name, self.pending_files)
        self.after(120, self.check_transition)

    def on_open_project(self):
        selected = self.selected_project_var.get().strip()
        if not selected:
            messagebox.showinfo("Open Project", "Select a project first.")
            return
        self._open_project_path(selected)

    def on_delete_project(self, path: str):
        if not path:
            return
        project_name = Path(path).name
        for item in self.project_records:
            if str(item.get("path") or "") == path:
                project_name = str(item.get("name") or project_name)
                break
        confirmed = messagebox.askyesno(
            "Delete Project",
            f'Delete "{project_name}"?\n\nThis removes the project folder and the copied files stored inside DIAD.',
        )
        if not confirmed:
            return
        if self.selected_project_var.get() == path:
            self.selected_project_var.set("")
        self.app.controller.delete_project(path)

    def on_refresh_projects(self):
        self.app.controller.refresh_projects()

    def check_transition(self):
        if self.app.app_state.is_busy:
            self.after(120, self.check_transition)
            return
        if self.app.app_state.error:
            self.status_label.configure(text=f"Error: {self.app.app_state.error}", text_color=ERROR)
            return
        if self.app.app_state.current_project_path:
            self.pending_files = []
            self.project_name_entry.delete(0, tk.END)
            self.app.show_page(MainPage)

    def _format_created_at(self, value: str | None) -> str:
        if not value:
            return "unknown date"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)

    def _show_progress(self, visible: bool):
        if visible:
            self.progress_bar.grid()
            if not self._progress_running:
                self.progress_bar.start()
                self._progress_running = True
        else:
            if self._progress_running:
                self.progress_bar.stop()
                self._progress_running = False
            self.progress_bar.grid_remove()

    def render(self):
        self.project_records = list(self.app.app_state.available_projects)
        self._render_pending_files()
        self._render_projects()

        busy = self.app.app_state.is_busy
        state = "disabled" if busy else "normal"
        self.project_name_entry.configure(state=state)
        self.btn_pick_files.configure(state=state)
        self.btn_clear_files.configure(state=state)
        self.btn_create_project.configure(state=state)
        self.btn_refresh_projects.configure(state=state)
        self.btn_open_project.configure(state=state if self.project_records and not busy else "disabled")

        if busy:
            status_message = getattr(self.app.app_state, "status_message", None) or "Working..."
            self.status_label.configure(text=status_message, text_color=WARNING)
            self._show_progress(True)
        else:
            self._show_progress(False)
            self.status_label.configure(
                text=self.app.app_state.error or "",
                text_color=ERROR if self.app.app_state.error else MUTED,
            )


class MainPage(ctk.CTkFrame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.controller = app.controller
        self.state = app.app_state
        self.schema_search_var = tk.StringVar()
        self.schema_search_var.trace_add("write", lambda *_: self.refresh_schema_tree())
        self.selected_schema_item: tuple[str, str | None, str | None] | None = None
        self.selected_schema_kind: str | None = None
        self._progress_running = False
        self._last_auto_open_path: Path | None = None
        self._build_layout()

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        self.sidebar = glass_panel(self, width=278)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10), pady=0)
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        add_corner_help(
            self.sidebar,
            "This is your project control area. Use Projects to switch workspaces, Add Files to expand the dataset, Schema to see table/column names, Categories to inspect common values, and Latest SQL to debug the last query.",
        )

        row = 0
        if self.app.logo_image_medium is not None:
            holder = ctk.CTkFrame(self.sidebar, fg_color="#FFFFFF", corner_radius=14, width=168, height=92)
            holder.grid(row=row, column=0, sticky="w", padx=16, pady=(16, 10))
            holder.grid_propagate(False)
            ctk.CTkLabel(holder, text="", image=self.app.logo_image_medium, fg_color="#FFFFFF").place(
                relx=0.5, rely=0.5, anchor="center"
            )
            row += 1

        self.sidebar.grid_rowconfigure(row + 7, weight=1)
        ctk.CTkLabel(self.sidebar, text="Project", font=app_font(16, "bold"), text_color=TEXT).grid(
            row=row, column=0, sticky="w", padx=16, pady=(0, 6)
        )
        self.project_label = ctk.CTkLabel(
            self.sidebar,
            text="No project open",
            text_color=TEXT,
            font=app_font(13),
            wraplength=230,
            justify="left",
            anchor="w",
        )
        self.project_label.grid(row=row + 1, column=0, sticky="ew", padx=16)
        self.project_path_label = ctk.CTkLabel(
            self.sidebar,
            text="",
            text_color=MUTED,
            font=app_font(11),
            wraplength=230,
            justify="left",
            anchor="w",
        )
        self.project_path_label.grid(row=row + 2, column=0, sticky="ew", padx=16, pady=(6, 14))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.grid(row=row + 3, column=0, sticky="ew", padx=16)
        nav.grid_columnconfigure(0, weight=1)
        self.btn_projects = small_button(nav, "Projects", self.on_back_to_projects)
        self.btn_projects.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.btn_add_files = small_button(nav, "Add Files", self.on_add_files)
        self.btn_add_files.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.btn_view_schema = small_button(nav, "Schema", self.open_schema_window)
        self.btn_view_schema.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.btn_view_categories = small_button(nav, "Categories", self.open_categories_window)
        self.btn_view_categories.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.btn_view_sql = small_button(nav, "Latest SQL", self.open_sql_window)
        self.btn_view_sql.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        self.btn_view_tips = small_button(nav, "Tips", self.open_tips_window)
        self.btn_view_tips.grid(row=5, column=0, sticky="ew")

        files_section = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        files_section.grid(row=row + 7, column=0, sticky="nsew", padx=16, pady=(14, 16))
        files_section.grid_rowconfigure(1, weight=1)
        files_section.grid_columnconfigure(0, weight=1)
        files_header = ctk.CTkFrame(files_section, fg_color="transparent")
        files_header.grid(row=0, column=0, sticky="ew")
        files_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(files_header, text="Files", font=app_font(14, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w"
        )
        self.file_count_label_main = ctk.CTkLabel(files_header, text="0 loaded", text_color=MUTED_2, font=app_font(11))
        self.file_count_label_main.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.files_scroll = ctk.CTkScrollableFrame(
            files_section,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
        )
        self.files_scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        add_corner_help(
            self.files_scroll,
            "These are the files currently loaded in this project. Drag more CSV, XLSX, or JSON files here when you want DIAD to add new tables to the same workspace.",
            x=-6,
            y=6,
        )
        self._enable_drop_target(self.files_scroll, self.on_project_files_drop)

        self.chat_card = glass_panel(self)
        self.chat_card.grid(row=0, column=1, sticky="nsew", padx=10, pady=0)
        self.chat_card.grid_columnconfigure(0, weight=1)
        self.chat_card.grid_rowconfigure(1, weight=1)
        add_corner_help(
            self.chat_card,
            "Ask data questions here. Try filters like 'who makes 100k or more?', summaries like 'average salary by department', or schema checks like 'what columns are in this table?'. When DIAD creates rows, Open Output and Download CSV become useful.",
        )

        title_wrap = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        title_wrap.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(title_wrap, text="Chat with your data", font=app_font(21, "bold"), text_color=TEXT)
        self.title_label.grid(row=0, column=0, sticky="w")
        self.result_hint = ctk.CTkLabel(title_wrap, text="", text_color=MUTED, font=app_font(12))
        self.result_hint.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.warning_label = ctk.CTkLabel(
            title_wrap,
            text="DIAD is an AI application and can make mistakes, please double check outputs",
            text_color=MUTED_2,
            font=app_font(12),
            wraplength=720,
            justify="left",
            anchor="w",
        )
        self.warning_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
        if self.app.logo_image_small is not None:
            holder = ctk.CTkFrame(title_wrap, fg_color="#FFFFFF", corner_radius=10, width=102, height=58)
            holder.grid(row=0, column=1, rowspan=3, sticky="e", padx=(12, 0))
            holder.grid_propagate(False)
            ctk.CTkLabel(holder, text="", image=self.app.logo_image_small, fg_color="#FFFFFF").place(
                relx=0.5, rely=0.5, anchor="center"
            )

        self.chat_history = ctk.CTkScrollableFrame(
            self.chat_card,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=16,
        )
        self.chat_history.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.chat_history.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)
        self.output_summary_label = ctk.CTkLabel(toolbar, text="No output yet", text_color=MUTED, anchor="w", font=app_font(12))
        self.output_summary_label.grid(row=0, column=0, sticky="w")
        self.btn_open_output = small_button(toolbar, "Open Output", self.open_output_window, width=120)
        self.btn_open_output.grid(row=0, column=1, padx=(8, 0))
        self.btn_download_output = primary_button(toolbar, "Download CSV", self.download_output_csv, width=135)
        self.btn_download_output.grid(row=0, column=2, padx=(8, 0))

        composer = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        composer.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))
        composer.grid_columnconfigure(0, weight=1)
        self.chat_entry = ctk.CTkEntry(
            composer,
            height=42,
            corner_radius=14,
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Ask something about your data...",
            placeholder_text_color=MUTED_2,
            font=app_font(13),
        )
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda _e: self.on_send())
        self.btn_edit_last_query = small_button(composer, "Edit Last", self.edit_last_query, width=104)
        self.btn_edit_last_query.grid(row=0, column=1, padx=(8, 0))
        self.btn_send = primary_button(composer, "Send", self.on_send, width=96)
        self.btn_send.grid(row=0, column=2, padx=(8, 0))

        self.status = ctk.CTkLabel(self.chat_card, text="Ready", text_color=MUTED, font=app_font(12))
        self.status.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 6))
        self.progress_bar = ctk.CTkProgressBar(
            self.chat_card,
            height=8,
            corner_radius=8,
            mode="indeterminate",
            fg_color=SURFACE_3,
            progress_color=ACCENT,
        )
        self.progress_bar.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 16))
        self.progress_bar.grid_remove()

        self.guide_card = glass_panel(self, width=340)
        self.guide_card.grid(row=0, column=2, sticky="nse", padx=(10, 0), pady=0)
        self.guide_card.grid_propagate(False)
        self.guide_card.grid_columnconfigure(0, weight=1)
        self.guide_card.grid_rowconfigure(3, weight=1)
        self.guide_card.grid_rowconfigure(7, weight=1)
        add_corner_help(
            self.guide_card,
            "Use the Data Guide to see exact table names, columns, and known values. Select a column to enable Copy Column, or use Insert Selected to drop exact schema wording into your next question.",
        )

        section_title(self.guide_card, "Data Guide").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        section_subtitle(
            self.guide_card,
            "Browse tables, headers, and sample values. Double-click an item to add it to the chat box.",
            wraplength=285,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        self.schema_search = ctk.CTkEntry(
            self.guide_card,
            textvariable=self.schema_search_var,
            height=38,
            corner_radius=12,
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Search tables, columns, or values...",
            placeholder_text_color=MUTED_2,
            font=app_font(12),
        )
        self.schema_search.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        tree_wrap = glass_panel(self.guide_card, fg_color=SURFACE_2, corner_radius=14)
        tree_wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        self.schema_tree = ttk.Treeview(tree_wrap, show="tree", style="Dark.Treeview")
        self.schema_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.schema_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_schema_details())
        self.schema_tree.bind("<Double-Button-1>", self.on_schema_tree_double_click)
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.schema_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.schema_tree.configure(yscrollcommand=tree_scroll.set)

        detail_header = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        detail_header.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        detail_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(detail_header, text="Selected item", font=app_font(14, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w"
        )
        self.schema_summary_label = ctk.CTkLabel(detail_header, text="Nothing selected", text_color=MUTED_2, font=app_font(11))
        self.schema_summary_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        copy_row = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        copy_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))
        copy_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_copy_table = small_button(copy_row, "Copy table", self.copy_selected_table, width=120)
        self.btn_copy_table.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_copy_column = small_button(copy_row, "Copy column", self.copy_selected_column, width=120)
        self.btn_copy_column.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        chip_row = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        chip_row.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 8))
        chip_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_insert_selected = small_button(chip_row, "Insert selected", self.insert_selected_schema_item, width=120)
        self.btn_insert_selected.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_search_selected = small_button(chip_row, "Search selected", self.search_selected_schema_item, width=120)
        self.btn_search_selected.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.schema_detail = ctk.CTkTextbox(
            self.guide_card,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
            text_color=TEXT,
            font=app_font(12),
            wrap="word",
        )
        self.schema_detail.grid(row=7, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.schema_detail.configure(state="disabled")
        self._update_schema_copy_buttons()

    def _enable_drop_target(self, widget, callback):
        if DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", callback)
        except Exception:
            pass

    def _parse_drop_paths(self, event) -> list[str]:
        try:
            return list(self.tk.splitlist(event.data))
        except Exception:
            return []

    def _safe_open_path(self, path: Path):
        path = Path(path)
        if not path.exists():
            messagebox.showinfo("Open File", f"Could not find: {path}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showinfo("Open File", f"Could not open file:\n{exc}")

    def _insert_text_into_chat_entry(self, text: str):
        text = str(text).strip()
        if not text:
            return
        current = self.chat_entry.get()
        spacer = "" if not current or current.endswith((" ", "\n")) else " "
        self.chat_entry.insert(tk.END, f"{spacer}{text}")
        self.chat_entry.focus_set()

    def _set_schema_search_text(self, text: str):
        text = str(text).strip()
        if not text:
            return
        self.schema_search.delete(0, tk.END)
        self.schema_search.insert(0, text)
        self.schema_search.focus_set()

    def _schema_payload_from_tree_item(self, item_id: str) -> dict[str, str] | None:
        if not item_id:
            return None
        values = list(self.schema_tree.item(item_id, "values") or [])
        item_text = str(self.schema_tree.item(item_id, "text") or "")
        if not values and not item_text:
            return None
        table = str(values[0]) if len(values) > 0 and values[0] else item_text
        column = str(values[1]) if len(values) > 1 and values[1] else ""
        kind = str(values[2]) if len(values) > 2 and values[2] else ("column" if column else "table")
        value = str(values[3]) if len(values) > 3 and values[3] else ""
        return self._make_schema_payload(table, column or None, value or None, kind)

    def _selected_schema_payload(self) -> dict[str, str] | None:
        selected = self.schema_tree.selection()
        if not selected:
            return None
        return self._schema_payload_from_tree_item(selected[0])

    def _make_schema_payload(
        self,
        table: str,
        column: str | None = None,
        value: str | None = None,
        kind: str | None = None,
    ) -> dict[str, str]:
        table = str(table or "")
        column = str(column or "")
        value = str(value or "")
        kind = kind or ("value" if value and column else "column" if column else "table")
        insert_text = self.controller.format_schema_insert_text(
            table=table,
            column=column or None,
            value=value or None,
        )
        search_text = self.controller.format_schema_search_text(
            table=table,
            column=column or None,
            value=value or None,
        )
        if kind == "value":
            display = f'{column} is "{value}"'
        elif kind == "column":
            display = column
        else:
            display = table
        return {
            "kind": kind,
            "table": table,
            "column": column,
            "value": value,
            "insert_text": insert_text,
            "search_text": search_text,
            "display": display,
        }

    def on_schema_tree_double_click(self, event):
        payload = self._selected_schema_payload()
        if not payload:
            return
        self._insert_text_into_chat_entry(payload.get("insert_text", ""))
        self.status.configure(text=f"Added: {payload.get('display', 'item')}", text_color=SUCCESS)
        return "break"

    def insert_selected_schema_item(self):
        payload = self._selected_schema_payload()
        if not payload:
            return
        self._insert_text_into_chat_entry(payload.get("insert_text", ""))

    def search_selected_schema_item(self):
        payload = self._selected_schema_payload()
        if not payload:
            return
        self._set_schema_search_text(payload.get("search_text", ""))

    def fill_suggestion(self, text: str):
        self.chat_entry.delete(0, tk.END)
        self.chat_entry.insert(0, text)
        self.chat_entry.focus_set()

    def _iter_columns(self, table: str):
        columns = self.state.schema_map.get(table, {})
        if isinstance(columns, dict):
            for column, dtype in columns.items():
                yield str(column), str(dtype)
        else:
            for item in columns:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    yield str(item[0]), str(item[1])
                else:
                    yield str(item), "unknown"

    def _table_column_counts(self) -> tuple[int, int]:
        table_count = len(self.state.schema_map)
        column_count = sum(1 for table in self.state.schema_map for _ in self._iter_columns(table))
        return table_count, column_count

    def _format_file_card_meta(self, path: Path) -> str:
        ext = path.suffix.upper().replace(".", "") or "FILE"
        size_text = "unknown size"
        try:
            size = path.stat().st_size
            if size >= 1024 * 1024:
                size_text = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_text = f"{size / 1024:.1f} KB"
            else:
                size_text = f"{size} B"
        except Exception:
            pass
        return f"{ext} • {size_text}"

    def _guess_table_for_file(self, path: Path) -> str | None:
        stem = path.stem.lower().replace(" ", "_").replace("-", "_")
        for table in self.state.tables:
            if stem in table.lower() or table.lower() in stem:
                return table
        return None

    def _render_files(self):
        clear_children(self.files_scroll)
        files = list(self.state.csv_files) + list(self.state.xlsx_files) + list(getattr(self.state, "json_files", []))
        self.file_count_label_main.configure(text=f"{len(files)} loaded")
        if not files:
            ctk.CTkLabel(self.files_scroll, text="No files loaded.", text_color=MUTED, font=app_font(13)).pack(
                anchor="w", padx=8, pady=8
            )
            return

        seen_names: dict[str, int] = {}
        for path in files:
            seen_names[path.name] = seen_names.get(path.name, 0) + 1

        for path in files:
            duplicate = seen_names.get(path.name, 0) > 1
            card = ctk.CTkFrame(self.files_scroll, fg_color=SURFACE_3, corner_radius=12)
            card.pack(fill="x", padx=4, pady=5)
            card.grid_columnconfigure(1, weight=1)
            badge_text = path.suffix.replace(".", "").upper() or "FILE"
            badge = ctk.CTkLabel(
                card,
                text=badge_text,
                width=54,
                height=26,
                fg_color=ACCENT_SOFT,
                corner_radius=8,
                text_color=TEXT,
                font=app_font(12, "bold"),
            )
            badge.grid(row=0, column=0, rowspan=3, padx=10, pady=8)
            name_label = ctk.CTkLabel(card, text=path.name, text_color=TEXT, anchor="w", wraplength=160, font=app_font(12))
            name_label.grid(row=0, column=1, sticky="ew", pady=(8, 0), padx=(0, 10))

            table = self._guess_table_for_file(path)
            meta = self._format_file_card_meta(path)
            if table:
                meta += f" • table: {table}"
            if duplicate:
                meta += " • duplicate name"
            meta_label = ctk.CTkLabel(
                card,
                text=meta,
                text_color=WARNING if duplicate else MUTED_2,
                anchor="w",
                wraplength=165,
                font=app_font(10),
            )
            meta_label.grid(row=1, column=1, sticky="ew", pady=(1, 2), padx=(0, 10))
            hint_label = ctk.CTkLabel(
                card,
                text="Double-click to preview",
                text_color=MUTED_2,
                anchor="w",
                font=app_font(10),
            )
            hint_label.grid(row=2, column=1, sticky="ew", pady=(0, 8), padx=(0, 10))
            self._bind_loaded_file_card([card, badge, name_label, meta_label, hint_label], path)

    def _bind_loaded_file_card(self, widgets, path: Path):
        for widget in widgets:
            widget.bind("<Double-Button-1>", lambda _e, p=path: self.open_file_preview(p))
            widget.bind("<Enter>", lambda _e, card=widgets[0]: card.configure(fg_color=SURFACE_4))
            widget.bind("<Leave>", lambda _e, card=widgets[0]: card.configure(fg_color=SURFACE_3))
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass

    def _render_messages(self):
        try:
            self.chat_history._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

        clear_children(self.chat_history)
        messages = list(self.state.messages)
        if not messages:
            ctk.CTkLabel(
                self.chat_history,
                text="Ask a question to get started.",
                text_color=MUTED,
                font=app_font(13),
                anchor="w",
                justify="left",
            ).pack(anchor="w", padx=14, pady=14)
            return

        available_width = self.chat_card.winfo_width()
        if available_width <= 100:
            available_width = 760
        bubble_wrap = max(360, min(760, int(available_width * 0.62)))

        for msg in messages:
            role = msg.get("role", "assistant")
            content = str(msg.get("content", ""))
            is_user = role == "user"

            row = ctk.CTkFrame(self.chat_history, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=(8, 4))

            bubble = ctk.CTkFrame(
                row,
                fg_color=ACCENT if is_user else SURFACE_3,
                border_width=1,
                border_color=ACCENT_HOVER if is_user else BORDER_SOFT,
                corner_radius=18,
            )
            bubble.pack(anchor="e" if is_user else "w", padx=(92, 4) if is_user else (4, 92))

            ctk.CTkLabel(
                bubble,
                text="You" if is_user else "DIAD",
                text_color=ACCENT_TEXT if is_user else MUTED_2,
                font=app_font(11, "bold"),
                anchor="w",
            ).pack(anchor="w", padx=13, pady=(9, 0))
            ctk.CTkLabel(
                bubble,
                text=content,
                text_color=ACCENT_TEXT if is_user else TEXT,
                font=app_font(13),
                justify="left",
                anchor="w",
                wraplength=bubble_wrap,
            ).pack(anchor="w", padx=13, pady=(3, 10))

        self._scroll_chat_to_latest_message()

    def _scroll_chat_to_latest_message(self):
        def scroll_later():
            try:
                self.chat_history._parent_canvas.update_idletasks()
                self.chat_history._parent_canvas.yview_moveto(1.0)
            except Exception:
                pass

        try:
            self.after(80, scroll_later)
        except tk.TclError:
            pass

    def _categorical_values_for(self, table: str, column: str) -> list[str]:
        index = getattr(self.state, "categorical_index", {}) or {}
        for key, values in index.items():
            try:
                key_table, key_col = key
            except Exception:
                continue
            if str(key_table) == str(table) and str(key_col) == str(column):
                return [str(v) for v in values]
        return []

    def refresh_schema_tree(self):
        if not hasattr(self, "schema_tree"):
            return

        query = self.schema_search_var.get().strip().lower()
        selected_before = self.schema_tree.selection()
        for item in self.schema_tree.get_children():
            self.schema_tree.delete(item)

        for table in sorted(self.state.schema_map.keys()):
            column_items = list(self._iter_columns(table))
            searchable_table_text = " ".join([table] + [c for c, _d in column_items]).lower()
            if query and query not in searchable_table_text:
                matching_columns = []
                for col, dtype in column_items:
                    values = self._categorical_values_for(table, col)
                    value_blob = " ".join(values).lower()
                    if query in col.lower() or query in str(dtype).lower() or query in value_blob:
                        matching_columns.append((col, dtype))
                if not matching_columns:
                    continue
                column_items = matching_columns

            table_id = self.schema_tree.insert(
                "",
                "end",
                text=table,
                open=bool(query),
                values=(table, "", "table", ""),
            )
            for col, dtype in column_items:
                values = self._categorical_values_for(table, col)
                col_label = f"{col} ({dtype})"
                col_id = self.schema_tree.insert(
                    table_id,
                    "end",
                    text=col_label,
                    open=False,
                    values=(table, col, "column", ""),
                )
                for value in values[:12]:
                    if query and query not in str(value).lower() and query not in col.lower():
                        continue
                    self.schema_tree.insert(
                        col_id,
                        "end",
                        text=str(value),
                        values=(table, col, "value", str(value)),
                    )

        if selected_before:
            try:
                self.schema_tree.selection_set(selected_before[0])
            except Exception:
                pass
        self.show_schema_details()

    def show_schema_details(self):
        payload = self._selected_schema_payload()
        self.schema_detail.configure(state="normal")
        self.schema_detail.delete("1.0", tk.END)

        if not payload:
            self.selected_schema_item = None
            self.selected_schema_kind = None
            self.schema_summary_label.configure(text="Nothing selected")
            self.schema_detail.insert(
                "1.0",
                "Select a table, column, or known value to see details here. Double-click it to add it to your next question.",
            )
            self.schema_detail.configure(state="disabled")
            self._update_schema_copy_buttons()
            return

        table = payload.get("table", "")
        column = payload.get("column", "")
        value = payload.get("value", "")
        kind = payload.get("kind", "table")
        self.selected_schema_item = (table, column or None, value or None)
        self.selected_schema_kind = kind

        if kind == "value":
            self.schema_summary_label.configure(text="Value")
            text = f"Table: {table}\nColumn: {column}\nValue: {value}\n\nUse this when you want to filter records where {column} equals this value."
        elif kind == "column":
            dtype = "unknown"
            for col, col_type in self._iter_columns(table):
                if col == column:
                    dtype = col_type
                    break
            values = self._categorical_values_for(table, column)
            self.schema_summary_label.configure(text="Column")
            text = f"Table: {table}\nColumn: {column}\nType: {dtype}"
            if values:
                text += "\n\nKnown values:\n" + "\n".join(f"- {v}" for v in values[:25])
            text += "\n\nUse Copy Column or Insert Selected to avoid typos in prompts."
        else:
            columns = list(self._iter_columns(table))
            self.schema_summary_label.configure(text="Table")
            text = f"Table: {table}\nColumns: {len(columns)}\n\n"
            text += "\n".join(f"- {col}: {dtype}" for col, dtype in columns)

        self.schema_detail.insert("1.0", text)
        self.schema_detail.configure(state="disabled")
        self._update_schema_copy_buttons()

    def _update_schema_copy_buttons(self):
        payload = self._selected_schema_payload() if hasattr(self, "schema_tree") else None
        kind = payload.get("kind") if payload else None
        has_table = bool(payload and payload.get("table"))
        has_column = bool(payload and payload.get("column"))
        state_table = "normal" if has_table else "disabled"
        state_column = "normal" if has_column else "disabled"
        for button, state in [
            (getattr(self, "btn_copy_table", None), state_table),
            (getattr(self, "btn_copy_column", None), state_column),
            (getattr(self, "btn_insert_selected", None), "normal" if payload else "disabled"),
            (getattr(self, "btn_search_selected", None), "normal" if payload else "disabled"),
        ]:
            if button is not None:
                button.configure(state=state)
        self.selected_schema_kind = kind

    def copy_selected_table(self):
        payload = self._selected_schema_payload()
        if not payload or not payload.get("table"):
            return
        self.clipboard_clear()
        self.clipboard_append(payload["table"])
        self.status.configure(text=f"Copied table: {payload['table']}", text_color=SUCCESS)

    def copy_selected_column(self):
        payload = self._selected_schema_payload()
        if not payload or not payload.get("column"):
            return
        self.clipboard_clear()
        self.clipboard_append(payload["column"])
        self.status.configure(text=f"Copied column: {payload['column']}", text_color=SUCCESS)

    def _render_output_status(self):
        df = self.state.result_preview
        export_path = self.state.export_path
        artifact_path = self.state.artifact_path

        if artifact_path:
            self.output_summary_label.configure(text=f"Chart ready: {Path(artifact_path).name}", text_color=SUCCESS)
            self.btn_open_output.configure(state="normal")
            self.btn_download_output.configure(text="Download Chart", state="normal")
            return

        if df is not None:
            try:
                rows, cols = df.shape
                text = f"Output ready: {rows} rows × {cols} columns"
            except Exception:
                text = "Output ready"
            self.output_summary_label.configure(text=text, text_color=SUCCESS)
            self.btn_open_output.configure(state="normal")
            self.btn_download_output.configure(text="Download CSV", state="normal")
            return

        if export_path:
            self.output_summary_label.configure(text=f"Output ready: {Path(export_path).name}", text_color=SUCCESS)
            self.btn_open_output.configure(state="normal")
            self.btn_download_output.configure(text="Download CSV", state="normal")
            return

        self.output_summary_label.configure(text="No output yet", text_color=MUTED)
        self.btn_open_output.configure(state="disabled")
        self.btn_download_output.configure(text="Download CSV", state="disabled")

    def _set_busy_controls(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.btn_send.configure(state=state)
        self.btn_edit_last_query.configure(state=state)
        self.chat_entry.configure(state=state)
        self.btn_add_files.configure(state=state)
        if busy:
            self.progress_bar.grid()
            if not self._progress_running:
                self.progress_bar.start()
                self._progress_running = True
        else:
            if self._progress_running:
                self.progress_bar.stop()
                self._progress_running = False
            self.progress_bar.grid_remove()

    def on_send(self):
        text = self.chat_entry.get().strip()
        if not text or self.state.is_busy:
            return
        self.chat_entry.delete(0, tk.END)
        self.controller.send_chat(text)

    def edit_last_query(self):
        for msg in reversed(self.state.messages):
            if msg.get("role") == "user":
                self.chat_entry.delete(0, tk.END)
                self.chat_entry.insert(0, str(msg.get("content", "")))
                self.chat_entry.focus_set()
                return
        self.status.configure(text="No previous query to edit.", text_color=WARNING)

    def on_back_to_projects(self):
        self.app.show_page(UploadPage)

    def on_add_files(self):
        paths = filedialog.askopenfilenames(title="Select CSV/XLSX/JSON files", filetypes=_ALLOWED_FILE_TYPES)
        if paths:
            self.controller.add_files_to_current_project(list(paths))

    def on_project_files_drop(self, event):
        paths = self._parse_drop_paths(event)
        if paths:
            self.controller.add_files_to_current_project(paths)

    def open_file_preview(self, path: Path):
        path = Path(path)
        if not path.exists():
            messagebox.showinfo("Preview", f"Could not find: {path}")
            return
        if path.suffix.lower() in _IMAGE_EXTENSIONS:
            self._safe_open_path(path)
            return
        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path)
            elif path.suffix.lower() == ".xlsx":
                df = pd.read_excel(path)
            elif path.suffix.lower() == ".json":
                try:
                    df = pd.read_json(path)
                except ValueError:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    df = pd.json_normalize(data)
            else:
                self._safe_open_path(path)
                return
            self._open_dataframe_window(df, f"Preview: {path.name}")
        except Exception as exc:
            messagebox.showinfo("Preview", f"Could not preview file:\n{exc}")

    def _open_dataframe_window(self, df, title: str = "Output"):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("980x620")
        win.configure(bg=APP_BG)

        frame = tk.Frame(win, bg=APP_BG)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        columns = [str(c) for c in list(df.columns)]
        tree = ttk.Treeview(frame, columns=columns, show="headings", style="Dark.Treeview")
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=max(120, min(260, len(col) * 12)), anchor="w")

        max_rows = min(len(df), 1000)
        for _, row in df.head(max_rows).iterrows():
            values = ["" if pd.isna(row[col]) else str(row[col]) for col in df.columns]
            tree.insert("", "end", values=values)

        footer = tk.Label(
            win,
            text=f"Showing {max_rows} of {len(df)} rows",
            bg=APP_BG,
            fg=MUTED,
            font=tk_app_font(11),
        )
        footer.pack(anchor="w", padx=14, pady=(0, 10))

    def open_output_window(self):
        if self.state.artifact_path:
            self._safe_open_path(Path(self.state.artifact_path))
            return
        if self.state.result_preview is not None:
            self._open_dataframe_window(self.state.result_preview, "DIAD Output")
            return
        if self.state.export_path:
            path = Path(self.state.export_path)
            if path.suffix.lower() in _IMAGE_EXTENSIONS:
                self._safe_open_path(path)
                return
            try:
                self._open_dataframe_window(pd.read_csv(path), "DIAD Output")
            except Exception:
                self._safe_open_path(path)
            return
        messagebox.showinfo("Open Output", "No output is available yet.")

    def download_output_csv(self):
        if self.state.artifact_path:
            source = Path(self.state.artifact_path)
            default_ext = source.suffix or ".png"
            filetypes = [("Image file", f"*{default_ext}"), ("All files", "*.*")]
            title = "Save chart"
        elif self.state.export_path:
            source = Path(self.state.export_path)
            default_ext = ".csv"
            filetypes = [("CSV file", "*.csv"), ("All files", "*.*")]
            title = "Save CSV"
        else:
            messagebox.showinfo("Download", "No output is available yet.")
            return

        target = filedialog.asksaveasfilename(
            title=title,
            defaultextension=default_ext,
            initialfile=source.name,
            filetypes=filetypes,
        )
        if not target:
            return
        try:
            shutil.copy2(source, target)
            self.status.configure(text=f"Saved to {target}", text_color=SUCCESS)
        except Exception as exc:
            messagebox.showinfo("Download", f"Could not save file:\n{exc}")

    def open_schema_window(self):
        lines = []
        for table in sorted(self.state.schema_map.keys()):
            lines.append(f"{table}")
            for col, dtype in self._iter_columns(table):
                lines.append(f"  - {col}: {dtype}")
            lines.append("")
        self._open_text_window("Schema", "\n".join(lines).strip() or "No schema loaded.")

    def open_categories_window(self):
        lines = []
        for key, values in sorted((self.state.categorical_index or {}).items(), key=lambda item: str(item[0])):
            try:
                table, column = key
            except Exception:
                table, column = "", str(key)
            lines.append(f"{table}.{column}")
            for value in list(values)[:50]:
                lines.append(f"  - {value}")
            lines.append("")
        self._open_text_window("Categories", "\n".join(lines).strip() or "No categorical values loaded.")

    def open_sql_window(self):
        self._open_text_window("Latest SQL", self.state.generated_sql or "No SQL generated yet.")

    def open_tips_window(self):
        tips = """Try prompts like:

- What columns are in this project?
- Show users where status is Active
- Sort employees by salary descending
- Count records by department
- Average salary by team
- Make a bar chart of employees by department

Tips:
- Use the Data Guide when you are unsure of exact column names.
- Double-click a table, column, or value to insert it into the chat box.
- Turn on DIAD_DEBUG_MESSAGES=1 before running the app if you want routing and SQL repair details."""
        self._open_text_window("Tips", tips)

    def _open_text_window(self, title: str, text: str):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("780x560")
        win.configure(bg=APP_BG)
        box = tk.Text(
            win,
            bg=SURFACE_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            font=tk_app_font(12),
            padx=12,
            pady=12,
        )
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _handle_auto_open_artifact(self):
        path = self.state.auto_open_artifact_path
        if not path:
            return
        path = Path(path)
        if self._last_auto_open_path == path:
            return
        self._last_auto_open_path = path
        self._safe_open_path(path)

    def render(self):
        project_name = self.state.current_project_name or "No project open"
        self.project_label.configure(text=project_name)
        self.project_path_label.configure(text=str(self.state.current_project_path or ""))

        self._render_files()
        self._render_messages()
        self.refresh_schema_tree()
        self._render_output_status()
        self._set_busy_controls(self.state.is_busy)
        self._handle_auto_open_artifact()

        table_count, column_count = self._table_column_counts()
        if self.state.is_busy:
            self.status.configure(text=self.state.status_message or "Working...", text_color=WARNING)
        elif self.state.error:
            self.status.configure(text=f"Error: {self.state.error}", text_color=ERROR)
        else:
            self.status.configure(text=f"Ready • {table_count} table(s), {column_count} column(s)", text_color=MUTED)


if __name__ == "__main__":
    app = TkApp()
    app.mainloop()