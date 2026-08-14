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
from soloclarity.audio.engine import AudioEngine
from soloclarity.dsp import chain as chain_mod
from soloclarity.dsp.chain import FRAME_SIZE
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
    def test_does_not_raise_on_any_platform(self):
        """Windows以外ではno-op、Windows(CI含む)では実際にDPI awarenessを
        試みるが、いずれの場合も例外を送出しないこと(D-005参照)。

        CI(.github/workflows/build-windows.yml)がwindows-latest上で
        このテストを実行するため、`platform.system()`の値をどちらか一方に
        決め打ちしないこと(過去にLinux決め打ちの表明でWindows CI上で
        失敗した実績があるため)。"""
        from soloclarity.gui.app import _set_windows_dpi_awareness

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

        spec_ranges = {spec.key: (spec.lo, spec.hi) for spec in app_mod.ADVANCED_SLIDER_SPECS}
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


class TestAdvancedSliderChangesReflectLiveInAudioEngine:
    """Manager指摘(追加1): 詳細設定スライダーの変更がAudioEngineの実処理へ
    ライブ反映されているかを、xvfb環境でAudioEngineを(実オーディオデバイスを
    介さず)直接駆動して検証する。`App._apply_slider_values_to_chain()`は
    `self.chain`(AudioEngineがコールバック内で参照するのと同一のインスタンス)
    を直接書き換えるため、追加の配線なしに次のフレームから反映されるはずである。
    """

    @staticmethod
    def _process_once(engine: AudioEngine, frame: np.ndarray) -> np.ndarray:
        indata = frame.reshape(-1, 1)
        engine._input_callback(indata, FRAME_SIZE, None, None)
        outdata = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
        engine._output_callback(outdata, FRAME_SIZE, None, None)
        return outdata[:, 0].copy()

    @classmethod
    def _process_settled(cls, engine: AudioEngine, frame: np.ndarray, n: int = 8) -> np.ndarray:
        """同じフレーム内容をn回繰り返し流し、最後の出力を返す。

        D-015: `VoiceChain`にdry/wetパスの時間整列バッファ(2フレーム)が追加され、
        `AudioEngine`のjitterバッファpriming(D-015、PRIME_TARGET_FRAMES=2)と合わせて
        起動直後は出力が無音のままになる区間が伸びた。1回きりの`_process_once`では
        両方のバッファがまだ埋まりきっておらず、スライダー変更前後どちらの呼び出しも
        無音のまま比較してしまう恐れがあるため、十分な回数流してから比較する。
        """
        out = cls._process_once(engine, frame)
        for _ in range(n - 1):
            out = cls._process_once(engine, frame)
        return out

    def test_engine_holds_the_same_chain_instance_as_the_app(self, app_factory):
        app = app_factory()
        engine = AudioEngine(app.chain)
        assert engine.chain is app.chain

    def test_moving_a_slider_mutates_the_chain_the_engine_is_already_wired_to(self, app_factory):
        app = app_factory()
        engine = AudioEngine(app.chain)
        app._toggle_advanced()  # 実際のユーザー操作と同じく、パネルを開いてから動かす
        app.update()

        before_stage = app.chain._noise_stage
        new_value = 0.0 if before_stage.background_wet_dry_mix != 0.0 else 1.0
        app._advanced_sliders["noise_background_mix"].set(new_value)
        app.update()

        # set_noise_stage()は新しいNoiseStageインスタンスを代入する(chain.py参照)。
        assert app.chain._noise_stage is not before_stage
        assert app.chain._noise_stage.background_wet_dry_mix == pytest.approx(new_value)
        # AudioEngine.chainはApp.chainと同一オブジェクトなので、ストリームを
        # 再構築しなくても次のフレームから新しい値が使われる。
        assert engine.chain._noise_stage.background_wet_dry_mix == pytest.approx(new_value)

    def test_input_callback_output_changes_after_slider_moves(self, app_factory):
        """スライダー変更の効果が、実際に_input_callback/_output_callback
        経由の出力に現れることを、同一入力に対する処理結果の変化で確認する。"""
        app = app_factory()
        engine = AudioEngine(app.chain)
        app._toggle_advanced()
        app.update()

        rng = np.random.default_rng(1)
        frame = rng.normal(0.0, 0.05, FRAME_SIZE).astype(np.float32)
        out_before = self._process_settled(engine, frame)

        # background_wet_dry_mixを大きく変える(RNNoiseの適用量が変わり、
        # 同一フレームに対する出力が変わるはず)。
        app._advanced_sliders["noise_background_mix"].set(0.0)
        app.update()
        out_after = self._process_settled(engine, frame)

        assert not np.allclose(out_before, out_after)


