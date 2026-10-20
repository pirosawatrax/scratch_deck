"""プリセット生成。`python src/presets.py` で presets/*.json を書き出す。"""
from __future__ import annotations

import math
import os

import numpy as np

from automation import Automation, simplify

TAU = 2 * math.pi


def _sampled(fn, dur, dt=0.005, eps=0.04):
    t = np.arange(0, dur + dt / 2, dt)
    return simplify(np.column_stack([t, [fn(x) for x in t]]), eps)


def baby():
    return Automation(_sampled(lambda t: 3.0 * math.sin(TAU * t / 0.5), 2.0), name="Baby Scratch")


def chirp():
    def fn(t):
        ph = (t % 0.3) / 0.3
        return 3.5 * math.sin(math.pi * ph / 0.35) if ph < 0.35 \
            else -1.885 * math.sin(math.pi * (ph - 0.35) / 0.65)
    return Automation(_sampled(fn, 1.5), name="Chirp")


def transform():  # クロスフェーダーの代わりに「止める」ことでゲートを再現
    pts = []
    for k in range(8):
        t0 = k * 0.24
        pts += [[t0, 0], [t0 + 0.005, 1], [t0 + 0.095, 1], [t0 + 0.1, 0]]
    pts.append([8 * 0.24, 0])
    return Automation(pts, mode="linear", name="Transform")


def scribble():
    return Automation(_sampled(lambda t: 2.2 * (1 - 0.3 * t) * math.sin(TAU * t / 0.07), 1.0, 0.003, 0.05),
                      name="Scribble")


def crab():
    pts = []
    for k in range(4):
        t0 = k * 0.1
        pts += [[t0, 0], [t0 + 0.01, 2.5], [t0 + 0.04, 2.5], [t0 + 0.05, 0]]
    pts += [[0.4, 0], [0.45, -4], [0.55, -4], [0.6, 0]]
    return Automation(pts, mode="linear", name="Crab")


def orbit():
    fn = lambda t: 2.8 * math.sin(TAU * t / 0.6) + 1.6 * math.sin(TAU * t / 0.3 + 0.5)
    return Automation(_sampled(fn, 1.8), name="Orbit")


ALL = {"BabyScratch": baby, "Chirp": chirp, "Transform": transform,
       "Scribble": scribble, "Crab": crab, "Orbit": orbit}


def write_all(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in ALL.items():
        fn().save(os.path.join(out_dir, f"{name}.json"))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_all(os.path.join(here, "..", "presets"))
    print("presets written")
