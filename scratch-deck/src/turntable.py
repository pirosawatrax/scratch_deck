"""ターンテーブルの物理モデル (慣性・モーター・ブレーキ・スリップマット)。

速度は「再生速度の倍率」。33 1/3 rpm = 1.0、45 rpm = 1.35。
パラメータを変えると、軽いプラスチック機から重いダイレクトドライブ機まで表現できる。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

BASE_RPM = 100.0 / 3.0
REV_PER_SEC_1X = BASE_RPM / 60.0  # 等速時の回転数 (回/秒)


@dataclass
class TurntableParams:
    rpm: float = BASE_RPM      # 33.333 または 45
    inertia: float = 0.015     # 秒。大きいほど重く、手の動きに遅れて追従する
    grip: float = 0.9          # 0〜1。スリップマットの摩擦。小さいと手が滑って追従が鈍い
    startup_time: float = 0.35 # 秒。モーターが等速へ戻る/立ち上がる速さ (小さいほどトルクが強い)
    brake_time: float = 1.2    # 秒。モーターOFF時に等速から止まるまで

    @property
    def target_speed(self) -> float:
        return self.rpm / BASE_RPM


class Turntable:
    def __init__(self, params: TurntableParams | None = None):
        self.p = params or TurntableParams()
        self.w = 0.0            # 現在の盤の速度(倍率)
        self.motor_on = False

    def step(self, dt: float, hand_v: float, touching: bool) -> float:
        p, w = self.p, self.w
        if touching:
            # 手が盤を掴む: 摩擦と慣性で決まる時定数で手の速度に追従
            tau = max(1e-3, p.inertia / max(p.grip, 0.05))
            w += (hand_v - w) * (1.0 - math.exp(-dt / tau))
        elif self.motor_on:
            # モーターが一定トルクで目標速度へ加速/減速
            target = p.target_speed
            step = target / max(p.startup_time, 1e-3) * dt
            w += max(-step, min(step, target - w))
        else:
            # モーターOFF: ブレーキで0へ
            step = 1.0 / max(p.brake_time, 1e-3) * dt
            w += max(-step, min(step, -w))
        self.w = w
        return w
