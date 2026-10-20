"""手の動き(速度)の記録。ブロックごとに [時間, 速度] を貯め、終了時に点を間引く。"""
from __future__ import annotations

from automation import Automation, simplify


class Recorder:
    def __init__(self):
        self.active = False
        self.samples: list[tuple[float, float]] = []
        self.start_pos = 0.0
        self.n = 0

    def start(self, start_pos_sec: float, v0: float = 0.0):
        self.samples = [(0.0, float(v0))]
        self.start_pos = float(start_pos_sec)
        self.n = 0
        self.active = True

    def push(self, frames: int, sr: int, v: float):
        self.n += frames
        self.samples.append((self.n / sr, float(v)))

    def stop(self, eps: float = 0.02) -> Automation:
        self.active = False
        pts = simplify(self.samples, eps) if len(self.samples) >= 2 else self.samples
        if len(pts) < 2:
            return Automation(start_pos=self.start_pos)
        return Automation([list(map(float, p)) for p in pts], start_pos=self.start_pos, name="Recorded")
