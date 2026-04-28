from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import pandas as pd
from tkinterdnd2 import DND_FILES, TkinterDnD

from UI.controller import Controller
from UI.state import AppState

import tkinter.font as tkfont


_ALLOWED_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx"),
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx"),
]

# Older mauve / red color scheme
APP_BG = "#353441"
SURFACE = "#2C2B37"
SURFACE_2 = "#1B1A1D"
SURFACE_3 = "#3F3D4C"
SURFACE_4 = "#4A4757"
BORDER = "#B18B8B"

TEXT = "#F3D8D8"
MUTED = "#D8BDBD"
MUTED_2 = "#B18B8B"

ACCENT = "#EF1A1A"
ACCENT_HOVER = "#AC1717"
ACCENT_TEXT = "#F3D8D8"

SUCCESS = "#F3D8D8"
WARNING = "#B18B8B"
ERROR = "#FF9AA5"

#PROJECT FONT
FONT_FAMILY = "Courier New"
def app_font(size=14, weight="normal"):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)



def glass_panel(parent, **kwargs):
    defaults = {
        "fg_color": SURFACE,
        "border_width": 1,
        "border_color": BORDER,
        "corner_radius": 18,
    }
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def section_title(parent, text: str):
    return ctk.CTkLabel(
        parent,
        text=text,
<<<<<<< Updated upstream
        font=app_font(18, "bold"),
=======
        font=ctk.CTkFont(family="Courier New", size=18, weight="bold"),
>>>>>>> Stashed changes
        text_color=TEXT,
    )


def section_subtitle(parent, text: str, wraplength: int = 320):
    return ctk.CTkLabel(
        parent,
        text=text,
<<<<<<< Updated upstream
        font=app_font(16, "bold"),
=======
        font=ctk.CTkFont(family="Courier New", size=13),
>>>>>>> Stashed changes
        text_color=MUTED,
        wraplength=wraplength,
        justify="left",
    )


<<<<<<< Updated upstream
=======
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
        font=ctk.CTkFont(family="Courier New", size=12, weight="bold")
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
        font=ctk.CTkFont(family="Courier New", size=12, weight="bold")
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
        font=ctk.CTkFont(family="Courier New", size=12, weight="bold")
    )


>>>>>>> Stashed changes
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
            bg="#F3D8D8",
            fg="#1B1A1D",
            relief="solid",
            borderwidth=1,
            justify="left",
            padx=8,
            pady=6,
<<<<<<< Updated upstream
            font=app_font(12, "normal"),
=======
            font=("Courier New", 10),
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
        font=app_font(20, "bold"),
=======
        font=("Courier New", 20, "bold"),
>>>>>>> Stashed changes
        fg=ACCENT_HOVER,
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


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class TkApp(DnDCTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

<<<<<<< Updated upstream
        super().__init__()
=======
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family="Courier New", size=13)

        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family="Courier New", size=13)

        fixed_font = tkfont.nametofont("TkFixedFont")
        fixed_font.configure(family="Courier New", size=13)

        self.APP_FONT = ctk.CTkFont(family="Courier New", size=13)
        self.APP_FONT_BOLD = ctk.CTkFont(family="Courier New", size=13, weight="bold")
        self.APP_FONT_SMALL = ctk.CTkFont(family="Courier New", size=11)

>>>>>>> Stashed changes
        self.title("DIAD")
        self.geometry("1440x880")
        self.minsize(1180, 760)
        self.configure(fg_color=APP_BG)

        # Important: do NOT use self.state, because Tk/CTk already has a state() method
        self.app_state = AppState()
        self.controller = Controller(self.app_state, self.render)

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

        default_font = tkfont.nametofont("TkDefaultFont") #Setting default font
        default_font.configure(family="Courier New", size=14)

        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family="Courier New", size=14)

        fixed_font = tkfont.nametofont("TkFixedFont")
        fixed_font.configure(family="Courier New", size=14)
    

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
            bordercolor=BORDER,
            borderwidth=0,
            font=("Courier New", 13) 
        )
<<<<<<< Updated upstream
        style.map("Dark.Treeview", background=[("selected", SURFACE_4)])
=======

        style.map("Dark.Treeview", background=[("selected", ACCENT_SOFT)])

>>>>>>> Stashed changes
        style.configure(
            "Dark.Treeview.Heading",
            background=SURFACE,
            foreground=TEXT,
            relief="flat",
            font=("Courier New", 13, "bold") 
        )

        style.map("Dark.Treeview.Heading", background=[("active", SURFACE_3)])

    def show_page(self, page_class):
        self.pages[page_class].tkraise()

    def render(self):
        self.pages[UploadPage].render()
        self.pages[MainPage].render()


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
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="DIAD",
<<<<<<< Updated upstream
            font=app_font(30, "bold"),
=======
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Create a project, add your files, and start chatting with your data.",
<<<<<<< Updated upstream
            font=app_font(16, "normal"),
