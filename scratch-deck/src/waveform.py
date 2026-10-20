"""波形表示 (pyqtgraph)。クリックで頭出し位置を指定する。"""
from __future__ import annotations

import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np  # noqa: E402
import pyqtgraph as pg  # noqa: E402
from PySide6 import QtCore  # noqa: E402

from audio_engine import compute_envelope  # noqa: E402


class WaveformView(pg.PlotWidget):
    seek = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#14161a")
        pi = self.plotItem
        pi.setMenuEnabled(False)
        pi.setMouseEnabled(x=False, y=False)
        pi.hideButtons()
        pi.hideAxis("left")
        pi.setLabel("bottom", "音源の位置 (秒)  ※クリックで頭出し位置を設定")
        pen = pg.mkPen("#4cc9f0", width=1)
        self.top = pi.plot(pen=pen)
        self.bot = pi.plot(pen=pen)
        pi.addItem(pg.FillBetweenItem(self.top, self.bot, brush=pg.mkBrush(76, 201, 240, 90)))
        self.cue = pg.InfiniteLine(angle=90, pen=pg.mkPen("#ff9f1c", width=2, style=QtCore.Qt.PenStyle.DashLine))
        self.head = pg.InfiniteLine(angle=90, pen=pg.mkPen("#ffffff", width=1))
        pi.addItem(self.cue)
        pi.addItem(self.head)
        self._dur = 1.0

    def set_clip(self, clip):
        mn, mx, k = compute_envelope(clip.audio)
        x = np.arange(len(mn)) * k / clip.sr
        self.top.setData(x, mx)
        self.bot.setData(x, mn)
        self._dur = max(clip.duration, 0.1)
        self.plotItem.setXRange(0, self._dur, padding=0)
        self.plotItem.setYRange(-1, 1, padding=0.02)

    def set_playhead(self, sec: float):
        self.head.setValue(sec)

    def set_cue(self, sec: float):
        self.cue.setValue(sec)

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            sp = self.mapToScene(ev.position().toPoint())
            x = self.plotItem.vb.mapSceneToView(sp).x()
            self.seek.emit(float(min(max(x, 0.0), self._dur)))
