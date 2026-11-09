"""Graphical interface built with Tkinter (ships with Python, no extra deps)."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert,
    default_output_path,
)

# Human-readable choices shown in the drop-downs -> internal values.
FORMAT_CHOICES = {
    "MP4 — plays everywhere (recommended)": "mp4",
    "MKV — audio unchanged (lossless)": "mkv",
}
RESOLUTION_CHOICES = {
    "854 px — fastest": 854,
    "1280 px (720p) — fast": 1280,
    "1920 px (1080p)": 1920,
    "Original image size": None,
}
DEFAULT_RESOLUTION = "1280 px (720p) — fast"


def options_from_choices(format_label: str, resolution_label: str) -> ConversionOptions:
    """Translate the drop-down labels into :class:`ConversionOptions`."""
    return ConversionOptions(
        output_format=FORMAT_CHOICES[format_label],
        max_width=RESOLUTION_CHOICES[resolution_label],
        overwrite=True,  # the save dialog already asked about overwriting
    )


def _patterns(extensions: tuple[str, ...]) -> str:
    return " ".join(f"*{ext}" for ext in extensions)


class App(ttk.Frame):
    """Main window."""

    def __init__(self, master: tk.Tk | tk.Toplevel) -> None:
        super().__init__(master, padding=16)
        self.master = master
        master.title(f"Audio to Video {__version__}")
        master.minsize(560, 0)
        master.protocol("WM_DELETE_WINDOW", self._on_close)

        self.audio_var = tk.StringVar()
        self.image_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.format_var = tk.StringVar(value=next(iter(FORMAT_CHOICES)))
        self.resolution_var = tk.StringVar(value=DEFAULT_RESOLUTION)
        self.status_var = tk.StringVar(value="Choose an audio file and an image")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._events: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None

        self._build()
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        self._poll_job = self.after(100, self._poll_events)

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        row = 0
        for label, var, command in (
            ("Audio (mp3/wav/flac):", self.audio_var, self.choose_audio),
            ("Image:", self.image_var, self.choose_image),
            ("Save as:", self.output_var, self.choose_output),
        ):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(self, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Button(self, text="Browse…", command=command).grid(row=row, column=2)
            row += 1

        ttk.Label(self, text="Format:").grid(row=row, column=0, sticky="w", pady=4)
        self.format_box = ttk.Combobox(
            self, textvariable=self.format_var, values=list(FORMAT_CHOICES), state="readonly"
        )
        self.format_box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        self.format_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_output_extension())
        row += 1

        ttk.Label(self, text="Video width:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            self, textvariable=self.resolution_var, values=list(RESOLUTION_CHOICES), state="readonly"
        ).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1

        self.progress = ttk.Progressbar(self, variable=self.progress_var, maximum=1.0)
        self.progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(16, 4))
        row += 1
        ttk.Label(self, textvariable=self.status_var).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        buttons = ttk.Frame(self)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right")
        self.convert_button = ttk.Button(buttons, text="Create video", command=self.start)
        self.convert_button.pack(side="right", padx=8)

    # ---------------------------------------------------------------- dialogs
    def choose_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an audio file",
            filetypes=[("Audio", _patterns(AUDIO_EXTENSIONS)), ("All files", "*.*")],
        )
        if path:
            self.set_audio(path)

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images", _patterns(IMAGE_EXTENSIONS)), ("All files", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def choose_output(self) -> None:
        fmt = FORMAT_CHOICES[self.format_var.get()]
        current = self.output_var.get()
        path = filedialog.asksaveasfilename(
            title="Save video as",
            defaultextension="." + fmt,
            initialdir=str(Path(current).parent) if current else None,
            initialfile=Path(current).name if current else None,
            filetypes=[(fmt.upper(), "*." + fmt)],
        )
        if path:
            self.output_var.set(path)

    def set_audio(self, path: str) -> None:
        """Remember the audio file and suggest an output name next to it."""
        self.audio_var.set(path)
        if not self.output_var.get():
            fmt = FORMAT_CHOICES[self.format_var.get()]
            self.output_var.set(str(default_output_path(Path(path), fmt)))

    def _sync_output_extension(self) -> None:
        current = self.output_var.get()
        if current:
            fmt = FORMAT_CHOICES[self.format_var.get()]
            self.output_var.set(str(Path(current).with_suffix("." + fmt)))

    # ------------------------------------------------------------- conversion
    def start(self) -> None:
        audio = self.audio_var.get().strip()
        image = self.image_var.get().strip()
        output = self.output_var.get().strip()
        if not audio or not image:
            messagebox.showwarning("Missing files", "Choose an audio file and an image.")
            return
        if not output:
            fmt = FORMAT_CHOICES[self.format_var.get()]
            output = str(default_output_path(Path(audio), fmt))
            self.output_var.set(output)
        if Path(output).exists() and not messagebox.askyesno(
            "File exists", f"The file already exists:\n{output}\n\nOverwrite it?"
        ):
            return

        options = options_from_choices(self.format_var.get(), self.resolution_var.get())
        self._cancel.clear()
        self._set_running(True)
        self.progress_var.set(0.0)
        self.status_var.set("Converting…")
        self._worker = threading.Thread(
            target=self._run, args=(audio, image, output, options), daemon=True
        )
        self._worker.start()

    def _run(self, audio: str, image: str, output: str, options: ConversionOptions) -> None:
        # Runs in a background thread: talk to Tk only through the queue.
        try:
            result = convert(
                audio,
                image,
                output,
                options,
                progress=lambda f: self._events.put(("progress", f)),
                cancel_event=self._cancel,
            )
            self._events.put(("done", result))
        except ConversionCancelled:
            self._events.put(("cancelled", None))
        except ConversionError as exc:
            self._events.put(("error", str(exc)))
        except Exception as exc:  # unexpected: still report instead of hanging
            self._events.put(("error", f"Unexpected error: {exc!r}"))

    def cancel(self) -> None:
        self._cancel.set()
        self.status_var.set("Cancelling…")

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self._events.get_nowait()
                self._handle_event(kind, value)
        except queue.Empty:
            pass
        self._poll_job = self.after(100, self._poll_events)

    def destroy(self) -> None:
        self.after_cancel(self._poll_job)
        super().destroy()

    def _handle_event(self, kind: str, value) -> None:
        if kind == "progress":
            self.progress_var.set(value)
            self.status_var.set(f"Converting… {value * 100:.0f}%")
            return
        self._set_running(False)
        if kind == "done":
            self.progress_var.set(1.0)
            self.status_var.set(f"Done: {value}")
            if messagebox.askyesno("Done", f"Video created:\n{value}\n\nOpen the folder?"):
                open_folder(Path(value).parent)
        elif kind == "cancelled":
            self.progress_var.set(0.0)
            self.status_var.set("Cancelled")
        elif kind == "error":
            self.status_var.set("Error")
            messagebox.showerror("Error", value)

    def _set_running(self, running: bool) -> None:
        self.convert_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            if not messagebox.askyesno("Quit", "A conversion is still running. Stop it and quit?"):
                return
            self._cancel.set()
            self._worker.join(timeout=5)
        self.master.destroy()


def open_folder(path: Path) -> None:
    """Open a folder in the system file manager."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _enable_high_dpi() -> None:
    """Render crisp text on scaled Windows displays instead of a blurry bitmap."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def main() -> None:
    _enable_high_dpi()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
