from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
import pandas as pd
import os

from UI.state import AppState
from UI.controller import Controller

import tkinterdnd2
from tkinterdnd2 import TkinterDnD, DND_FILES


class TkApp(TkinterDnD.Tk):

    def __init__(self):
        super().__init__()
        self.title("DIAD PoC")
        self.geometry("1100x700")

        self.state = AppState()
        self.controller = Controller(self.state, self.render)

        # Container for pages
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)

        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        self.pages = {}

        for Page in (UploadPage, MainPage):
            page = Page(self.container, self)
            self.pages[Page] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.show_page(UploadPage)

    def show_page(self, page_class):
        page = self.pages[page_class]
        page.tkraise()

    def render(self):
        # Always render main page (data lives there)
        self.pages[MainPage].render()


# ------------
# LANDING PAGE
# ------------
class UploadPage(ttk.Frame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, padding=20)
        self.app = app

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        label = ttk.Label(self, text="Drop a folder with CSV files or click below", font=("Arial", 16))
        label.grid(row=0, column=0, pady=20)

        # Drag-and-drop area
        self.drop_area = ttk.Frame(self, borderwidth=2, relief="ridge")
        self.drop_area.grid(row=1, column=0, sticky="nsew", padx=50, pady=20)

        drop_label = ttk.Label(self.drop_area, text="Drag & Drop Folder Here", anchor="center")
        drop_label.place(relx=0.5, rely=0.5, anchor="center")

        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind("<<Drop>>", self.on_folder_drop)

        # Button fallback
        self.btn_load = ttk.Button(self, text="Select CSV Folder", command=self.on_load_folder)
        self.btn_load.grid(row=2, column=0, pady=10)

        self.status_label = ttk.Label(self, text="")
        self.status_label.grid(row=3, column=0)

    def on_load_folder(self):
        folder = filedialog.askdirectory(title="Select folder with CSV files")
        if not folder:
            return
        self.start_loading(folder)

    def on_folder_drop(self, event):
        paths = self.app.tk.splitlist(event.data)
        for path in paths:
            if os.path.isdir(path):
                self.start_loading(path)

    def start_loading(self, folder):
        self.status_label.config(text=f"Loading: {folder}")
        self.app.controller.load_folder(Path(folder))
        self.after(100, self.check_loading)

    def check_loading(self):
        if self.app.state.is_busy:
            self.after(100, self.check_loading)
        else:
            if self.app.state.error:
                self.status_label.config(text=f"Error: {self.app.state.error}")
            else:
                self.app.show_page(MainPage)

