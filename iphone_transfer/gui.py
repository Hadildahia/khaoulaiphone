"""The app window (Tkinter, built into Python, keeps the .exe small)."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import device as dev
from .transfer import Summary, run_transfer

DEFAULT_DEST = Path.home() / "Pictures" / "iPhone"


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("iPhone Photo Transfer")
        self.geometry("620x460")
        self.minsize(520, 400)

        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.devices: list[dev.Device] = []

        self.device_var = tk.StringVar()
        self.dest_var = tk.StringVar(value=str(DEFAULT_DEST))
        self.status_var = tk.StringVar(value="Plug in your iPhone with a USB cable.")

        self._build()
        self.refresh_devices()
        self.after(100, self._poll)

    # ---------- layout ----------
    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="iPhone").grid(row=0, column=0, sticky="w", **pad)
        self.device_box = ttk.Combobox(frame, textvariable=self.device_var, state="readonly")
        self.device_box.grid(row=0, column=1, sticky="ew", **pad)
        self.refresh_btn = ttk.Button(frame, text="Refresh", command=self.refresh_devices)
        self.refresh_btn.grid(row=0, column=2, **pad)

        ttk.Label(frame, text="Save to").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.dest_var).grid(row=1, column=1, sticky="ew", **pad)
        self.browse_btn = ttk.Button(frame, text="Choose…", command=self.choose_dest)
        self.browse_btn.grid(row=1, column=2, **pad)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", **pad)
        self.start_btn = ttk.Button(buttons, text="Copy photos and videos", command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=4, column=0, columnspan=3, sticky="w", **pad
        )

        self.log = ScrolledText(frame, height=10, state="disabled", wrap="word")
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew", **pad)
        frame.rowconfigure(5, weight=1)

        ttk.Label(
            frame,
            text="Files already in the folder are skipped, so you can run it again any time.",
            foreground="gray",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=12)

    # ---------- actions ----------
    def write_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_devices(self) -> None:
        try:
            self.devices = dev.find_iphones()
        except Exception as exc:
            self.devices = []
            self.write_log(f"Couldn't look for devices: {exc}")
        names = [d.name for d in self.devices]
        self.device_box["values"] = names
        if names:
            self.device_box.current(0)
            self.status_var.set("iPhone found. Unlock it and tap Trust if asked.")
        else:
            self.device_var.set("")
            self.status_var.set(
                "No iPhone found. Plug it in, unlock it, tap Trust, then press Refresh."
            )

    def choose_dest(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_var.get() or str(Path.home()))
        if folder:
            self.dest_var.set(folder)

    def _set_busy(self, busy: bool) -> None:
        normal = "disabled" if busy else "normal"
        for w in (self.start_btn, self.refresh_btn, self.browse_btn):
            w.configure(state=normal)
        self.device_box.configure(state="disabled" if busy else "readonly")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def start(self) -> None:
        idx = self.device_box.current()
        if idx < 0 or idx >= len(self.devices):
            messagebox.showinfo("No iPhone", "Plug in your iPhone, unlock it, then press Refresh.")
            return
        dest = Path(self.dest_var.get().strip() or DEFAULT_DEST)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Can't use this folder", str(exc))
            return

        self.cancel.clear()
        self.progress["value"] = 0
        self._set_busy(True)
        device = self.devices[idx]
        self.write_log(f"Copying from {device.name} to {dest}")

        def work() -> None:
            report = lambda *ev: self.events.put(ev)
            try:
                summary = run_transfer(device, dest, self.cancel, report)
                report("done", summary, dest)
            except dev.DeviceError as exc:
                report("error", str(exc))
            except Exception as exc:
                report("error", f"Unexpected problem: {exc}")

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.cancel.set()
        self.status_var.set("Stopping after the current file…")

    # ---------- updates from the worker thread ----------
    def _poll(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self.status_var.set(ev[1])
                elif kind == "log":
                    self.write_log(ev[1])
                elif kind == "progress":
                    done, total = ev[1], ev[2]
                    self.progress["maximum"] = max(total, 1)
                    self.progress["value"] = done
                elif kind == "error":
                    self._set_busy(False)
                    self.status_var.set("Stopped.")
                    self.write_log(ev[1])
                    messagebox.showwarning("iPhone Photo Transfer", ev[1])
                elif kind == "done":
                    self._finish(ev[1], ev[2])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, s: Summary, dest: Path) -> None:
        self._set_busy(False)
        head = "Stopped." if s.cancelled else "Done."
        text = (
            f"{head} Copied {s.copied} new files ({_size(s.bytes_copied)}), "
            f"skipped {s.skipped} already copied"
            + (f", {len(s.failed)} couldn't be copied." if s.failed else ".")
        )
        self.status_var.set(text)
        self.write_log(text)
        if s.failed:
            self.write_log("Files that failed are listed above. Run the copy again to retry them.")
        if s.copied and messagebox.askyesno("iPhone Photo Transfer", text + "\n\nOpen the folder?"):
            os.startfile(dest)


def main() -> None:
    App().mainloop()
