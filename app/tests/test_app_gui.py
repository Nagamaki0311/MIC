"""Tkinter GUI(app.py)の構造的な動作をxvfb環境で検証する。

実際のオーディオデバイス・SoloCast/VB-Cable経由の聞こえ方はこの環境では
検証できない(WINDOWS_VERIFICATION_CHECKLIST.md参照)。ここではウィジェット構築・
状態表示の責務分離・エラー導線・デバイス0件時の挙動等、Discordクライアントや
実オーディオデバイスに依存しない構造面のみを確認する。
"""

from __future__ import annotations

import math
import threading

import numpy as np
import pytest

from soloclarity import __version__, presets
from soloclarity.audio import devices as device_lib
from soloclarity.dsp import chain as chain_mod
from soloclarity.gui import app as app_mod


@pytest.fixture
def patched_voice_chain(rnnoise_library_path, monkeypatch):
    """VoiceChainの既定ライブラリ探索先をこの環境のテスト用RNNoiseへ差し替える。

    実配布(Windows)ではsoloclarity/dsp/vendor/rnnoise.dllが使われるが(D-001)、
    この開発環境のvendor下には共有ライブラリが存在しないため、pyrnnoise由来の
    テスト用ライブラリを常に使うようVoiceChain.__init__を差し替える。
    """
    original_init = chain_mod.VoiceChain.__init__
    lib_path = rnnoise_library_path

    def patched(self, preset_name=presets.DEFAULT_PRESET, rnnoise_library_path=None):
        original_init(self, preset_name, rnnoise_library_path=lib_path)

    monkeypatch.setattr(chain_mod.VoiceChain, "__init__", patched)


@pytest.fixture
def app_factory(gui_display, patched_voice_chain):
    from soloclarity.gui.app import App

    created = []

    def _factory():
        app = App()
        created.append(app)
        return app

    yield _factory
    for app in created:
        try:
            app.destroy()
        except Exception:
            pass


class TestWindowTitleAndVersion:
    def test_title_shows_version(self, app_factory):
        app = app_factory()
        assert app.title() == f"SoloClarity v{__version__}"


class TestEngineStatusIsSeparateFromTestStatus:
    def test_initial_engine_status_is_stopped(self, app_factory):
        app = app_factory()
        assert app.engine_status_var.get() == "停止中"

    def test_engine_error_updates_engine_status_only(self, app_factory):
        app = app_factory()
        app.test_status_var.set("録音中...")

        app._on_engine_error("synthetic failure")
        app.update()  # after(0, ...)で予約されたコールバックを処理する

        assert "synthetic failure" in app.engine_status_var.get()
        # テストボタン専用のラベルは変化しない(責務分離)
        assert app.test_status_var.get() == "録音中..."

    def test_stream_start_failure_updates_engine_status_only(self, app_factory):
        app = app_factory()
        app.test_status_var.set("")
        # 入出力デバイスが存在しない状態(存在しないデバイス名)でストリーム開始を試み、
        # AudioEngine.start()が例外を送出する経路を再現する。
        app.input_device_var.set("__does_not_exist__")
        app.output_device_var.set("__does_not_exist__")

        app._start_engine()

        assert app.engine_status_var.get().startswith("ストリーム開始エラー")
        assert app.test_status_var.get() == ""


class TestZeroDevices:
    def test_app_does_not_crash_with_no_devices(self, gui_display, patched_voice_chain, monkeypatch):
        monkeypatch.setattr(device_lib, "list_devices", lambda: [])
        from soloclarity.gui.app import App

        app = App()
        try:
            assert app.input_device_var.get() == ""
            assert app.output_device_var.get() == ""
            assert app._input_devices == []
            assert app._output_devices == []
        finally:
            app.destroy()


class TestVoiceChainInitFailureIsReportedClearly:
    def test_missing_rnnoise_library_raises_clear_runtime_error(self, gui_display, monkeypatch):
        """RNNoiseライブラリが見つからない場合、意味不明なスタックトレースではなく
        分かりやすいRuntimeErrorとして起動シーケンスへ伝播すること(main側でmessageboxに変換する)。
        """
        from soloclarity.gui.app import App

        def raise_missing_library(self, *args, **kwargs):
            raise OSError("RNNoise library not found: /dummy/path/librnnoise.so")

        monkeypatch.setattr(chain_mod.VoiceChain, "__init__", raise_missing_library)

        with pytest.raises(RuntimeError, match="音声処理エンジンの初期化に失敗しました"):
            App()


