"""Guards against slow Tk canvas repaints.

Tk on Windows draws polylines wider than 1 px with geometric GDI pens, which makes an
1800-point waveform line take tens of milliseconds per frame and makes the window
choppy. This test repaints a line the way the app does and checks it stays fast.
"""
import time
import tkinter as tk
import unittest

import numpy as np

from waveform.app import LINE_WIDTH, _wave_coords

POINTS = 900          # canvas width in px; min/max mode yields 2 points per column
FRAME_BUDGET_MS = 8.0 # must leave room for three lines inside a 16 ms frame


class CanvasRepaintTests(unittest.TestCase):
    def test_wide_waveform_line_repaints_within_budget(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:  # no display available
            self.skipTest(f"no display: {exc}")
        root.geometry(f"{POINTS}x300")
        canvas = tk.Canvas(root, width=POINTS, height=300, highlightthickness=0)
        canvas.pack()
        line = canvas.create_line(0, 0, 0, 0, width=LINE_WIDTH)
        root.update()
        rng = np.random.default_rng(0)
        samples = rng.uniform(-0.8, 0.8, 1920).astype(np.float32)
        timings = []
        for _ in range(10):
            canvas.coords(line, *_wave_coords(samples, POINTS, 0, 300))
            t0 = time.perf_counter()
            root.update_idletasks()  # forces the pending redraw
            timings.append((time.perf_counter() - t0) * 1000)
            samples = np.roll(samples, 37)
        root.destroy()
        median = float(np.median(timings))
        self.assertLess(median, FRAME_BUDGET_MS,
                        f"canvas repaint took {median:.1f} ms (line width {LINE_WIDTH})")


if __name__ == "__main__":
    unittest.main()
