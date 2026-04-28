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
except ImportError:
    Image = None
    ImageTk = None
from tkinterdnd2 import DND_FILES, TkinterDnD

from UI.controller import Controller
from UI.state import AppState


_ALLOWED_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx *.json"),
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx"),
    ("JSON files", "*.json"),
]
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Dark UI palette with DIAD's red kept as the main brand accent.
# The red is softer than the original so the app still feels polished instead of harsh.
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
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color=TEXT,
    )


def section_subtitle(parent, text: str, wraplength: int = 320):
    return ctk.CTkLabel(
        parent,
        text=text,
        font=ctk.CTkFont(size=13),
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
        command=command,
    )


class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_pointerx() + 12
        y = self.widget.winfo_pointery() + 12
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip,
            text=self.text,
            bg="#FFF3F5",
            fg="#121114",
            relief="solid",
            borderwidth=1,
            justify="left",
            padx=8,
            pady=6,
            font=("Arial", 10),
        )
        label.pack()

    def hide(self, event=None):
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
        font=("Arial", 10, "bold"),
        fg=MUTED_2,
        bg=parent_bg,
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
    """Destroy child widgets safely during re-render cycles."""
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


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


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

        # Important: do NOT use self.state, because Tk/CTk already has a state() method.
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
            bordercolor=BORDER_SOFT,
            borderwidth=0,
        )
        style.map("Dark.Treeview", background=[("selected", ACCENT_SOFT)])
        style.configure(
            "Dark.Treeview.Heading",
            background=SURFACE,
            foreground=TEXT,
            relief="flat",
        )
        style.map("Dark.Treeview.Heading", background=[("active", SURFACE_3)])

    def _prepare_logo_pil(self, square: bool = False):
        if not self.logo_path or Image is None:
            return None

        try:
            img = Image.open(self.logo_path).convert("RGBA")

            # The source logo has transparency and dark lettering, so crop the
            # transparent padding and composite it onto white. This makes the
            # logo visible on DIAD's dark UI and gives the app icon a clean
            # white background.
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
            return ctk.CTkImage(
                light_image=logo,
                dark_image=logo,
                size=size,
            )
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
        """Schedule UI refreshes on Tk's main thread.

        Controller work runs in background threads, so calling render directly
        from the controller can randomly break CustomTkinter widgets while they
        are drawing or being destroyed.
        """
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

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 18))
        header.grid_columnconfigure(0, weight=0)
        header.grid_columnconfigure(1, weight=1)

        if self.app.logo_image_large is not None:
            self.upload_logo_holder = ctk.CTkFrame(
                header,
                fg_color="#FFFFFF",
                corner_radius=16,
                width=214,
                height=118,
            )
            self.upload_logo_holder.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 16))
            self.upload_logo_holder.grid_propagate(False)
            self.upload_logo_label = ctk.CTkLabel(
                self.upload_logo_holder,
                text="",
                image=self.app.logo_image_large,
                fg_color="#FFFFFF",
            )
            self.upload_logo_label.place(relx=0.5, rely=0.5, anchor="center")
            brand_col = 1
        else:
            brand_col = 0

        brand_text = ctk.CTkFrame(header, fg_color="transparent")
        brand_text.grid(row=0, column=brand_col, sticky="ew")
        brand_text.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            brand_text,
            text="DIAD",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            brand_text,
            text="Create a project, add your files, and start chatting with your data.",
            font=ctk.CTkFont(size=14),
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
            "Create a project by giving it a name and adding one or more CSV/XLSX/JSON files.",
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
        self.status_label = ctk.CTkLabel(bottom_row, text="", text_color=MUTED, anchor="w")
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
        self._progress_running = False

        self.projects_frame = glass_panel(body)
        self.projects_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.projects_frame.grid_columnconfigure(0, weight=1)
        self.projects_frame.grid_rowconfigure(3, weight=1)
        add_corner_help(self.projects_frame, "Open an existing project you already created.")

        section_title(self.projects_frame, "Existing Projects").grid(row=0, column=0, sticky="w", padx=22, pady=(22, 4))
        section_subtitle(self.projects_frame, "Pick a project to continue where you left off.", 440).grid(
            row=1, column=0, sticky="w", padx=22, pady=(0, 16)
        )

        project_actions = ctk.CTkFrame(self.projects_frame, fg_color="transparent")
        project_actions.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        project_actions.grid_columnconfigure(0, weight=1)
        self.project_count_label = ctk.CTkLabel(project_actions, text="0 available", text_color=MUTED, anchor="w")
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

    def _render_pending_files(self):
        clear_children(self.pending_frame)

        if not self.pending_files:
            ctk.CTkLabel(
                self.pending_frame,
                text="No files selected yet. Drop CSV/XLSX/JSON files here.",
                text_color=MUTED,
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
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, rowspan=2, padx=10, pady=10)
            ctk.CTkLabel(card, text=path.name, text_color=TEXT, anchor="w").grid(
                row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0)
            )
            ctk.CTkLabel(card, text=str(path.parent), text_color=MUTED_2, anchor="w").grid(
                row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10)
            )

    def _render_projects(self):
        clear_children(self.projects_scroll)

        self.project_count_label.configure(text=f"{len(self.project_records)} available")
        if not self.project_records:
            ctk.CTkLabel(self.projects_scroll, text="No projects yet.", text_color=MUTED).pack(anchor="w", padx=8, pady=8)
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
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=TEXT,
                anchor="w",
            )
            name_label.grid(row=0, column=1, sticky="ew", pady=(10, 2), padx=(0, 10))

            meta_label = ctk.CTkLabel(card, text=meta, text_color=MUTED, anchor="w")
            meta_label.grid(row=1, column=1, sticky="ew", pady=(0, 10), padx=(0, 10))

            delete_btn = ctk.CTkButton(
                card,
                text="Delete",
                width=72,
                height=28,
                corner_radius=10,
                fg_color=DANGER,
                hover_color=DANGER_HOVER,
                text_color=ACCENT_TEXT,
                command=lambda p=path: self.on_delete_project(p),
            )
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

    def _add_pending_files(self, raw_paths: list[str | Path]):
        existing = {p.resolve() for p in self.pending_files}
        for raw in raw_paths:
            p = Path(raw).expanduser().resolve()
            if not p.exists() or not p.is_file():
                continue
            if p.suffix.lower() not in {".csv", ".xlsx", ".json"}:
                continue
            if p.resolve() in existing:
                continue
            self.pending_files.append(p)
            existing.add(p.resolve())
        self.render()

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
            return value

    def _show_progress(self, visible: bool):
        if not hasattr(self, "progress_bar"):
            return
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

        # Internal drag/drop state for the Data Guide.
        # This is not OS-level file drag/drop. It lets users drag table names,
        # column names, and categorical values into the chat/search boxes.
        self.drag_payload: dict[str, str] | None = None
        self._drag_start_xy: tuple[int, int] | None = None
        self._drag_started = False
        self._drag_ghost: tk.Toplevel | None = None

        self._build_layout()

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        # Sidebar
        self.sidebar = glass_panel(self, width=278)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10), pady=0)
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        add_corner_help(
            self.sidebar,
            "This sidebar shows the current project and its files. Use it to go back, add files, or inspect schema details.",
        )

        if self.app.logo_image_medium is not None:
            self.sidebar_logo_holder = ctk.CTkFrame(
                self.sidebar,
                fg_color="#FFFFFF",
                corner_radius=14,
                width=168,
                height=92,
            )
            self.sidebar_logo_holder.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 10))
            self.sidebar_logo_holder.grid_propagate(False)
            self.sidebar_logo_label = ctk.CTkLabel(
                self.sidebar_logo_holder,
                text="",
                image=self.app.logo_image_medium,
                fg_color="#FFFFFF",
            )
            self.sidebar_logo_label.place(relx=0.5, rely=0.5, anchor="center")
            logo_text_row = 1
        else:
            logo_text_row = 0

        self.sidebar.grid_rowconfigure(logo_text_row + 7, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="Project",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT,
        ).grid(row=logo_text_row, column=0, sticky="w", padx=16, pady=(0, 6))

        self.project_label = ctk.CTkLabel(
            self.sidebar,
            text="No project open",
            text_color=TEXT,
            wraplength=230,
            justify="left",
            anchor="w",
        )
        self.project_label.grid(row=logo_text_row + 1, column=0, sticky="ew", padx=16)

        self.project_path_label = ctk.CTkLabel(
            self.sidebar,
            text="",
            text_color=MUTED,
            wraplength=230,
            justify="left",
            anchor="w",
        )
        self.project_path_label.grid(row=logo_text_row + 2, column=0, sticky="ew", padx=16, pady=(6, 14))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.grid(row=logo_text_row + 3, column=0, sticky="ew", padx=16)
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
        self.btn_view_sql.grid(row=4, column=0, sticky="ew")

        files_section = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        files_section.grid(row=logo_text_row + 7, column=0, sticky="nsew", padx=16, pady=(14, 16))
        files_section.grid_rowconfigure(1, weight=1)
        files_section.grid_columnconfigure(0, weight=1)

        files_header = ctk.CTkFrame(files_section, fg_color="transparent")
        files_header.grid(row=0, column=0, sticky="ew")
        files_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            files_header,
            text="Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.file_count_label_main = ctk.CTkLabel(files_header, text="0 loaded", text_color=MUTED_2)
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
            "These are the files stored inside the current project. You can drag CSV, XLSX, or JSON files here to add them.",
            x=-6,
            y=6,
        )
        self._enable_drop_target(self.files_scroll, self.on_project_files_drop)

        # Chat card
        self.chat_card = glass_panel(self)
        self.chat_card.grid(row=0, column=1, sticky="nsew", padx=10, pady=0)
        self.chat_card.grid_columnconfigure(0, weight=1)
        self.chat_card.grid_rowconfigure(1, weight=1)
        add_corner_help(
            self.chat_card,
            "Ask questions about your project data here. Output actions show up when DIAD creates a result table.",
        )

        title_wrap = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        title_wrap.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            title_wrap,
            text="Chat with your data",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=TEXT,
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        self.result_hint = ctk.CTkLabel(title_wrap, text="", text_color=MUTED)
        self.result_hint.grid(row=1, column=0, sticky="w", pady=(4, 0))

        if self.app.logo_image_small is not None:
            self.chat_logo_holder = ctk.CTkFrame(
                title_wrap,
                fg_color="#FFFFFF",
                corner_radius=10,
                width=102,
                height=58,
            )
            self.chat_logo_holder.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
            self.chat_logo_holder.grid_propagate(False)
            self.chat_logo_label = ctk.CTkLabel(
                self.chat_logo_holder,
                text="",
                image=self.app.logo_image_small,
                fg_color="#FFFFFF",
            )
            self.chat_logo_label.place(relx=0.5, rely=0.5, anchor="center")


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
        self.output_summary_label = ctk.CTkLabel(toolbar, text="No output yet", text_color=MUTED, anchor="w")
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
        )
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.on_send())
        self.btn_edit_last_query = small_button(composer, "Edit Last", self.edit_last_query, width=104)
        self.btn_edit_last_query.grid(row=0, column=1, padx=(8, 0))
        self.btn_send = primary_button(composer, "Send", self.on_send, width=96)
        self.btn_send.grid(row=0, column=2, padx=(8, 0))

        self.status = ctk.CTkLabel(self.chat_card, text="Ready", text_color=MUTED)
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
        self._progress_running = False

        # Data guide
        self.guide_card = glass_panel(self, width=340)
        self.guide_card.grid(row=0, column=2, sticky="nse", padx=(10, 0), pady=0)
        self.guide_card.grid_propagate(False)
        self.guide_card.grid_columnconfigure(0, weight=1)
        self.guide_card.grid_rowconfigure(3, weight=1)
        self.guide_card.grid_rowconfigure(7, weight=1)
        add_corner_help(
            self.guide_card,
            "Use the Data Guide to see table names and headers before you ask a question.",
        )

        section_title(self.guide_card, "Data Guide").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        section_subtitle(
            self.guide_card,
            "Browse tables, headers, and sample values. Drag or double-click an item to add it to the chat box.",
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
        )
        self.schema_search.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        tree_wrap = glass_panel(self.guide_card, fg_color=SURFACE_2, corner_radius=14)
        tree_wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        self.schema_tree = ttk.Treeview(tree_wrap, show="tree", style="Dark.Treeview")
        self.schema_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.schema_tree.bind("<<TreeviewSelect>>", lambda e: self.show_schema_details())
        self.schema_tree.bind("<Double-Button-1>", self.on_schema_tree_double_click)
        self.schema_tree.bind("<ButtonPress-1>", self.on_schema_tree_press, add="+")
        self.schema_tree.bind("<B1-Motion>", self.on_schema_tree_motion)
        self.schema_tree.bind("<ButtonRelease-1>", self.on_schema_tree_release, add="+")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.schema_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.schema_tree.configure(yscrollcommand=tree_scroll.set)

        detail_header = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        detail_header.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        detail_header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            detail_header,
            text="Selected item",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        self.schema_summary_label = ctk.CTkLabel(detail_header, text="Nothing selected", text_color=MUTED_2)
        self.schema_summary_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        copy_row = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        copy_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))
        copy_row.grid_columnconfigure((0, 1), weight=1)
        self.btn_copy_table = small_button(copy_row, "Copy table", self.copy_selected_table, width=120)
        self.btn_copy_table.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_copy_column = small_button(copy_row, "Copy column", self.copy_selected_column, width=120)
        self.btn_copy_column.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self._update_schema_copy_buttons()

        self.schema_chip_area = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        self.schema_chip_area.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.schema_chip_area.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.schema_chip_area,
            text="Quick insert",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=MUTED_2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.schema_chip_frame = ctk.CTkFrame(self.schema_chip_area, fg_color="transparent")
        self.schema_chip_frame.grid(row=1, column=0, sticky="ew")
        self.schema_chip_frame.grid_columnconfigure((0, 1), weight=1)

        self.schema_detail = ctk.CTkTextbox(
            self.guide_card,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
            text_color=TEXT,
            wrap="word",
        )
        self.schema_detail.grid(row=7, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.schema_detail.configure(state="disabled")

    def _enable_drop_target(self, widget, callback):
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

        return self._make_schema_payload(
            table=table,
            column=column or None,
            value=value or None,
            kind=kind,
        )

    def _schema_payload_from_event(self, event) -> dict[str, str] | None:
        item_id = self.schema_tree.identify_row(event.y)
        return self._schema_payload_from_tree_item(item_id)

    def _clear_schema_chips(self):
        if not hasattr(self, "schema_chip_frame"):
            return
        clear_children(self.schema_chip_frame)

    def _bind_schema_chip(self, chip, payload: dict[str, str]):
        try:
            chip.configure(cursor="hand2")
        except Exception:
            pass
        chip.bind("<ButtonPress-1>", lambda event, p=payload: self.on_schema_chip_press(event, p), add="+")
        chip.bind("<B1-Motion>", self.on_schema_chip_motion, add="+")
        chip.bind("<ButtonRelease-1>", self.on_schema_chip_release, add="+")

    def _render_schema_chips(self, payloads: list[dict[str, str]]):
        self._clear_schema_chips()
        if not hasattr(self, "schema_chip_frame"):
            return

        if not payloads:
            chip = ctk.CTkLabel(
                self.schema_chip_frame,
                text="Select an item to show draggable chips.",
                text_color=MUTED_2,
                anchor="w",
            )
            chip.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
            return

        for idx, payload in enumerate(payloads[:10]):
            label_text = payload.get("display", "item")
            if len(label_text) > 28:
                label_text = label_text[:25] + "..."

            chip = ctk.CTkFrame(
                self.schema_chip_frame,
                fg_color=ACCENT_SOFT,
                border_width=1,
                border_color=BORDER_SOFT,
                corner_radius=18,
            )
            chip.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=(0, 6), pady=(0, 6))

            label = ctk.CTkLabel(
                chip,
                text=label_text,
                text_color=TEXT,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="center",
                wraplength=125,
            )
            label.pack(fill="both", expand=True, padx=10, pady=5)

            self._bind_schema_chip(chip, payload)
            self._bind_schema_chip(label, payload)

    def _start_schema_drag(self, payload: dict[str, str] | None, event):
        self.drag_payload = payload
        self._drag_start_xy = (event.x_root, event.y_root)
        self._drag_started = False

    def on_schema_chip_press(self, event, payload: dict[str, str]):
        self._start_schema_drag(payload, event)
        return "break"

    def on_schema_chip_motion(self, event):
        return self.on_schema_tree_motion(event)

    def on_schema_chip_release(self, event):
        if not self.drag_payload:
            return "break"

        if not self._drag_started:
            payload = self.drag_payload
            self._insert_text_into_chat_entry(payload.get("insert_text", ""))
            self.status.configure(text=f"Added: {payload.get('display', 'item')}", text_color=SUCCESS)
            self._reset_schema_drag()
            return "break"

        return self.on_schema_tree_release(event)

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

    def _widget_is_or_contains(self, widget, possible_parent) -> bool:
        while widget is not None:
            if widget == possible_parent:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _drop_target_for_pointer(self, event) -> str | None:
        target = self.winfo_containing(event.x_root, event.y_root)
        if target is None:
            return None
        if self._widget_is_or_contains(target, self.chat_entry):
            return "chat"
        if self._widget_is_or_contains(target, self.schema_search):
            return "schema_search"
        return None

    def _create_drag_ghost(self, text: str, x: int, y: int):
        self._destroy_drag_ghost()
        self._drag_ghost = tk.Toplevel(self)
        self._drag_ghost.wm_overrideredirect(True)
        self._drag_ghost.wm_attributes("-topmost", True)
        self._drag_ghost.configure(bg=APP_BG)

        bubble = ctk.CTkFrame(
            self._drag_ghost,
            fg_color=ACCENT,
            border_width=1,
            border_color=ACCENT_HOVER,
            corner_radius=18,
        )
        bubble.pack()
        ctk.CTkLabel(
            bubble,
            text=text,
            text_color=ACCENT_TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=12, pady=6)
        self._move_drag_ghost(x, y)

    def _move_drag_ghost(self, x: int, y: int):
        if self._drag_ghost is not None:
            self._drag_ghost.wm_geometry(f"+{x + 12}+{y + 12}")

    def _destroy_drag_ghost(self):
        if self._drag_ghost is not None:
            try:
                self._drag_ghost.destroy()
            except Exception:
                pass
        self._drag_ghost = None

    def _reset_schema_drag(self):
        self._destroy_drag_ghost()
        self.drag_payload = None
        self._drag_start_xy = None
        self._drag_started = False

    def on_schema_tree_press(self, event):
        self._start_schema_drag(self._schema_payload_from_event(event), event)

    def on_schema_tree_motion(self, event):
        if not self.drag_payload or not self._drag_start_xy:
            return

        start_x, start_y = self._drag_start_xy
        distance = abs(event.x_root - start_x) + abs(event.y_root - start_y)
        if not self._drag_started and distance < 8:
            return

        if not self._drag_started:
            self._drag_started = True
            self._create_drag_ghost(self.drag_payload.get("display", "item"), event.x_root, event.y_root)
            self.status.configure(text="Drop into the chat box, or drop into Data Guide search to filter.", text_color=WARNING)
        else:
            self._move_drag_ghost(event.x_root, event.y_root)

    def on_schema_tree_release(self, event):
        if not self.drag_payload:
            return

        if not self._drag_started:
            self._reset_schema_drag()
            return

        target = self._drop_target_for_pointer(event)
        if target == "chat":
            self._insert_text_into_chat_entry(self.drag_payload.get("insert_text", ""))
            self.status.configure(text=f"Added: {self.drag_payload.get('display', 'item')}", text_color=SUCCESS)
        elif target == "schema_search":
            self._set_schema_search_text(self.drag_payload.get("search_text", ""))
            self.status.configure(text=f"Searching: {self.drag_payload.get('search_text', '')}", text_color=SUCCESS)
        else:
            self.status.configure(text="Drag canceled", text_color=MUTED)

        self._reset_schema_drag()
        return "break"

    def on_schema_tree_double_click(self, event):
        payload = self._schema_payload_from_event(event)
        if not payload:
            return
        self._insert_text_into_chat_entry(payload.get("insert_text", ""))
        self.status.configure(text=f"Added: {payload.get('display', 'item')}", text_color=SUCCESS)
        return "break"

    def fill_suggestion(self, text: str):
        self.chat_entry.delete(0, tk.END)
        self.chat_entry.insert(0, text)
        self.chat_entry.focus_set()

    def _table_column_counts(self) -> tuple[int, int]:
        table_count = len(self.state.schema_map)
        column_count = sum(len(cols) for cols in self.state.schema_map.values())
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
            ctk.CTkLabel(self.files_scroll, text="No files loaded.", text_color=MUTED).pack(anchor="w", padx=8, pady=8)
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
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            badge.grid(row=0, column=0, rowspan=3, padx=10, pady=8)

            name_label = ctk.CTkLabel(card, text=path.name, text_color=TEXT, anchor="w", wraplength=160)
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
            )
            meta_label.grid(row=1, column=1, sticky="ew", pady=(1, 2), padx=(0, 10))

            hint_label = ctk.CTkLabel(
                card,
                text="Double-click to preview",
                text_color=MUTED_2,
                anchor="w",
                font=ctk.CTkFont(size=11),
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
        # CTkScrollableFrame can keep an old scroll position when its children are
        # destroyed and rebuilt. Reset first so the canvas never shows a blank
        # lower portion while the new message bubbles are being laid out.
        try:
            self.chat_history._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

        clear_children(self.chat_history)

        messages = list(self.state.messages)
        if not messages:
            empty = ctk.CTkLabel(
                self.chat_history,
                text="Ask a question to get started.",
                text_color=MUTED,
                anchor="w",
                justify="left",
            )
            empty.pack(anchor="w", padx=14, pady=14)
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
            bubble.pack(
                anchor="e" if is_user else "w",
                padx=(92, 4) if is_user else (4, 92),
            )

            ctk.CTkLabel(
                bubble,
                text="You" if is_user else "DIAD",
                text_color=ACCENT_TEXT if is_user else MUTED_2,
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w",
            ).pack(anchor="w", padx=13, pady=(9, 0))

            ctk.CTkLabel(
                bubble,
                text=content,
                text_color=ACCENT_TEXT if is_user else TEXT,
                font=ctk.CTkFont(size=13),
                justify="left",
                anchor="w",
                wraplength=bubble_wrap,
            ).pack(anchor="w", padx=13, pady=(3, 10))

        self._scroll_chat_to_latest_message()

    def _scroll_chat_to_latest_message(self):
        """Scroll to the newest bubble after the scrollregion has settled.

        Without this delay, CustomTkinter sometimes keeps the old scrollregion
        from the previous render, which creates the blank black area at the
        bottom of the chat until you manually scroll up.
        """

        def do_scroll():
            try:
                self.chat_history.update_idletasks()
                canvas = self.chat_history._parent_canvas
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.yview_moveto(1.0)
            except Exception:
                pass

        self.after_idle(do_scroll)
        self.after(80, do_scroll)
        self.after(180, do_scroll)

    def refresh_schema_tree(self):
        if not hasattr(self, "schema_tree"):
            return

        query = self.schema_search_var.get().strip().lower()
        self.schema_tree.delete(*self.schema_tree.get_children())

        for table, columns in sorted(self.state.schema_map.items()):
            table_matches = not query or query in table.lower()
            inserted_table = False
            table_id = ""

            for column in sorted(columns.keys()):
                values = [str(value) for value in self.state.categorical_index.get((table, column), [])]
                matching_values = [value for value in values if query and query in value.lower()]
                value_matches = bool(matching_values)
                column_matches = not query or query in column.lower() or value_matches

                if table_matches or column_matches:
                    if not inserted_table:
                        table_id = self.schema_tree.insert(
                            "",
                            "end",
                            text=table,
                            open=True,
                            values=(table, "", "table", ""),
                        )
                        inserted_table = True

                    column_id = self.schema_tree.insert(
                        table_id,
                        "end",
                        text=column,
                        open=bool(query and value_matches),
                        values=(table, column, "column", ""),
                    )

                    values_to_show = matching_values if query and value_matches else values[:8]
                    for value in values_to_show[:12]:
                        self.schema_tree.insert(
                            column_id,
                            "end",
                            text=f"↳ {value}",
                            values=(table, column, "value", value),
                        )

        self.show_schema_details(clear_only=True)

    def show_schema_details(self, clear_only: bool = False):
        if not hasattr(self, "schema_detail"):
            return

        selected = self.schema_tree.selection()
        if clear_only and not selected:
            self._set_schema_detail(
                "Select a table, column, or value to see more detail.\n\n"
                "Tip: drag or double-click an item to add it to the chat box."
            )
            self.schema_summary_label.configure(text=self._schema_counts_text())
            self.selected_schema_item = None
            self.selected_schema_kind = None
            self._update_schema_copy_buttons()
            self._render_schema_chips([])
            return

        if not selected:
            self._set_schema_detail(
                "Select a table, column, or value to see more detail.\n\n"
                "Tip: drag or double-click an item to add it to the chat box."
            )
            self.schema_summary_label.configure(text=self._schema_counts_text())
            self.selected_schema_item = None
            self.selected_schema_kind = None
            self._update_schema_copy_buttons()
            self._render_schema_chips([])
            return

        item = selected[0]
        values = list(self.schema_tree.item(item, "values") or [])
        table = str(values[0]) if len(values) > 0 and values[0] else self.schema_tree.item(item, "text")
        column = str(values[1]) if len(values) > 1 and values[1] else None
        kind = str(values[2]) if len(values) > 2 and values[2] else ("column" if column else "table")
        value = str(values[3]) if len(values) > 3 and values[3] else None
        self.selected_schema_item = (table, column, value if kind == "value" else None)
        self.selected_schema_kind = kind
        self._update_schema_copy_buttons()

        if kind == "table" or column is None:
            columns = list(self.state.schema_map.get(table, {}).keys())
            text = [f"Table: {table}", "", f"Columns: {len(columns)}", ""]
            text.append("Double-click or drag this table into the chat box to reference it.")
            text.append("")
            for col in columns:
                text.append(f"- {col}")
            chip_payloads = [self._make_schema_payload(table=table, kind="table")]
            self.schema_summary_label.configure(text=f"table • {len(columns)} columns")
            self._render_schema_chips(chip_payloads)
        elif kind == "value" and value is not None:
            dtype = self.state.schema_map.get(table, {}).get(column, "unknown")
            insert_text = self.controller.format_schema_insert_text(table=table, column=column, value=value)
            text = [
                f"Table: {table}",
                f"Column: {column}",
                f"Type: {dtype}",
                f"Value: {value}",
                "",
                "Double-click or drag this value into the chat box to add:",
                insert_text,
            ]
            chip_payloads = [
                self._make_schema_payload(table=table, column=column, kind="column"),
                self._make_schema_payload(table=table, column=column, value=value, kind="value"),
            ]
            self.schema_summary_label.configure(text=f"value • {column}")
            self._render_schema_chips(chip_payloads)
        else:
            dtype = self.state.schema_map.get(table, {}).get(column, "unknown")
            samples = [str(value) for value in self.state.categorical_index.get((table, column), [])]
            text = [f"Table: {table}", f"Column: {column}", f"Type: {dtype}", ""]
            text.append("Double-click or drag this column into the chat box to reference it.")
            text.append("")
            if samples:
                text.append("Sample values shown under this column in the tree:")
                for sample in samples[:12]:
                    text.append(f"- {sample}")
            else:
                text.append("No sample values available for this column.")
            chip_payloads = [self._make_schema_payload(table=table, column=column, kind="column")]
            chip_payloads.extend(
                self._make_schema_payload(table=table, column=column, value=sample, kind="value")
                for sample in samples[:7]
            )
            self.schema_summary_label.configure(text=f"column • {dtype}")
            self._render_schema_chips(chip_payloads)

        self._set_schema_detail("\n".join(text))

    def _schema_counts_text(self) -> str:
        table_count, column_count = self._table_column_counts()
        return f"{table_count} tables • {column_count} columns"

    def _set_schema_detail(self, text: str):
        self.schema_detail.configure(state="normal")
        self.schema_detail.delete("1.0", tk.END)
        self.schema_detail.insert(tk.END, text)
        self.schema_detail.configure(state="disabled")

    def _update_schema_copy_buttons(self):
        if not hasattr(self, "btn_copy_table") or not hasattr(self, "btn_copy_column"):
            return

        has_selection = self.selected_schema_item is not None
        table, column, _value = self.selected_schema_item if has_selection else (None, None, None)

        # Copy table can be used for any selected table/column/value because each item belongs to a table.
        self.btn_copy_table.configure(state="normal" if table else "disabled")

        # Copy column should only be clickable for real column/value selections.
        # When a table is selected, column is None, so this stays disabled and cannot copy the table/file text by mistake.
        column_selected = bool(column) and self.selected_schema_kind in {"column", "value"}
        self.btn_copy_column.configure(state="normal" if column_selected else "disabled")

    def copy_selected_table(self):
        if not self.selected_schema_item:
            self.status.configure(text="Select a table, column, or value first.", text_color=MUTED)
            return
        table, _column, _value = self.selected_schema_item
        if not table:
            self.status.configure(text="Select a table, column, or value first.", text_color=MUTED)
            return
        self.clipboard_clear()
        self.clipboard_append(table)
        self.status.configure(text=f"Copied table: {table}", text_color=SUCCESS)

    def copy_selected_column(self):
        if not self.selected_schema_item:
            self.status.configure(text="Select a column first.", text_color=MUTED)
            return
        _table, column, _value = self.selected_schema_item
        if not column or self.selected_schema_kind not in {"column", "value"}:
            self.status.configure(text="Select a column first.", text_color=MUTED)
            self._update_schema_copy_buttons()
            return
        self.clipboard_clear()
        self.clipboard_append(column)
        self.status.configure(text=f"Copied column: {column}", text_color=SUCCESS)

    def _last_user_query(self) -> str | None:
        for msg in reversed(self.state.messages):
            if msg.get("role") == "user":
                text = str(msg.get("content", "")).strip()
                if text:
                    return text
        return None

    def edit_last_query(self):
        text = self._last_user_query()
        if not text or self.state.is_busy:
            return
        self.chat_entry.configure(state="normal")
        self.chat_entry.delete(0, tk.END)
        self.chat_entry.insert(0, text)
        self.chat_entry.focus_set()
        try:
            self.chat_entry.select_range(0, tk.END)
        except Exception:
            pass
        self.status.configure(text="Last query loaded. Edit it and press Send.", text_color=SUCCESS)

    def on_send(self):
        text = self.chat_entry.get().strip()
        if not text or self.state.is_busy:
            return
        self.chat_entry.delete(0, tk.END)
        self.controller.send_chat(text)

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

    def open_schema_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Schema")
        win.geometry("720x520")
        win.configure(fg_color=APP_BG)
        text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
        text.pack(fill="both", expand=True, padx=14, pady=14)
        lines: list[str] = []
        for table, cols in self.state.schema_map.items():
            lines.append(table)
            for col, dtype in cols.items():
                lines.append(f"  - {col}: {dtype}")
            lines.append("")
        text.insert(tk.END, "\n".join(lines) if lines else "No schema loaded.")
        text.configure(state="disabled")

    def open_categories_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Categories")
        win.geometry("720x520")
        win.configure(fg_color=APP_BG)
        text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
        text.pack(fill="both", expand=True, padx=14, pady=14)
        lines: list[str] = []
        for (table, col), values in sorted(self.state.categorical_index.items()):
            lines.append(f"{table}.{col}")
            for value in values[:50]:
                lines.append(f"  - {value}")
            lines.append("")
        text.insert(tk.END, "\n".join(lines) if lines else "No categorical values loaded.")
        text.configure(state="disabled")

    def open_sql_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Latest SQL")
        win.geometry("760x480")
        win.configure(fg_color=APP_BG)
        text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
        text.pack(fill="both", expand=True, padx=14, pady=14)
        text.insert(tk.END, self.state.generated_sql or "No SQL generated yet.")
        text.configure(state="disabled")

    def open_file_external(self, file_path: str | Path):
        path = Path(file_path)
        if not path.exists():
            messagebox.showerror("Open File", f"File not found:\n{path}")
            return

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])

            self.status.configure(text=f"Opened {path.name}", text_color=SUCCESS)
        except Exception as exc:
            messagebox.showerror("Open File", str(exc))

    def open_file_preview(self, file_path: str | Path):
        path = Path(file_path)
        if not path.exists():
            messagebox.showerror("File Preview", f"File not found:\n{path}")
            return

        win = ctk.CTkToplevel(self)
        win.title(f"File Preview - {path.name}")
        win.geometry("980x620")
        win.configure(fg_color=APP_BG)
        win.grid_rowconfigure(2, weight=1)
        win.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(win, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=path.name,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        table = self._guess_table_for_file(path)
        meta = self._format_file_card_meta(path)
        if table:
            meta += f" • table: {table}"

        ctk.CTkLabel(
            header,
            text=f"{meta}\n{path}",
            text_color=MUTED,
            justify="left",
            anchor="w",
            wraplength=740,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(12, 0))
        small_button(button_row, "Open in app", lambda p=path: self.open_file_external(p), width=120).pack(anchor="e")
        small_button(button_row, "Close", win.destroy, width=120).pack(anchor="e", pady=(8, 0))

        preview_note = ctk.CTkLabel(
            win,
            text="Previewing up to the first 500 rows.",
            text_color=MUTED_2,
            anchor="w",
        )
        preview_note.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        try:
            suffix = path.suffix.lower()
            if suffix == ".csv":
                df = pd.read_csv(path, nrows=500)
                self._render_dataframe_preview(win, df)
                preview_note.configure(text=f"CSV preview • showing {len(df)} row(s)")
            elif suffix == ".xlsx":
                excel = pd.ExcelFile(path)
                sheet_name = excel.sheet_names[0] if excel.sheet_names else 0
                df = pd.read_excel(path, sheet_name=sheet_name, nrows=500)
                self._render_dataframe_preview(win, df)
                preview_note.configure(text=f"XLSX preview • sheet: {sheet_name} • showing {len(df)} row(s)")
            elif suffix == ".json":
                df = self._read_json_preview(path)
                if isinstance(df, pd.DataFrame):
                    self._render_dataframe_preview(win, df.head(500))
                    preview_note.configure(text=f"JSON preview • showing {min(len(df), 500)} row(s)")
                else:
                    pretty = json.dumps(df, indent=2, ensure_ascii=False)
                    self._render_text_preview(win, pretty[:50000])
                    preview_note.configure(text="JSON preview • formatted text")
            else:
                self._render_text_preview(win, f"No preview is available for this file type:\n{path.suffix}")
        except Exception as exc:
            self._render_text_preview(
                win,
                "DIAD could not preview this file.\n\n"
                f"Error:\n{exc}\n\n"
                "You can still use Open in app to open it with your computer's default app.",
            )


    def _read_json_preview(self, path: Path):
        """Return a small DataFrame or parsed JSON object for the preview window."""
        try:
            return pd.read_json(path, lines=True)
        except ValueError:
            pass

        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            if not data:
                return pd.DataFrame()
            if all(isinstance(item, dict) for item in data):
                return pd.json_normalize(data)
            return pd.DataFrame({"value": data})

        if isinstance(data, dict):
            # Common API export shape: {"items": [{...}, {...}]}
            list_keys = [key for key, value in data.items() if isinstance(value, list)]
            for key in list_keys:
                value = data[key]
                if all(isinstance(item, dict) for item in value):
                    return pd.json_normalize(value)
            return data

        return data

    def _render_dataframe_preview(self, parent, df: pd.DataFrame):
        frame = ctk.CTkFrame(parent, fg_color=SURFACE_2)
        frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(frame, style="Dark.Treeview", show="headings")
        tree.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        columns = [str(col) for col in df.columns]
        tree["columns"] = columns

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor="w")

        for _, row in df.iterrows():
            tree.insert("", "end", values=[str(row[col]) for col in df.columns])

    def _render_text_preview(self, parent, text_value: str):
        text = ctk.CTkTextbox(
            parent,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
            text_color=TEXT,
            wrap="word",
        )
        text.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        text.insert(tk.END, text_value)
        text.configure(state="disabled")

    def _image_artifact_path(self) -> Path | None:
        path_value = getattr(self.state, "artifact_path", None)
        if not path_value:
            return None
        path = Path(path_value)
        if path.suffix.lower() not in _IMAGE_EXTENSIONS:
            return None
        if not path.exists():
            return None
        return path

    def open_chart_window(self, image_path: str | Path, auto_open: bool = False):
        path = Path(image_path)
        if not path.exists():
            messagebox.showerror("Open Chart", f"Chart file not found:\n{path}")
            return
        if path.suffix.lower() not in _IMAGE_EXTENSIONS:
            messagebox.showerror("Open Chart", f"This does not look like an image file:\n{path}")
            return

        win = ctk.CTkToplevel(self)
        win.title(f"Chart Preview - {path.name}")
        win.geometry("980x720")
        win.configure(fg_color=APP_BG)
        win.grid_rowconfigure(2, weight=1)
        win.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(win, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        header.grid_columnconfigure(0, weight=1)

        title_text = "Chart opened automatically" if auto_open else "Chart Preview"
        ctk.CTkLabel(
            header,
            text=title_text,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(
            header,
            text=f"{path.name}\n{path}",
            text_color=MUTED,
            justify="left",
            anchor="w",
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(12, 0))
        primary_button(button_row, "Download Chart", lambda p=path: self.download_chart_file(p), width=135).pack(anchor="e")
        small_button(button_row, "Open in app", lambda p=path: self.open_file_external(p), width=135).pack(anchor="e", pady=(8, 0))
        small_button(button_row, "Close", win.destroy, width=135).pack(anchor="e", pady=(8, 0))

        note = ctk.CTkLabel(
            win,
            text="The chart image is shown below. Use Download Chart to save a copy.",
            text_color=MUTED_2,
            anchor="w",
        )
        note.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        body = ctk.CTkFrame(
            win,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER_SOFT,
            corner_radius=14,
        )
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        if Image is None:
            ctk.CTkLabel(
                body,
                text="Pillow is not installed, so DIAD cannot show the image inside this window.\nUse Open in app or Download Chart instead.",
                text_color=TEXT,
                justify="center",
            ).grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
            return

        try:
            image = Image.open(path)
            image.thumbnail((920, 560), Image.Resampling.LANCZOS)
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            image_label = ctk.CTkLabel(body, text="", image=ctk_image)
            image_label.image = ctk_image
            image_label.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        except Exception as exc:
            ctk.CTkLabel(
                body,
                text=f"DIAD could not preview this chart image.\n\nError:\n{exc}",
                text_color=ERROR,
                justify="center",
            ).grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

    def download_chart_file(self, image_path: str | Path | None = None):
        path = Path(image_path) if image_path else self._image_artifact_path()
        if not path or not path.exists():
            messagebox.showinfo("Download Chart", "No chart image is available yet.")
            return

        suffix = path.suffix.lower() or ".png"
        filetypes = [
            ("PNG image", "*.png"),
            ("JPEG image", "*.jpg *.jpeg"),
            ("WebP image", "*.webp"),
            ("GIF image", "*.gif"),
            ("All files", "*.*"),
        ]
        target = filedialog.asksaveasfilename(
            title="Save chart image",
            defaultextension=suffix,
            initialfile=path.name,
            filetypes=filetypes,
        )
        if not target:
            return
        try:
            shutil.copyfile(path, target)
            messagebox.showinfo("Download Chart", f"Saved to:\n{target}")
        except Exception as exc:
            messagebox.showerror("Download Chart", str(exc))

    def open_output_window(self):
        image_path = self._image_artifact_path()
        if image_path is not None:
            self.open_chart_window(image_path)
            return

        if self.state.result_preview is None:
            messagebox.showinfo("Output", "No output table yet.")
            return
        win = ctk.CTkToplevel(self)
        win.title("Output Preview")
        win.geometry("900x560")
        win.configure(fg_color=APP_BG)

        df = self.state.result_preview
        if isinstance(df, pd.DataFrame):
            frame = ctk.CTkFrame(win, fg_color=SURFACE_2)
            frame.pack(fill="both", expand=True, padx=14, pady=14)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            tree = ttk.Treeview(frame, style="Dark.Treeview", show="headings")
            tree.grid(row=0, column=0, sticky="nsew")
            yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            xscroll.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

            tree["columns"] = list(df.columns)
            for col in df.columns:
                tree.heading(col, text=str(col))
                tree.column(col, width=140, anchor="w")
            for _, row in df.head(500).iterrows():
                tree.insert("", "end", values=[str(row[col]) for col in df.columns])
        else:
            text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
            text.pack(fill="both", expand=True, padx=14, pady=14)
            text.insert(tk.END, str(df))
            text.configure(state="disabled")

    def download_output_csv(self):
        image_path = self._image_artifact_path()
        if image_path is not None:
            self.download_chart_file(image_path)
            return

        if not self.state.export_path:
            messagebox.showinfo("Download CSV", "No CSV output available yet.")
            return
        target = filedialog.asksaveasfilename(
            title="Save output CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not target:
            return
        try:
            shutil.copyfile(self.state.export_path, target)
            messagebox.showinfo("Download CSV", f"Saved to:\n{target}")
        except Exception as exc:
            messagebox.showerror("Download CSV", str(exc))

    def _show_progress(self, visible: bool):
        if not hasattr(self, "progress_bar"):
            return
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
        self.project_label.configure(text=self.state.current_project_name or "No project open")
        self.project_path_label.configure(text=str(self.state.current_project_path or ""))
        self.title_label.configure(text=f"Chat with {self.state.current_project_name}" if self.state.current_project_name else "Chat with your data")
        self.result_hint.configure(text=f"Project: {self.state.current_project_name}" if self.state.current_project_name else "")

        self._render_files()
        self._render_messages()
        self.refresh_schema_tree()

        busy = self.state.is_busy
        image_path = self._image_artifact_path()
        has_chart = image_path is not None
        has_output = self.state.result_preview is not None or self.state.export_path is not None or has_chart
        self.btn_send.configure(state="disabled" if busy else "normal")
        last_query_available = self._last_user_query() is not None
        self.btn_edit_last_query.configure(state="normal" if last_query_available and not busy else "disabled")
        self.chat_entry.configure(state="disabled" if busy else "normal")
        self.btn_open_output.configure(state="normal" if has_output and not busy else "disabled")
        self.btn_download_output.configure(state="normal" if ((has_chart or self.state.export_path) and not busy) else "disabled")
        self.btn_open_output.configure(text="Open Chart" if has_chart else "Open Output")
        self.btn_download_output.configure(text="Download Chart" if has_chart else "Download CSV")
        self.btn_add_files.configure(state="disabled" if busy else "normal")

        if busy:
            status_message = getattr(self.state, "status_message", None) or "Running request..."
            self.status.configure(text=status_message, text_color=WARNING)
            self._show_progress(True)
        elif self.state.error:
            self._show_progress(False)
            self.status.configure(text=f"Error: {self.state.error}", text_color=ERROR)
        else:
            self._show_progress(False)
            self.status.configure(text="Ready", text_color=MUTED)

        if has_output:
            if has_chart:
                detail = "Chart ready"
                if isinstance(self.state.result_preview, pd.DataFrame):
                    rows, cols = self.state.result_preview.shape
                    detail += f" • chart data: {rows} rows • {cols} columns"
                self.output_summary_label.configure(text=detail, text_color=SUCCESS)
            elif isinstance(self.state.result_preview, pd.DataFrame):
                rows, cols = self.state.result_preview.shape
                self.output_summary_label.configure(text=f"Output ready • {rows} rows • {cols} columns", text_color=SUCCESS)
            else:
                self.output_summary_label.configure(text="Output ready", text_color=SUCCESS)
        else:
            self.output_summary_label.configure(text="No output yet", text_color=MUTED)

        auto_open_path = getattr(self.state, "auto_open_artifact_path", None)
        if auto_open_path and not busy:
            path = Path(auto_open_path)
            self.state.auto_open_artifact_path = None
            if path.exists() and path.suffix.lower() in _IMAGE_EXTENSIONS:
                self.after_idle(lambda p=path: self.open_chart_window(p, auto_open=True))


def main():
    app = TkApp()
    app.mainloop()


if __name__ == "__main__":
    main()
