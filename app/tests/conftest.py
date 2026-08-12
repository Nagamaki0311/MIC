import os
import platform
import shutil
import subprocess
import time

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


def _find_free_x_display_number() -> int:
    for candidate in range(90, 200):
        if not os.path.exists(f"/tmp/.X{candidate}-lock"):
            return candidate
    raise RuntimeError("no free X display number found for Xvfb")


@pytest.fixture(scope="session")
def gui_display():
    """GUI(Tkinter)テスト用のディスプレイを用意する。

    `DISPLAY`が既に設定されていればそのまま使う。未設定でLinux上に`Xvfb`が
    インストールされていれば、テストセッション用に一時的なXvfbを起動する
    (新規pip依存を増やさず、既にシステムに存在するバイナリのみを使う)。
    どちらもなければGUIテストをスキップする。
    """
    if os.environ.get("DISPLAY"):
        yield os.environ["DISPLAY"]
        return
    if platform.system() != "Linux":
        pytest.skip("GUI tests require a display; DISPLAY is not set on this platform")
    xvfb_path = shutil.which("Xvfb")
    if xvfb_path is None:
        pytest.skip("GUI tests require a display; DISPLAY unset and Xvfb not installed")

    display = f":{_find_free_x_display_number()}"
    proc = subprocess.Popen(
        [xvfb_path, display, "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)  # Xvfbがソケットを開くまでの短い待ち
    old_display = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    try:
        yield display
    finally:
        if old_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old_display
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
