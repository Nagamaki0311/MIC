"""Tkinterメインウィンドウ。

不要な常駐機能・複雑な設定画面を増やさない方針(Issue原文)に沿い、基本画面は
1画面に収め、パラメータの生値編集は折りたたみ式の詳細設定パネルにのみ置く。
"""

from __future__ import annotations

import platform
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from soloclarity import __version__, presets
from soloclarity.audio import devices as device_lib
from soloclarity.audio.engine import AudioEngine, play_preview, record_and_process_preview
from soloclarity.config import AppConfig
from soloclarity.dsp.chain import VoiceChain
from soloclarity.gui.meter_widget import MeterWidget

TEST_PREVIEW_SECONDS = 3.0
# テストボタンのworker thread(録音+再生)の完了を`_on_close`で待つ際の上限。
# 録音(TEST_PREVIEW_SECONDS)+再生+デバイスI/Oの余裕を見込む。
TEST_THREAD_JOIN_TIMEOUT_SECONDS = TEST_PREVIEW_SECONDS * 2 + 5.0
# `_on_close`がworker threadの完了を待つ間、self.update()を呼ぶ間隔。
TEST_THREAD_POLL_INTERVAL_SECONDS = 0.01

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

# キー -> (最小, 最大)。config.json経由で範囲外の極端な値が注入された場合に、
# tk.Scale.set()の暗黙のクランプ挙動に頼らず明示的にクランプするために使う
# (Reviewer指摘5)。
_ADVANCED_SLIDER_RANGES: dict[str, tuple[float, float]] = {
    key: (lo, hi) for key, _label, lo, hi, _res in ADVANCED_SLIDER_SPECS
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"SoloClarity v{__version__}")
        self.resizable(False, False)

        self.app_config = AppConfig.load()
        try:
            self.chain = VoiceChain(self.app_config.preset)
        except Exception as exc:
            # RNNoiseライブラリが見つからない等、DSPチェーンの初期化自体に失敗した場合。
            # ウィンドウを破棄した上で、main()側でmessageboxとして分かりやすく表示する。
            self.destroy()
            raise RuntimeError(f"音声処理エンジンの初期化に失敗しました: {exc}") from exc
        self.engine: Optional[AudioEngine] = None
        self._test_thread: Optional[threading.Thread] = None
        self._closing = False

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

        status_frame = ttk.Frame(self)
        status_frame.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Label(status_frame, text="状態:").grid(row=0, column=0, sticky="w")
        # ストリーム全体の状態・エラーはここに表示する(テスト再生ボタン専用の
        # test_status_varとは責務を分ける)。
        self.engine_status_var = tk.StringVar(value="停止中")
        ttk.Label(status_frame, textvariable=self.engine_status_var).grid(
            row=0, column=1, sticky="w"
        )

        test_frame = ttk.Frame(self)
        test_frame.grid(row=4, column=0, sticky="ew", **pad)
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
        toggle_frame.grid(row=5, column=0, sticky="ew", padx=8, pady=(4, 0))
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
                lo, hi = _ADVANCED_SLIDER_RANGES[key]
                # tk.Scale.set()は範囲外の値を暗黙にクランプするが、それに頼らず
                # ここで明示的にクランプする(Reviewer指摘5)。
                self._advanced_sliders[key].set(_clamp(value, lo, hi))
        if overrides:
            self._apply_slider_values_to_chain()

    def _on_advanced_slider_changed(self, _changed_key: Optional[str]) -> None:
        if self._updating_from_code:
            return
        self._apply_slider_values_to_chain()

    def _apply_slider_values_to_chain(self) -> None:
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
            self._advanced_frame.grid(row=6, column=0, sticky="ew", padx=8, pady=4)
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
            # このworkerはバックグラウンドスレッドで動く。Tkinterウィジェットの
            # 直接操作はスレッドセーフでないため、_on_meter_update等と同様に
            # self.after(0, ...)経由でメインスレッドへ処理を戻す(Reviewer指摘3)。
            try:
                audio = record_and_process_preview(self.chain, input_device, TEST_PREVIEW_SECONDS)
                self.after(0, lambda: self.test_status_var.set("再生中..."))
                play_preview(audio, output_device)
                self.after(0, lambda: self.test_status_var.set("完了"))
            except Exception as exc:  # デバイスエラー等をGUIに表示するため広く捕捉する
                # `except ... as exc`はブロック終了時に暗黙で`del exc`されるため、
                # after(0, ...)で遅延実行するlambdaがexcを直接参照するとNameErrorに
                # なる。先にメッセージへ変換してから閉じ込める。
                message = str(exc)
                self.after(0, lambda: self.test_status_var.set(f"エラー: {message}"))
            finally:
                self.after(0, lambda: self.test_button.configure(state="normal"))

        self._test_thread = threading.Thread(target=worker, daemon=True)
        self._test_thread.start()

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
            on_error=self._on_engine_error,
        )
        engine.bypass = not self.processing_enabled_var.get()
        try:
            engine.start()
        except Exception as exc:
            # デバイス未接続・権限エラー等でここに到達し得る。アプリ全体を落とさず、
            # ユーザーがデバイスを選び直せるようにステータス表示のみ行う。
            self.engine_status_var.set(f"ストリーム開始エラー: {exc}")
            return
        self.engine = engine
        self.engine_status_var.set("動作中")

    def _stop_engine(self) -> None:
        if self.engine is not None:
            self.engine.stop()
            self.engine = None
            self.engine_status_var.set("停止中")

    def _on_meter_update(self, in_rms, in_peak, out_rms, out_peak) -> None:
        # sounddeviceのコールバックスレッドから呼ばれるため、Tkinter更新はafterで
        # メインスレッドに戻す。
        self.after(0, lambda: self.input_meter.update_levels(in_rms, in_peak))
        self.after(0, lambda: self.output_meter.update_levels(out_rms, out_peak))

    def _on_engine_error(self, message: str) -> None:
        # AudioEngineのコールバックスレッドから呼ばれるため、Tkinter更新はafterで
        # メインスレッドに戻す。処理は自動的にバイパスへフォールバック済みなので、
        # ここでは状態表示のみ行う(音は止めない)。
        self.after(
            0,
            lambda: self.engine_status_var.set(f"処理エラー(未加工の音声で継続中): {message}"),
        )

    def _on_close(self) -> None:
        if self._closing:
            # `_test_thread`の完了待ちループ中(最大TEST_THREAD_JOIN_TIMEOUT_SECONDS)は
            # self.update()でTclのイベントループが回っているため、ユーザーが再度
            # 閉じる操作(ウィンドウのXボタン等)をすると`_on_close`が再入され得る。
            # 内側の呼び出しが先にself.destroy()まで完了すると、外側の呼び出しが
            # 自分のself.destroy()に到達した時点で
            # `TclError: application has been destroyed`になる(Reviewer指摘、実機再現済み)。
            # 多重実行防止フラグで即座に無視する。
            return
        self._closing = True
        self._save_config()
        if self._test_thread is not None and self._test_thread.is_alive():
            # テスト再生のworker threadが`self.chain`を使用中に`chain.close()`と
            # 競合しないよう、閉じる前に完了を待つ(構造的にレースを避ける。
            # Reviewer指摘3)。
            #
            # 単純な`Thread.join()`ではなく`self.update()`を挟みながらポーリングする
            # 必要がある: workerが`self.after(0, ...)`でメインスレッドに処理を戻そうと
            # した際、Tclはメインスレッドがイベントループを実際に処理していることを
            # 要求する。メインスレッドが素の`join()`でブロックしたままだと、worker側の
            # `after()`呼び出しがメインスレッドの応答を待って停止し、双方が互いを
            # 待ち続ける状態になることを実機検証で確認した。`update()`でイベントを
            # 処理し続けることでworkerのafter()呼び出しを解放し、正しく完了させる。
            deadline = time.monotonic() + TEST_THREAD_JOIN_TIMEOUT_SECONDS
            while self._test_thread.is_alive() and time.monotonic() < deadline:
                self.update()
                time.sleep(TEST_THREAD_POLL_INTERVAL_SECONDS)
        self._stop_engine()
        self.chain.close()
        self.destroy()


