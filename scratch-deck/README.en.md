# Scratch Deck

[日本語](README.md)

A Python tool for performing, recording and editing turntable scratches with your mouse, then rendering them to WAV.
It is meant to feed a DAW such as REAPER for the final mix. Linux and Windows are supported (source distribution); macOS is untested.

## Install and run

```
pip install -r requirements.txt
python src/main.py                    # launch
python src/main.py examples/demo.wav  # launch with an audio file
```

A practice sample is bundled as `examples/demo.wav`; regenerate it with `python examples/make_demo_audio.py`.
MP3 files are read with `soundfile` (libsndfile 1.1 or later), falling back to `librosa` if that fails.
Audio is converted to 44.1 kHz stereo on load.

## Usage

1. **Open audio.** The waveform appears. Click it to set the cue point (orange dashed line).
2. **Drag the platter** to play. While you hold it, the platter follows your hand; stop moving and it stops; release and the motor brings it back to normal speed.
   - Turn on **Motor** to keep the platter spinning (turn it off and the brake stops it).
   - "Mouse travel per revolution (px)" sets how far you must move the mouse for one turn.
3. Press **● Record**, perform, and press it again to stop. The hand motion `[time, speed]` appears in the graph at the lower right.
4. **Edit in the graph.** Click to add a point, drag to move it, right-click to delete it. Curve modes: `bezier`, `linear`, `monotone`.
5. Check with **▶ Play edit**, then **Export WAV**.
6. **Presets** live in `presets/`: Baby, Chirp, Transform, Scribble, Crab, Orbit. A loaded preset is applied at the cue point.

Speed is a playback-rate multiplier (1.0 = normal, negative = reverse). The position advances as `position += velocity`, and fractional positions are interpolated to read the audio.

### Turntable settings (inertia, motor, brake, slip mat)

| Setting | Effect |
| --- | --- |
| Inertia (weight) | Higher values make the platter lag behind your hand (heavier deck) |
| Slip mat friction | Lower values let your hand slip, so tracking gets looser |
| Motor startup | Lower values return to normal speed faster after release (stronger torque) |
| Brake time | Time to stop from normal speed when the motor is off |
| 33 / 45 rpm | Target speed 1.0 / 1.35 |
| Hand smoothing | Reduces jitter in mouse speed (higher values feel less responsive) |

### Interpolation and sound quality

- Real-time interpolation: `linear` / `cubic` (default) / `sinc`. Export interpolation defaults to `sinc`.
- `sinc` lowers its cutoff frequency at high playback speeds to suppress aliasing.
- A high-pass filter of about 3.5 Hz removes DC, so a stopped record is silent.
- Export only prevents clipping (it lowers the peak to 0.98 if needed); quiet audio is never boosted.

## Working with REAPER

- Drag and drop the exported WAV onto a REAPER track.
- Tick "Also create a REAPER project (.rpp)" to get a minimal project with the WAV on one track (experimental).
- Batch render without the GUI: `python examples/render_cli.py source.wav presets/Chirp.json out.wav 1.5 sinc`

## Layout

```
src/
  main.py          GUI (timers and actions)
  audio_engine.py  loading / interpolation / offline render / real-time playback
  turntable.py     physics model (inertia, motor, brake, slip mat)
  automation.py    point list, interpolation, RDP simplification, JSON save/load
  recorder.py      hand-motion recording
  waveform.py      waveform view   editor.py  curve editor   ui_widgets.py  platter widget
  export.py        WAV export / .rpp generation
  presets.py       preset generator (python src/presets.py)
tests/test_core.py core-logic tests (python tests/test_core.py)
```

## Status

- Core logic (interpolation, rendering, physics, automation, recording, export, real-time path) is covered by automated tests.
- Feel and latency depend on your OS and audio hardware. If something misbehaves, report your OS, audio device and the symptom.

## Ideas for later

Crossfader (transformer), record noise, MIDI knobs, direct platter-angle control, per-point Bezier handles.