class TestWindowsDpiAwareness:
    def test_no_op_and_does_not_raise_on_linux(self):
        from soloclarity.gui.app import _set_windows_dpi_awareness

        # このテスト自体がLinux上で実行される前提(壊れたら失敗する最小限の確認)。
        import platform

        assert platform.system() != "Windows"
        _set_windows_dpi_awareness()  # 例外を送出しないこと


class TestExtremeAdvancedOverrideValuesAreClamped:
    """Reviewer指摘5(Low, CONFIRMED)への対応。

    ADVANCED_SLIDER_SPECSの範囲外の極端な値がconfig.json経由で注入されても、
    tk.Scale.set()の暗黙のクランプ挙動に頼らず明示的にクランプされ、VoiceChainへ
    NaN/Infや極端値が到達しないことを直接検証する。
    """

    def test_extreme_finite_overrides_are_clamped_into_spec_range(self, app_factory):
        app = app_factory()
        overrides = {
            "agc_target_dbfs": -1e9,  # spec range: -30.0..-6.0
            "agc_max_gain_db": 1e9,  # spec range: 0.0..24.0
            "compressor_ratio": -50.0,  # spec range: 1.0..10.0
            "clarity_highpass_hz": 1e12,  # spec range: 40.0..150.0
        }

        app._apply_advanced_overrides(overrides)

        spec_ranges = {
            key: (lo, hi) for key, _label, lo, hi, _res in app_mod.ADVANCED_SLIDER_SPECS
        }
        for key in overrides:
            lo, hi = spec_ranges[key]
            slider_value = app._advanced_sliders[key].get()
            assert math.isfinite(slider_value)
            assert lo <= slider_value <= hi

        # チェーンに実際に反映された値も有限であること(NaN/Infがどこにも伝播しない)。
        assert math.isfinite(app.chain.agc.target_linear)
        assert math.isfinite(app.chain.agc.max_gain_linear)
        assert math.isfinite(app.chain.agc.min_gain_linear)

    def test_clamp_helper_bounds_values_to_the_given_range(self):
        assert app_mod._clamp(5.0, 0.0, 10.0) == 5.0
        assert app_mod._clamp(-100.0, 0.0, 10.0) == 0.0
        assert app_mod._clamp(100.0, 0.0, 10.0) == 10.0