def _set_windows_dpi_awareness() -> None:
    """Windowsの高DPI(125%/150%等)環境で文字・要素がぼやけるのを防ぐ。

    Tkinterは既定では高DPIを意識しないため、起動時にプロセスのDPI Awarenessを
    明示的に設定する。古いWindowsや権限の問題等でこの呼び出し自体が失敗しても、
    アプリの起動は継続する(表示が多少ぼやける程度で機能自体に影響しないため)。
    Linux(この開発・テスト環境含む)では`platform.system() != "Windows"`の時点で
    何もせず戻るため、このモジュールのテストはLinux上でも壊れない。
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        # PROCESS_SYSTEM_DPI_AWARE(=1)。Shcore.dllはWindows 8.1以降で利用可能。
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _show_startup_error(exc: Exception) -> None:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "SoloClarity 起動エラー",
        "SoloClarityの起動に失敗しました。\n\n"
        f"{exc}\n\n"
        "RNNoiseライブラリ(rnnoise.dll)が正しい場所に配置されているか確認してください。",
    )
    root.destroy()


def main() -> None:
    _set_windows_dpi_awareness()
    try:
        app = App()
    except Exception as exc:
        _show_startup_error(exc)
        return
    app._start_engine()
    app.mainloop()


if __name__ == "__main__":
    main()
