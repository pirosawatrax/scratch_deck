"""GUIなしで書き出す: python examples/render_cli.py 音源.wav プリセット.json 出力.wav [開始秒] [補間]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from audio_engine import load_audio  # noqa: E402
from automation import Automation  # noqa: E402
from export import export_wav  # noqa: E402

if len(sys.argv) < 4:
    sys.exit(__doc__)
clip = load_audio(sys.argv[1])
auto = Automation.load(sys.argv[2])
if len(sys.argv) > 4:
    auto.start_pos = float(sys.argv[4])
info = export_wav(sys.argv[3], clip, auto, method=sys.argv[5] if len(sys.argv) > 5 else "sinc")
print(f"wrote {sys.argv[3]}  {info['seconds']:.2f}s  peak={info['peak']:.2f}")