class TestTestButtonThreadSafety:
    """Reviewer指摘3(Medium, CONFIRMED/PLAUSIBLE)への対応。

    テスト再生のworker threadからのTkinter操作をself.after(0, ...)経由に統一し、
    `_on_close`がworker threadの完了を待ってからchain.close()するようにした。

    `self.after(0, ...)`をworker thread(バックグラウンドスレッド)から呼ぶには、
    メインスレッドが実際に`mainloop()`でTclのイベントループを回している必要がある
    ことを実機検証で確認した(`app.update()`のポーリングだけでは、Tcl側が
    「メインスレッドがメインループ中である」と認識せず、workerの`after()`呼び出しが
    `RuntimeError: main thread is not in main loop`になる)。そのため、以下のテストは
    実際に`app.mainloop()`をテストのメインスレッドで走らせ、workerの完了を監視する
    別スレッド(watcher)が`app.after(0, app.quit)`でmainloopを止める構成にする。
    ハング防止に安全弁のタイムアウトも設定する。
    """

    SAFETY_TIMEOUT_MS = 5000

    def test_worker_updates_status_via_after_and_reaches_completed_state(
        self, app_factory, monkeypatch
    ):
        monkeypatch.setattr(
            app_mod,
            "record_and_process_preview",
            lambda chain, device, duration: np.zeros(10, dtype=np.float32),
        )
        monkeypatch.setattr(app_mod, "play_preview", lambda audio, device: None)

        app = app_factory()
        app._on_test_clicked()
        assert app._test_thread is not None

        def stop_when_done():
            app._test_thread.join()
            app.after(0, app.quit)

        watcher = threading.Thread(target=stop_when_done, daemon=True)
        watcher.start()
        app.after(self.SAFETY_TIMEOUT_MS, app.quit)  # 安全弁(ハング防止)
        app.mainloop()
        watcher.join(timeout=1.0)

        assert not app._test_thread.is_alive()
        assert app.test_status_var.get() == "完了"
        assert str(app.test_button.cget("state")) == "normal"

    def test_closing_window_while_worker_is_running_waits_and_does_not_raise(
        self, app_factory, monkeypatch
    ):
        """テスト再生ボタンを押した直後にウィンドウを閉じても、workerとchain.close()が
        競合してクラッシュしない(Reviewerが実機再現した`TclError`シナリオの再現)。

        `_on_close`自体は変更せず、mainloopが実際に回っている状態からウィンドウの
        閉じるイベントを起こして検証する。
        """
        monkeypatch.setattr(
            app_mod,
            "record_and_process_preview",
            lambda chain, device, duration: np.zeros(10, dtype=np.float32),
        )
        play_finished = threading.Event()

        def slow_play_preview(audio, device):
            import time

            time.sleep(0.2)
            play_finished.set()

        monkeypatch.setattr(app_mod, "play_preview", slow_play_preview)

        app = app_factory()
        errors: list[BaseException] = []

        def click_then_close():
            app._on_test_clicked()
            # workerがまだ実行中(録音/再生の途中)のはずのタイミングで即座に閉じる。
            try:
                app._on_close()  # 例外を送出しないこと。内部でworkerの完了を待つ。
            except BaseException as exc:  # noqa: BLE001 - テストで検出するため広く捕捉
                errors.append(exc)
            finally:
                if app.winfo_exists():
                    app.quit()

        app.after(0, click_then_close)
        app.after(self.SAFETY_TIMEOUT_MS, lambda: app.quit() if app.winfo_exists() else None)
        app.mainloop()

        assert errors == []
        assert play_finished.is_set()  # closeがworkerの完了を待ったことの確認

    def test_reentrant_close_while_waiting_for_worker_does_not_raise(
        self, app_factory, monkeypatch
    ):
        """`_on_close`が待機ループ(self.update()ポーリング)中に再入されても
        `TclError: application has been destroyed`を起こさない(Reviewer再指摘、
        実機再現済み: `_on_close`実行中はself.update()でTclのイベントループが
        回っているため、ユーザーが再度閉じる操作をすると`_on_close`が再入され得る。
        内側の呼び出しが先にdestroy()し、外側の呼び出しが自分のdestroy()に到達した
        時点でTclErrorになっていた)。

        Reviewerの再現方法(app.after()で_on_closeを2回ディスパッチする)を踏襲する。
        """
        monkeypatch.setattr(
            app_mod,
            "record_and_process_preview",
            lambda chain, device, duration: np.zeros(10, dtype=np.float32),
        )

        def slow_play_preview(audio, device):
            import time

            time.sleep(0.3)

        monkeypatch.setattr(app_mod, "play_preview", slow_play_preview)

        app = app_factory()
        errors: list[BaseException] = []
        close_call_count = {"n": 0}

        def safe_close():
            close_call_count["n"] += 1
            try:
                app._on_close()
            except BaseException as exc:  # noqa: BLE001 - テストで検出するため広く捕捉
                errors.append(exc)

        def start_and_schedule_double_close():
            app._on_test_clicked()
            # workerがまだ実行中(slow_play_previewの0.3秒待ち)の間に_on_close()を
            # 2回ディスパッチする。1回目の待機ループ(self.update()ポーリング)中に
            # 2回目がTclのイベントループ経由で再入されるケースを狙う。
            app.after(0, safe_close)
            app.after(20, safe_close)

        app.after(0, start_and_schedule_double_close)
        app.after(self.SAFETY_TIMEOUT_MS, lambda: app.quit() if app.winfo_exists() else None)
        app.mainloop()

        assert close_call_count["n"] == 2  # 2回とも呼ばれた(2回目は即returnする)こと
        assert errors == []  # 再入によるTclErrorが発生しないこと