# ------------
# MAIN PAGE 
# ------------
class MainPage(ttk.Frame):
    def __init__(self, parent, app: TkApp):
        super().__init__(parent, padding=10)
        self.app = app
        self.controller = app.controller
        self.state = app.state
        self._build_layout()

    def _build_layout(self):
        # SAME LAYOUT (UNCHANGED)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=2)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)

        # Left panel
        self.left = ttk.Frame(self, padding=10)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.rowconfigure(2, weight=1)

        self.btn_load = ttk.Button(self.left, text="Load CSV Folder", command=self.on_load_folder)
        self.btn_load.grid(row=0, column=0, sticky="ew")

        self.lbl_folder = ttk.Label(self.left, text="No folder loaded")
        self.lbl_folder.grid(row=1, column=0, sticky="ew", pady=(8, 4))

        self.tables_list = tk.Listbox(self.left, height=10)
        self.tables_list.grid(row=2, column=0, sticky="nsew")

        # Right panel
        self.right = ttk.Frame(self, padding=10)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.rowconfigure(0, weight=1)
        self.right.rowconfigure(1, weight=1)
        self.right.columnconfigure(0, weight=1)

        self.schema_text = tk.Text(self.right, height=12, wrap="none")
        self.schema_text.grid(row=0, column=0, sticky="nsew")
        self.schema_text.configure(state="disabled")

        self.cats_text = tk.Text(self.right, height=10, wrap="none")
        self.cats_text.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.cats_text.configure(state="disabled")

        # Bottom panel
        self.bottom = ttk.Frame(self, padding=10)
        self.bottom.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.bottom.rowconfigure(0, weight=2)
        self.bottom.rowconfigure(2, weight=2)
        self.bottom.columnconfigure(0, weight=1)

        self.chat_history = tk.Text(self.bottom, height=10, wrap="word")
        self.chat_history.grid(row=0, column=0, sticky="nsew")
        self.chat_history.configure(state="disabled")

        entry_row = ttk.Frame(self.bottom)
        entry_row.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        entry_row.columnconfigure(0, weight=1)

        self.chat_entry = ttk.Entry(entry_row)
        self.chat_entry.grid(row=0, column=0, sticky="ew")
        self.chat_entry.bind("<Return>", lambda e: self.on_send())

        self.btn_send = ttk.Button(entry_row, text="Send", command=self.on_send)
        self.btn_send.grid(row=0, column=1, padx=(8, 0))

        self.results_text = tk.Text(self.bottom, height=10, wrap="none")
        self.results_text.grid(row=2, column=0, sticky="nsew")
        self.results_text.configure(state="disabled")

        self.status = ttk.Label(self, text="", anchor="w")
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.left.drop_target_register(DND_FILES)
        self.left.dnd_bind("<<Drop>>", self.on_folder_drop)

    def on_load_folder(self):
        folder = filedialog.askdirectory(title="Select folder with CSV files")
        if not folder:
            return
        self.controller.load_folder(Path(folder))
    
    #file loading when DND
    def load_folder(self, folder):
        self.controller.load_folder(Path(folder))
    
    def on_folder_drop(self, event):
        #event.data contain dropped paths
        paths = self.tk.splitlist(event.data)
        for path in paths:
            if os.path.isdir(path):
                #clear current list
                self.tables_list.delete(0, tk.END)
                #load csv files from folder
                for file in os.listdir(path):
                    if file.lower().endswith(".csv" or ".xlsx"):
                        self.tables_list.insert(tk.END, file)
                #uploading files into database
                self.load_folder(path)

    def on_send(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        self.controller.send_chat(text)

    def render(self):
        # SAME RENDER LOGIC (UNCHANGED)
        if self.state.is_busy:
            self.status.configure(text="Working...")
            self.btn_send.configure(state="disabled")
            self.btn_load.configure(state="disabled")
        else:
            self.status.configure(text=self.state.error or "Ready")
            self.btn_send.configure(state="normal")
            self.btn_load.configure(state="normal")

        if self.state.data_folder:
            self.lbl_folder.configure(text=str(self.state.data_folder))
        else:
            self.lbl_folder.configure(text="No folder loaded")

        self.tables_list.delete(0, tk.END)
        for t in self.state.tables:
            self.tables_list.insert(tk.END, t)

        schema_str = ""
        for table, cols in sorted(self.state.schema_map.items()):
            schema_str += f'TABLE "{table}"\n'
            for col, typ in cols.items():
                schema_str += f'  - "{col}" ({typ})\n'
            schema_str += "\n"

        self.schema_text.configure(state="normal")
        self.schema_text.delete("1.0", tk.END)
        self.schema_text.insert(tk.END, schema_str.strip() or "(schema will appear here after loading)")
        self.schema_text.configure(state="disabled")

        cats_lines = []
        for (t, c), vals in sorted(self.state.categorical_index.items(), key=lambda x: (x[0][0].lower(), x[0][1].lower())):
            uniq, seen = [], set()
            for v in vals:
                s = str(v).strip()
                if s and s not in seen:
                    uniq.append(s)
                    seen.add(s)
            if uniq:
                cats_lines.append(f'"{t}"."{c}": {", ".join(uniq[:25])}{" ..." if len(uniq) > 25 else ""}')
        cats_str = "\n".join(cats_lines) or "(categorical values will appear here after loading)"

        self.cats_text.configure(state="normal")
        self.cats_text.delete("1.0", tk.END)
        self.cats_text.insert(tk.END, cats_str)
        self.cats_text.configure(state="disabled")

        chat_str = ""
        for m in self.state.messages[-50:]:
            role = m.get("role", "?")
            chat_str += f"{role.upper()}: {m.get('content','')}\n\n"

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


# ------------------------
# RUN APP
# ------------------------
if __name__ == "__main__":
    app = TkApp()
    app.mainloop()
