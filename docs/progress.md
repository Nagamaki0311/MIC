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

## 2026-08-12 T-003 Reviewer差し戻し対応(修正ループ、D-005への5件の指摘すべて解消)

### 実施内容
- D-005実装(コミット913189c)に対する別セッションReviewerの敵対的検証で、High×2・Medium×1・Low×2(すべてCONFIRMED)の指摘を受け、Managerの指示に従いすべて対応した(詳細はdocs/decisions.md D-006参照)。
  1. (High) `config.py`の`advanced_overrides`検証にNaN/Infinity/-Infinityへの`math.isfinite()`チェックを追加。`AppConfig.save()`にも`json.dump(..., allow_nan=False)`を追加し、読み込み・書き込み両方の信頼境界で有限性を防御。
  2. (High) `AudioEngine.start()`で`sd.Stream(...)`成功後の`.start()`失敗時に、開いたストリームを`close()`してから例外を再送出するよう修正(修正前はストリームハンドルがリークしていた)。
  3. (Medium) `_on_test_clicked`のworker thread内Tkinter操作を`self.after(0, ...)`経由に統一。`_on_close()`でworker threadの完了を待ってから`chain.close()`するよう変更。
  4. (Low) `advanced_overrides`のバリデーションをall-or-nothingからキー単位のフィルタリング(`_sanitize_advanced_overrides`)に変更。
  5. (Low) `ADVANCED_SLIDER_SPECS`のmin/maxを使った明示的なクランプ(`_clamp`)を`_apply_advanced_overrides`に追加し、Tkinterの暗黙のクランプ挙動への依存を解消。
- 指摘3の実装中、xvfb実機検証で追加の重要な問題を発見した: `_on_close()`を単純な`self._test_thread.join(timeout=...)`で実装したところ、Tkinterの`self.after(0, ...)`をバックグラウンドスレッドから呼ぶにはメインスレッドが実際に`mainloop()`でTclのイベントループを処理している必要があり、単純な`join()`でメインスレッドがブロックしている間はworker側の`after()`呼び出しが解放されず、最大タイムアウト(11秒)まで無意味にブロックすることを実測で確認した。`self.update()`を挟みながらポーリングするループへ修正し、実際のworker処理時間相当(実測0.22秒)で`_on_close()`が返ることを確認した。
- 上記の発見に伴い、`tests/test_app_gui.py`のスレッド関連テストも、単なる`app.update()`ポーリングでは`RuntimeError: main thread is not in main loop`になることが判明したため、`app.mainloop()`を実際に走らせ、workerの完了を監視する別スレッド(watcher)が`app.after(0, app.quit)`でmainloopを止める構成に書き直した(安全弁のタイムアウトも設定)。このテスト設計変更は、セッション中断を挟んでManagerから再指示を受けて完了させた。

### 結果(実際に実行したテストの数値のみ記録)
- `pytest tests/`(このLinux環境): **81 passed, 0 failed**(D-005時点の66件から新規15件追加。内訳: `test_config.py` 17→25件、`test_engine.py` 5→8件、`test_app_gui.py` 7→11件)。
- `pyflakes soloclarity tests`: 警告0件。
- `python -m tests.bench_chain`(再測定、DSPロジックは今回無変更): 1passed、リグレッションなし。
- `python -m tests.soak_chain`(再測定、10万フレーム): 1 passed(95.13秒)、リグレッションなし。DSPロジック本体は今回のReviewer対応で一切変更していない(`config.py`/`engine.py`/`gui/app.py`のみ変更)。
- 新規テストの主な内容: NaN/Infinity/-Infinityそれぞれの読み込み側フォールバックとsave側ValueError(`TestAdvancedOverridesRejectNonFiniteValues`)、advanced_overridesのキー単位フィルタリング(`TestAdvancedOverridesPartialValidity`)、Pa_StartStream失敗時のストリームclose(単発・50回連続、`TestStartClosesStreamOnPaStartStreamFailure`)、極端値のクランプ(`TestExtremeAdvancedOverrideValuesAreClamped`)、テストボタンworker threadの`self.after()`経由での状態更新とウィンドウクローズ時の競合回避(`TestTestButtonThreadSafety`、実際に`app.mainloop()`を走らせる構成で検証)。

### 次回開始位置
- ReviewerによるT-003の再レビュー(敵対的検証、REVIEW.md準拠)。承認後、Manager判断でT-003を完了とする。

---

## 2026-08-12 T-003 Reviewer再差し戻し対応(`_on_close()`再入によるTclError, Medium, CONFIRMED)

