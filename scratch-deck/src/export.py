"""WAV書き出しとREAPERプロジェクト生成。"""
from __future__ import annotations

import os

import numpy as np

from audio_engine import Clip, render_offline
from automation import Automation

SUBTYPES = ("PCM_24", "PCM_16", "FLOAT")


def write_wav(path: str, data: np.ndarray, sr: int, subtype: str = "PCM_24"):
    try:
        import soundfile as sf
        sf.write(path, data, sr, subtype=subtype)
    except Exception:  # noqa: BLE001  soundfile が無い環境向けの代替 (24bit非対応)
        from scipy.io import wavfile
        if subtype == "PCM_16":
            wavfile.write(path, sr, (np.clip(data, -1, 1) * 32767).astype(np.int16))
        else:
            wavfile.write(path, sr, data.astype(np.float32))


def export_wav(path: str, clip: Clip, auto: Automation, method: str = "sinc",
               subtype: str = "PCM_24", tail: float = 0.3, normalize: bool = True) -> dict:
    v = auto.curve(clip.sr, tail=tail)
    out = render_offline(clip, v, auto.start_pos, method=method)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if normalize and peak > 0.98:  # クリップ防止のみ (小さい音は持ち上げない)
        out = out * (0.98 / peak)
    write_wav(path, out, clip.sr, subtype)
    return {"peak": peak, "seconds": len(out) / clip.sr, "samples": len(out)}


def write_reaper_project(rpp_path: str, wav_path: str, seconds: float, sr: int = 44100):
    """WAVを1トラックに置いただけの最小の REAPER プロジェクト (.rpp) を作る。"""
    wav_abs = os.path.abspath(wav_path).replace("\\", "/")
    name = os.path.basename(wav_path)
    text = (
        '<REAPER_PROJECT 0.1 "6.0" 0\n'
        f"  SAMPLERATE {sr} 0 0\n"
        "  <TRACK\n"
        '    NAME "Scratch Deck"\n'
        "    <ITEM\n"
        "      POSITION 0\n"
        f"      LENGTH {seconds:.6f}\n"
        f'      NAME "{name}"\n'
        "      <SOURCE WAVE\n"
        f'        FILE "{wav_abs}"\n'
        "      >\n"
        "    >\n"
        "  >\n"
        ">\n"
    )
    with open(rpp_path, "w", encoding="utf-8") as f:
        f.write(text)
