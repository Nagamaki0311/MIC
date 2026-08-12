"""AppConfigの読み書きと、信頼境界(config.json)での入力検証を確認する。

config.jsonはユーザーが手動編集したり、書き込み中の異常終了で壊れたりしうる
外部入力であるため、構文エラー・型不一致・非dict等の壊れ方それぞれに対して
クラッシュせずデフォルト相当へフォールバックすることを確認する。
"""

from __future__ import annotations

import json
import os

import pytest

from soloclarity import presets
from soloclarity.config import AppConfig


class TestSaveIsAtomic:
    def test_save_then_load_round_trip(self, tmp_path):
        path = str(tmp_path / "config.json")
        cfg = AppConfig(
            input_device_name="Mic A",
            output_device_name="CABLE Input",
            preset="low_voice",
            processing_enabled=False,
            advanced_overrides={"agc_target_dbfs": -18.5, "compressor_ratio": 2.5},
        )
        cfg.save(path)
        assert AppConfig.load(path) == cfg

    def test_save_does_not_leave_temp_file_behind(self, tmp_path):
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()
        path = str(config_dir / "config.json")
        AppConfig().save(path)
        assert os.listdir(config_dir) == ["config.json"]

    def test_failed_write_does_not_corrupt_existing_config(self, tmp_path, monkeypatch):
        """書き込み途中で失敗しても、既存のconfig.jsonが壊れず・一時ファイルも残らない。

        修正前の実装(open(path, "w")への直接書き込み)では、この失敗経路で
        既存ファイルが空/中途半端な内容に上書きされ得た。
        """
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()
        path = str(config_dir / "config.json")
        AppConfig(preset="natural").save(path)
        with open(path, "r", encoding="utf-8") as f:
            original_content = f.read()

        def boom(*args, **kwargs):
            raise OSError("simulated disk full")

        monkeypatch.setattr(json, "dump", boom)
        with pytest.raises(OSError):
            AppConfig(preset="low_voice").save(path)

        with open(path, "r", encoding="utf-8") as f:
            assert f.read() == original_content
        assert os.listdir(config_dir) == ["config.json"]


class TestLoadHandlesCorruptedConfig:
    def test_missing_file_returns_default(self, tmp_path):
        path = str(tmp_path / "does_not_exist.json")
        assert AppConfig.load(path) == AppConfig()

    def test_syntax_error_json_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        assert AppConfig.load(path) == AppConfig()

    @pytest.mark.parametrize("raw", ["null", "[1, 2, 3]", '"just a string"', "42", "true"])
    def test_valid_json_non_dict_falls_back_to_default(self, tmp_path, raw):
        """構文上は妥当なJSONでも中身がdictでなければクラッシュせずデフォルトへ戻る。"""
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
        assert AppConfig.load(path) == AppConfig()

    def test_missing_required_fields_uses_defaults_for_the_rest(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"preset": "low_voice"}, f)
        loaded = AppConfig.load(path)
        assert loaded.preset == "low_voice"
        assert loaded.processing_enabled == AppConfig().processing_enabled
        assert loaded.advanced_overrides == {}

    def test_wrong_type_processing_enabled_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"processing_enabled": "yes"}, f)
        loaded = AppConfig.load(path)
        assert loaded.processing_enabled == AppConfig().processing_enabled

    def test_unknown_preset_name_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"preset": "does_not_exist"}, f)
        loaded = AppConfig.load(path)
        assert loaded.preset == presets.DEFAULT_PRESET

    def test_wrong_type_advanced_overrides_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"advanced_overrides": "not-a-dict"}, f)
        loaded = AppConfig.load(path)
        assert loaded.advanced_overrides == {}

    def test_advanced_overrides_with_non_numeric_value_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"advanced_overrides": {"agc_target_dbfs": "loud"}}, f)
        loaded = AppConfig.load(path)
        assert loaded.advanced_overrides == {}

    def test_wrong_type_device_name_falls_back_to_default(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"input_device_name": 123}, f)
        loaded = AppConfig.load(path)
        assert loaded.input_device_name is None

    def test_unknown_extra_fields_are_ignored(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"preset": "natural", "some_future_field": 123}, f)
        loaded = AppConfig.load(path)
        assert loaded.preset == "natural"


