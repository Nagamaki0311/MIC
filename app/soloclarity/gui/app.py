"""Tkinterメインウィンドウ。

不要な常駐機能・複雑な設定画面を増やさない方針(Issue原文)に沿い、基本画面は
1画面に収め、パラメータの生値編集は折りたたみ式の詳細設定パネルにのみ置く。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from soloclarity import presets
from soloclarity.audio import devices as device_lib
from soloclarity.audio.engine import AudioEngine, play_preview, record_and_process_preview
from soloclarity.config import AppConfig
from soloclarity.dsp.chain import VoiceChain
from soloclarity.gui.meter_widget import MeterWidget

TEST_PREVIEW_SECONDS = 3.0
METER_UPDATE_INTERVAL_MS = 100

# 詳細設定スライダーの定義: (キー, ラベル, 最小, 最大, 刻み)
ADVANCED_SLIDER_SPECS: tuple[tuple[str, str, float, float, float], ...] = (
    ("clarity_highpass_hz", "Highpass (Hz)", 40.0, 150.0, 1.0),
    ("clarity_200hz_gain_db", "200Hz Gain (dB)", -6.0, 3.0, 0.1),
    ("clarity_300hz_gain_db", "300Hz Gain (dB)", -6.0, 3.0, 0.1),
    ("clarity_2000hz_gain_db", "2kHz Gain (dB)", -3.0, 6.0, 0.1),
    ("clarity_3000hz_gain_db", "3kHz Gain (dB)", -3.0, 6.0, 0.1),
    ("clarity_4000hz_gain_db", "4kHz Gain (dB)", -3.0, 6.0, 0.1),
    ("noise_wet_dry_mix", "ノイズ除去 Mix (0-1)", 0.0, 1.0, 0.01),
    ("noise_gate_threshold", "ゲート閾値 (0-1)", 0.0, 1.0, 0.01),
    ("noise_gate_release_ms", "ゲート Release (ms)", 50.0, 500.0, 1.0),
    ("compressor_threshold_db", "Comp Threshold (dB)", -40.0, 0.0, 0.5),
    ("compressor_ratio", "Comp Ratio", 1.0, 10.0, 0.1),
    ("compressor_attack_ms", "Comp Attack (ms)", 1.0, 50.0, 1.0),
    ("compressor_release_ms", "Comp Release (ms)", 50.0, 500.0, 1.0),
    ("agc_target_dbfs", "AGC Target (dBFS)", -30.0, -6.0, 0.5),
    ("agc_max_gain_db", "AGC Max Gain (dB)", 0.0, 24.0, 0.5),
)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SoloClarity")
        self.resizable(False, False)

        self.app_config = AppConfig.load()
        self.chain = VoiceChain(self.app_config.preset)
        self.engine: Optional[AudioEngine] = None

        self._input_devices = device_lib.list_input_devices()
        self._output_devices = device_lib.list_output_devices()
        self._updating_from_code = False

        self._build_widgets()
        self._restore_from_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- ウィジェット構築 -----------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}

        device_frame = ttk.LabelFrame(self, text="デバイス")
        device_frame.grid(row=0, column=0, sticky="ew", **pad)

        ttk.Label(device_frame, text="マイク(入力)").grid(row=0, column=0, sticky="w")
        self.input_device_var = tk.StringVar()
        self.input_device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.input_device_var,
            values=[d.name for d in self._input_devices],
            state="readonly",
            width=34,
        )
        self.input_device_combo.grid(row=0, column=1, sticky="ew")
        self.input_device_combo.bind("<<ComboboxSelected>>", self._on_device_changed)

        ttk.Label(device_frame, text="出力先(仮想マイク)").grid(row=1, column=0, sticky="w")
        self.output_device_var = tk.StringVar()
        self.output_device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.output_device_var,
            values=[d.name for d in self._output_devices],
            state="readonly",
            width=34,
        )
        self.output_device_combo.grid(row=1, column=1, sticky="ew")
        self.output_device_combo.bind("<<ComboboxSelected>>", self._on_device_changed)

        control_frame = ttk.LabelFrame(self, text="処理設定")
        control_frame.grid(row=1, column=0, sticky="ew", **pad)

        self.processing_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            control_frame,
            text="処理ON/OFF",
            variable=self.processing_enabled_var,
            command=self._on_processing_toggle,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(control_frame, text="プリセット").grid(row=1, column=0, sticky="w")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(
            control_frame,
            textvariable=self.preset_var,
            values=[presets.PRESETS[name].label_ja for name in presets.PRESET_ORDER],
            state="readonly",
            width=20,
        )
        self.preset_combo.grid(row=1, column=1, sticky="w")
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Label(control_frame, text="明瞭度").grid(row=2, column=0, sticky="w")
        self.clarity_var = tk.StringVar()
        self.clarity_combo = ttk.Combobox(
            control_frame,
            textvariable=self.clarity_var,
            values=list(presets.CLARITY_LEVELS),
            state="readonly",
            width=20,
        )
        self.clarity_combo.grid(row=2, column=1, sticky="w")
        self.clarity_combo.bind("<<ComboboxSelected>>", self._on_clarity_selected)

        ttk.Label(control_frame, text="ノイズ除去").grid(row=3, column=0, sticky="w")
        self.noise_var = tk.StringVar()
        self.noise_combo = ttk.Combobox(
            control_frame,
            textvariable=self.noise_var,
            values=list(presets.NOISE_LEVELS),
            state="readonly",
            width=20,
        )
        self.noise_combo.grid(row=3, column=1, sticky="w")
        self.noise_combo.bind("<<ComboboxSelected>>", self._on_noise_selected)

        meter_frame = ttk.LabelFrame(self, text="レベルメーター")
        meter_frame.grid(row=2, column=0, sticky="ew", **pad)

        ttk.Label(meter_frame, text="入力").grid(row=0, column=0, sticky="w")
        self.input_meter = MeterWidget(meter_frame)
        self.input_meter.grid(row=0, column=1)

        ttk.Label(meter_frame, text="出力").grid(row=1, column=0, sticky="w")
        self.output_meter = MeterWidget(meter_frame)
        self.output_meter.grid(row=1, column=1)

        test_frame = ttk.Frame(self)
        test_frame.grid(row=3, column=0, sticky="ew", **pad)
        self.test_button = ttk.Button(
            test_frame,
            text=f"テスト再生({int(TEST_PREVIEW_SECONDS)}秒録音→再生)",
            command=self._on_test_clicked,
        )
        self.test_button.grid(row=0, column=0, sticky="w")
        self.test_status_var = tk.StringVar(value="")
        ttk.Label(test_frame, textvariable=self.test_status_var).grid(row=0, column=1, sticky="w")

        self._build_advanced_panel()

    def _build_advanced_panel(self) -> None:
        self._advanced_visible = False
        toggle_frame = ttk.Frame(self)
        toggle_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(4, 0))
        self._advanced_toggle_button = ttk.Button(
            toggle_frame, text="詳細設定を開く", command=self._toggle_advanced
        )
        self._advanced_toggle_button.grid(row=0, column=0, sticky="w")

        self._advanced_frame = ttk.LabelFrame(self, text="詳細設定(パラメータの生値)")
        self._advanced_sliders: dict[str, tk.Scale] = {}
        for row, (key, label, lo, hi, res) in enumerate(ADVANCED_SLIDER_SPECS):
            ttk.Label(self._advanced_frame, text=label).grid(row=row, column=0, sticky="w")
            scale = tk.Scale(
                self._advanced_frame,
                from_=lo,
                to=hi,
                resolution=res,
                orient="horizontal",
                length=220,
                command=lambda _value, key=key: self._on_advanced_slider_changed(key),
            )
            scale.grid(row=row, column=1, sticky="ew")
            self._advanced_sliders[key] = scale

    # --- 設定の復元/保存 --------------------------------------------------

    def _restore_from_config(self) -> None:
        self._updating_from_code = True
        cfg = self.app_config

        if cfg.input_device_name:
            self.input_device_var.set(cfg.input_device_name)
        elif self._input_devices:
            guessed = device_lib.guess_solocast_device(self._input_devices)
            self.input_device_var.set((guessed or self._input_devices[0]).name)

        if cfg.output_device_name:
            self.output_device_var.set(cfg.output_device_name)
        elif self._output_devices:
            guessed = device_lib.guess_cable_output_device(self._output_devices)
            self.output_device_var.set((guessed or self._output_devices[0]).name)

        self.processing_enabled_var.set(cfg.processing_enabled)
        self.preset_var.set(presets.PRESETS[cfg.preset].label_ja)
        self.clarity_var.set(self.chain.clarity_level)
        self.noise_var.set(self.chain.noise_level)
        self._sync_advanced_sliders_from_chain()
        self._apply_advanced_overrides(cfg.advanced_overrides)
        self._updating_from_code = False

    def _current_config(self) -> AppConfig:
        preset_label_to_name = {p.label_ja: name for name, p in presets.PRESETS.items()}
        return AppConfig(
            input_device_name=self.input_device_var.get() or None,
            output_device_name=self.output_device_var.get() or None,
            preset=preset_label_to_name.get(self.preset_var.get(), presets.DEFAULT_PRESET),
            processing_enabled=self.processing_enabled_var.get(),
            advanced_overrides={k: s.get() for k, s in self._advanced_sliders.items()},
        )

    def _save_config(self) -> None:
        self.app_config = self._current_config()
        self.app_config.save()

    # --- イベントハンドラ --------------------------------------------------

    def _on_device_changed(self, _event=None) -> None:
        was_running = self.engine is not None and self.engine.is_running()
        if was_running:
            self._stop_engine()
        self._save_config()
        if was_running:
            self._start_engine()

    def _on_processing_toggle(self) -> None:
        if self.engine is not None:
            self.engine.bypass = not self.processing_enabled_var.get()
        self._save_config()

    def _on_preset_selected(self, _event=None) -> None:
        if self._updating_from_code:
            return
        preset_label_to_name = {p.label_ja: name for name, p in presets.PRESETS.items()}
        preset_name = preset_label_to_name[self.preset_var.get()]
        self.chain.set_preset(preset_name)
        self._updating_from_code = True
        self.clarity_var.set(self.chain.clarity_level)
        self.noise_var.set(self.chain.noise_level)
        self._sync_advanced_sliders_from_chain()
        self._updating_from_code = False
        self._save_config()

    def _on_clarity_selected(self, _event=None) -> None:
        if self._updating_from_code:
            return
        self.chain.set_clarity(self.clarity_var.get())
        self._updating_from_code = True
        self._sync_advanced_sliders_from_chain()
        self._updating_from_code = False
        self._save_config()

    def _on_noise_selected(self, _event=None) -> None:
        if self._updating_from_code:
            return
        self.chain.set_noise(self.noise_var.get())
        self._updating_from_code = True
        self._sync_advanced_sliders_from_chain()
        self._updating_from_code = False
        self._save_config()

    def _sync_advanced_sliders_from_chain(self) -> None:
        clarity_stage = presets.CLARITY_STAGES[self.chain.clarity_level]
        noise_stage = presets.NOISE_STAGES[self.chain.noise_level]
        preset = presets.PRESETS[self.chain.preset_name]
        band_by_freq = {band.frequency_hz: band for band in clarity_stage.bands}

        values = {
            "clarity_highpass_hz": clarity_stage.highpass_hz,
            "clarity_200hz_gain_db": band_by_freq[200.0].gain_db,
            "clarity_300hz_gain_db": band_by_freq[300.0].gain_db,
            "clarity_2000hz_gain_db": band_by_freq[2000.0].gain_db,
            "clarity_3000hz_gain_db": band_by_freq[3000.0].gain_db,
            "clarity_4000hz_gain_db": band_by_freq[4000.0].gain_db,
            "noise_wet_dry_mix": noise_stage.wet_dry_mix,
            "noise_gate_threshold": noise_stage.gate_threshold,
            "noise_gate_release_ms": noise_stage.gate_release_ms,
            "compressor_threshold_db": preset.compressor.threshold_db,
            "compressor_ratio": preset.compressor.ratio,
            "compressor_attack_ms": preset.compressor.attack_ms,
            "compressor_release_ms": preset.compressor.release_ms,
            "agc_target_dbfs": preset.agc.target_dbfs,
            "agc_max_gain_db": preset.agc.max_gain_db,
        }
        for key, value in values.items():
            self._advanced_sliders[key].set(value)

    def _apply_advanced_overrides(self, overrides: dict) -> None:
        for key, value in overrides.items():
            if key in self._advanced_sliders:
                self._advanced_sliders[key].set(value)
        if overrides:
            self._on_advanced_slider_changed(None)

    def _on_advanced_slider_changed(self, _changed_key: Optional[str]) -> None:
        if self._updating_from_code:
            return
        s = {key: scale.get() for key, scale in self._advanced_sliders.items()}
        clarity_stage = presets.ClarityStage(
            highpass_hz=s["clarity_highpass_hz"],
            bands=(
                presets.EqBand(200.0, s["clarity_200hz_gain_db"], 1.2),
                presets.EqBand(300.0, s["clarity_300hz_gain_db"], 1.2),
                presets.EqBand(2000.0, s["clarity_2000hz_gain_db"], 1.0),
                presets.EqBand(3000.0, s["clarity_3000hz_gain_db"], 1.0),
                presets.EqBand(4000.0, s["clarity_4000hz_gain_db"], 1.0),
            ),
        )
        noise_stage = presets.NoiseStage(
            wet_dry_mix=s["noise_wet_dry_mix"],
            gate_threshold=s["noise_gate_threshold"],
            gate_release_ms=s["noise_gate_release_ms"],
        )
        compressor = presets.CompressorParams(
            threshold_db=s["compressor_threshold_db"],
            ratio=s["compressor_ratio"],
            attack_ms=s["compressor_attack_ms"],
            release_ms=s["compressor_release_ms"],
        )
        agc = presets.AgcParams(target_dbfs=s["agc_target_dbfs"], max_gain_db=s["agc_max_gain_db"])

        self.chain.set_clarity_stage(clarity_stage)
        self.chain.set_noise_stage(noise_stage)
        self.chain.set_compressor(compressor)
        self.chain.set_agc(agc)
        self._save_config()

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._advanced_frame.grid(row=5, column=0, sticky="ew", padx=8, pady=4)
            self._advanced_toggle_button.configure(text="詳細設定を閉じる")
        else:
            self._advanced_frame.grid_remove()
            self._advanced_toggle_button.configure(text="詳細設定を開く")

    def _on_test_clicked(self) -> None:
        input_device = self._device_index_by_name(self._input_devices, self.input_device_var.get())
        output_device = self._device_index_by_name(self._output_devices, self.output_device_var.get())
        self.test_button.configure(state="disabled")
        self.test_status_var.set("録音中...")

        def worker():
            try:
                audio = record_and_process_preview(self.chain, input_device, TEST_PREVIEW_SECONDS)
                self.test_status_var.set("再生中...")
                play_preview(audio, output_device)
                self.test_status_var.set("完了")
            except Exception as exc:  # デバイスエラー等をGUIに表示するため広く捕捉する
                self.test_status_var.set(f"エラー: {exc}")
            finally:
                self.test_button.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _device_index_by_name(devices, name: str) -> Optional[int]:
        for d in devices:
            if d.name == name:
                return d.index
        return None

    # --- エンジン制御(ストリーム開始/停止) ---------------------------------

    def _start_engine(self) -> None:
        input_device = self._device_index_by_name(self._input_devices, self.input_device_var.get())
        output_device = self._device_index_by_name(self._output_devices, self.output_device_var.get())
        engine = AudioEngine(
            self.chain,
            input_device=input_device,
            output_device=output_device,
            on_meter_update=self._on_meter_update,
        )
        engine.bypass = not self.processing_enabled_var.get()
        try:
            engine.start()
        except Exception as exc:
            # デバイス未接続・権限エラー等でここに到達し得る。アプリ全体を落とさず、
            # ユーザーがデバイスを選び直せるようにステータス表示のみ行う。
            self.test_status_var.set(f"ストリーム開始エラー: {exc}")
            return
        self.engine = engine

    def _stop_engine(self) -> None:
        if self.engine is not None:
            self.engine.stop()
            self.engine = None

    def _on_meter_update(self, in_rms, in_peak, out_rms, out_peak) -> None:
        # sounddeviceのコールバックスレッドから呼ばれるため、Tkinter更新はafterで
        # メインスレッドに戻す。
        self.after(0, lambda: self.input_meter.update_levels(in_rms, in_peak))
        self.after(0, lambda: self.output_meter.update_levels(out_rms, out_peak))

    def _on_close(self) -> None:
        self._save_config()
        self._stop_engine()
        self.chain.close()
        self.destroy()


def main() -> None:
    app = App()
    app._start_engine()
    app.mainloop()


if __name__ == "__main__":
    main()
