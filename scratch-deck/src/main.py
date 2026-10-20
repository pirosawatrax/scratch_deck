"""Scratch Deck: ターンテーブル風マウス操作でスクラッチを演奏・録音・編集し、WAVに書き出す。"""
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

from PySide6 import QtCore, QtWidgets  # noqa: E402

from audio_engine import INTERP_METHODS, RealtimeEngine, load_audio  # noqa: E402
from automation import MODES, Automation  # noqa: E402
from editor import AutomationEditor  # noqa: E402
from export import SUBTYPES, export_wav, write_reaper_project  # noqa: E402
from turntable import BASE_RPM, REV_PER_SEC_1X  # noqa: E402
from ui_widgets import TurntableWidget  # noqa: E402
from waveform import WaveformView  # noqa: E402

PRESET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "presets"))
STYLE = """
QWidget { background:#1b1d22; color:#e6e6e6; font-size:13px; }
QPushButton { background:#2b2f38; border:1px solid #444a56; border-radius:4px; padding:6px 10px; }
QPushButton:hover { background:#353a45; }
QPushButton:checked { background:#ff9f1c; color:#111; }
QComboBox, QDoubleSpinBox { background:#2b2f38; border:1px solid #444a56; padding:3px; }
QGroupBox { border:1px solid #3a3f4a; border-radius:4px; margin-top:10px; padding-top:8px; }
QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 4px; }
"""


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scratch Deck v0.5")
        self.engine = RealtimeEngine()
        self.ppr = 600.0       # 1回転に必要なマウス移動量 (px)
        self.smooth = 0.35     # 手の速度の平滑化 (0=なし)
        self.hand_v = 0.0
        self._last_t = time.perf_counter()
        self._last_ui = self._last_t

        self.deck = TurntableWidget()
        self.wave = WaveformView()
        self.editor = AutomationEditor()
        self._build_ui()

        self.ctrl_timer = QtCore.QTimer(self)
        self.ctrl_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.ctrl_timer.timeout.connect(self._control_tick)
        self.ctrl_timer.start(8)
        self.ui_timer = QtCore.QTimer(self)
        self.ui_timer.timeout.connect(self._ui_tick)
        self.ui_timer.start(33)

    # ------------------------------------------------------------ UI構築
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)

        # 左: ターンテーブルと設定
        left = QtWidgets.QVBoxLayout()
        left.addWidget(self.deck, 1)
        self.speed_label = QtWidgets.QLabel("速度 +0.00×")
        self.speed_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.speed_label)

        row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("音源を開く")
        self.motor_btn = QtWidgets.QPushButton("モーター")
        self.motor_btn.setCheckable(True)
        self.cue_btn = QtWidgets.QPushButton("頭出し")
        for b in (self.open_btn, self.motor_btn, self.cue_btn):
            row.addWidget(b)
        left.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        self.rec_btn = QtWidgets.QPushButton("● 録音")
        self.rec_btn.setCheckable(True)
        self.rpm_combo = QtWidgets.QComboBox()
        self.rpm_combo.addItems(["33 rpm", "45 rpm"])
        row2.addWidget(self.rec_btn)
        row2.addWidget(self.rpm_combo)
        left.addLayout(row2)

        box = QtWidgets.QGroupBox("ターンテーブル設定")
        form = QtWidgets.QFormLayout(box)
        p = self.engine.table.p
        self._slider(form, "慣性(重さ)", 0.002, 0.25, p.inertia, 3, lambda x: setattr(p, "inertia", x))
        self._slider(form, "スリップマット摩擦", 0.05, 1.0, p.grip, 2, lambda x: setattr(p, "grip", x))
        self._slider(form, "モーター立上り(秒)", 0.05, 2.0, p.startup_time, 2, lambda x: setattr(p, "startup_time", x))
        self._slider(form, "ブレーキ時間(秒)", 0.1, 4.0, p.brake_time, 2, lambda x: setattr(p, "brake_time", x))
        self._slider(form, "1回転のマウス移動(px)", 200, 1500, self.ppr, 0, lambda x: setattr(self, "ppr", x))
        self._slider(form, "手の平滑化", 0.0, 0.9, self.smooth, 2, lambda x: setattr(self, "smooth", x))
        self._slider(form, "音量", 0.0, 1.0, self.engine.volume, 2, lambda x: setattr(self.engine, "volume", x))
        left.addWidget(box)
        leftw = QtWidgets.QWidget()
        leftw.setLayout(left)
        leftw.setFixedWidth(340)
        root.addWidget(leftw)

        # 右: 波形・編集・書き出し
        right = QtWidgets.QVBoxLayout()
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        split.addWidget(self.wave)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        right.addWidget(split, 1)

        bar = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("▶ 編集内容を再生")
        self.play_btn.setCheckable(True)
        self.start_spin = QtWidgets.QDoubleSpinBox()
        self.start_spin.setRange(0, 3600)
        self.start_spin.setDecimals(3)
        self.start_spin.setSuffix(" 秒")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(MODES)
        self.load_btn = QtWidgets.QPushButton("プリセット読込")
        self.save_btn = QtWidgets.QPushButton("プリセット保存")
        bar.addWidget(self.play_btn)
        bar.addWidget(QtWidgets.QLabel("開始位置"))
        bar.addWidget(self.start_spin)
        bar.addWidget(QtWidgets.QLabel("曲線"))
        bar.addWidget(self.mode_combo)
        bar.addStretch(1)
        bar.addWidget(self.load_btn)
        bar.addWidget(self.save_btn)
        right.addLayout(bar)

        bar2 = QtWidgets.QHBoxLayout()
        self.live_interp = QtWidgets.QComboBox()
        self.live_interp.addItems(INTERP_METHODS)
        self.live_interp.setCurrentText(self.engine.method)
        self.exp_interp = QtWidgets.QComboBox()
        self.exp_interp.addItems(INTERP_METHODS)
        self.exp_interp.setCurrentText("sinc")
        self.exp_bits = QtWidgets.QComboBox()
        self.exp_bits.addItems(SUBTYPES)
        self.reaper_chk = QtWidgets.QCheckBox("REAPERプロジェクト(.rpp)も作る")
        self.export_btn = QtWidgets.QPushButton("WAV書き出し")
        bar2.addWidget(QtWidgets.QLabel("リアルタイム補間"))
        bar2.addWidget(self.live_interp)
        bar2.addStretch(1)
        bar2.addWidget(QtWidgets.QLabel("書出し補間"))
        bar2.addWidget(self.exp_interp)
        bar2.addWidget(self.exp_bits)
        bar2.addWidget(self.reaper_chk)
        bar2.addWidget(self.export_btn)
        right.addLayout(bar2)
        rw = QtWidgets.QWidget()
        rw.setLayout(right)
        root.addWidget(rw, 1)

        # 接続
        self.open_btn.clicked.connect(self.open_dialog)
        self.motor_btn.toggled.connect(self._motor)
        self.cue_btn.clicked.connect(lambda: self.engine.seek(self.start_spin.value()))
        self.rec_btn.toggled.connect(self._record)
        self.rpm_combo.currentIndexChanged.connect(
            lambda i: setattr(self.engine.table.p, "rpm", BASE_RPM if i == 0 else 45.0))
        self.play_btn.toggled.connect(self._play_auto)
        self.start_spin.valueChanged.connect(self._start_changed)
        self.mode_combo.currentTextChanged.connect(self.editor.set_mode)
        self.live_interp.currentTextChanged.connect(lambda m: setattr(self.engine, "method", m))
        self.wave.seek.connect(self._wave_seek)
        self.load_btn.clicked.connect(self.load_preset)
        self.save_btn.clicked.connect(self.save_preset)
        self.export_btn.clicked.connect(self.export)
        self.statusBar().showMessage("音源(WAV/MP3)を開いてください")

    def _slider(self, form, label, lo, hi, value, decimals, setter):
        sld = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        sld.setRange(0, 1000)
        val = QtWidgets.QLabel()
        val.setMinimumWidth(48)

        def on(v):
            x = lo + (hi - lo) * v / 1000.0
            val.setText(f"{x:.{decimals}f}")
            setter(x)

        sld.valueChanged.connect(on)
        sld.setValue(int(round((value - lo) / (hi - lo) * 1000)))
        on(sld.value())
        h = QtWidgets.QHBoxLayout()
        h.addWidget(sld, 1)
        h.addWidget(val)
        form.addRow(label, h)

    # ------------------------------------------------------------ タイマー
    def _control_tick(self):
        now = time.perf_counter()
        dt = max(now - self._last_t, 1e-3)
        self._last_t = now
        dx = self.deck.consume_dx()
        if self.deck.touching:
            raw = (dx / self.ppr) / dt / REV_PER_SEC_1X  # マウス移動 → 回転速度(倍率)
            raw = max(-15.0, min(15.0, raw))
            self.hand_v = self.hand_v * self.smooth + raw * (1.0 - self.smooth)
        else:
            self.hand_v = 0.0
        self.engine.hand_v = self.hand_v
        self.engine.touching = self.deck.touching

    def _ui_tick(self):
        now = time.perf_counter()
        dt, self._last_ui = now - self._last_ui, now
        eng = self.engine
        self.deck.angle = (self.deck.angle + eng.v * dt * 360.0 * REV_PER_SEC_1X) % 360.0
        self.deck.update()
        self.speed_label.setText(f"速度 {eng.v:+.2f}×")
        if eng.clip is not None:
            self.wave.set_playhead(eng.pos / eng.sr)
        self.editor.set_playhead(eng.play_time if eng.mode == "auto" else None)
        if eng.auto_finished:
            eng.auto_finished = False
            self.play_btn.blockSignals(True)
            self.play_btn.setChecked(False)
            self.play_btn.blockSignals(False)

    # ------------------------------------------------------------ 操作
    def open_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "音源を開く", "", "Audio (*.wav *.mp3 *.flac *.ogg *.aiff);;All files (*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            clip = load_audio(path)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "読込エラー", str(e))
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.engine.set_clip(clip)
        self.wave.set_clip(clip)
        self.start_spin.setValue(0.0)
        try:
            self.engine.start()
            self.statusBar().showMessage(
                f"{clip.name} ({clip.duration:.1f}秒)  盤をドラッグして演奏。モーターを入れると回り続けます")
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"{clip.name} を読込。オーディオ出力を開けません: {e}")
            QtWidgets.QMessageBox.warning(
                self, "オーディオ出力エラー",
                f"リアルタイム再生を開始できませんでした (編集と書き出しは使えます):\n{e}")

    def _motor(self, on: bool):
        self.engine.table.motor_on = on

    def _wave_seek(self, sec: float):
        self.start_spin.setValue(sec)
        self.engine.seek(sec)

    def _start_changed(self, sec: float):
        self.editor.auto.start_pos = sec
        self.wave.set_cue(sec)

    def _record(self, on: bool):
        if self.engine.clip is None:
            self.rec_btn.blockSignals(True)
            self.rec_btn.setChecked(False)
            self.rec_btn.blockSignals(False)
            return
        if on:
            self.engine.start_recording()
            self.statusBar().showMessage("録音中... 盤を動かしてください")
        else:
            take = self.engine.stop_recording()
            self.editor.set_automation(take)
            self.mode_combo.setCurrentText(take.mode)
            self.start_spin.setValue(take.start_pos)
            self.statusBar().showMessage(f"録音完了: {take.duration:.2f}秒 / {len(take.points)}点 (右のグラフで編集できます)")

    def _play_auto(self, on: bool):
        if on:
            self.engine.play_automation(self.editor.auto)
        else:
            self.engine.stop_automation()

    def load_preset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "プリセット読込", PRESET_DIR, "Preset (*.json)")
        if not path:
            return
        try:
            auto = Automation.load(path)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "プリセットエラー", str(e))
            return
        auto.start_pos = self.start_spin.value()  # 頭出し位置に適用
        self.editor.set_automation(auto)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(auto.mode)
        self.mode_combo.blockSignals(False)
        self.statusBar().showMessage(f"プリセット「{auto.name}」を読込。『編集内容を再生』で確認できます")

    def save_preset(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "プリセット保存", PRESET_DIR, "Preset (*.json)")
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            self.editor.auto.name = os.path.splitext(os.path.basename(path))[0]
            self.editor.auto.save(path)
            self.statusBar().showMessage(f"保存しました: {path}")

    def export(self):
        clip = self.engine.clip
        if clip is None:
            QtWidgets.QMessageBox.information(self, "書き出し", "先に音源を開いてください。")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "WAV書き出し", "scratch.wav", "WAV (*.wav)")
        if not path:
            return
        if not path.lower().endswith(".wav"):
            path += ".wav"
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            info = export_wav(path, clip, self.editor.auto,
                              self.exp_interp.currentText(), self.exp_bits.currentText())
            if self.reaper_chk.isChecked():
                write_reaper_project(os.path.splitext(path)[0] + ".rpp", path, info["seconds"], clip.sr)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "書き出しエラー", str(e))
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"書き出し完了: {path} ({info['seconds']:.2f}秒, ピーク {info['peak']:.2f})")

    def closeEvent(self, ev):
        self.engine.close()
        super().closeEvent(ev)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.resize(1320, 780)
    win.show()
    if len(sys.argv) > 1:
        win.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
