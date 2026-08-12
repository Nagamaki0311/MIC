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
