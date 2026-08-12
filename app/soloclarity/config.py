"""AppConfig, %APPDATA%読み書き。"""

from __future__ import annotations

import json
import math
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


# 各フィールド(advanced_overridesを除く)について、config.json(信頼境界の外にある
# 入力)から読み込んだ値を採用してよいか判定する。不正な値は無視し、dataclassの
# 既定値へフォールバックする。advanced_overridesはキー単位で個別に検証するため
# (_sanitize_advanced_overrides参照)、ここには含めない。
_FIELD_VALIDATORS = {
    "input_device_name": _is_valid_optional_str,
    "output_device_name": _is_valid_optional_str,
    "preset": _is_valid_preset,
    "processing_enabled": _is_valid_bool,
}


def _is_valid_advanced_override_value(value: Any) -> bool:
    # JSONの`NaN`/`Infinity`/`-Infinity`トークンはPythonのjson.loadでそのまま
    # float('nan')/float('inf')等として読み戻される。これがtk.Scale.set()に渡ると
    # TclErrorで起動シーケンス全体が落ち、config.jsonを直さない限り毎回再現する
    # (Reviewer指摘1)。math.isfinite()で明示的に拒否する。
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _sanitize_advanced_overrides(value: Any) -> dict[str, float]:
    """advanced_overridesをキー単位で検証する。

    1項目でも不正なら辞書全体を捨てるall-or-nothingにはせず(Reviewer指摘4)、
    不正なキーだけを取り除き、残りの正当な値はそのまま採用する。
    """
    if not isinstance(value, dict):
        return {}
    return {
        k: float(v)
        for k, v in value.items()
        if isinstance(k, str) and _is_valid_advanced_override_value(v)
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
        filtered = {
            k: v
            for k, v in data.items()
            if k in _FIELD_VALIDATORS and _FIELD_VALIDATORS[k](v)
        }
        if "advanced_overrides" in data:
            filtered["advanced_overrides"] = _sanitize_advanced_overrides(
                data["advanced_overrides"]
            )
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
                # allow_nan=False: NaN/Infinityを書き込み側でも拒否する(読み込み側の
                # _is_valid_advanced_override_valueと対になる、信頼境界の両側での防御。
                # Reviewer指摘1)。通常はスライダーの値は常に有限のためここで失敗する
                # ことはないはずだが、万一到達したら早期にValueErrorで失敗させる。
                json.dump(asdict(self), f, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
