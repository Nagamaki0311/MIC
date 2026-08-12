"""AppConfig, %APPDATA%読み書き。"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from soloclarity import presets

APP_DIR_NAME = "SoloClarity"
CONFIG_FILE_NAME = "config.json"


def _is_valid_optional_str(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _is_valid_preset(value: Any) -> bool:
    return isinstance(value, str) and value in presets.PRESET_ORDER


def _is_valid_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_valid_advanced_overrides(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
        for k, v in value.items()
    )


# 各フィールドについて、config.json(信頼境界の外にある入力)から読み込んだ値を
# 採用してよいか判定する。不正な値は無視し、dataclassの既定値へフォールバックする。
_FIELD_VALIDATORS = {
    "input_device_name": _is_valid_optional_str,
    "output_device_name": _is_valid_optional_str,
    "preset": _is_valid_preset,
    "processing_enabled": _is_valid_bool,
    "advanced_overrides": _is_valid_advanced_overrides,
}


def config_dir() -> str:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, APP_DIR_NAME)
    # Windows以外(このLinux開発/テスト環境含む)向けのフォールバック。
    return os.path.join(os.path.expanduser("~"), ".config", APP_DIR_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), CONFIG_FILE_NAME)


@dataclass
class AppConfig:
    input_device_name: Optional[str] = None
    output_device_name: Optional[str] = None
    preset: str = presets.DEFAULT_PRESET
    processing_enabled: bool = True
    # 詳細設定パネルでの生値の上書き。キーはVoiceChain/preset側のパラメータ名。
    # 空ならプリセットの値をそのまま使う。
    advanced_overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppConfig":
        path = path or config_path()
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return cls()
        if not isinstance(data, dict):
            # 構文上は妥当なJSONでも(null, 配列, 文字列等)、config.jsonとしては
            # 不正な形なのでデフォルト設定にフォールバックする。
            return cls()
        known_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {
            k: v
            for k, v in data.items()
            if k in known_fields and _FIELD_VALIDATORS[k](v)
        }
        return cls(**filtered)

    def save(self, path: Optional[str] = None) -> None:
        path = path or config_path()
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        # 書き込み中のプロセス異常終了でconfig.jsonが壊れないよう、同じディレクトリ内の
        # 一時ファイルへ書いてからos.replace()でアトミックに置き換える。
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".config_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
