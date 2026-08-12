"""レベルメーター表示用のCanvasウィジェット(RMS/ピーク)。"""

from __future__ import annotations

import tkinter as tk


class MeterWidget(tk.Canvas):
    def __init__(
        self,
        master: tk.Misc,
        floor_db: float = -60.0,
        width: int = 220,
        height: int = 18,
        **kwargs,
    ):
        super().__init__(
            master, width=width, height=height, bg="#1a1a1a", highlightthickness=0, **kwargs
        )
        self.floor_db = floor_db
        self._width = width
        self._height = height
        self._rms_bar = self.create_rectangle(0, 0, 0, height, fill="#4caf50", width=0)
        self._peak_line = self.create_line(0, 0, 0, height, fill="#f44336", width=2)

    def update_levels(self, rms_dbfs: float, peak_dbfs: float) -> None:
        rms_x = self._ratio(rms_dbfs) * self._width
        peak_x = self._ratio(peak_dbfs) * self._width
        self.coords(self._rms_bar, 0, 0, rms_x, self._height)
        self.coords(self._peak_line, peak_x, 0, peak_x, self._height)

    def _ratio(self, dbfs: float) -> float:
        clamped = max(self.floor_db, min(0.0, dbfs))
        return (clamped - self.floor_db) / (0.0 - self.floor_db)
