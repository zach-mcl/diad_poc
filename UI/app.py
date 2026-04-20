from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from tkinterdnd2 import DND_FILES, TkinterDnD

from UI.controller import Controller
from UI.state import AppState


_ALLOWED_FILE_TYPES = [
    ("Data files", "*.csv *.xlsx"),
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx"),
]


class TkApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title("DIAD PoC")
        self.geometry("1180x760")

        self.state = AppState()
        self.controller = Controller(self.state, self.render)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        self.pages: dict[type[ttk.Frame], ttk.Frame] = {}
        for page_cls in (UploadPage, MainPage):
            page = page_cls(self.container, self)
            self.pages[page_cls] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.controller.refresh_projects()
        self.show_page(UploadPage)
        self.render()

    def show_page(self, page_class):
        page = self.pages[page_class]
        page.tkraise()

    def render(self):
        self.pages[UploadPage].render()
        self.pages[MainPage].render()


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

        x = self.widget.winfo_pointerx() + 10
        y = self.widget.winfo_pointery() + 10

        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tip,
            text=self.text,
            bg="#ffffe0",
            fg="black",
            relief="solid",
            borderwidth=1,
            justify="left",
            padx=6,
            pady=4,
        )
        label.pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class UploadPage(ttk.Frame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, padding=20)
        self.app = app
        self.pending_files: list[Path] = []
        self.project_records: list[dict] = []

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        title = ttk.Label(
            self,
            text="Create a new project or open an existing one",
            font=("Arial", 18),
        )
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))

        self.create_frame = ttk.LabelFrame(self, text="Create New Project", padding=16)
        self.create_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.create_frame.columnconfigure(0, weight=1)
        self.create_frame.rowconfigure(4, weight=1)

        ttk.Label(self.create_frame, text="Project Name").grid(row=0, column=0, sticky="w")
        self.project_name_entry = ttk.Entry(self.create_frame)
        self.project_name_entry.grid(row=1, column=0, sticky="ew", pady=(6, 12))

        files_toolbar = ttk.Frame(self.create_frame)
        files_toolbar.grid(row=2, column=0, sticky="ew")
        files_toolbar.columnconfigure(0, weight=1)

        self.btn_pick_files = ttk.Button(files_toolbar, text="Add Files", command=self.on_pick_files)
        self.btn_pick_files.grid(row=0, column=1, padx=(8, 0))

        self.btn_clear_files = ttk.Button(files_toolbar, text="Clear", command=self.on_clear_files)
        self.btn_clear_files.grid(row=0, column=2, padx=(8, 0))

        self.files_list = tk.Listbox(self.create_frame, height=12)
        self.files_list.grid(row=3, column=0, sticky="nsew", pady=(10, 10))

        self.drop_hint = ttk.Label(
            self.create_frame,
            text="You can also drag and drop CSV/XLSX files into this box.",
        )
        self.drop_hint.grid(row=4, column=0, sticky="w", pady=(0, 10))

        self.btn_create_project = ttk.Button(
            self.create_frame,
            text="Create Project",
            command=self.on_create_project,
        )
        self.btn_create_project.grid(row=5, column=0, sticky="ew")

        self.files_list.drop_target_register(DND_FILES)
        self.files_list.dnd_bind("<<Drop>>", self.on_files_drop)

        self.open_frame = ttk.LabelFrame(self, text="Existing Projects", padding=16)
        self.open_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        self.open_frame.columnconfigure(0, weight=1)
        self.open_frame.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(self.open_frame)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top_bar.columnconfigure(0, weight=1)

        self.btn_refresh_projects = ttk.Button(top_bar, text="Refresh", command=self.on_refresh_projects)
        self.btn_refresh_projects.grid(row=0, column=1, padx=(8, 0))

        self.projects_list = tk.Listbox(self.open_frame, height=14)
        self.projects_list.grid(row=1, column=0, sticky="nsew")
        self.projects_list.bind("<Double-Button-1>", lambda e: self.on_open_project())

        self.btn_open_project = ttk.Button(
            self.open_frame,
            text="Open Selected Project",
            command=self.on_open_project,
        )
        self.btn_open_project.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        self.status_label = ttk.Label(self, text="")
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))

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
        raw_items = self.app.tk.splitlist(event.data)
        self._add_pending_files(list(raw_items))

    def on_create_project(self):
        project_name = self.project_name_entry.get().strip()
        if not project_name:
            messagebox.showinfo("Create Project", "Enter a project name first.")
            return
        if not self.pending_files:
            messagebox.showinfo("Create Project", "Add at least one CSV or XLSX file.")
            return

        self.app.controller.create_project(project_name, self.pending_files)
        self.after(100, self.check_transition)

    def on_open_project(self):
        selection = self.projects_list.curselection()
        if not selection:
            messagebox.showinfo("Open Project", "Select a project first.")
            return

        record = self.project_records[selection[0]]
        self.app.controller.open_project(record["path"])
        self.after(100, self.check_transition)

    def on_refresh_projects(self):
        self.app.controller.refresh_projects()

    def check_transition(self):
        if self.app.state.is_busy:
            self.after(100, self.check_transition)
            return

        if self.app.state.error:
            self.status_label.config(text=f"Error: {self.app.state.error}")
            return

        if self.app.state.current_project_path:
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
        self.project_records = list(self.app.state.available_projects)

        self.projects_list.delete(0, tk.END)
        for item in self.project_records:
            created = self._format_created_at(item.get("created_at"))
            text = f'{item.get("name", "(unnamed)")}  •  {item.get("file_count", 0)} file(s)  •  {created}'
            self.projects_list.insert(tk.END, text)

        self.files_list.delete(0, tk.END)
        for p in self.pending_files:
            self.files_list.insert(tk.END, p.name)

        busy = self.app.state.is_busy
        state = "disabled" if busy else "normal"
        self.btn_pick_files.configure(state=state)
        self.btn_clear_files.configure(state=state)
        self.btn_create_project.configure(state=state)
        self.btn_refresh_projects.configure(state=state)
        self.btn_open_project.configure(state=state if self.project_records else "disabled")
        self.project_name_entry.configure(state=state)

        if busy:
            self.status_label.configure(text="Working...")
        else:
            self.status_label.configure(text=self.app.state.error or "")


