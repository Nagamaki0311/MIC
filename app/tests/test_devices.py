"""デバイス列挙のエッジケース(接続されているオーディオデバイスが0件)を確認する。"""

from __future__ import annotations

from soloclarity.audio import devices as device_lib


def test_list_devices_handles_empty_device_list(monkeypatch):
    monkeypatch.setattr(device_lib.sd, "query_devices", lambda: [])
    assert device_lib.list_devices() == []
    assert device_lib.list_input_devices() == []
    assert device_lib.list_output_devices() == []


def test_guess_functions_return_none_when_no_devices(monkeypatch):
    monkeypatch.setattr(device_lib.sd, "query_devices", lambda: [])
    assert device_lib.guess_solocast_device() is None
    assert device_lib.guess_cable_output_device() is None
