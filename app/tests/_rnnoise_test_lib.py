"""テスト専用ヘルパー: `pyrnnoise`(開発依存, requirements-dev.txt)から
RNNoiseの共有ライブラリの絶対パスを取得する。

アプリ本体(soloclarity以下)はこのモジュールを一切importしない。
`pip install pyrnnoise`で入るmanylinuxホイール内の`librnnoise.so`を、
自前のctypesラッパー(soloclarity.dsp.rnnoise)へ直接渡してロードするために使う。
"""

from __future__ import annotations

import importlib.metadata
import platform


def find_rnnoise_test_library_path() -> str:
    system = platform.system()
    if system == "Windows":
        file_name = "rnnoise.dll"
    elif system == "Darwin":
        file_name = "librnnoise.dylib"
    else:
        file_name = "librnnoise.so"

    files = importlib.metadata.files("pyrnnoise")
    if files is None:
        raise RuntimeError(
            "pyrnnoise is not installed. Install dev dependencies: "
            "pip install -r requirements-dev.txt"
        )
    for f in files:
        if f.name == file_name:
            located = f.locate()
            if located is None or not str(located):
                continue
            return str(located)
    raise RuntimeError(f"{file_name} not found among pyrnnoise package files")
