"""Minimal drop-and-run desktop interface."""
import contextlib
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES, COPY, REFUSE_DROP

from .runner import ROOT, SUFFIXES, input_folder, store_inputs, useful_outputs, run_job, current_inputs


class Writer:
    def __init__(self, events):
        self.events = events

    def write(self, value):
        if value.strip():
            self.events.put(("progress", value.strip()))
        return len(value)

    def flush(self):
        pass


class Workflow(ttk.Frame):
    def __init__(self, parent, app, mode):
        super().__init__(parent, padding=24)
        self.app, self.mode = app, mode
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(7, weight=1)
        input_folder(mode).mkdir(parents=True, exist_ok=True)
        title = "Abstracts" if mode == "abstracts" else "Webinar reports"
        ttk.Label(self, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        types = "PDF or Word files" if mode == "abstracts" else "Zoom attendee CSV files"
        self.drop = tk.Label(self, text=f"Drop {types} or a folder here\n\nor click to add files",
                             background="#eaf3f7", foreground="#17596e", font=("Segoe UI", 13),
                             relief="flat", highlightthickness=1, highlightbackground="#aacbd7",
                             height=4, cursor="hand2", takefocus=True)
        self.drop.grid(row=1, column=0, sticky="ew", pady=(18, 8))
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self.on_drop)
        self.drop.dnd_bind("<<DropEnter>>", self.enter)
        self.drop.dnd_bind("<<DropLeave>>", lambda e: self.drop.configure(background="#eaf3f7"))
        self.drop.bind("<Button-1>", self.browse)
        self.drop.bind("<Return>", self.browse)
        self.count = tk.StringVar()
        input_bar = ttk.Frame(self)
        input_bar.grid(row=2, column=0, sticky="ew")
        ttk.Label(input_bar, textvariable=self.count, foreground="#536579").pack(side="left")
        self.folder_button = ttk.Button(input_bar, text="Choose folder…", command=self.browse_folder)
        self.folder_button.pack(side="right")
        input_frame = ttk.Frame(self)
        input_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.inputs = tk.Listbox(input_frame, height=4, relief="flat", background="white",
                                 foreground="#182d43", highlightthickness=0)
        input_scroll = ttk.Scrollbar(input_frame, command=self.inputs.yview)
        self.inputs.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side="right", fill="y")
        self.inputs.pack(fill="both", expand=True)
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, sticky="ew", pady=16)
        self.run_button = ttk.Button(bar, text="Run", command=self.run, style="Accent.TButton")
        self.run_button.pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.status = tk.StringVar(value="Ready. Running replaces the previous outputs.")
        ttk.Label(self, textvariable=self.status, wraplength=620).grid(row=5, column=0, sticky="w")
        output = "output/handoff_bundle" if mode == "abstracts" else "webinar/output"
        output_bar = ttk.Frame(self)
        output_bar.grid(row=6, column=0, sticky="ew", pady=(22, 8))
        output_bar.columnconfigure(0, weight=1)
        ttk.Label(output_bar, text=f"Outputs · {output}", foreground="#536579",
                  wraplength=370).grid(row=0, column=0, sticky="w")
        ttk.Button(output_bar, text="Open output folder", command=self.open_output_folder).grid(
            row=0, column=1, sticky="e", padx=(12, 0))
        frame = ttk.Frame(self)
        frame.grid(row=7, column=0, sticky="nsew")
        self.results = tk.Listbox(frame, height=8, relief="flat", background="white",
                                  foreground="#182d43", highlightthickness=0)
        scroll = ttk.Scrollbar(frame, command=self.results.yview)
        self.results.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.results.pack(fill="both", expand=True)
        self.refresh()

    def open_output_folder(self):
        folder = ROOT / ("output/handoff_bundle" if self.mode == "abstracts" else "webinar/output")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(folder))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Could not open output folder", str(exc))

    def refresh(self):
        files = current_inputs(self.mode)
        self.inputs.delete(0, "end")
        for path in files:
            self.inputs.insert("end", str(path.relative_to(input_folder(self.mode))))
        self.folder_button.configure(state="disabled" if self.app.busy else "normal")
        self.count.set(f"{len(files)} files in {input_folder(self.mode).relative_to(ROOT)}/")
        self.results.delete(0, "end")
        for path in useful_outputs(self.mode):
            self.results.insert("end", str(path.relative_to(ROOT)))
        self.run_button.configure(state="disabled" if self.app.busy else "normal")

    def enter(self, event):
        if self.app.busy:
            return REFUSE_DROP
        self.drop.configure(background="#d6eaf2")
        return COPY

    def on_drop(self, event):
        self.drop.configure(background="#eaf3f7")
        if self.app.busy:
            return REFUSE_DROP
        return COPY if self.add(self.tk.splitlist(event.data)) else REFUSE_DROP

    def browse(self, event=None):
        self.choose_inputs(folder=False)

    def browse_folder(self):
        self.choose_inputs(folder=True)

    def choose_inputs(self, folder):
        if self.app.busy:
            return
        try:
            if folder:
                path = filedialog.askdirectory(
                    parent=self, title="Add a folder (includes subfolders)", mustexist=True,
                )
                paths = [path] if path else []
            else:
                patterns = " ".join(f"*{extension}" for suffix in sorted(SUFFIXES[self.mode])
                                    for extension in (suffix, suffix.upper()))
                paths = filedialog.askopenfilenames(parent=self, filetypes=[("Input files", patterns)])
            if paths:
                self.add(paths)
        except (OSError, tk.TclError, ValueError) as exc:
            messagebox.showerror("Could not choose inputs", str(exc))

    def add(self, paths):
        try:
            store_inputs(self.mode, [Path(p) for p in paths])
            self.status.set("Files added. Ready to run.")
            self.refresh()
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not add files", str(exc))
            return False

    def run(self):
        if self.app.busy:
            return
        self.app.busy = True
        for view in self.app.views:
            view.refresh()
        self.progress.start(12)
        self.status.set("Processing…")
        threading.Thread(target=self.worker, daemon=True).start()
        self.after(100, self.poll)

    def worker(self):
        try:
            with contextlib.redirect_stdout(Writer(self.app.events)):
                summary = run_job(self.mode)
            self.app.events.put(("done", summary))
        except Exception as exc:
            self.app.events.put(("error", str(exc)))

    def poll(self):
        for _ in range(100):
            try:
                kind, text = self.app.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if text.startswith(("Collecting", "Converting", "Splitting", "Extracting", "Anonymising", "Processing report")):
                    self.status.set(text)
            else:
                self.app.busy = False
                self.progress.stop()
                self.status.set(text if kind == "done" else "Could not finish. Outputs may be incomplete.")
                for view in self.app.views:
                    view.refresh()
                if kind == "error":
                    messagebox.showerror("Processing stopped", text)
                return
        self.after(100, self.poll)


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("IWA Learn")
        self.geometry("740x720")
        self.minsize(640, 660)
        self.busy = False
        self.events = queue.Queue()
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f5f7fa", foreground="#182d43")
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("TNotebook.Tab", padding=(12, 5))
        style.map(
            "TNotebook.Tab",
            padding=[("selected", (24, 10)), ("!selected", (12, 5))],
            background=[("selected", "#eaf3f7"), ("!selected", "#e3e8ee")],
            foreground=[("selected", "#17596e"), ("!selected", "#536579")],
        )
        style.configure("Accent.TButton", padding=(30, 10), background="#176b87", foreground="white")
        style.map("Accent.TButton", background=[("disabled", "#b9c4cc"), ("active", "#12556b")])
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)
        self.views = []
        for mode, label in [("abstracts", "Abstracts"), ("webinar", "Webinar reports")]:
            view = Workflow(tabs, self, mode)
            self.views.append(view)
            tabs.add(view, text=label)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        if self.busy:
            messagebox.showinfo("Processing", "Please wait for processing to finish.")
        else:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