class TestAdvancedOverridesRejectNonFiniteValues:
    """Reviewer指摘1(High, CONFIRMED)への対応。

    json.load()はJSONの`NaN`/`Infinity`/`-Infinity`トークンをそのまま
    float('nan')/float('inf')等として読み戻す。この値がtk.Scale.set()に渡ると
    TclErrorでアプリ起動が落ち、config.jsonを直さない限り毎回再現していた。
    """

    def test_nan_value_is_dropped_but_other_keys_are_kept(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"advanced_overrides": {"agc_target_dbfs": NaN, "compressor_ratio": 2.5}}')
        loaded = AppConfig.load(path)
        assert "agc_target_dbfs" not in loaded.advanced_overrides
        assert loaded.advanced_overrides == {"compressor_ratio": 2.5}

    def test_positive_infinity_value_is_dropped(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"advanced_overrides": {"agc_max_gain_db": Infinity, "agc_target_dbfs": -17.0}}')
        loaded = AppConfig.load(path)
        assert "agc_max_gain_db" not in loaded.advanced_overrides
        assert loaded.advanced_overrides == {"agc_target_dbfs": -17.0}

    def test_negative_infinity_value_is_dropped(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"advanced_overrides": {"compressor_threshold_db": -Infinity}}')
        loaded = AppConfig.load(path)
        assert loaded.advanced_overrides == {}

    def test_save_rejects_nan_in_advanced_overrides(self, tmp_path):
        """書き込み側でも有限性を防御する(信頼境界の両側での検証)。"""
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()
        path = str(config_dir / "config.json")
        cfg = AppConfig(advanced_overrides={"agc_target_dbfs": float("nan")})
        with pytest.raises(ValueError):
            cfg.save(path)
        # 失敗時に一時ファイルを残さない(既存のアトミック書き込みの保証と両立する)。
        assert not os.path.exists(path)
        assert os.listdir(config_dir) == []

    def test_save_rejects_infinity_in_advanced_overrides(self, tmp_path):
        path = str(tmp_path / "config.json")
        cfg = AppConfig(advanced_overrides={"agc_max_gain_db": float("inf")})
        with pytest.raises(ValueError):
            cfg.save(path)


class TestAdvancedOverridesPartialValidity:
    """Reviewer指摘4(Low, CONFIRMED)への対応。

    1項目でも不正だと辞書全体を破棄するall-or-nothingではなく、不正なキーだけを
    取り除き、ユーザーが調整した他の正当な設定は保持する。
    """

    def test_one_invalid_key_does_not_discard_the_rest(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "advanced_overrides": {
                        "agc_target_dbfs": -17.0,
                        "compressor_ratio": "bad-type",
                    }
                },
                f,
            )
        loaded = AppConfig.load(path)
        assert loaded.advanced_overrides == {"agc_target_dbfs": -17.0}

    def test_multiple_invalid_keys_are_all_dropped_independently(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                '{"advanced_overrides": {'
                '"agc_target_dbfs": -17.0, '
                '"compressor_ratio": "bad", '
                '"agc_max_gain_db": NaN, '
                '"compressor_threshold_db": -20.0'
                "}}"
            )
        loaded = AppConfig.load(path)
        assert loaded.advanced_overrides == {
            "agc_target_dbfs": -17.0,
            "compressor_threshold_db": -20.0,
        }

    def test_non_string_key_is_dropped(self):
        # JSONオブジェクトのキーは常に文字列だが、_sanitize_advanced_overrides自体は
        # 単独でも安全であるべき(将来の呼び出し元変化に対する防御)ことを直接確認する。
        from soloclarity.config import _sanitize_advanced_overrides

        result = _sanitize_advanced_overrides({"agc_target_dbfs": -17.0, 42: 1.0})
        assert result == {"agc_target_dbfs": -17.0}
