"""パラメータ定義（明瞭度/ノイズ除去の3段階 + プリセット）。

数値の根拠はdocs/decisions.md D-001（初版）・D-010（既定プリセットの再調整、
ノイズ除去3段階の再調整）・D-012（バックグラウンド/インパクト2系統分離）に
記載のパラメータ表そのもの。UIやDSPチェーンはこのモジュールの値のみを参照し、
数値をコード中に埋め込まないこと。
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
            EqBand(2000.0, 1.5, 1.0),
            EqBand(3000.0, 0.7, 1.0),
            EqBand(4000.0, 0.1, 1.0),
        ),
    ),
    "standard": ClarityStage(
        highpass_hz=75.0,
        bands=(
            EqBand(200.0, -1.5, 1.2),
            EqBand(300.0, -1.0, 1.2),
            EqBand(2000.0, 3.0, 1.0),
            EqBand(3000.0, 1.5, 1.0),
            EqBand(4000.0, 0.3, 1.0),
        ),
    ),
    "strong": ClarityStage(
        highpass_hz=80.0,
        bands=(
            EqBand(200.0, -2.0, 1.2),
            EqBand(300.0, -1.5, 1.2),
            EqBand(2000.0, 5.0, 1.0),
            EqBand(3000.0, 2.5, 1.0),
            EqBand(4000.0, 0.5, 1.0),
        ),
    ),
}
# D-015: 旧値(standard: hp80/-2.5/-1.5, strong: hp90/-4.0/-2.5)は低い声(f0=110Hz)の
# 80-350Hz帯を実測でそれぞれ-2.94dB/-4.11dB削っており、低い声の厚みを失わせすぎていた。
# 緩和後の値では-2.24dB/-2.74dBまで低減しつつ、既存テストが前提とする
# 「strongはstandardより強くEQをかける」大小関係は維持している。
# D-016: 旧gain_db(2000/3000/4000Hzが単調増加)は、PeakFilterのQ=1.0による帯域間の
# 重なりも合わさって実効ゲイン(_build_eq_board+highpassの合成、周波数応答スイープで
# 実測)のピークが3000-3500Hz付近になり、歯擦音帯域(5-8kHz)の手前でさらにピークを
# 高めていく形になっていた。2000Hzのgainを引き上げ、3000Hz/4000Hzのgainを引き下げる
# ことで、実効ゲインのピークを2000-2500Hz付近へ寄せ4000Hzに向けて緩やかに減衰する形
# (Sonarのカーブの"形"を参考にしつつ絶対値は既存の声量感とのバランスを保つ範囲で調整)
# へ変更した。実測値・確定根拠はdocs/decisions.md D-016参照。

CLARITY_LEVELS: tuple[str, ...] = ("weak", "standard", "strong")

# 明瞭度/ノイズ除去とも同じキー(weak/standard/strong)を使うため、
# 表示名の対応表は共通で1つにまとめる。
LEVEL_LABELS_JA: dict[str, str] = {"weak": "弱", "standard": "標準", "strong": "強"}


# --- ノイズ除去（RNNoise + 発話確率ゲート） ---------------------------------


@dataclass(frozen=True)
class NoiseStage:
    background_wet_dry_mix: float  # 0.0-1.0, 定常ノイズに対するRNNoise denoise適用量
    impact_wet_dry_mix: float  # 0.0-1.0, インパクト音に対するRNNoise denoise適用量
    gate_threshold: float  # 発話確率(0.0-1.0)のこの値未満をゲートで減衰させる
    gate_release_ms: float


NOISE_STAGES: dict[str, NoiseStage] = {
    "weak": NoiseStage(
        background_wet_dry_mix=0.35, impact_wet_dry_mix=0.15, gate_threshold=0.12, gate_release_ms=350.0
    ),
    "standard": NoiseStage(
        background_wet_dry_mix=0.75, impact_wet_dry_mix=0.25, gate_threshold=0.20, gate_release_ms=250.0
    ),
    "strong": NoiseStage(
        background_wet_dry_mix=0.85, impact_wet_dry_mix=0.35, gate_threshold=0.25, gate_release_ms=200.0
    ),
}
# D-015: strongのbackground_wet_dry_mixは旧1.00(RNNoise出力を100%使用)から実測に
# 基づき0.85へ引き下げた。ファンノイズ単独での減衰量はmix=0.85で約16.5dB(閾値12dB以上
# を満たす)、mix=0.70では約10.5dB(閾値未達)だった。声帯域(100-4000Hz)損失は
# 合成音声信号では有意差が測れなかった(RNNoiseが周期的な合成音をほぼ無加工で
# 通す傾向があるため、実声の複雑さを十分再現できない実測上の限界)ため、mixの
# 引き下げそのものは「実声でもノイズ処理の副作用を抑える安全マージン」としての
# 判断も含む。standardも連動して0.80→0.75へ引き下げた。

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
    # D-015: 旧既定(2.0秒/4.0秒)はCompressorにmakeup gain機構が無い状態では
    # 数秒の発話区間内に目標音量へ収束しきらず「十分な声量でも遠く/小さく聞こえる」
    # 原因になっていた。実測(quiet_low_voice相当の入力で±3dB収束: 旧6.8〜8.6秒→
    # 新2.6〜3.2秒)に基づき短縮した。
    attack_seconds: float = 0.4
    release_seconds: float = 1.5


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
        label_ja="小さくて低い声＋高品質バックグラウンドノイズ抑制＋弱いインパクト音抑制",
        clarity="strong",
        noise="strong",
        # D-015: pedalboard.Compressorにmakeup gain機構が無いため、旧値
        # (threshold -23.0dB, ratio 2.8)は過剰なgain reductionを起こしAGCの
        # 負担を増やしていた。thresholdを上げ・ratioを緩め・attackをやや遅くして
        # 圧縮量そのものを抑え、音量の持ち上げはAGC(時定数短縮済み)に委ねる。
        compressor=CompressorParams(-20.0, 2.2, 15.0, 200.0),
        agc=AgcParams(target_dbfs=-17.0, max_gain_db=12.0),
    ),
}

DEFAULT_PRESET = "quiet_low_voice"

PRESET_ORDER: tuple[str, ...] = ("natural", "low_voice", "quiet_voice", "quiet_low_voice")