class TestOpeningAdvancedPanelDoesNotSpuriouslyChangeSettings:
    """Manager指摘(追加1)の調査で判明した副作用への回帰テスト。

    tk.Scaleは初めて画面上にマップされる際、内部の表示同期処理として
    -commandを現在値のまま自動的に一度発火させることがある(xvfb実機検証で
    確認したTkinter固有の挙動)。ユーザーが何も操作していないのに詳細設定
    パネルを開いただけでchainの値やconfig.jsonが変わってしまわないことを
    確認する(ガード無しではこの挙動が再現することを、ガードを一時的に外す
    ことで確認済み)。
    """

    def test_first_open_does_not_mutate_chain_or_show_feedback(self, app_factory):
        app = app_factory()
        before_values = {key: scale.get() for key, scale in app._advanced_sliders.items()}
        before_mix = app.chain._noise_stage.background_wet_dry_mix

        app._toggle_advanced()
        app.update()

        after_values = {key: scale.get() for key, scale in app._advanced_sliders.items()}
        assert after_values == before_values
        assert app.chain._noise_stage.background_wet_dry_mix == before_mix
        assert app.advanced_apply_status_var.get() == ""


class TestAdvancedApplyFeedback:
    """Manager指摘(追加1): 反映済みであることをユーザーに示すフィードバック表示。"""

    def test_real_slider_change_shows_and_then_clears_feedback(self, app_factory, monkeypatch):
        monkeypatch.setattr(app_mod, "ADVANCED_APPLY_FEEDBACK_DURATION_MS", 50)
        app = app_factory()
        app._toggle_advanced()
        app.update()

        assert app.advanced_apply_status_var.get() == ""
        app._advanced_sliders["noise_impact_mix"].set(0.9)
        app.update()
        assert app.advanced_apply_status_var.get() == "設定を反映しました"

        import time

        time.sleep(0.1)
        app.update()
        assert app.advanced_apply_status_var.get() == ""

    def test_config_restore_does_not_show_feedback(self, app_factory):
        """`_apply_advanced_overrides`(config復元経路)は`_apply_slider_values_to_chain()`
        を直接呼ぶため、ユーザー操作用のフィードバックは表示されないこと。"""
        app = app_factory()
        app._apply_advanced_overrides({"noise_impact_mix": 0.5})
        app.update()
        assert app.advanced_apply_status_var.get() == ""


