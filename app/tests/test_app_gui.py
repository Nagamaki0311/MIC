"""Tkinter GUI(app.py)の構造的な動作をxvfb環境で検証する。

実際のオーディオデバイス・SoloCast/VB-Cable経由の聞こえ方はこの環境では
検証できない(WINDOWS_VERIFICATION_CHECKLIST.md参照)。ここではウィジェット構築・
状態表示の責務分離・エラー導線・デバイス0件時の挙動等、Discordクライアントや
実オーディオデバイスに依存しない構造面のみを確認する。
"""

from __future__ import annotations

import pytest

from soloclarity import __version__, presets
from soloclarity.audio import devices as device_lib
from soloclarity.dsp import chain as chain_mod


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
