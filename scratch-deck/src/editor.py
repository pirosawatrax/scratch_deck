"""オートメーション編集: クリックで点追加 / ドラッグで移動 / 右クリックで削除。"""
from __future__ import annotations

import math
import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import numpy as np  # noqa: E402
import pyqtgraph as pg  # noqa: E402
from PySide6 import QtCore  # noqa: E402

from automation import Automation  # noqa: E402

HIT_PX = 12.0


class AutomationEditor(pg.PlotWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground("#14161a")
        pi = self.plotItem
        self.vb = pi.vb
        pi.setMenuEnabled(False)
        pi.setMouseEnabled(x=False, y=False)
        pi.hideButtons()
        pi.showGrid(x=True, y=True, alpha=0.15)
        pi.setLabel("left", "速度 (×)  負=逆再生")
        pi.setLabel("bottom", "時間 (秒)  ※クリック:追加 / ドラッグ:移動 / 右クリック:削除")
        pi.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#555b66", width=1)))
        self.line = pi.plot(pen=pg.mkPen("#ff9f1c", width=2))
        self.scatter = pg.ScatterPlotItem(size=11, pen=pg.mkPen("#ffffff"), brush=pg.mkBrush("#ff9f1c"))
        pi.addItem(self.scatter)
        self.head = pg.InfiniteLine(angle=90, pen=pg.mkPen("#ffffff", width=1))
        self.head.setVisible(False)
        pi.addItem(self.head)
        self.auto = Automation()
        self._drag = None
        self.refresh(rescale=True)

    # ---- 状態 ----
    def set_automation(self, auto: Automation):
        self.auto = auto
        self.refresh(rescale=True)
        self.changed.emit()

    def set_mode(self, mode: str):
        self.auto.mode = mode
        self.refresh()
        self.changed.emit()

    def set_playhead(self, sec: float | None):
        self.head.setVisible(sec is not None)
        if sec is not None:
            self.head.setValue(sec)

    def refresh(self, rescale: bool = False):
        a = self.auto
        dur = max(a.duration, 0.1)
        t = np.linspace(0, dur, max(200, int(dur * 400)))
        self.line.setData(t, a.evaluate(t))
        self.scatter.setData(x=[p[0] for p in a.points], y=[p[1] for p in a.points])
        if rescale:
            ymax = max(3.0, max(abs(p[1]) for p in a.points) * 1.2)
            self.plotItem.setXRange(0, max(1.0, dur * 1.25), padding=0)
            self.plotItem.setYRange(-ymax, ymax, padding=0)

    # ---- マウス ----
    def _view_xy(self, ev):
        p = self.vb.mapSceneToView(self.mapToScene(ev.position().toPoint()))
        return p.x(), p.y()

    def _hit(self, ev):
        sp = self.mapToScene(ev.position().toPoint())
        best, bd = None, HIT_PX
        for i, (t, v) in enumerate(self.auto.points):
            q = self.vb.mapViewToScene(QtCore.QPointF(t, v))
            d = math.hypot(q.x() - sp.x(), q.y() - sp.y())
            if d < bd:
                best, bd = i, d
        return best

    def mousePressEvent(self, ev):
        i = self._hit(ev)
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if i is None:
                x, y = self._view_xy(ev)
                i = self.auto.add_point(x, y)
            self._drag = i
            self.refresh()
        elif ev.button() == QtCore.Qt.MouseButton.RightButton and i is not None:
            if self.auto.remove_point(i):
                self.refresh()
                self.changed.emit()

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            x, y = self._view_xy(ev)
            self.auto.move_point(self._drag, x, y)
            self.refresh()

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            self.refresh(rescale=True)
            self.changed.emit()
