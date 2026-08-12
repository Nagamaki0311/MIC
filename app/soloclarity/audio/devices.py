"""sounddeviceのデバイス列挙ラッパー。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sounddevice as sd


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


def list_devices() -> list[DeviceInfo]:
    devices = sd.query_devices()
    return [
        DeviceInfo(
            index=idx,
            name=d["name"],
            max_input_channels=d["max_input_channels"],
            max_output_channels=d["max_output_channels"],
            default_samplerate=d["default_samplerate"],
        )
        for idx, d in enumerate(devices)
    ]


def list_input_devices() -> list[DeviceInfo]:
    return [d for d in list_devices() if d.max_input_channels > 0]


def list_output_devices() -> list[DeviceInfo]:
    return [d for d in list_devices() if d.max_output_channels > 0]


def find_device_by_name(name_substring: str, devices: list[DeviceInfo]) -> Optional[DeviceInfo]:
    lowered = name_substring.lower()
    for d in devices:
        if lowered in d.name.lower():
            return d
    return None


def guess_solocast_device(devices: Optional[list[DeviceInfo]] = None) -> Optional[DeviceInfo]:
    devices = devices if devices is not None else list_input_devices()
    return find_device_by_name("solocast", devices)


def guess_cable_output_device(devices: Optional[list[DeviceInfo]] = None) -> Optional[DeviceInfo]:
    """VB-Audio Virtual Cableの入力デバイス("CABLE Input")を名前から推測する。"""
    devices = devices if devices is not None else list_output_devices()
    return find_device_by_name("cable input", devices)