### 実施内容
- D-006の修正(コミットedd73b2)をReviewerが再検証し、指摘1・2・4・5は解消をCONFIRMEDしたが、指摘3の対応そのもの(`_on_close()`の`self.update()`ポーリング待機)が新たな問題を持ち込んでいることを発見した(詳細はdocs/decisions.md D-007参照)。
- `_on_close()`はworker thread完了待ちの間、最大11秒`self.update()`をポーリングし続けるが、この待機ループ中はTclのイベントループが回っているため、ユーザーが再度閉じる操作をすると`_on_close()`が再入され得る。Reviewerが`app.after()`で`_on_close`を2回ディスパッチする形で実際に再現し、内側の呼び出しが先に`self.destroy()`まで完了した後、外側の呼び出しが自分の`self.destroy()`に到達した時点で`TclError: application has been destroyed`が発生することを確認していた。
- `App.__init__`に`self._closing = False`を追加し、`_on_close()`冒頭に`if self._closing: return`という多重実行防止フラグを追加した。
- `tests/test_app_gui.py::TestTestButtonThreadSafety::test_reentrant_close_while_waiting_for_worker_does_not_raise`を追加し、Reviewerの再現方法(`app.after()`での2回ディスパッチ)を踏襲して検証した。ガードを一時的に取り除いた状態でこのテストを実行し、実際に同じ`TclError`でテストが失敗することを確認した上で、ガードを戻すとpassすることを確認した(テスト自体が指摘内容を正しく検出できることの二重チェック)。

### 結果(実際に実行したテストの数値のみ記録)
- `pytest tests/`(このLinux環境): **82 passed, 0 failed**(D-006時点の81件から新規1件追加)。`tests/test_app_gui.py`単体を5回連続実行してもフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- 変更は`app/soloclarity/gui/app.py`のみ(`App.__init__`への1行追加、`_on_close()`冒頭への6行のガード追加)。DSPロジック・config.py・engine.pyは無変更。

### 次回開始位置
- ReviewerによるT-003の再レビュー(敵対的検証、REVIEW.md準拠)。承認後、Manager判断でT-003を完了とする。
- Windows実機での最終確認は引き続きユーザー側の作業として残っている(`app/WINDOWS_VERIFICATION_CHECKLIST.md`、全項目未実施)。

---

## 2026-08-12 T-003 最終総点検・完成化(敵対的検証による堅牢化)

### 実施内容
- `app/soloclarity/`全体を通読した上で、Managerの事前調査で特定済みの5件の具体的バグを修正した(詳細はdocs/decisions.md D-005参照)。
  1. `config.py`の`AppConfig.save()`を`tempfile.mkstemp()`+`os.replace()`によるアトミック書き込みへ変更。
  2. `AppConfig.load()`に`isinstance(data, dict)`チェックと、フィールドごとの型/値バリデータ(`_FIELD_VALIDATORS`)を追加。非dict JSON・型違い値・不明なプリセット名等をすべてデフォルトへフォールバックするようにした。
  3. `AudioEngine._callback`内の`chain.process()`をtry/exceptで保護し、失敗時はバイパス(未加工の入力をそのまま出力)にフォールバック。`on_error`コールバックを新設し、GUI側へエラーを伝える導線を追加。
  4. `app.py`にストリーム全体の状態・エラー専用の`engine_status_var`を新設し、テスト再生ボタン専用の`test_status_var`と責務を分離。
  5. `app.py`に`_set_windows_dpi_awareness()`を追加し、`main()`冒頭でWindows限定で`SetProcessDpiAwareness`を試みるようにした(Linux上では即returnし、失敗しても起動継続)。
- 追加確認項目を実装・実行した。
  - RNNoiseライブラリ不在時、`App.__init__`でのVoiceChain初期化失敗を`RuntimeError`として明確化し、`main()`側で`tkinter.messagebox`によるエラーダイアログ表示に置き換えた。
  - デバイス0件時の挙動を`sd.query_devices`モンキーパッチで確認(`tests/test_devices.py`、`tests/test_app_gui.py::TestZeroDevices`)。
  - `app/tests/soak_chain.py`(長時間ソークテスト、10万フレーム)を新規作成・実行。
  - `tests/test_chain.py`にプリセット・詳細設定の高頻度ランダム切り替え(3,000回)テストを追加し、RNNoiseネイティブ状態が再作成されない(リークしない)ことを確認。
  - `tests/test_gate.py`に実際の3段階ノイズ除去プリセットのgate_threshold/gate_release_msを使った語尾・小さい声の欠落確認テストを追加。
  - `tests/test_chain.py`にコンプレッサーの急激な音量変化・リミッターの発動頻度を確認するテストを追加。
  - `tests/test_config.py`(corrupted config.jsonの9パターン)、`tests/test_engine.py`(コールバック内エラー処理5パターン)、`tests/test_app_gui.py`(GUI構造検証7パターン、xvfb環境)を新規作成。
  - `tests/conftest.py`に`gui_display`フィクスチャを追加(DISPLAY未設定時、Linux上にXvfbがあれば自動起動、無ければGUIテストをskip。新規pip依存は追加せず既存システムバイナリのみで完結)。
  - 設計整理: `app/soloclarity/`全体をgrepで棚卸しし、未使用の`METER_UPDATE_INTERVAL_MS`定数(app.py)と`SpeechProbabilityGate.reset()`メソッド(gate.py)を削除。requirements.txt/requirements-dev.txtの依存が実際のimportと一致することを再確認(未使用依存なし、新規追加なし)。
  - `app/soloclarity/__init__.py`の`__version__`をウィンドウタイトル(`SoloClarity v{__version__}`)へ表示。バージョン番号自体は変更していない。
  - `app/WINDOWS_VERIFICATION_CHECKLIST.md`に、この環境で検証不可能な項目(高DPI表示崩れ、デバイス抜き差し、Discordとの起動順序、スリープ復帰、Windows起動直後の動作、長期間の実運用)を10〜15節として追記。