=======
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Left side: create new project
        self.create_frame = glass_panel(body)
        self.create_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.create_frame.grid_columnconfigure(0, weight=1)
        self.create_frame.grid_rowconfigure(5, weight=1)

        add_corner_help(
            self.create_frame,
            "Create a project by giving it a name and adding one or more CSV/XLSX files.\n"
            "The files are copied into the project so you can reopen it later.",
        )

        section_title(self.create_frame, "Create New Project").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 4)
        )
        section_subtitle(
            self.create_frame,
            "Start with a name, then add the files you want this project to use.",
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            self.create_frame,
            text="Project name",
            text_color=MUTED,
        ).grid(row=2, column=0, sticky="w", padx=18)

        self.project_name_entry = ctk.CTkEntry(
            self.create_frame,
            height=40,
            corner_radius=12,
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="My project",
            font=app_font(12, "normal"),
            placeholder_text_color=MUTED,
        )
<<<<<<< Updated upstream
        self.project_name_entry.grid(row=3, column=0, sticky="ew", padx=18, pady=(8, 14))
=======
        self.project_name_entry.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 12))
        self.project_name_entry.configure(font=ctk.CTkFont(family='Courier New', size=13))
>>>>>>> Stashed changes

        files_toolbar = ctk.CTkFrame(self.create_frame, fg_color="transparent")
        files_toolbar.grid(row=4, column=0, sticky="ew", padx=18)
        files_toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(files_toolbar, text="Files", text_color=MUTED).grid(row=0, column=0, sticky="w")

        self.file_count_label = ctk.CTkLabel(files_toolbar, text="0 selected", text_color=MUTED_2)
        self.file_count_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.btn_pick_files = ctk.CTkButton(
            files_toolbar,
            text="Add Files",
            width=100,
            height=34,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.on_pick_files,
            font=app_font(14, "bold")
        )
        self.btn_pick_files.grid(row=0, column=2, padx=(8, 0))

        self.btn_clear_files = ctk.CTkButton(
            files_toolbar,
            text="Clear",
            width=80,
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.on_clear_files,
            font=app_font(14, "bold")
        )
        self.btn_clear_files.grid(row=0, column=3, padx=(8, 0))

        self.files_scroll = ctk.CTkScrollableFrame(
            self.create_frame,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            corner_radius=14,
        )
        self.files_scroll.grid(row=5, column=0, sticky="nsew", padx=18, pady=(12, 12))

        add_corner_help(
            self.files_scroll,
            "These files will be included in the new project.\n"
            "You can drag CSV or XLSX files into this area.",
            x=-6,
            y=6,
        )

        self.drop_hint = ctk.CTkLabel(
            self.create_frame,
            text="Use Add Files or drag CSV/XLSX files into the files area.",
            text_color=MUTED,
            font=app_font(12, "normal")
        )
        self.drop_hint.grid(row=6, column=0, sticky="w", padx=18, pady=(0, 10))

        self.btn_create_project = ctk.CTkButton(
            self.create_frame,
            text="Create Project",
            height=42,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.on_create_project,
            font=app_font(14, "bold")
        )
        self.btn_create_project.grid(row=7, column=0, sticky="ew", padx=18, pady=(0, 18))

        self._enable_drop_target(self.create_frame, self.on_files_drop)
        self._enable_drop_target(self.files_scroll, self.on_files_drop)

        # Right side: open existing project
        self.open_frame = glass_panel(body)
        self.open_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.open_frame.grid_columnconfigure(0, weight=1)
        self.open_frame.grid_rowconfigure(3, weight=1)

        add_corner_help(
            self.open_frame,
            "Open a project you already created.\n"
            "Double-click a project card to open it immediately.",
        )

        section_title(self.open_frame, "Open Existing Project").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 4)
        )
        section_subtitle(
            self.open_frame,
            "Pick a saved project and reopen its files and schema instantly.",
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 12))

        top_bar = ctk.CTkFrame(self.open_frame, fg_color="transparent")
        top_bar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        top_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top_bar, text="Projects", text_color=MUTED).grid(row=0, column=0, sticky="w")

        self.project_count_label = ctk.CTkLabel(top_bar, text="0 available", text_color=MUTED_2)
        self.project_count_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.btn_refresh_projects = ctk.CTkButton(
            top_bar,
            text="Refresh",
            width=90,
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.on_refresh_projects,
            font=app_font(14, "bold")
        )
        self.btn_refresh_projects.grid(row=0, column=2, padx=(8, 0))

        self.projects_scroll = ctk.CTkScrollableFrame(
            self.open_frame,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            corner_radius=14,
        )
        self.projects_scroll.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 12))

        self.btn_open_project = ctk.CTkButton(
            self.open_frame,
            text="Open Selected Project",
            height=42,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.on_open_project,
            font=app_font(14, "bold")
        )
        self.btn_open_project.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 18))

        self.status_label = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.status_label.grid(row=2, column=0, sticky="w", padx=12, pady=(10, 0))

    def _enable_drop_target(self, widget, callback):
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", callback)
        except Exception:
            pass

    def _parse_drop_paths(self, event) -> list[str]:
        try:
            items = self.app.tk.splitlist(event.data)
        except Exception:
            raw = str(getattr(event, "data", "")).strip()
            items = [raw] if raw else []

        out: list[str] = []
        for item in items:
            if not item:
                continue
            cleaned = str(item).strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                cleaned = cleaned[1:-1]
            out.append(cleaned)
        return out

    def _select_project(self, path: str):
        self.selected_project_var.set(path)
        self.render()

    def _open_project_path(self, path: str):
        self.selected_project_var.set(path)
        self.app.controller.open_project(path)
        self.after(120, self.check_transition)

    def _bind_project_card(self, widgets: list[tk.Widget], path: str):
        for widget in widgets:
            widget.bind("<Button-1>", lambda e, p=path: self._select_project(p))
            widget.bind("<Double-Button-1>", lambda e, p=path: self._open_project_path(p))

    def _render_pending_files(self):
        for child in self.files_scroll.winfo_children():
            child.destroy()

        self.file_count_label.configure(text=f"{len(self.pending_files)} selected")

        if not self.pending_files:
            ctk.CTkLabel(
                self.files_scroll,
                text="No files added yet.",
                text_color=MUTED,
               font= app_font(12, "normal")
            ).pack(anchor="w", padx=8, pady=8)
            return

        for p in self.pending_files:
            row = ctk.CTkFrame(self.files_scroll, fg_color=SURFACE_3, corner_radius=12)
            row.pack(fill="x", padx=4, pady=4)

            ext = p.suffix.lower().replace(".", "").upper() or "FILE"

            badge = ctk.CTkLabel(
                row,
                text=ext,
                width=46,
                corner_radius=8,
                fg_color=ACCENT,
                text_color=ACCENT_TEXT,
            )
            badge.pack(side="left", padx=(10, 8), pady=10)

            ctk.CTkLabel(
                row,
                text=p.name,
                text_color=TEXT,
<<<<<<< Updated upstream
                anchor="w",
                font=app_font(12, "normal")
            ).pack(fill="x", padx=(0, 12), pady=10)