class TestAdvancedPanelIsScrollableAndWindowFitsCommonScreens:
    """Manager指摘(追加2): ウィンドウが縦長で画面からはみ出る問題への対応。

    詳細設定パネルをCanvas+Scrollbarでラップし、パネルを開いた状態でも
    ウィンドウ全体の高さが一般的なノートPC画面(1366x768等)に収まる
    (またはスクロールで全項目にアクセスできる)ことを確認する。
    """

    # 1366x768のようなノートPC画面でタイトルバー・タスクバー分の余白を見込んだ
    # 上限。ウィンドウの高さがこれを超えないことを確認する。
    COMMON_LAPTOP_SCREEN_HEIGHT_MARGIN = 700

    def test_window_height_with_panel_open_fits_common_laptop_screen(self, app_factory):
        app = app_factory()
        app.update()
        app._toggle_advanced()
        app.update()

        assert app.winfo_height() <= self.COMMON_LAPTOP_SCREEN_HEIGHT_MARGIN

    def test_advanced_frame_content_exceeds_visible_canvas_and_scrollbar_covers_it(
        self, app_factory
    ):
        """16項目分のスライダー全体の高さは表示領域より大きく、実際に
        スクロール可能である(=はみ出た項目にアクセスする手段がある)ことを
        確認する。"""
        app = app_factory()
        app._toggle_advanced()
        app.update()
        app.update_idletasks()

        content_height = app._advanced_frame.winfo_reqheight()
        assert content_height > app_mod.ADVANCED_PANEL_MAX_HEIGHT_PX

        before_top = app._advanced_canvas.yview()[0]
        app._advanced_canvas.yview_scroll(5, "units")
        app.update()
        after_top = app._advanced_canvas.yview()[0]
        assert after_top > before_top

    def test_base_screen_without_advanced_panel_fits_common_laptop_screen(self, app_factory):
        """詳細設定を開く前の基本画面自体も、一般的なノートPC画面に収まること。"""
        app = app_factory()
        app.update()
        assert app.winfo_height() <= self.COMMON_LAPTOP_SCREEN_HEIGHT_MARGIN


class TestAdvancedPanelDoesNotClipHorizontallyAndWindowIsResizable:
    """T-007: 実機報告(v1.2.0でスライダーが横方向に見切れる)への対応(D-014)。

    Canvasのwidthを内容(self._advanced_frame)の実測要求幅に合わせて動的に
    設定していること、ウィンドウがユーザー側で拡縮可能になっていることを
    確認する。
    """

    def test_advanced_canvas_width_covers_content_width(self, app_factory):
        app = app_factory()
        app.update()
        app._toggle_advanced()
        app.update()
        app.update_idletasks()

        canvas_width = app._advanced_canvas.winfo_width()
        content_width = app._advanced_frame.winfo_reqwidth()
        assert canvas_width >= content_width

    def test_window_is_resizable(self, app_factory):
        app = app_factory()
        app.update()
        assert app.resizable() == (1, 1)

    def test_minsize_width_covers_advanced_panel_content(self, app_factory):
        """パネルを開いた状態で必要な幅以上をminsizeの幅として設定していること
        (幅だけ縮めて再び見切れることを防ぐ)。高さは意図的にこの下限に含めない
        (次のtest_closed_state_window_is_not_inflated_by_minsize参照)。"""
        app = app_factory()
        app.update()
        app._toggle_advanced()
        app.update()
        app.update_idletasks()

        required_width = app.winfo_reqwidth()
        min_width, _min_height = app.minsize()
        assert min_width >= required_width

    def test_closed_state_window_is_not_inflated_by_minsize(self, app_factory):
        """Reviewer指摘(High, CONFIRMED)の回帰防止。詳細設定パネルを一度も
        開いていない起動直後に、minsize()の高さがパネルを開いた状態のサイズ
        まで強制的に引き伸ばし、パネルの行(row=6)に空白を作っていないこと。
        縦方向はCanvas自身のスクロールバーで常にアクセスできるため、開いた
        状態の高さをウィンドウ全体の最小値として強制する必要はない。"""
        app = app_factory()
        app.update()
        closed_height = app.winfo_height()

        app._toggle_advanced()
        app.update()
        open_height = app.winfo_height()

        assert closed_height < open_height

    def test_widening_window_does_not_stretch_unrelated_frames(self, app_factory):
        """Reviewer指摘(Medium, CONFIRMED)の回帰防止。ルートのcolumnconfigure
        にweightを与えると、詳細設定パネル(row=6)だけでなくデバイス選択等の
        他フレーム(row=0)も同じ列を共有しているため、ウィンドウを横に広げた
        際にそれらの外枠だけ不自然に間延びしてしまっていた。"""
        app = app_factory()
        app.update()
        device_frame = app.grid_slaves(row=0, column=0)[0]
        app.update_idletasks()
        before_width = device_frame.winfo_width()

        app.geometry(f"{app.winfo_width() + 800}x{app.winfo_height()}")
        app.update()

        after_width = device_frame.winfo_width()
        assert after_width == before_width
