"""AppConfig, %APPDATA%読み書き。"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from soloclarity import presets

APP_DIR_NAME = "SoloClarity"
CONFIG_FILE_NAME = "config.json"


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
        known_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def save(self, path: Optional[str] = None) -> None:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