=======
                font=self.app.APP_FONT,
            ).grid(row=0, column=0, rowspan=2, padx=10, pady=10)
            ctk.CTkLabel(card, text=path.name, text_color=TEXT, anchor="w").grid(
                row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0)
            )
            ctk.CTkLabel(card, text=str(path.parent), text_color=MUTED_2, anchor="w").grid(
                row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10)
            )
>>>>>>> Stashed changes

    def _render_projects(self):
        for child in self.projects_scroll.winfo_children():
            child.destroy()

        self.project_count_label.configure(text=f"{len(self.project_records)} available")

        if not self.project_records:
            ctk.CTkLabel(
                self.projects_scroll,
                text="No projects yet.",
                text_color=MUTED,
                font=app_font(12, "normal")
            ).pack(anchor="w", padx=8, pady=8)
            return

        selected = self.selected_project_var.get()

        for item in self.project_records:
            path = item["path"]
            selected_now = selected == path

            card = ctk.CTkFrame(
                self.projects_scroll,
                fg_color=SURFACE_3 if selected_now else SURFACE,
                border_width=1,
                border_color=ACCENT if selected_now else BORDER,
                corner_radius=14,
            )
            card.pack(fill="x", padx=4, pady=5)

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
                font=app_font(14, "bold")
            )
            radio.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=12, sticky="n")

            created = self._format_created_at(item.get("created_at"))
            meta = f'{item.get("file_count", 0)} file(s)  •  {created}'

            card.grid_columnconfigure(1, weight=1)

            name_label = ctk.CTkLabel(
                card,
                text=item.get("name", "(unnamed)"),
<<<<<<< Updated upstream
                font=app_font(12, "normal"),
=======
                font=self.app.APP_FONT,
>>>>>>> Stashed changes
                text_color=TEXT,
                anchor="w",
            )
            name_label.grid(row=0, column=1, sticky="ew", pady=(10, 2), padx=(0, 10))

            meta_label = ctk.CTkLabel(
                card,
                text=meta,
                text_color=MUTED,
                anchor="w",
                font=app_font(12, "normal")
            )
            meta_label.grid(row=1, column=1, sticky="ew", pady=(0, 10), padx=(0, 10))

<<<<<<< Updated upstream
            self._bind_project_card([card, name_label, meta_label], path)
