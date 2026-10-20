"""音声エンジン: 読込・補間・オフライン描画・リアルタイム再生。

速度 v は「再生速度の倍率」(1.0=等速, 負=逆再生) で、1サンプルごとに
    position[n+1] = position[n] + v[n]
と進む。位置は小数なので補間 (linear / cubic / sinc) で音を取り出す。
"""
from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import lfilter, resample_poly

from turntable import Turntable

ENGINE_SR = 44100
PAD = 16  # 補間用の余白(サンプル)
INTERP_METHODS = ("linear", "cubic", "sinc")


# ----------------------------------------------------------------- 読込
class Clip:
    """ステレオ float32 の音源。端に余白を付けた配列も持つ。"""

    def __init__(self, audio, sr: int = ENGINE_SR, name: str = ""):
        a = np.asarray(audio, dtype=np.float32)
        if a.ndim == 1:
            a = a[:, None]
        if a.shape[1] == 1:
            a = np.repeat(a, 2, axis=1)
        self.audio = np.ascontiguousarray(a[:, :2])
        self.sr = int(sr)
        self.name = name
        self.padded = np.pad(self.audio, ((PAD, PAD), (0, 0)))

    @property
    def length(self) -> int:
        return self.audio.shape[0]

    @property
    def duration(self) -> float:
        return self.length / self.sr


def _read_any(path: str):
    errors = []
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        return data, int(sr)
    except Exception as e:  # noqa: BLE001
        errors.append(f"soundfile: {e}")
    try:
        import librosa
        y, sr = librosa.load(path, sr=None, mono=False)
        y = y.T if y.ndim == 2 else y[:, None]
        return y.astype(np.float32), int(sr)
    except Exception as e:  # noqa: BLE001
        errors.append(f"librosa: {e}")
    if path.lower().endswith(".wav"):
        try:
            from scipy.io import wavfile
            sr, d = wavfile.read(path)
            if d.dtype == np.int16:
                d = d / 32768.0
            elif d.dtype == np.int32:
                d = d / 2147483648.0
            elif d.dtype == np.uint8:
                d = (d.astype(np.float32) - 128.0) / 128.0
            d = d.astype(np.float32)
            return (d[:, None] if d.ndim == 1 else d), int(sr)
        except Exception as e:  # noqa: BLE001
            errors.append(f"scipy: {e}")
    raise RuntimeError("音声ファイルを読み込めませんでした: " + " / ".join(errors))


