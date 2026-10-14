"""Tkinter window that draws live system audio: waveform, stereo view and spectrum."""
from __future__ import annotations

import tkinter as tk

import numpy as np

from .capture import LoopbackCapture, downmix_to_mono
from .spectrum import SpectrumAnalyzer

BG = "#101216"
BAR_BG = "#181b21"
LINE = "#3ddc97"
LINE_L = "#4fc3f7"
LINE_R = "#ff8a65"
SPEC = "#b388ff"
AXIS = "#2a2f38"
TEXT = "#8b93a1"
FONT = ("Segoe UI", 10)
SMALL = ("Segoe UI", 8)
LINE_WIDTH = 1  # keep at 1: Tk on Windows draws wider polylines with slow GDI pens (~30 ms/frame)

WINDOW_MS = 40          # how much audio the waveform views show across the width
FRAME_MS = 16           # redraw interval (~60 fps)
DEVICE_POLL_MS = 2000   # how often to check for a device change
SPECTRUM_BANDS = 48
LABEL_H = 16            # space reserved at the top of each panel for its label


def _wave_coords(samples: np.ndarray, w: int, y0: float, y1: float) -> list[float]:
    """Polyline coords for `samples` filling the box x=0..w, y=y0..y1."""
    n = len(samples)
    mid = (y0 + y1) / 2
    half = (y1 - y0) / 2
    if n > w:
        # More samples than columns: draw min/max per column so transients survive.
        per_col = n // w
        cols = samples[: per_col * w].reshape(w, per_col)
        ys = np.empty(2 * w)
        ys[0::2] = mid - cols.min(axis=1) * half
        ys[1::2] = mid - cols.max(axis=1) * half
        xs = np.repeat(np.arange(w, dtype=np.float64), 2)
    else:
        xs = np.linspace(0, w - 1, max(n, 2))
        ys = mid - np.resize(samples, max(n, 2)) * half
    ys = np.clip(ys, y0 + 1, y1 - 1)
    coords = np.empty(2 * len(xs))
    coords[0::2] = xs
    coords[1::2] = ys
    return coords.tolist()


