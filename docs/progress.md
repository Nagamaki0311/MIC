# 作業履歴

作業内容、実施結果、次回開始位置を記録する。新しいエントリは先頭に追加する（新しい順）。

## 記録フォーマット

```
## YYYY-MM-DD タスクID/概要

### 実施内容
- 何を行ったか

### 結果
- 動作確認結果、テスト結果など

### 次回開始位置
- 次に着手すべき場所（ファイル/関数/タスクID）
```

---

## 2026-08-12 T-001 SoloClarity実装（Developer作業完了、レビュー待ち）

### 実施内容
- D-001のアーキテクチャに従い、`app/`以下にSoloClarity(Python 3)を実装した。
  - `soloclarity/presets.py`: 明瞭度/ノイズ除去3段階・4プリセットのパラメータ表をコード化（仕様書の数値表をそのまま反映）。
  - `soloclarity/dsp/rnnoise.py`: RNNoiseの自前ctypesラッパー（Apache-2.0出典コメント付き、pyrnnoiseパッケージ本体はimportしない）。
  - `soloclarity/dsp/chain.py`: VoiceChain（Highpass→RNNoise denoise(wet/dry blend)→EQ→Compressor→AGC→Limiter→ゲート、の順で実装。仕様書のチェーン順序どおり）。
  - `soloclarity/dsp/agc.py` / `gate.py` / `meter.py`: 自前AGC・発話確率ゲート・RMS/ピークメーター。
  - `soloclarity/audio/devices.py` / `engine.py`: sounddeviceのデバイス列挙・ストリーム管理・テスト再生機能。
  - `soloclarity/gui/app.py` / `meter_widget.py`: Tkinter GUI（デバイス選択・プリセット・明瞭度/ノイズ除去・レベルメーター・テストボタン・折りたたみ式詳細設定15スライダー）。
  - `soloclarity/config.py`: `%APPDATA%\SoloClarity\config.json`の読み書き。
  - `app/tests/`: pytest一式（test_agc.py/test_gate.py/test_chain.py/test_rnnoise_wrapper.py/bench_chain.py/conftest.py/_rnnoise_test_lib.py）。
  - `app/LICENSE`（GPLv3全文, `/usr/share/common-licenses/GPL-3`から取得した正規のGPLv3全文）、`THIRD-PARTY-NOTICES.txt`、`はじめにお読みください.txt`（日本語マニュアル）、`WINDOWS_VERIFICATION_CHECKLIST.md`、`build/build_windows.bat`を作成。
  - README.mdの「使い方」節を実装内容に沿って更新。docs/decisions.mdにD-002（実装時に補った数値パラメータ・テスト設計の判断）を追記。
- 開発用にこのLinux環境へ`libportaudio2`（sounddeviceのimportに必要）、`python3.11-tk`（Tkinter）、`pyrnnoise`+依存（pytest含む、テスト専用）をaptおよびpipでインストールした。

### 結果（実際に実行したテスト・ベンチマークの数値のみを記録。Windows/Discordでの動作確認は一切行っていない）
- `pytest tests/` (このLinux環境、pip install済みの`pyrnnoise`のmanylinux wheel内`librnnoise.so`を自前ラッパーへ直接ロードして検証): **26 passed, 0 failed**。
  - EQ(明瞭度): FFTで200-300Hz帯の減衰・2-4kHz帯の増幅を弱/標準/強すべてで確認（強ほど効果が大きいことも確認）。
  - Compressor+AGC+Limiter: 大振幅入力(振幅0.999)でも出力ピークがceiling(-1.0dBFS, 線形0.891)を一度も超えないことを確認。無音直後の急な大振幅バーストでも超えないことを確認。
  - AGC単体: peak -30dBFS相当の小振幅入力に対し、出力RMSがtarget_dbfsへ近づく方向に持ち上がることを確認（発話確率低下時はゲイン更新が凍結されることも確認）。
  - 発話確率ゲート: ホワイトノイズのみの入力でエネルギーが90%以上減衰することを確認（ゲート単体・フルチェーン経由の両方）。
  - RNNoiseラッパー: 定常ノイズを含む合成音に対し、ウォームアップ後の区間でRMSが50%以上（実測は99.99%以上）減衰することを確認。
- `python -m tests.bench_chain`（1000フレーム処理の実測）: **平均0.7515〜0.7580ms/フレーム**（10ms予算の**7.5〜7.6%**、閾値30%を十分に下回る）。
- Tkinter GUI: `python3.11-tk` + `xvfb-run`によるヘッドレス起動検証で、ウィンドウ生成・プリセット/明瞭度/ノイズ除去の切り替え・詳細設定パネルの開閉・スライダー変更→VoiceChainへの反映・config.jsonへの保存/再起動後の復元・ストリーム開始失敗時（デバイス未接続）のエラーハンドリングを確認（実オーディオデバイスなしでの構造検証。実際の音の聞こえ方は未検証）。
- `pyflakes soloclarity tests`: 警告0件。
- `grep -rn "^import pyrnnoise\|^from pyrnnoise" soloclarity/`: 0件（アプリ本体からpyrnnoiseパッケージ本体をimportしていないことを確認）。

### 次回開始位置
- Reviewer観点: (1) D-001/D-002のパラメータ表・チェーン順序と実装の一致、(2) AGC/ゲートの時定数等D-002で補った値の妥当性、(3) GUI詳細設定パネルとconfig.jsonのoverride適用ロジックの整合性、(4) build_windows.batの手順の妥当性（Windows実機で未実行のため、手順の論理的な正しさのレビュー）。
- レビュー承認後、Windows実機でのT-001完了確認は`app/WINDOWS_VERIFICATION_CHECKLIST.md`のチェックリストをユーザーに依頼する（本セッションでは実施不可）。
- 未着手: `app/build/build_windows.bat`の実機実行、Windows上でのSoloCast/VB-Cable/Discordを使った実際の動作確認一式。