def load_audio(path: str, target_sr: int = ENGINE_SR) -> Clip:
    """WAV/MP3 等を読み込み、エンジンのサンプルレートに変換して Clip にする。"""
    data, sr = _read_any(path)
    if sr != target_sr:
        g = gcd(sr, target_sr)
        data = resample_poly(data, target_sr // g, sr // g, axis=0).astype(np.float32)
    return Clip(data, target_sr, name=str(path).replace("\\", "/").split("/")[-1])


# ----------------------------------------------------------------- 補間
def _sample_chunk(clip: Clip, pos: np.ndarray, method: str, speed) -> np.ndarray:
    pad = clip.padded
    n = clip.length
    valid = (pos >= 0) & (pos <= n - 1)
    q = np.clip(pos, 0, n - 1) + PAD
    i0 = np.floor(q).astype(np.int64)
    fr = q - i0
    f = fr[:, None]
    if method == "linear":
        out = pad[i0] * (1 - f) + pad[i0 + 1] * f
    elif method == "cubic":  # Catmull-Rom
        y0, y1, y2, y3 = pad[i0 - 1], pad[i0], pad[i0 + 1], pad[i0 + 2]
        out = y1 + 0.5 * f * (
            y2 - y0 + f * (2 * y0 - 5 * y1 + 4 * y2 - y3 + f * (3 * (y1 - y2) + y3 - y0))
        )
    elif method == "sinc":  # 16タップ窓付きsinc。高速時は遮断周波数を下げて折り返しを抑える
        k = np.arange(-7, 9)
        idx = i0[:, None] + k[None, :]
        x = idx - q[:, None]
        if speed is None:
            c = np.ones_like(q)
        else:
            c = np.clip(1.0 / np.maximum(np.abs(speed), 1e-3), 0.25, 1.0)
        cx = c[:, None]
        win = 0.5 + 0.5 * np.cos(np.pi * np.clip(x / 8.5, -1, 1))
        w = np.sinc(x * cx) * cx * win
        w /= np.sum(w, axis=1, keepdims=True)
        out = np.einsum("nk,nkc->nc", w, pad[idx])
    else:
        raise ValueError(f"unknown interpolation: {method}")
    out = out * valid[:, None]
    return out.astype(np.float32)


def sample_at(clip: Clip, pos, method: str = "cubic", speed=None) -> np.ndarray:
    """小数サンプル位置 pos の音を補間して返す (範囲外は無音)。"""
    pos = np.asarray(pos, dtype=np.float64)
    spd = None if speed is None else np.asarray(speed, dtype=np.float64)
    step = 1 << 15
    parts = []
    for s in range(0, len(pos), step):
        parts.append(
            _sample_chunk(clip, pos[s:s + step], method, None if spd is None else spd[s:s + step])
        )
    if not parts:
        return np.zeros((0, 2), np.float32)
    return np.concatenate(parts, axis=0)


# ----------------------------------------------------------------- DCカット
class DCBlocker:
    """針が止まったときのDC成分を消す1次ハイパス (約3.5Hz)。止めた盤が無音になる。"""

    def __init__(self, r: float = 0.9995):
        self.r = r
        self.zi = None

    def reset(self):
        self.zi = None

    def process(self, x: np.ndarray) -> np.ndarray:
        if len(x) == 0:
            return x
        b, a = [1.0, -1.0], [1.0, -self.r]
        if self.zi is None:
            self.zi = np.zeros((1, x.shape[1]))
        y, self.zi = lfilter(b, a, x, axis=0, zi=self.zi)
        return y.astype(np.float32)


# ----------------------------------------------------------------- オフライン描画
def velocity_to_positions(v: np.ndarray, start_pos: float) -> np.ndarray:
    return start_pos + np.cumsum(v) - v


def render_offline(clip: Clip, v: np.ndarray, start_pos_sec: float,
                   method: str = "sinc", dc_block: bool = True) -> np.ndarray:
    """速度カーブ v (出力サンプルごと) から音声を生成する。"""
    v = np.asarray(v, dtype=np.float64)
    pos = velocity_to_positions(v, start_pos_sec * clip.sr)
    out = sample_at(clip, pos, method, v)
    if dc_block:
        out = DCBlocker().process(out)
    return out


def compute_envelope(audio: np.ndarray, buckets: int = 3000):
    """波形表示用の (min, max, 1バケット当たりのサンプル数)。"""
    mono = audio.mean(axis=1)
    k = max(1, len(mono) // buckets)
    m = (len(mono) // k) * k
    blocks = mono[:m].reshape(-1, k)
    return blocks.min(axis=1), blocks.max(axis=1), k


# ----------------------------------------------------------------- リアルタイム
class RealtimeEngine:
    """sounddevice 出力ストリーム。mode='live' はマウス(物理モデル)、'auto' はオートメーション再生。"""

    def __init__(self, sr: int = ENGINE_SR, blocksize: int = 256):
        from recorder import Recorder
        self.sr = sr
        self.blocksize = blocksize
        self.clip: Clip | None = None
        self.pos = 0.0            # 現在の再生位置 (サンプル)
        self.v = 0.0              # 現在の速度
        self.table = Turntable()
        self.hand_v = 0.0
        self.touching = False
        self.method = "cubic"
        self.volume = 0.8
        self.dc = DCBlocker()
        self.mode = "live"
        self.auto_finished = False
        self.recorder = Recorder()
        self._curve = None
        self._cidx = 0
        self.stream = None

    # ---- 設定 ----
    def set_clip(self, clip: Clip):
        self.clip = clip
        self.seek(0.0)

    def seek(self, sec: float):
        n = self.clip.length if self.clip else 0
        self.pos = float(np.clip(sec * self.sr, 0, max(n - 1, 0)))
        self.table.w = 0.0 if not self.table.motor_on else self.table.w
        self.v = 0.0
        self.dc.reset()

    @property
    def play_time(self) -> float:
        return self._cidx / self.sr

    # ---- ストリーム ----
    def start(self):
        if self.stream is not None:
            return
        import sounddevice as sd
        self.stream = sd.OutputStream(
            samplerate=self.sr, channels=2, dtype="float32",
            blocksize=self.blocksize, latency="low", callback=self._callback,
        )
        self.stream.start()

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None

    # ---- オートメーション再生 / 録音 ----
    def play_automation(self, auto):
        if self.clip is None:
            return
        self._curve = auto.curve(self.sr)
        self._cidx = 0
        self.pos = float(np.clip(auto.start_pos * self.sr, 0, self.clip.length - 1))
        self.dc.reset()
        self.auto_finished = False
        self.mode = "auto"

    def stop_automation(self):
        if self.mode == "auto":
            self.table.w = self.v
        self.mode = "live"

    def start_recording(self):
        self.recorder.start(self.pos / self.sr, self.v)

    def stop_recording(self):
        return self.recorder.stop()

    # ---- オーディオコールバック ----
    def _callback(self, outdata, frames, time_info, status):
        try:
            outdata[:] = self._render_block(frames)
        except Exception:  # noqa: BLE001  コールバック内の例外でストリームを落とさない
            outdata.fill(0)

    def _render_block(self, frames: int) -> np.ndarray:
        clip = self.clip
        if clip is None:
            return np.zeros((frames, 2), np.float32)
        if self.mode == "auto":
            c, i = self._curve, self._cidx
            v = np.zeros(frames)
            seg = c[i:i + frames]
            v[:len(seg)] = seg
            self._cidx += frames
            if self._cidx >= len(c):
                self.table.w = float(v[-1])
                self.mode = "live"
                self.auto_finished = True
        else:
            v_end = self.table.step(frames / self.sr, self.hand_v, self.touching)
            v = np.linspace(self.v, v_end, frames + 1)[1:]
        pos = velocity_to_positions(v, self.pos)
        out = sample_at(clip, pos, self.method, v)
        self.pos += float(v.sum())
        self.v = float(v[-1])
        if self.pos < 0 or self.pos > clip.length - 1:  # レコードの端
            self.pos = float(np.clip(self.pos, 0, clip.length - 1))
            self.table.w = 0.0
            self.v = 0.0
        if self.recorder.active:
            self.recorder.push(frames, self.sr, self.v)
        return np.clip(self.dc.process(out) * self.volume, -1.0, 1.0)
