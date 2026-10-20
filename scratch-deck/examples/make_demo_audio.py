"""練習用のデモ音源 demo.wav を作る (ピッチが動くノコギリ波のスタブ + 低音)。"""
import os

import numpy as np
from scipy.io import wavfile

SR = 44100
t = np.arange(int(SR * 4.0)) / SR
f = 220 * (1 + 0.5 * np.sin(2 * np.pi * 0.5 * t))           # 揺れる基音
ph = 2 * np.pi * np.cumsum(f) / SR
saw = sum(np.sin(k * ph) / k for k in range(1, 12)) * 0.35    # 倍音の多い音 (スクラッチ向き)
env = np.where((t % 1.0) < 0.5, 1.0, 0.0) * np.exp(-((t % 1.0) * 4)) + 0.15
bass = 0.25 * np.sin(2 * np.pi * 55 * t)
x = (saw * env + bass).astype(np.float32)
x *= 0.8 / np.max(np.abs(x))
out = os.path.join(os.path.dirname(__file__), "demo.wav")
wavfile.write(out, SR, np.stack([x, x], 1))
print("wrote", out)
