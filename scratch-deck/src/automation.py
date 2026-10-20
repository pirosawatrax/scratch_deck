"""オートメーション: [時間, 速度] の点列と補間 (linear / bezier / monotone)。"""
from __future__ import annotations

import json

import numpy as np
from scipy.interpolate import PchipInterpolator

MIN_GAP = 1e-3
MODES = ("bezier", "linear", "monotone")


def simplify(points, eps: float = 0.02) -> np.ndarray:
    """Ramer-Douglas-Peucker。速度方向の誤差が eps 以下の点を間引く。"""
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    if n <= 2:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        t = pts[a + 1:b, 0]
        chord = np.interp(t, [pts[a, 0], pts[b, 0]], [pts[a, 1], pts[b, 1]])
        d = np.abs(pts[a + 1:b, 1] - chord)
        k = int(np.argmax(d))
        if d[k] > eps:
            m = a + 1 + k
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return pts[keep]


class Automation:
    def __init__(self, points=None, start_pos: float = 0.0, mode: str = "bezier", name: str = ""):
        self.points = [[float(t), float(v)] for t, v in points] if points is not None \
            else [[0.0, 0.0], [1.0, 0.0]]
        self.start_pos = float(start_pos)  # 音源上の開始位置 (秒)
        self.mode = mode if mode in MODES else "bezier"
        self.name = name
        self._fix()

    # ---- 編集 ----
    def _fix(self):
        self.points.sort(key=lambda p: p[0])
        if self.points:
            self.points[0][0] = max(0.0, self.points[0][0])
        for i in range(1, len(self.points)):
            if self.points[i][0] < self.points[i - 1][0] + MIN_GAP:
                self.points[i][0] = self.points[i - 1][0] + MIN_GAP

    @property
    def duration(self) -> float:
        return self.points[-1][0] if self.points else 0.0

    def add_point(self, t: float, v: float) -> int:
        self.points.append([max(0.0, float(t)), float(v)])
        self._fix()
        return min(range(len(self.points)), key=lambda i: abs(self.points[i][0] - t))

    def move_point(self, i: int, t: float, v: float) -> int:
        lo = self.points[i - 1][0] + MIN_GAP if i > 0 else 0.0
        hi = self.points[i + 1][0] - MIN_GAP if i < len(self.points) - 1 else float("inf")
        self.points[i] = [min(max(float(t), lo), hi), float(v)]
        return i

    def remove_point(self, i: int) -> bool:
        if len(self.points) <= 2:
            return False
        del self.points[i]
        return True

    # ---- 評価 ----
    def evaluate(self, t, mode: str | None = None) -> np.ndarray:
        mode = mode or self.mode
        T = np.array([p[0] for p in self.points])
        V = np.array([p[1] for p in self.points])
        t = np.asarray(t, dtype=np.float64)
        if len(T) == 1:
            return np.full_like(t, V[0])
        tc = np.clip(t, T[0], T[-1])
        if mode == "linear":
            return np.interp(tc, T, V)
        if mode == "monotone":
            return PchipInterpolator(T, V)(tc)
        # bezier: Catmull-Rom 接線のエルミート(= 3次ベジェ)。ハンドルは時間方向に1/3
        m = np.empty_like(V)
        m[1:-1] = (V[2:] - V[:-2]) / (T[2:] - T[:-2])
        m[0] = (V[1] - V[0]) / (T[1] - T[0])
        m[-1] = (V[-1] - V[-2]) / (T[-1] - T[-2])
        idx = np.clip(np.searchsorted(T, tc, side="right") - 1, 0, len(T) - 2)
        h = T[idx + 1] - T[idx]
        s = (tc - T[idx]) / h
        s2, s3 = s * s, s * s * s
        return ((2 * s3 - 3 * s2 + 1) * V[idx] + (s3 - 2 * s2 + s) * h * m[idx]
                + (-2 * s3 + 3 * s2) * V[idx + 1] + (s3 - s2) * h * m[idx + 1])

    def curve(self, sr: int, tail: float = 0.0) -> np.ndarray:
        """出力サンプルごとの速度配列 (先頭は t=0)。"""
        n = max(1, int(round((self.duration + tail) * sr)))
        return self.evaluate(np.arange(n) / sr)

    # ---- 保存 ----
    def to_dict(self) -> dict:
        return {
            "format": "scratchdeck-preset", "version": 1, "name": self.name,
            "mode": self.mode, "start_pos": round(self.start_pos, 4),
            "points": [[round(t, 4), round(v, 4)] for t, v in self.points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Automation":
        return cls(d["points"], d.get("start_pos", 0.0), d.get("mode", "bezier"), d.get("name", ""))

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, path: str) -> "Automation":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
