"""ターンテーブル描画ウィジェット (マウスで盤を掴んで左右に動かす)。"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets


class TurntableWidget(QtWidgets.QWidget):
    grabbed = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0.0          # 表示用の盤の角度 (度)
        self.touching = False
        self._dx = 0.0
        self._last_x = 0.0
        self.setMinimumSize(280, 280)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    # ---- 入力 ----
    def _center_radius(self):
        r = min(self.width(), self.height()) / 2 - 8
        return QtCore.QPointF(self.width() / 2, self.height() / 2), r

    def mousePressEvent(self, ev):
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        c, r = self._center_radius()
        p = ev.position()
        if math.hypot(p.x() - c.x(), p.y() - c.y()) <= r:
            self.touching = True
            self._last_x = p.x()
            self._dx = 0.0
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.grabbed.emit(True)
            self.update()

    def mouseMoveEvent(self, ev):
        if self.touching:
            x = ev.position().x()
            self._dx += x - self._last_x
            self._last_x = x

    def mouseReleaseEvent(self, ev):
        if self.touching and ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self.touching = False
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self.grabbed.emit(False)
            self.update()

    def consume_dx(self) -> float:
        d, self._dx = self._dx, 0.0
        return d

    # ---- 描画 ----
    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        c, r = self._center_radius()
        p.setPen(QtGui.QPen(QtGui.QColor("#ff9f1c" if self.touching else "#555b66"), 3))
        p.setBrush(QtGui.QColor("#101216"))
        p.drawEllipse(c, r, r)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for k in range(1, 9):  # 溝
            rr = r * (0.36 + 0.07 * k)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 18), 1))
            p.drawEllipse(c, rr, rr)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor("#c0392b"))
        p.drawEllipse(c, r * 0.3, r * 0.3)  # レーベル
        p.save()
        p.translate(c)
        p.rotate(self.angle)
        p.setPen(QtGui.QPen(QtGui.QColor("#f5f5f5"), 3))
        p.drawLine(QtCore.QPointF(0, -r * 0.12), QtCore.QPointF(0, -r * 0.95))  # 回転マーカー
        p.setPen(QtGui.QPen(QtGui.QColor("#f5f5f5"), 2))
        p.drawLine(QtCore.QPointF(-r * 0.12, 0), QtCore.QPointF(r * 0.12, 0))
        p.restore()
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor("#dddddd"))
        p.drawEllipse(c, 4, 4)