=======
            delete_btn = ctk.CTkButton(
                card,
                text="Delete",
                width=72,
                height=28,
                corner_radius=10,
                fg_color=DANGER,
                hover_color=DANGER_HOVER,
                text_color=ACCENT_TEXT,
                font=self.app.APP_FONT,
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
>>>>>>> Stashed changes

    def _add_pending_files(self, raw_paths: list[str | Path]):
        existing = {p.resolve() for p in self.pending_files}
        for raw in raw_paths:
            p = Path(raw).expanduser().resolve()
            if not p.exists() or not p.is_file():
                continue
            if p.suffix.lower() not in {".csv", ".xlsx"}:
                continue
            if p.resolve() in existing:
                continue
            self.pending_files.append(p)
            existing.add(p.resolve())
        self.render()

    def on_pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Select CSV/XLSX files",
            filetypes=_ALLOWED_FILE_TYPES,
        )
        if not paths:
            return
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
            messagebox.showinfo("Create Project", "Add at least one CSV or XLSX file.")
            return

        self.app.controller.create_project(project_name, self.pending_files)
        self.after(120, self.check_transition)

    def on_open_project(self):
        selected = self.selected_project_var.get().strip()
        if not selected:
            messagebox.showinfo("Open Project", "Select a project first.")
            return

        self.app.controller.open_project(selected)
        self.after(120, self.check_transition)

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
            self.status_label.configure(text="Working...", text_color=WARNING)
        else:
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
        self.selected_schema_item: tuple[str, str | None] | None = None

        self._build_layout()

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)

        # Sidebar
        self.sidebar = glass_panel(self, width=270)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10), pady=0)
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(6, weight=1)

        add_corner_help(
            self.sidebar,
            "This sidebar shows the current project and its files.\n"
            "Use it to go back to Projects, add files, or open schema, categories, and SQL.",
        )

        ctk.CTkLabel(
            self.sidebar,
            text="Project",
<<<<<<< Updated upstream
            font=app_font(12, "normal"),
=======
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))

        self.project_label = ctk.CTkLabel(
            self.sidebar,
            text="No project open",
            text_color=TEXT,
            wraplength=220,
            justify="left",
            anchor="w",
            font=app_font(12, "normal")
        )
        self.project_label.grid(row=1, column=0, sticky="ew", padx=16)

        self.project_path_label = ctk.CTkLabel(
            self.sidebar,
            text="",
            text_color=MUTED,
            wraplength=220,
            justify="left",
            anchor="w",
            font=app_font(12, "normal")
        )
        self.project_path_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 14))

        button_row_1 = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        button_row_1.grid(row=3, column=0, sticky="ew", padx=16)
        button_row_1.grid_columnconfigure((0, 1), weight=1)

        self.btn_projects = ctk.CTkButton(
            button_row_1,
            text="Projects",
            height=38,
            corner_radius=12,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.on_back_to_projects,
            font=app_font(14, "bold")
        )
        self.btn_projects.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_add_files = ctk.CTkButton(
            button_row_1,
            text="Add Files",
            height=38,
            corner_radius=12,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.on_add_files,
            font=app_font(14, "bold")
        )
        self.btn_add_files.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        button_row_2 = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        button_row_2.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
        button_row_2.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_view_schema = ctk.CTkButton(
            button_row_2,
            text="Schema",
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.open_schema_window,
            font=app_font(14, "bold")
        )
        self.btn_view_schema.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_view_categories = ctk.CTkButton(
            button_row_2,
            text="Categories",
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.open_categories_window,
            font=app_font(14, "bold")
        )
        self.btn_view_categories.grid(row=0, column=1, sticky="ew", padx=4)

        self.btn_view_sql = ctk.CTkButton(
            button_row_2,
            text="Latest SQL",
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.open_sql_window,
            font=app_font(14, "bold")
        )
        self.btn_view_sql.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        files_section = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        files_section.grid(row=6, column=0, sticky="nsew", padx=16, pady=(14, 16))
        files_section.grid_rowconfigure(1, weight=1)
        files_section.grid_columnconfigure(0, weight=1)

        files_header = ctk.CTkFrame(files_section, fg_color="transparent")
        files_header.grid(row=0, column=0, sticky="ew")
        files_header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            files_header,
            text="Files",
<<<<<<< Updated upstream
            font=app_font(12, "normal"),
=======
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        self.file_count_label_main = ctk.CTkLabel(
            files_header,
            text="0 loaded",
            text_color=MUTED_2,
            font=app_font(12, "normal")
        )
        self.file_count_label_main.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.files_scroll = ctk.CTkScrollableFrame(
            files_section,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            corner_radius=14,
        )
        self.files_scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        add_corner_help(
            self.files_scroll,
            "These are the files stored inside the current project.\n"
            "You can also drag CSV or XLSX files here to add them to the project.",
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
            "Ask questions about your project data here.\n"
            "Results will appear in the conversation, and you can open or download CSV output when available.",
        )

        title_wrap = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        title_wrap.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            title_wrap,
<<<<<<< Updated upstream
            text="Ask a question about your data",
            font=app_font(20, "bold"),
