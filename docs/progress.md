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

## 2026-08-12 T-002 GitHub Actionsによるexeビルドの自動化

### 実施内容
- ユーザーから「実行ファイルは出せるか」との質問に対し、この開発環境（Linux、Wine等も未導入）ではPyInstallerのクロスコンパイル不可により直接exeを渡せない旨を説明し、代替案としてGitHub Actionsでのビルド提案を提示、了承を得た。
- `.github/workflows/build-windows.yml`を新規作成（D-004参照）。`windows-latest`ランナーでpytest実行→既存の`app/build/build_windows.bat`によるビルド→`app/dist/SoloClarity.exe`をArtifact公開する構成。トリガーはpush(main, app/**)・pull_request(同条件)・workflow_dispatch。
- `docs/tasks.md`にT-002を追加（状態=完了、ワークフロー追加自体は完了。実際のCI実行結果の確認はこの後のPRで行う）。

### 結果
- ワークフローYAMLの構文はPythonのyamlモジュールでパース可能なことを確認済み（`on:`キーがPyYAMLの仕様上boolean Trueとして読み込まれるのはYAML 1.1の既知の挙動であり、GitHub Actions側のパーサーには影響しない）。
- `build_windows.bat`の内容を読み、CI環境（非対話、`--noconfirm`済み、errorlevelチェックあり）で問題なく動作する構成であることを確認した。
- 実際のCI実行結果（Windows上でのpytest・ビルド成功可否）は、本エントリ作成時点では未確認。次のPRでActionsの実行結果を確認する。

### 次回開始位置
- PRを作成し、Actionsの実行結果（pytest・PyInstallerビルド・Artifact生成）を確認する。失敗した場合は原因を調査し修正する。

### 追記: 初回CI実行の失敗と修正
- PR #3のCI（windows-latest、run 31609477972）で`pytest tests/`は26 passedだったが、PyInstallerのビルドが`rnnoise.dllが見つからない`エラーで失敗した。`--add-binary`の相対パスが`--specpath`（`build\output`）基準で解決される仕様のためだった。`app/build/build_windows.bat`で絶対パスに展開するよう修正した（D-004追記参照）。
- このLinux環境ではPyInstallerのビルドフェーズ自体を一度も実行できていなかったため、CIをWindows上で実際に走らせて初めて発見できた問題であり、D-004でCIを追加した狙い（Windows固有の問題の可視化）がさっそく機能した形になる。
- 修正をpushし、CIの再実行結果を確認する（次回開始位置）。

---

## 2026-08-12 T-001 Reviewer再検証・完了

### 実施内容
- 前回の修正（High: advanced_overrides未反映バグ、Low: release_msマジックナンバー）に対し、別のReviewerセッションが再検証を実施した。Developerの報告を鵜呑みにせず、xvfb環境でDeveloperとは異なるパラメータ（AGC・コンプレッサー・EQ・ノイズ段それぞれ）を使って`config.json`からの復元を再現し、`app.chain`側の実パラメータが保存値と一致することを確認した。あわせて通常のスライダー操作によるリアルタイム反映（既存の正常動作）に回帰がないことも確認した。
- 両指摘とも解消(CONFIRMED)、新たな問題（回帰・エッジケース漏れ）は検出されなかった。
- Reviewerから追加のLow/任意提案（GUI(app.py)のadvanced_overrides反映ロジックへの自動回帰テスト追加）があったが、要件・セキュリティ・データ整合性に影響しないためREVIEW.mdの過剰指摘抑制ルールに従い必須修正とせず、docs/tasks.mdのバックログへ記録するに留めた。
- `docs/tasks.md`のT-001を「完了」に更新した。

### 結果
- Reviewer再検証: High/Low指摘とも解消(CONFIRMED)。`pytest tests/` 26 passed（再実行、リグレッションなし）。
- 完了条件（AGENTS.md）の充足状況: 要件達成・エラーなし・コードレビュー済みはこのLinux環境で確認済み。「動作確認済み」のうちDSPロジック・GUIロジックの構造的動作はこの環境で自動テスト・xvfb検証済みだが、SoloCast実機でのキャプチャ・VB-Cable経由のDiscordでの実際の聞こえ方はこの環境では検証不可能なため未実施（D-001に記載済みの既知の制約）。WINDOWS_VERIFICATION_CHECKLIST.mdに沿ったユーザー側での最終確認をもって完全な完了とする。

### 次回開始位置
- ユーザーがWindows実機でWINDOWS_VERIFICATION_CHECKLIST.mdを実施し、問題があれば新規タスクとして起票する。
- バックログの2項目（GUI自動回帰テストの追加、Windows実機確認）は優先度未確定。

---

## 2026-08-12 T-001 Reviewer差し戻し対応（advanced_overrides未反映バグの修正）

### 実施内容
- Reviewer指摘(High, CONFIRMED)への対応: `app/soloclarity/gui/app.py`の`_on_advanced_slider_changed`からchainへの反映ロジックを`_apply_slider_values_to_chain()`へ切り出し、`_apply_advanced_overrides`(config復元経路)が`_updating_from_code`ガードに関わらずchainへ反映できるようにした（D-003参照）。
- Reviewer指摘(Low, CONFIRMED)への対応: `app/soloclarity/dsp/chain.py`の`_build_limiter_board()`に直書きされていた`release_ms=100.0`を、`app/soloclarity/presets.py`に新規追加した`LIMITER_RELEASE_MS`定数の参照に置き換えた。
- docs/decisions.mdにD-003を追記。

### 結果（実際に実行した検証）
- xvfb環境(`xvfb-run`)で以下を実機検証した: `agc_target_dbfs=-18.5`（プリセットデフォルト`-17.0`とは異なる値）を含む`advanced_overrides`を持つ`config.json`を用意し、`App()`を起動して復元させた結果、スライダー表示値(`-18.5`)だけでなく`app.chain.agc.target_linear`が保存値から計算される期待値(`10**(-18.5/20) = 0.11885022274370183`)と完全一致することを確認した（修正前は`_on_advanced_slider_changed`がガードでreturnするため、chain側はプリセットデフォルト由来の値のままになっていたはずの箇所）。
- `pytest tests/`（この環境）: **26 passed, 0 failed**（新規リグレッションなし）。

### 次回開始位置
- Reviewerへ再レビューを依頼する。承認されればT-001は完了(AGENTS.mdのレビュー基準4項目を満たすかReviewer側で最終確認)。

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