class WaveformApp:
    PANELS = (("wave", "Waveform", "1"), ("stereo", "Stereo", "2"), ("spectrum", "Spectrum", "3"))

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Waveform Visualizer")
        root.configure(bg=BG)
        root.geometry("900x520")
        root.minsize(320, 200)

        self.gain = 1.0
        self.topmost = False
        self.error = ""

        # -- toolbar with the three view toggles ---------------------------------
        bar = tk.Frame(root, bg=BAR_BG)
        bar.pack(side=tk.TOP, fill=tk.X)
        self.enabled: dict[str, tk.BooleanVar] = {}
        for key, label, hotkey in self.PANELS:
            var = tk.BooleanVar(value=True)
            self.enabled[key] = var
            tk.Checkbutton(bar, text=f"{label} ({hotkey})", variable=var, bg=BAR_BG, fg=TEXT,
                           selectcolor=BG, activebackground=BAR_BG, activeforeground="white",
                           highlightthickness=0, font=FONT, cursor="hand2",
                           command=self._layout_changed).pack(side=tk.LEFT, padx=6, pady=3)
            root.bind(hotkey, lambda e, k=key: self.toggle(k))
        self.status_label = tk.Label(bar, bg=BAR_BG, fg=TEXT, font=FONT, anchor="e")
        self.status_label.pack(side=tk.RIGHT, padx=8)

        # -- canvas and its drawable items ---------------------------------------
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        c = self.canvas
        self.items = {
            "wave": {"axis": c.create_line(0, 0, 0, 0, fill=AXIS),
                     "line": c.create_line(0, 0, 0, 0, fill=LINE, width=LINE_WIDTH),
                     "label": c.create_text(8, 0, anchor="nw", fill=TEXT, font=SMALL, text="MONO")},
            "stereo": {"axis_l": c.create_line(0, 0, 0, 0, fill=AXIS),
                       "axis_r": c.create_line(0, 0, 0, 0, fill=AXIS),
                       "line_l": c.create_line(0, 0, 0, 0, fill=LINE_L, width=LINE_WIDTH),
                       "line_r": c.create_line(0, 0, 0, 0, fill=LINE_R, width=LINE_WIDTH),
                       "label": c.create_text(8, 0, anchor="nw", fill=TEXT, font=SMALL, text="STEREO  L / R")},
            "spectrum": {"bars": [c.create_rectangle(0, 0, 0, 0, fill=SPEC, outline="")
                                  for _ in range(SPECTRUM_BANDS)],
                         "label": c.create_text(8, 0, anchor="nw", fill=TEXT, font=SMALL,
                                                text="SPECTRUM  30 Hz - 20 kHz")},
        }
        self.separators = [c.create_line(0, 0, 0, 0, fill=AXIS) for _ in range(len(self.PANELS))]
        self.hint = c.create_text(0, 0, anchor="center", fill=TEXT, font=FONT,
                                  text="All views are off. Enable one from the toolbar or press 1, 2 or 3.")

        root.bind("<Escape>", lambda e: self.quit())
        root.bind("<Key-t>", lambda e: self.toggle_topmost())
        root.bind("<Key-T>", lambda e: self.toggle_topmost())
        root.bind("<Key-plus>", lambda e: self.change_gain(1.25))
        root.bind("<Key-equal>", lambda e: self.change_gain(1.25))
        root.bind("<Key-minus>", lambda e: self.change_gain(0.8))
        root.protocol("WM_DELETE_WINDOW", self.quit)

        self.capture = LoopbackCapture()
        self.analyzer = SpectrumAnalyzer(self.capture.sample_rate, SPECTRUM_BANDS)
        self._start_capture()
        self._draw()
        self._poll_device()

    # -- capture ----------------------------------------------------------
    def _start_capture(self):
        try:
            self.capture.start()
            self.error = ""
        except Exception as exc:  # show the problem instead of dying
            self.error = f"Audio capture failed: {exc}"
        if self.analyzer.sample_rate != self.capture.sample_rate:
            self.analyzer = SpectrumAnalyzer(self.capture.sample_rate, SPECTRUM_BANDS)
        self._update_status()

    def _poll_device(self):
        if not self.capture.is_running() or self.capture.default_device_changed():
            self._start_capture()
        self.root.after(DEVICE_POLL_MS, self._poll_device)

    # -- ui state ---------------------------------------------------------
    def toggle(self, key: str):
        self.enabled[key].set(not self.enabled[key].get())
        self._layout_changed()

    def visible_panels(self) -> list[str]:
        return [k for k, _, _ in self.PANELS if self.enabled[k].get()]

    def _layout_changed(self):
        shown = set(self.visible_panels())
        for key, items in self.items.items():
            state = "normal" if key in shown else "hidden"
            for item in items.values():
                for i in (item if isinstance(item, list) else [item]):
                    self.canvas.itemconfigure(i, state=state)
        self.canvas.itemconfigure(self.hint, state="hidden" if shown else "normal")

    def _update_status(self):
        if self.error:
            text = self.error
        else:
            text = f"{self.capture.device_name}   |   gain {self.gain:.2f}x   |   Esc quit, T on top, +/- gain"
        self.status_label.configure(text=text)

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)

    def change_gain(self, factor: float):
        self.gain = float(np.clip(self.gain * factor, 0.05, 50.0))
        self._update_status()

    # -- drawing ----------------------------------------------------------
    def _draw(self):
        c = self.canvas
        w = max(2, c.winfo_width())
        h = max(2, c.winfo_height())
        panels = self.visible_panels()
        for sep in self.separators:
            c.coords(sep, 0, 0, 0, 0)

        if not panels:
            c.coords(self.hint, w / 2, h / 2)
        else:
            n = max(2, int(self.capture.sample_rate * WINDOW_MS / 1000))
            frames = self.capture.buffer.latest(n) * self.gain
            mono = downmix_to_mono(frames)
            panel_h = h / len(panels)
            for i, key in enumerate(panels):
                y0 = i * panel_h
                y1 = y0 + panel_h
                c.coords(self.items[key]["label"], 8, y0 + 2)
                if i > 0:
                    c.coords(self.separators[i], 0, y0, w, y0)
                body0 = y0 + LABEL_H
                if key == "wave":
                    self._draw_wave(mono, w, body0, y1)
                elif key == "stereo":
                    self._draw_stereo(frames, w, body0, y1)
                else:
                    self._draw_spectrum(mono, w, body0, y1)
        self.root.after(FRAME_MS, self._draw)

    def _draw_wave(self, mono, w, y0, y1):
        it = self.items["wave"]
        mid = (y0 + y1) / 2
        self.canvas.coords(it["axis"], 0, mid, w, mid)
        self.canvas.coords(it["line"], *_wave_coords(mono, w, y0, y1))

    def _draw_stereo(self, frames, w, y0, y1):
        it = self.items["stereo"]
        left = frames[:, 0]
        right = frames[:, 1] if frames.shape[1] > 1 else left
        mid = (y0 + y1) / 2
        for axis, line, data, a, b in (("axis_l", "line_l", left, y0, mid),
                                       ("axis_r", "line_r", right, mid, y1)):
            m = (a + b) / 2
            self.canvas.coords(it[axis], 0, m, w, m)
            self.canvas.coords(it[line], *_wave_coords(data, w, a, b))

    def _draw_spectrum(self, mono, w, y0, y1):
        # Use a longer block than the waveform window so low bands resolve.
        block = downmix_to_mono(self.capture.buffer.latest(self.analyzer.fft_size)) * self.gain
        levels = self.analyzer.update(block)
        bars = self.items["spectrum"]["bars"]
        gap = 2
        bw = (w - gap) / len(bars)
        height = y1 - y0 - 4
        for i, bar in enumerate(bars):
            x0 = gap + i * bw
            top = y1 - 2 - levels[i] * height
            self.canvas.coords(bar, x0, top, x0 + bw - gap, y1 - 2)

    def quit(self):
        self.capture.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    WaveformApp(root)
    root.mainloop()