=======
            text="Chat with your data",
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=TEXT,
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.result_hint = ctk.CTkLabel(title_wrap, text="", text_color=MUTED)
        self.result_hint.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.chat_history = ctk.CTkTextbox(
            self.chat_card,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            corner_radius=16,
            text_color=TEXT,
            wrap="word",
            font=app_font(12, "normal")
        )
        self.chat_history.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.chat_history.configure(state="disabled")

        toolbar = ctk.CTkFrame(self.chat_card, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)

        self.output_summary_label = ctk.CTkLabel(toolbar, text="", text_color=MUTED)
        self.output_summary_label.grid(row=0, column=0, sticky="w")

        self.btn_open_output = ctk.CTkButton(
            toolbar,
            text="Open Output",
            width=120,
            height=34,
            corner_radius=10,
            fg_color=SURFACE_3,
            hover_color=SURFACE_4,
            text_color=TEXT,
            command=self.open_output_window,
            font=app_font(14, "bold")
        )
        self.btn_open_output.grid(row=0, column=1, padx=(8, 0))

        self.btn_download_output = ctk.CTkButton(
            toolbar,
            text="Download CSV",
            width=130,
            height=34,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.download_output_csv,
            font=app_font(14, "bold")
        )
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
            placeholder_text_color=MUTED,
            font=app_font(12, "normal")
        )
        self.chat_entry.configure(font=ctk.CTkFont(family='Courier New', size=13))
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.on_send())

        self.btn_send = ctk.CTkButton(
            composer,
            text="Send",
            width=96,
            height=42,
            corner_radius=14,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.on_send,
            font=app_font(14, "bold")
        )
        self.btn_send.grid(row=0, column=1, padx=(8, 0))

        self.status = ctk.CTkLabel(self.chat_card, text="", text_color=MUTED)
        self.status.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 16))

        # Data guide
        self.guide_card = glass_panel(self, width=370)
        self.guide_card.grid(row=0, column=2, sticky="nse", padx=(10, 0), pady=0)
        self.guide_card.grid_propagate(False)
        self.guide_card.grid_columnconfigure(0, weight=1)
        self.guide_card.grid_rowconfigure(3, weight=1)
        self.guide_card.grid_rowconfigure(5, weight=1)

        add_corner_help(
            self.guide_card,
            "Use the Data Guide to see table names and headers.\n"
            "Search here if you do not know the exact field names yet.",
        )

        section_title(self.guide_card, "Data Guide").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        section_subtitle(
            self.guide_card,
            "Browse tables, headers, and sample values before you write a question.",
            wraplength=310,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        self.schema_search = ctk.CTkEntry(
            self.guide_card,
            textvariable=self.schema_search_var,
            height=38,
            corner_radius=12,
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Search tables or columns...",
            placeholder_text_color=MUTED,
            font=app_font(12, "normal")
        )
        self.schema_search.configure(font=ctk.CTkFont(family='Courier New', size=13))
        self.schema_search.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        tree_wrap = glass_panel(self.guide_card, fg_color=SURFACE_2, corner_radius=14)
        tree_wrap.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 12))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        self.schema_tree = ttk.Treeview(tree_wrap, show="tree", style="Dark.Treeview")
        self.schema_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.schema_tree.bind("<<TreeviewSelect>>", lambda e: self.show_schema_details())

        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.schema_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.schema_tree.configure(yscrollcommand=tree_scroll.set)

        detail_header = ctk.CTkFrame(self.guide_card, fg_color="transparent")
        detail_header.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))
        detail_header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            detail_header,
            text="Selected item",
<<<<<<< Updated upstream
            font=app_font(12, "normal"),
=======
            font=self.app.APP_FONT,
>>>>>>> Stashed changes
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")

        self.schema_summary_label = ctk.CTkLabel(
            detail_header,
            text="Nothing selected",
            text_color=MUTED_2,
            font=app_font(12, "normal")
        )
        self.schema_summary_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