### 結果(実際に実行したテスト・ベンチマークの数値のみ記録。Windows/Discordでの動作確認は一切行っていない)
- `pytest tests/`(このLinux環境): **66 passed, 0 failed**(既存26件 + 新規40件。`bench_chain.py`/`soak_chain.py`はファイル名が`test_*.py`パターンに一致しないため既定収集対象外、既存の運用どおり個別実行)。
- `pyflakes soloclarity tests`: 警告0件。
- `python -m tests.bench_chain`(1000フレーム、全修正後の再測定): 平均**0.6991ms/フレーム**(10ms予算の**7.0%**、閾値30%を十分に下回る)。
- `python -m tests.soak_chain`(10万フレーム=1000秒相当、音声らしいsin波+ノイズ混合/無音/ノイズのみ区間を3秒周期で混在): 実行時間約71秒。RSSはウォームアップ後(10%地点)54,784KB→最終55,168KBで**成長率1.007倍**(閾値1.3倍を大きく下回る、無制限な増加なし)。フレーム処理時間は先頭1万フレーム平均0.6945ms→末尾1万フレーム平均0.6958msで**比率1.002倍**(閾値1.5倍を大きく下回る、時間経過での劣化なし)。
- `tests/test_config.py`: 構文エラーJSON・非dict JSON(null/配列/文字列/数値/真偽値)・フィールド欠落・型違い(processing_enabled/input_device_name)・不明プリセット名・型違いadvanced_overrides・非数値override値・未知フィールドの計9パターンすべてでクラッシュせずデフォルト相当にフォールバックすることを確認。アトミック書き込み(json.dump失敗を模した書き込み中断)で既存config.jsonが破損しないことも確認。
- `tests/test_engine.py`: `AudioEngine._callback`を直接呼び出し、chain.process()の例外がバイパスへフォールバックし出力が止まらないこと、on_errorコールバックが呼ばれること、1フレームの一時的な失敗から次フレームで正常復帰すること、on_error未指定でも例外を送出しないことを確認。
- `tests/test_app_gui.py`(xvfb環境、`tests/conftest.py`の`gui_display`フィクスチャが自動でXvfbを起動): ウィンドウタイトルにバージョンが表示されること、`engine_status_var`と`test_status_var`が独立していること(エラー発生時に前者のみ変化)、デバイス0件でもクラッシュしないこと、RNNoiseライブラリ不在時に分かりやすい`RuntimeError`になること、DPI awareness関数がLinux上で例外を出さないことを確認。なお、この開発環境自体が実際にオーディオデバイス0件・RNNoise共有ライブラリ未配置(vendor/)であるため、これらのエラー経路は模擬条件だけでなく実際の環境条件でも発火することを確認できた。
- `tests/test_gate.py`: 実際の3段階ノイズ除去プリセット(弱/標準/強)それぞれで、閾値をわずかに超える小さい声が5フレーム(50ms)以内に開くこと(頭の欠落なし)、release後の1フレームで無音まで落ちないこと(語尾の唐突な切れなし)を確認。
- `tests/test_chain.py`: 高頻度パラメータ切り替え(3,000回)で例外なし・RNNoiseネイティブ状態のオブジェクトIDが不変であることを確認。コンプレッサーがフレーム間dB変化量を悪化させないこと、通常音量(peak -10dBFS)ではリミッターの減衰がほぼ無い(出力/入力RMS比>0.98)ことを確認。

### 次回開始位置
- ReviewerによるT-003のレビュー(敵対的検証、REVIEW.md準拠)。承認後、Manager判断でT-003を完了とする。
- Windows実機での最終確認は引き続きユーザー側の作業として残っている(`app/WINDOWS_VERIFICATION_CHECKLIST.md`、10〜15節を含め全項目未実施)。

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
