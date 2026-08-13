"""パラメータ定義（明瞭度/ノイズ除去の3段階 + プリセット）。

数値の根拠はdocs/decisions.md D-001（初版）・D-010（既定プリセットの再調整、
ノイズ除去3段階の再調整）に記載のパラメータ表そのもの。UIやDSPチェーンはこの
モジュールの値のみを参照し、数値をコード中に埋め込まないこと。
"""

from __future__ import annotations

from dataclasses import dataclass


# --- 明瞭度（EQ） -----------------------------------------------------------


@dataclass(frozen=True)
class EqBand:
    frequency_hz: float
    gain_db: float
    q: float


@dataclass(frozen=True)
class ClarityStage:
    highpass_hz: float
    bands: tuple[EqBand, ...]


# 120Hz付近は声の厚みを失わないよう触らない(0dBのまま)。
CLARITY_STAGES: dict[str, ClarityStage] = {
    "weak": ClarityStage(
        highpass_hz=60.0,
        bands=(
            EqBand(200.0, -1.0, 1.2),
            EqBand(300.0, -0.5, 1.2),
            EqBand(2000.0, 0.5, 1.0),
            EqBand(3000.0, 1.0, 1.0),
            EqBand(4000.0, 1.0, 1.0),
        ),
    ),
    "standard": ClarityStage(
        highpass_hz=80.0,
        bands=(
            EqBand(200.0, -2.5, 1.2),
            EqBand(300.0, -1.5, 1.2),
            EqBand(2000.0, 1.5, 1.0),
            EqBand(3000.0, 2.0, 1.0),
            EqBand(4000.0, 2.5, 1.0),
        ),
    ),
    "strong": ClarityStage(
        highpass_hz=90.0,
        bands=(
            EqBand(200.0, -4.0, 1.2),
            EqBand(300.0, -2.5, 1.2),
            EqBand(2000.0, 2.0, 1.0),
            EqBand(3000.0, 3.0, 1.0),
            EqBand(4000.0, 4.0, 1.0),
        ),
    ),
}

CLARITY_LEVELS: tuple[str, ...] = ("weak", "standard", "strong")

# 明瞭度/ノイズ除去とも同じキー(weak/standard/strong)を使うため、
# 表示名の対応表は共通で1つにまとめる。
LEVEL_LABELS_JA: dict[str, str] = {"weak": "弱", "standard": "標準", "strong": "強"}


# --- ノイズ除去（RNNoise + 発話確率ゲート） ---------------------------------


@dataclass(frozen=True)
class NoiseStage:
    wet_dry_mix: float  # 0.0-1.0, RNNoise denoise後の信号をどれだけ混ぜるか
    gate_threshold: float  # 発話確率(0.0-1.0)のこの値未満をゲートで減衰させる
    gate_release_ms: float


NOISE_STAGES: dict[str, NoiseStage] = {
    "weak": NoiseStage(wet_dry_mix=0.30, gate_threshold=0.12, gate_release_ms=350.0),
    "standard": NoiseStage(wet_dry_mix=0.78, gate_threshold=0.20, gate_release_ms=250.0),
    "strong": NoiseStage(wet_dry_mix=1.00, gate_threshold=0.25, gate_release_ms=200.0),
}

NOISE_LEVELS: tuple[str, ...] = ("weak", "standard", "strong")


# --- コンプレッサー ----------------------------------------------------------


@dataclass(frozen=True)
class CompressorParams:
    threshold_db: float
    ratio: float
    attack_ms: float
    release_ms: float


# --- AGC ---------------------------------------------------------------------


@dataclass(frozen=True)
class AgcParams:
    target_dbfs: float
    max_gain_db: float
    attack_seconds: float = 2.0
    release_seconds: float = 4.0


# リミッターは全プリセット共通。Compressor/AGC後段でも突発的な大入力
# (咳・机を叩く音等)がDiscord側でクリップしないよう常時ONの安全弁として使う。
LIMITER_CEILING_DBFS = -1.0
LIMITER_RELEASE_MS = 100.0


# --- プリセット ----------------------------------------------------------


@dataclass(frozen=True)
class Preset:
    name: str
    label_ja: str
    clarity: str
    noise: str
    compressor: CompressorParams
    agc: AgcParams


PRESETS: dict[str, Preset] = {
    "natural": Preset(
        name="natural",
        label_ja="自然",
        clarity="weak",
        noise="weak",
        compressor=CompressorParams(-22.0, 2.0, 15.0, 250.0),
        agc=AgcParams(target_dbfs=-20.0, max_gain_db=6.0),
    ),
    "low_voice": Preset(
        name="low_voice",
        label_ja="低い声",
        clarity="strong",
        noise="standard",
        compressor=CompressorParams(-20.0, 2.5, 12.0, 200.0),
        agc=AgcParams(target_dbfs=-18.0, max_gain_db=8.0),
    ),
    "quiet_voice": Preset(
        name="quiet_voice",
        label_ja="小さい声",
        clarity="standard",
        noise="standard",
        compressor=CompressorParams(-24.0, 3.0, 10.0, 180.0),
        agc=AgcParams(target_dbfs=-16.0, max_gain_db=12.0),
    ),
    "quiet_low_voice": Preset(
        name="quiet_low_voice",
        label_ja="小さくて低い声＋高品質ノイズ除去",
        clarity="strong",
        noise="strong",
        compressor=CompressorParams(-23.0, 2.8, 10.0, 200.0),
        agc=AgcParams(target_dbfs=-17.0, max_gain_db=12.0),
    ),
}

DEFAULT_PRESET = "quiet_low_voice"

PRESET_ORDER: tuple[str, ...] = ("natural", "low_voice", "quiet_voice", "quiet_low_voice")