<<<<<<< Updated upstream
        self.schema_details = ctk.CTkTextbox(
=======
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
            font=self.app.APP_FONT,
            text_color=MUTED_2,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.schema_chip_frame = ctk.CTkFrame(self.schema_chip_area, fg_color="transparent")
        self.schema_chip_frame.grid(row=1, column=0, sticky="ew")
        self.schema_chip_frame.grid_columnconfigure((0, 1), weight=1)

        self.schema_detail = ctk.CTkTextbox(
>>>>>>> Stashed changes
            self.guide_card,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            corner_radius=14,
            text_color=TEXT,
            wrap="word",
            font=app_font(12, "normal")
        )
        self.schema_details.grid(row=5, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.schema_details.configure(state="disabled")

        add_corner_help(
            self.schema_details,
            "Click a table or column above to see details here.\n"
            "Sample values will appear when available.",
            x=-6,
            y=6,
        )
<<<<<<< Updated upstream
=======
        self.schema_detail.grid(row=7, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.schema_detail.configure(state="disabled",font=self.app.APP_FONT)
>>>>>>> Stashed changes

    def _enable_drop_target(self, widget, callback):
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", callback)
        except Exception:
            pass

    def _parse_drop_paths(self, event) -> list[str]:
        try:
            items = self.app.tk.splitlist(event.data)
        except Exception:
<<<<<<< Updated upstream
            raw = str(getattr(event, "data", "")).strip()
            items = [raw] if raw else []

        out: list[str] = []
        for item in items:
            if not item:
                continue
            cleaned = str(item).strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                cleaned = cleaned[1:-1]
            out.append(cleaned)
        return out

    def _schema_text_dump(self) -> str:
        schema_str = ""
        for table, cols in sorted(self.state.schema_map.items()):
            schema_str += f'TABLE "{table}"\n'
            for col, typ in cols.items():
                schema_str += f' - "{col}" ({typ})\n'
            schema_str += "\n"
        return schema_str.strip()

    def _categories_text_dump(self) -> str:
        cats_lines = []
        for (t, c), vals in sorted(
            self.state.categorical_index.items(),
            key=lambda x: (x[0][0].lower(), x[0][1].lower()),
        ):
            uniq = []
            seen = set()
            for v in vals:
                s = str(v).strip()
                if s and s.lower() not in seen:
                    uniq.append(s)
                    seen.add(s.lower())

            if uniq:
                cats_lines.append(f'"{t}"."{c}": {", ".join(uniq[:25])}{" ..." if len(uniq) > 25 else ""}')
        return "\n".join(cats_lines).strip()
=======
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
                font=self.app.APP_FONT,
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
            font=self.app.APP_FONT,
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
                font=self.app.APP_FONT,
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
                font=self.app.APP_FONT,
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
                font=self.app.APP_FONT,
                anchor="w",
            ).pack(anchor="w", padx=13, pady=(9, 0))

            ctk.CTkLabel(
                bubble,
                text=content,
                text_color=ACCENT_TEXT if is_user else TEXT,
                font=self.app.APP_FONT,
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
>>>>>>> Stashed changes

    def on_project_files_drop(self, event):
        if not self.state.current_project_path:
            return
        paths = self._parse_drop_paths(event)
        if paths:
            self.controller.add_files_to_current_project(paths)

<<<<<<< Updated upstream
    def on_back_to_projects(self):
        self.controller.refresh_projects()
        self.app.show_page(UploadPage)

    def on_add_files(self):
        if not self.state.current_project_path:
            messagebox.showinfo("Add Files", "Open or create a project first.")
            return

        paths = filedialog.askopenfilenames(
            title="Add CSV/XLSX files to project",
            filetypes=_ALLOWED_FILE_TYPES,
            font=app_font(12, "normal")
        )
        if not paths:
            return

        self.controller.add_files_to_current_project(list(paths))

    def on_send(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        self.controller.send_chat(text)

    def _open_text_window(self, title: str, content: str):
        if not content.strip():
            messagebox.showinfo(title, f"No {title.lower()} available yet.")
            return

        window = ctk.CTkToplevel(self)
        window.title(title)
        window.geometry("920x660")
        window.configure(fg_color=APP_BG)
        window.grid_rowconfigure(0, weight=1)
        window.grid_columnconfigure(0, weight=1)

        text = ctk.CTkTextbox(
            window,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
            corner_radius=16,
            text_color=TEXT,
            wrap="none",
            font=app_font(12, "normal")
        )
        text.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        text.insert("1.0", content)
        text.configure(state="disabled")
=======
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
        text.configure(state="disabled",font=self.app.APP_FONT)
>>>>>>> Stashed changes

    def open_schema_window(self):
        self._open_text_window("Schema", self._schema_text_dump())

    def open_categories_window(self):
<<<<<<< Updated upstream
        self._open_text_window("Categories", self._categories_text_dump())

    def open_sql_window(self):
        self._open_text_window("Latest SQL", self.state.generated_sql or "")
=======
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
        text.configure(state="disabled",font=self.app.APP_FONT)

    def open_sql_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Latest SQL")
        win.geometry("760x480")
        win.configure(fg_color=APP_BG)
        text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
        text.pack(fill="both", expand=True, padx=14, pady=14)
        text.insert(tk.END, self.state.generated_sql or "No SQL generated yet.")
        text.configure(state="disabled",font=self.app.APP_FONT)
>>>>>>> Stashed changes

    def _has_output(self) -> bool:
        if isinstance(self.state.result_preview, pd.DataFrame):
            return True
        if self.state.export_path and Path(self.state.export_path).exists():
            return True
        return False

    def _get_output_df(self) -> pd.DataFrame | None:
        if isinstance(self.state.result_preview, pd.DataFrame):
            return self.state.result_preview

        if self.state.export_path and Path(self.state.export_path).exists():
            try:
                return pd.read_csv(self.state.export_path)
            except Exception as exc:
                messagebox.showerror("Open Output", f"Could not read CSV:\n{exc}")
                return None

        return None

    def download_output_csv(self):
        df = self._get_output_df()
        if df is None:
            messagebox.showinfo("Download CSV", "There is no output CSV to download yet.")
            return

        initial_name = "output.csv"
        if self.state.export_path:
            initial_name = Path(self.state.export_path).name

<<<<<<< Updated upstream
        save_path = filedialog.asksaveasfilename(
            title="Save output CSV as",
            defaultextension=".csv",
            initialfile=initial_name,
            filetypes=[("CSV files", "*.csv")],
            font=app_font(12, "normal")
=======
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
            font=self.app.APP_FONT,
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
>>>>>>> Stashed changes
        )
        if not save_path:
            return

        try:
            df.to_csv(save_path, index=False)
            messagebox.showinfo("Download CSV", f"Saved CSV to:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("Download CSV", f"Could not save CSV:\n{exc}")

    def open_output_window(self):
        df = self._get_output_df()
        if df is None:
            messagebox.showinfo("Open Output", "There is no output CSV to open yet.")
            return

        window = ctk.CTkToplevel(self)
        window.title("Output")
        window.geometry("1120x720")
        window.configure(fg_color=APP_BG)
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(window, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        top_bar.grid_columnconfigure(0, weight=1)

        info_text = f"{len(df)} row(s), {len(df.columns)} column(s)"
        ctk.CTkLabel(top_bar, text=info_text, text_color=TEXT).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            top_bar,
            text="Download CSV",
            width=130,
            height=34,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            command=self.download_output_csv,
            font=app_font(14, "bold")
        ).grid(row=0, column=1, padx=(8, 0))

        table_wrap = glass_panel(window)
        table_wrap.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)

        x_scroll = ttk.Scrollbar(table_wrap, orient="horizontal")
        y_scroll = ttk.Scrollbar(table_wrap, orient="vertical")

        columns = [str(col) for col in df.columns]
        tree = ttk.Treeview(
            table_wrap,
            columns=columns,
            show="headings",
            style="Dark.Treeview",
            xscrollcommand=x_scroll.set,
            yscrollcommand=y_scroll.set,
            font=app_font(12, "normal")
        )

        x_scroll.config(command=tree.xview)
        y_scroll.config(command=tree.yview)

        tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 0))
        y_scroll.grid(row=0, column=1, sticky="ns", pady=(10, 0), padx=(0, 10))
        x_scroll.grid(row=1, column=0, sticky="ew", padx=(10, 0), pady=(0, 10))

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140, minwidth=100, stretch=True)

        max_rows = 2000
        display_df = df.head(max_rows)

<<<<<<< Updated upstream
        for _, row in display_df.iterrows():
            values = ["" if pd.isna(v) else str(v) for v in row.tolist()]
            tree.insert("", "end", values=values)

        if len(df) > max_rows:
=======
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
        text.configure(state="disabled",font=self.app.APP_FONT)

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
            font=self.app.APP_FONT,
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
>>>>>>> Stashed changes
            ctk.CTkLabel(
                window,
                text=f"Showing first {max_rows} rows for performance.",
                text_color=MUTED,
            ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 12))

    def _render_chat_history(self):
        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", tk.END)

        messages = self.state.messages[-50:]
        if not messages:
            self.chat_history.insert("1.0", "Start by asking a question about your project data.")
            self.chat_history.configure(state="disabled")
            return

        for m in messages:
            role = m.get("role", "").lower()
            content = m.get("content", "").strip()

            if role == "user":
                self.chat_history.insert("end", "You\n")
            else:
                self.chat_history.insert("end", "DIAD\n")

            self.chat_history.insert("end", content + "\n\n")

        self.chat_history.see("end")
        self.chat_history.configure(state="disabled")

    def _render_files(self):
        for child in self.files_scroll.winfo_children():
            child.destroy()

        files = [*self.state.csv_files, *self.state.xlsx_files]
        self.file_count_label_main.configure(text=f"{len(files)} loaded")

        if not files:
            ctk.CTkLabel(
                self.files_scroll,
                text="No files in this project.",
                text_color=MUTED,
                font=app_font(12, "normal")
            ).pack(anchor="w", padx=8, pady=8)
            return

        for p in files:
            row = ctk.CTkFrame(self.files_scroll, fg_color=SURFACE_3, corner_radius=12)
            row.pack(fill="x", padx=4, pady=4)

            ext = p.suffix.lower().replace(".", "").upper() or "FILE"

            badge = ctk.CTkLabel(
                row,
                text=ext,
                width=46,
                corner_radius=8,
                fg_color=ACCENT,
                text_color=ACCENT_TEXT,
                font=app_font(12, "normal")
            )
            badge.pack(side="left", padx=(10, 8), pady=10)

            ctk.CTkLabel(
                row,
                text=p.name,
                text_color=TEXT,
                anchor="w",
                font=app_font(12, "normal")
            ).pack(fill="x", padx=(0, 12), pady=10)

    def _set_schema_details(self, content: str):
        self.schema_details.configure(state="normal")
        self.schema_details.delete("1.0", tk.END)
        self.schema_details.insert("1.0", content)
        self.schema_details.configure(state="disabled")

    def _show_table_details(self, table_name: str):
        self.selected_schema_item = (table_name, None)
        cols = self.state.schema_map.get(table_name, {})
        self.schema_summary_label.configure(text=f"{len(cols)} columns")

        lines = [
            f"Table: {table_name}",
            "",
            f"Columns ({len(cols)}):",
        ]
        for col_name, col_type in cols.items():
            lines.append(f"- {col_name} ({col_type})")
        self._set_schema_details("\n".join(lines))

    def _show_column_details(self, table_name: str, col_name: str):
        self.selected_schema_item = (table_name, col_name)
        col_type = self.state.schema_map.get(table_name, {}).get(col_name, "Unknown")
        values = self.state.categorical_index.get((table_name, col_name), [])

        uniq: list[str] = []
        seen: set[str] = set()
        for v in values:
            s = str(v).strip()
            if s and s.lower() not in seen:
                uniq.append(s)
                seen.add(s.lower())

        self.schema_summary_label.configure(text=col_name)

        lines = [
            f"Table: {table_name}",
            f"Column: {col_name}",
            f"Type: {col_type}",
        ]

        if uniq:
            lines.extend(["", "Sample values:"])
            for v in uniq[:20]:
                lines.append(f"- {v}")
            if len(uniq) > 20:
                lines.append(f"- ... ({len(uniq)} total)")
        else:
<<<<<<< Updated upstream
            lines.extend(["", "No categorical preview available for this column."])
=======
            text = ctk.CTkTextbox(win, fg_color=SURFACE_2, text_color=TEXT, wrap="word")
            text.pack(fill="both", expand=True, padx=14, pady=14)
            text.insert(tk.END, str(df))
            text.configure(state="disabled",font=self.app.APP_FONT)
>>>>>>> Stashed changes

        self._set_schema_details("\n".join(lines))

    def refresh_schema_tree(self):
        self.schema_tree.delete(*self.schema_tree.get_children())

        schema_map = self.state.schema_map
        if not schema_map:
            self.schema_summary_label.configure(text="Nothing selected")
            self._set_schema_details("Open a project to see tables and column names.")
            return

        search = self.schema_search_var.get().strip().lower()
        rendered_any = False

        total_tables = len(schema_map)
        total_columns = sum(len(cols) for cols in schema_map.values())

        for table_name, cols in sorted(schema_map.items()):
            table_match = not search or search in table_name.lower()
            matching_cols = [c for c in cols.keys() if not search or search in c.lower()]

            if not table_match and not matching_cols:
                continue

            rendered_any = True
            table_id = f"table::{table_name}"
            self.schema_tree.insert("", "end", iid=table_id, text=table_name, open=True)

            cols_to_show = matching_cols if search else list(cols.keys())
            for col_name in sorted(cols_to_show):
                col_id = f"col::{table_name}::{col_name}"
                self.schema_tree.insert(table_id, "end", iid=col_id, text=col_name)

        if not rendered_any:
            self.schema_summary_label.configure(text="No matches")
            self._set_schema_details("No tables or columns matched your search.")
            return

        target_id = None
        if self.selected_schema_item is not None:
            table_name, col_name = self.selected_schema_item
            target_id = f"table::{table_name}" if col_name is None else f"col::{table_name}::{col_name}"

        if target_id and self.schema_tree.exists(target_id):
            self.schema_tree.selection_set(target_id)
            self.schema_tree.see(target_id)
            self.show_schema_details()
        else:
            self.schema_summary_label.configure(text=f"{total_tables} tables • {total_columns} columns")
            self._set_schema_details(
                "Select a table or column to see more detail.\n\n"
                "Tip: use the search box to find headers faster."
            )

    def show_schema_details(self):
        selection = self.schema_tree.selection()
        if not selection:
            self.schema_summary_label.configure(text="Nothing selected")
            self._set_schema_details(
                "Select a table or column to see more detail.\n\n"
                "Tip: use the search box to find headers faster."
            )
            return

        item_id = selection[0]

        if item_id.startswith("table::"):
            table_name = item_id.split("::", 1)[1]
            self._show_table_details(table_name)
            return

        if item_id.startswith("col::"):
            _, table_name, col_name = item_id.split("::", 2)
            self._show_column_details(table_name, col_name)
            return

    def _result_summary_text(self) -> str:
        if isinstance(self.state.result_preview, pd.DataFrame):
            rows = len(self.state.result_preview)
            cols = len(self.state.result_preview.columns)
            return f"Latest result: {rows} row(s) • {cols} column(s)"
        if self.state.export_path:
            return f"Latest export: {self.state.export_path.name}"
        return "No output yet"

    def render(self):
        busy = self.state.is_busy
        state = "disabled" if busy else "normal"

        self.btn_projects.configure(state=state)
        self.btn_add_files.configure(state=state if self.state.current_project_path else "disabled")
        self.btn_view_schema.configure(state=state if self.state.schema_map else "disabled")
        self.btn_view_categories.configure(state=state if self.state.categorical_index else "disabled")
        self.btn_view_sql.configure(state=state if self.state.generated_sql else "disabled")
        self.btn_send.configure(state=state)
        self.schema_search.configure(state=state if self.state.schema_map else "disabled")

        has_output = self._has_output()
        output_state = "normal" if has_output and not busy else "disabled"
        self.btn_open_output.configure(state=output_state)
        self.btn_download_output.configure(state=output_state)

        if self.state.current_project_name:
            self.project_label.configure(text=self.state.current_project_name)
            self.title_label.configure(text=f"Chat with {self.state.current_project_name}")
            self.result_hint.configure(text=f"Project: {self.state.current_project_name}")
        else:
            self.project_label.configure(text="No project open")
            self.title_label.configure(text="Ask a question about your data")
            self.result_hint.configure(text="")

        self.project_path_label.configure(
            text=str(self.state.current_project_path) if self.state.current_project_path else ""
        )

        self.output_summary_label.configure(text=self._result_summary_text())

        self._render_files()
        self._render_chat_history()
        self.refresh_schema_tree()

        if busy:
            self.status.configure(text="Working...", text_color=WARNING)
        else:
            self.status.configure(
                text=self.state.error or "Ready",
                text_color=ERROR if self.state.error else TEXT,
            )


if __name__ == "__main__":
    app = TkApp()
    app.mainloop()