class MainPage(ttk.Frame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, padding=10)
        self.app = app
        self.controller = app.controller
        self.state = app.state

        self._build_layout()

    def _build_layout(self):
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=2)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)

        self.top_bar = ttk.Frame(self, padding=(0, 0, 0, 8))
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.top_bar.columnconfigure(1, weight=1)

        self.btn_projects = ttk.Button(self.top_bar, text="Projects", command=self.on_back_to_projects)
        self.btn_projects.grid(row=0, column=0, padx=(0, 8))

        self.project_label = ttk.Label(self.top_bar, text="No project open", font=("Arial", 12, "bold"))
        self.project_label.grid(row=0, column=1, sticky="w")

        self.btn_add_files = ttk.Button(self.top_bar, text="Add Files to Project", command=self.on_add_files)
        self.btn_add_files.grid(row=0, column=2)

        self.left = ttk.Frame(self, padding=10)
        self.left.grid(row=1, column=0, sticky="nsew")
        self.left.rowconfigure(2, weight=1)
        self.left.columnconfigure(0, weight=1)

        self.lbl_folder = ttk.Label(self.left, text="No project loaded")
        self.lbl_folder.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.lbl_files = ttk.Label(self.left, text="Project Files")
        self.lbl_files.grid(row=1, column=0, sticky="w")

        self.files_list = tk.Listbox(self.left, height=10)
        self.files_list.grid(row=2, column=0, sticky="nsew")

        self.left_icon = tk.Label(
            self.left,
            text="?",
            cursor="question_arrow",
            fg="white",
            bg=self.files_list.cget("bg"),
            font=("Arial", 18, "bold"),
            padx=4,
            pady=1,
        )
        self.left_icon.place(in_=self.files_list, relx=1.0, rely=0.0, anchor="ne")
        ToolTip(
            self.left_icon,
            "These are the source files stored inside the current project.",
        )

        self.right = ttk.Frame(self, padding=10)
        self.right.grid(row=1, column=1, sticky="nsew")
        self.right.rowconfigure(0, weight=1)
        self.right.rowconfigure(1, weight=1)
        self.right.columnconfigure(0, weight=1)

        self.schema_text = tk.Text(self.right, height=12, wrap="none")
        self.schema_text.grid(row=0, column=0, sticky="nsew")
        self.schema_text.configure(state="disabled")

        self.schema_icon = tk.Label(
            self.right,
            text="?",
            cursor="question_arrow",
            fg="white",
            bg=self.schema_text.cget("bg"),
            font=("Arial", 18, "bold"),
            padx=4,
            pady=1,
        )
        self.schema_icon.place(in_=self.schema_text, relx=1.0, rely=0.0, anchor="ne")
        ToolTip(self.schema_icon, "Schema data for the currently loaded project.")

        self.cats_text = tk.Text(self.right, height=10, wrap="none")
        self.cats_text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.cats_text.configure(state="disabled")

        self.cats_icon = tk.Label(
            self.right,
            text="?",
            cursor="question_arrow",
            fg="white",
            bg=self.cats_text.cget("bg"),
            font=("Arial", 18, "bold"),
            padx=4,
            pady=1,
        )
        self.cats_icon.place(in_=self.cats_text, relx=1.0, rely=0.0, anchor="ne")
        ToolTip(self.cats_icon, "Detected categorical values for the current project.")

        self.bottom = ttk.Frame(self, padding=10)
        self.bottom.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self.bottom.rowconfigure(0, weight=2)
        self.bottom.rowconfigure(2, weight=0)
        self.bottom.rowconfigure(3, weight=2)
        self.bottom.columnconfigure(0, weight=1)

        self.chat_history = tk.Text(self.bottom, height=10, wrap="word")
        self.chat_history.grid(row=0, column=0, sticky="nsew")
        self.chat_history.configure(state="disabled")

        self.chat_icon = tk.Label(
            self.bottom,
            text="?",
            fg="white",
            bg=self.chat_history.cget("bg"),
            font=("Arial", 18, "bold"),
            cursor="question_arrow",
            borderwidth=0,
            highlightthickness=0,
        )
        self.chat_icon.place(in_=self.chat_history, relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)
        ToolTip(
            self.chat_icon,
            "Your prompt, debug information, generated SQL, and exported result path appear here.",
        )

        entry_row = ttk.Frame(self.bottom)
        entry_row.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        entry_row.columnconfigure(0, weight=1)

        self.chat_entry = ttk.Entry(entry_row)
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.on_send())

        self.btn_send = ttk.Button(entry_row, text="Send", command=self.on_send)
        self.btn_send.grid(row=0, column=1, padx=(8, 0))

        self.results_toolbar = ttk.Frame(self.bottom)
        self.results_toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.results_toolbar.columnconfigure(0, weight=1)

        self.btn_open_output = ttk.Button(
            self.results_toolbar,
            text="Open Output CSV",
            command=self.open_output_window,
        )
        self.btn_open_output.grid(row=0, column=1, padx=(8, 0))

        self.btn_download_output = ttk.Button(
            self.results_toolbar,
            text="Download CSV",
            command=self.download_output_csv,
        )
        self.btn_download_output.grid(row=0, column=2, padx=(8, 0))

        self.results_text = tk.Text(self.bottom, height=10, wrap="none")
        self.results_text.grid(row=3, column=0, sticky="nsew")
        self.results_text.configure(state="disabled")

        self.results_icon = tk.Label(
            self.bottom,
            text="?",
            fg="white",
            bg=self.results_text.cget("bg"),
            font=("Arial", 18, "bold"),
            cursor="question_arrow",
            borderwidth=0,
            highlightthickness=0,
        )
        self.results_icon.place(in_=self.results_text, relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)
        ToolTip(
            self.results_icon,
            "Result preview and export path. Open the full output in a new window or save it anywhere you want.",
        )

        self.status = ttk.Label(self, text="", anchor="w")
        self.status.grid(row=3, column=0, columnspan=2, sticky="ew")

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
                messagebox.showerror("Open Output CSV", f"Could not read CSV:\n{exc}")
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

        save_path = filedialog.asksaveasfilename(
            title="Save output CSV as",
            defaultextension=".csv",
            initialfile=initial_name,
            filetypes=[("CSV files", "*.csv")],
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
            messagebox.showinfo("Open Output CSV", "There is no output CSV to open yet.")
            return

        window = tk.Toplevel(self)
        window.title("Output CSV")
        window.geometry("1100x700")
        window.rowconfigure(1, weight=1)
        window.columnconfigure(0, weight=1)

        top_bar = ttk.Frame(window, padding=10)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(0, weight=1)

        info_text = f"{len(df)} row(s), {len(df.columns)} column(s)"
        ttk.Label(top_bar, text=info_text).grid(row=0, column=0, sticky="w")

        ttk.Button(
            top_bar,
            text="Download CSV",
            command=self.download_output_csv,
        ).grid(row=0, column=1, padx=(8, 0))

        table_frame = ttk.Frame(window, padding=(10, 0, 10, 10))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical")

        columns = [str(col) for col in df.columns]
        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            xscrollcommand=x_scroll.set,
            yscrollcommand=y_scroll.set,
        )

        x_scroll.config(command=tree.xview)
        y_scroll.config(command=tree.yview)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140, minwidth=100, stretch=True)

        max_rows = 2000
        display_df = df.head(max_rows)

        for _, row in display_df.iterrows():
            values = ["" if pd.isna(v) else str(v) for v in row.tolist()]
            tree.insert("", "end", values=values)

        if len(df) > max_rows:
            footer = ttk.Label(
                window,
                text=f"Showing first {max_rows} rows for performance.",
                padding=(10, 0, 10, 10),
            )
            footer.grid(row=2, column=0, sticky="w")

    def render(self):
        busy = self.state.is_busy
        button_state = "disabled" if busy else "normal"

        self.btn_projects.configure(state=button_state)
        self.btn_add_files.configure(state=button_state if self.state.current_project_path else "disabled")
        self.btn_send.configure(state=button_state)

        has_output = self._has_output()
        output_state = "normal" if has_output and not busy else "disabled"
        self.btn_open_output.configure(state=output_state)
        self.btn_download_output.configure(state=output_state)

        if self.state.current_project_name:
            self.project_label.configure(text=f"Project: {self.state.current_project_name}")
        else:
            self.project_label.configure(text="No project open")

        if self.state.current_project_path:
            self.lbl_folder.configure(text=str(self.state.current_project_path))
        else:
            self.lbl_folder.configure(text="No project loaded")

        self.files_list.delete(0, tk.END)
        for p in [*self.state.csv_files, *self.state.xlsx_files]:
            self.files_list.insert(tk.END, p.name)

        schema_str = ""
        for table, cols in sorted(self.state.schema_map.items()):
            schema_str += f'TABLE "{table}"\n'
            for col, typ in cols.items():
                schema_str += f' - "{col}" ({typ})\n'
            schema_str += "\n"

        self.schema_text.configure(state="normal")
        self.schema_text.delete("1.0", tk.END)
        self.schema_text.insert(tk.END, schema_str.strip() or "(schema will appear here after opening a project)")
        self.schema_text.configure(state="disabled")

        cats_lines = []
        for (t, c), vals in sorted(
            self.state.categorical_index.items(),
            key=lambda x: (x[0][0].lower(), x[0][1].lower()),
        ):
            uniq: list[str] = []
            seen: set[str] = set()
            for v in vals:
                s = str(v).strip()
                if s and s not in seen:
                    uniq.append(s)
                    seen.add(s)

            if uniq:
                suffix = " ..." if len(uniq) > 25 else ""
                cats_lines.append(f'"{t}"."{c}": {", ".join(uniq[:25])}{suffix}')

        cats_str = "\n".join(cats_lines) or "(categorical values will appear here after opening a project)"
        self.cats_text.configure(state="normal")
        self.cats_text.delete("1.0", tk.END)
        self.cats_text.insert(tk.END, cats_str)
        self.cats_text.configure(state="disabled")

        chat_str = ""
        for m in self.state.messages[-50:]:
            role = m.get("role", "?")
            chat_str += f"{role.upper()}: {m.get('content', '')}\n\n"

        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", tk.END)
        self.chat_history.insert(tk.END, chat_str.strip() or "(chat will appear here)")
        self.chat_history.configure(state="disabled")

        res_str = ""
        if self.state.generated_sql:
            res_str += "Generated SQL:\n" + self.state.generated_sql + "\n\n"

        if isinstance(self.state.result_preview, pd.DataFrame):
            res_str += "Preview (first 20 rows):\n"
            res_str += self.state.result_preview.head(20).to_string(index=False)
            res_str += "\n\n"

        if self.state.export_path:
            res_str += f"Exported: {self.state.export_path}\n"

        if not res_str:
            res_str = "(results will appear here)"

        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", tk.END)
        self.results_text.insert(tk.END, res_str)
        self.results_text.configure(state="disabled")

        if busy:
            self.status.configure(text="Working...")
        else:
            self.status.configure(text=self.state.error or "Ready")


if __name__ == "__main__":
    app = TkApp()
    app.mainloop()