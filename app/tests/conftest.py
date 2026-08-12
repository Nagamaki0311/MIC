import os

import pytest

from tests._rnnoise_test_lib import find_rnnoise_test_library_path


@pytest.fixture(scope="session")
def rnnoise_library_path() -> str:
    return find_rnnoise_test_library_path()


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """config.pyの保存先をテストごとに隔離する(ホストの実設定を汚さない)。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    os.makedirs(str(tmp_path / "AppData"), exist_ok=True)
    yield
