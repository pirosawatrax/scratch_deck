"""コアロジックのテスト (GUI/音声デバイス不要)。 python tests/test_core.py でも pytest でも動く。"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_engine import Clip, RealtimeEngine, load_audio, render_offline, sample_at  # noqa: E402
from automation import Automation, simplify  # noqa: E402
from export import export_wav  # noqa: E402
from turntable import Turntable, TurntableParams  # noqa: E402

SR = 44100


def sine_clip(freq=440.0, sec=3.0):
    t = np.arange(int(SR * sec)) / SR
    x = 0.5 * np.sin(2 * np.pi * freq * t)
    return Clip(np.stack([x, x], 1), SR)


def peak_freq(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spec) * SR / len(x)


def test_linear_fractional_exact_on_ramp():
    ramp = np.arange(1000, dtype=np.float32) / 1000
    clip = Clip(np.stack([ramp, ramp], 1), SR)
    out = sample_at(clip, np.array([120.35, 500.5]), "linear")
    assert np.allclose(out[:, 0], [0.12035, 0.5005], atol=1e-6)


def test_unity_speed_reproduces_source():
    clip = sine_clip()
    v = np.ones(SR)
    for method, tol in (("linear", 1e-6), ("cubic", 1e-5), ("sinc", 2e-3)):
        out = render_offline(clip, v, 0.5, method, dc_block=False)
        ref = clip.audio[int(0.5 * SR):int(0.5 * SR) + SR]
        assert np.max(np.abs(out[100:-100] - ref[100:-100])) < tol, method


def test_reverse_and_double_speed():
    clip = sine_clip()
    out = render_offline(clip, -np.ones(SR), 2.0, "cubic", dc_block=False)
    ref = clip.audio[int(2.0 * SR) - SR + 1:int(2.0 * SR) + 1][::-1]
    assert np.max(np.abs(out[10:-10] - ref[10:-10])) < 1e-4
    out2 = render_offline(clip, np.full(SR // 2, 2.0), 0.0, "sinc", dc_block=False)
    assert abs(peak_freq(out2[:, 0]) - 880) < 6


def test_sinc_reduces_aliasing_at_high_speed():
    clip = sine_clip(freq=8000.0, sec=3.0)  # 4倍速 → 32kHz: 折り返す帯域
    v = np.full(SR // 2, 4.0)
    lin = render_offline(clip, v, 0.0, "linear", dc_block=False)
    snc = render_offline(clip, v, 0.0, "sinc", dc_block=False)
    assert np.sqrt(np.mean(snc ** 2)) < 0.5 * np.sqrt(np.mean(lin ** 2))


def test_out_of_range_is_silent():
    clip = sine_clip(sec=1.0)
    out = render_offline(clip, np.ones(SR), 0.5, "cubic", dc_block=False)
    assert np.all(out[int(0.5 * SR) + 5:] == 0)


def test_held_record_is_silent_with_dc_block():
    clip = sine_clip()
    out = render_offline(clip, np.zeros(SR), 0.3, "cubic", dc_block=True)
    assert np.max(np.abs(out[SR // 2:])) < 1e-3


def test_automation_edit_and_modes():
    a = Automation([[0, 0], [1, 2], [2, 0]])
    assert len(a.points) == 3
    i = a.add_point(0.5, 1.0)
    assert i == 1 and [p[0] for p in a.points] == sorted(p[0] for p in a.points)
    a.move_point(i, 5.0, 0.3)  # 隣を越えない
    assert a.points[i][0] < a.points[i + 1][0]
    assert a.remove_point(i) and len(a.points) == 3
    for mode in ("linear", "bezier", "monotone"):
        c = a.evaluate(np.array([0.0, 1.0, 2.0]), mode)
        assert np.allclose(c, [0, 2, 0], atol=1e-9), mode
    assert not Automation([[0, 0], [1, 1]]).remove_point(0)
    assert len(a.curve(SR)) == 2 * SR


def test_monotone_has_no_overshoot():
    a = Automation([[0, 0], [0.1, 3], [0.2, 3], [0.3, 0]], mode="monotone")
    c = a.evaluate(np.linspace(0, 0.3, 500))
    assert c.max() <= 3.0 + 1e-9 and c.min() >= -1e-9


def test_simplify_and_roundtrip():
    t = np.arange(0, 1, 0.005)
    pts = np.column_stack([t, 2 * np.sin(2 * np.pi * 2 * t)])
    s = simplify(pts, 0.03)
    assert len(s) < len(pts) / 4
    a = Automation(s, start_pos=1.25, mode="monotone", name="x")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.json")
        a.save(p)
        b = Automation.load(p)
    assert b.mode == "monotone" and abs(b.start_pos - 1.25) < 1e-9
    assert np.allclose(np.array(b.points), np.array(a.points), atol=1e-4)


def test_presets_load():
    d = os.path.join(os.path.dirname(__file__), "..", "presets")
    for f in os.listdir(d):
        a = Automation.load(os.path.join(d, f))
        assert a.duration > 0.5 and len(a.points) >= 2


def test_turntable_physics():
    t = Turntable(TurntableParams(startup_time=0.5, brake_time=1.0))
    t.motor_on = True
    for _ in range(int(0.6 * 1000)):
        t.step(0.001, 0, False)
    assert abs(t.w - 1.0) < 1e-6  # 立ち上がり
    for _ in range(300):
        t.step(0.001, -2.0, True)  # 手で逆回転
    assert t.w < -1.5
    for _ in range(3000):
        t.step(0.001, 0, False)  # 離すとモーターで戻る
    assert abs(t.w - 1.0) < 1e-6
    t.motor_on = False
    for _ in range(1100):
        t.step(0.001, 0, False)
    assert t.w == 0.0  # ブレーキ
    heavy = Turntable(TurntableParams(inertia=0.2))
    light = Turntable(TurntableParams(inertia=0.01))
    for _ in range(50):
        heavy.step(0.001, 2.0, True)
        light.step(0.001, 2.0, True)
    assert light.w > heavy.w
    t45 = Turntable(TurntableParams(rpm=45.0))
    assert abs(t45.p.target_speed - 1.35) < 1e-3


def test_engine_automation_matches_offline():
    clip = sine_clip()
    eng = RealtimeEngine(blocksize=256)
    eng.set_clip(clip)
    eng.method = "cubic"
    eng.volume = 1.0
    a = Automation([[0, 0], [0.1, 2], [0.2, -1.5], [0.3, 1], [0.5, 0]], start_pos=1.0)
    eng.play_automation(a)
    blocks = []
    while eng.mode == "auto":
        blocks.append(eng._render_block(256))
    got = np.concatenate(blocks)
    n = len(a.curve(SR))
    ref = render_offline(clip, a.curve(SR), 1.0, "cubic", dc_block=True)
    assert np.max(np.abs(got[:n] - ref)) < 1e-4
    assert eng.auto_finished and eng.mode == "live"


def test_engine_live_motor_and_record():
    clip = sine_clip()
    eng = RealtimeEngine(blocksize=256)
    eng.set_clip(clip)
    eng.table.motor_on = True
    for _ in range(100):
        eng._render_block(256)
    assert abs(eng.v - 1.0) < 1e-3  # 等速
    eng.start_recording()
    for i in range(200):  # 掴んで往復
        eng.touching = True
        eng.hand_v = 2.0 * np.sin(2 * np.pi * i / 60)
        eng._render_block(256)
    eng.touching = False
    for _ in range(10):
        eng._render_block(256)
    take = eng.stop_recording()
    assert 1.0 < take.duration < 1.3 and len(take.points) > 10
    assert abs(take.start_pos - (eng.pos / SR) + take.duration) < 5.0  # 開始位置が記録されている
    assert max(abs(p[1]) for p in take.points) > 1.0


def test_load_and_export_roundtrip():
    clip = sine_clip(sec=1.0)
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.wav")
        from export import write_wav
        write_wav(src, clip.audio, SR, "FLOAT")
        loaded = load_audio(src)
        assert abs(loaded.length - clip.length) <= 1
        a = Automation([[0, 1], [0.5, 1]])
        out = os.path.join(d, "out.wav")
        info = export_wav(out, loaded, a, "sinc", "PCM_16", tail=0.1)
        assert os.path.getsize(out) > 1000 and info["seconds"] > 0.55


def test_load_resamples_48k():
    from scipy.io import wavfile
    t = np.arange(48000) / 48000
    x = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.wav")
        wavfile.write(p, 48000, x)
        clip = load_audio(p)
    assert clip.sr == SR and abs(clip.length - SR) <= 2 and clip.audio.shape[1] == 2


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    sys.exit(1 if fails else 0)
