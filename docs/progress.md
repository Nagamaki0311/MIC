# 作業履歴

作業内容、実施結果、次回開始位置を記録する。新しいエントリは先頭に追加する（新しい順）。

---

## 2026-08-13 T-007完了、version 1.2.1確定

### 実施内容
- Reviewer(2巡目)が、1巡目で指摘したHigh×1(閉状態でのウィンドウ膨張)・Medium×1(他フレームの不自然な伸縮)・Low×2(文書不整合・ガード欠如)のすべてについて、コード読解・xvfb実機実測・Before/After回帰テストの3系統で解消を確認し、「このままマージしてよい」と最終承認した。新たな回帰も確認されなかった。
- `docs/tasks.md`のT-007を完了に更新した。
- `app/soloclarity/__init__.py`の`__version__`を`1.2.0`→`1.2.1`へ変更(横見切れ・resizable化はバグ修正・UX改善であり新機能追加ではないため、D-008のバージョニング方針に従いパッチバージョンを上げる判断)。

### 結果
- このLinux環境での最終確認: `pytest tests/` 123 passed(3回連続、フレーキーな失敗なし)、`pyflakes soloclarity tests` 警告0件。
- Windows実機での最終確認(実際に横見切れが解消しているか、ウィンドウのリサイズが自然に行えるか)は、このLinux環境では引き続き検証不可能。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での確認が必要(次回追記予定)。

### 次回開始位置
- コミット・PR作成・GitHub ActionsのCI実行結果を確認し、成功していればPRをマージして最終Artifact(`SoloClarity-v1.2.1-{ビルド日}`)のダウンロードリンクをユーザーへ案内する。

## 2026-08-13 T-007 Reviewer指摘対応・第2ラウンドの自己発見バグ修正

### 実施内容
- Developer agentがセッション上限で中断したため、Managerが実装(Canvas幅の動的算出・resizable化・minsize設定・行/列weight設定)を引き取って完成させ、xvfbで見切れ解消を実測確認、回帰テスト3件を追加してpytest 121 passed・pyflakes警告0件を確認した上でコミット・プッシュした。
- Reviewerによる敵対的検証で、High×1(閉状態でも`minsize`がパネルを開いた状態の高さまでウィンドウを強制的に膨張させ、row=6に不要な空白ができる)、Medium×1(`columnconfigure(0, weight=1)`が他フレームにも波及し、ウィンドウを広げると各フレームが不自然に間延びする)、Low×2(D-014の文書と実装の不一致、`_updating_from_code`ガード漏れのPLAUSIBLE指摘)が報告された。
- Managerが指摘を引き取り、(1)minsizeの高さを閉状態のみから算出、(2)`columnconfigure(0, weight=1)`を削除、に修正。この過程で、Reviewer指摘4(PLAUSIBLE)の対応として一時grid→grid_remove処理を一度完全に廃止したところ、既存テスト`TestAdvancedApplyFeedback::test_config_restore_does_not_show_feedback`が新たに失敗することを自ら発見した。
- 調査の結果、この一時map→unmapの手順は「D-013で確認済みのtk.Scaleの遅延`-command`発火」を打ち消す副作用を持っており、単純に廃止すると`__init__`完了後の最初の`app.update()`呼び出しでガードなしに発火してしまう(誤ってフィードバック表示・config保存が起きる)実際の回帰であることが判明した。一時grid→grid_removeの処理自体は残し、`_updating_from_code`ガードで囲む対応に変更した(Reviewer指摘4が推奨していた対応そのもの)。
- `docs/decisions.md`のD-014に「修正ループ」「第2ラウンド」節を追加し、上記の経緯・最終実装を記録した。

### 結果
- `cd /home/user/MIC/app && python -m pytest tests/ -q`を3回連続実行し**123 passed**(既存118件 + 新規5件)、フレーキーな失敗なし。`pyflakes soloclarity tests`警告0件。
- 回帰テスト5件: Canvas幅が内容幅以上であること、resizableであること、minsizeの幅がパネル展開時の要求幅以上であること、**閉状態でウィンドウが不要に膨張していないこと(High再発防止)**、**ウィンドウを広げても他フレームが不自然に伸縮しないこと(Medium再発防止)**。

### 次回開始位置
- 修正後の差分をコミット・プッシュし、Reviewerへ再検証を依頼する(Reviewerの指摘が実際にすべて解消しているか、新たに追加した一時grid区間のガード付き実装に問題がないかを再度敵対的に確認してもらう)。
- 承認が得られたら、`app/soloclarity/__init__.py`の`__version__`をバグ修正としてパッチバージョン(1.2.1)へ更新し、コミット・PR作成・CI確認・マージ・最終ビルド提示という一連の流れを行う。

## 2026-08-13 T-007起票、原因特定・Developerへ委任

### 実施内容
- v1.2.0の実機スクリーンショットで、T-006で追加したCanvas+Scrollbarのスライダーが横方向に見切れる問題、およびウィンドウを手動でリサイズできるようにしてほしいという要望が報告された。
- `app/soloclarity/gui/app.py`を読み、原因を特定した: `_build_advanced_panel()`の`tk.Canvas`生成時、`height`(D-012で縦見切れ対策として明示指定済み)は指定されているが`width`が未指定のため、子ウィジェット(実際の必要幅500px超)より狭いTk既定幅でビューポートが確保され、スライダー右側が切り取られていた。
- `docs/tasks.md`にT-007を起票(状態=実装中)、`docs/decisions.md`にD-014として原因・修正方針(Canvas幅を`winfo_reqwidth()`で動的算出、`resizable(True, True)`化、`minsize()`設定、行・列の`weight`設定)を記録した。

### 結果
- 実装自体はまだ着手していない(Developerへ委任する直前)。

### 次回開始位置
- Developer agentの実装完了を待ち、xvfbでの見切れ再現(修正前)・解消(修正後)確認、`pytest tests/`(既存118件がpassすること)を確認した上でReviewerへ回す。
- Reviewer承認後、`app/soloclarity/__init__.py`の`__version__`をバグ修正としてパッチバージョン(1.2.1)へ更新し、コミット・PR作成・CI確認・マージ・最終ビルド提示という一連の流れ(T-001〜T-006と同じワークフロー)を行う。

## 2026-08-13 T-006完了、version 1.2.0確定

### 実施内容
- Reviewerの最終所見(Medium指摘1件を除きすべてCONFIRMED、Medium自体も「声の欠落はなく自己制限的、リリースをブロックしない」との判断、「このまま次のビルドへ進めて問題ない」)を受け、`docs/tasks.md`のT-006を完了に更新した。
- Reviewerが推奨した最小対応として、`app/WINDOWS_VERIFICATION_CHECKLIST.md`に「静かな部屋で発話の合間の後、話し始めの一瞬だけ背景ノイズ抑制が弱まって聞こえないか」という確認項目を追加した。回帰テスト自体の追加(Reviewer推奨の別案)は次タスクのバックログへ記録した。
- `app/soloclarity/__init__.py`の`__version__`を`1.1.0`→`1.2.0`へ変更(ノイズ処理のバックグラウンド/インパクト2系統分離という新機能追加のため、D-008のバージョニング方針に従いマイナーバージョンを上げる判断)。

### 結果
- このLinux環境での最終確認: `pytest tests/` 118 passed、`pyflakes soloclarity tests` 警告0件。
- ReviewerがManagerの事前調査(WebRTC Audio Processing比較)・Developerの実装(TransientDetector、NoiseStage2分割)を独立に検証し、2系統分離が実際に機能していること、打鍵音抑制による声の欠損がないこと、ライブ反映・スクロール対応がいずれも正しく動作することをCONFIRMEDした。
- 唯一のMedium指摘(真の無音から音が立ち上がる際、トランジェント検出器の過渡特性により約120ms背景抑制が弱まる)は、声自体が欠落するものではなく、影響が最も出る「元々静かな部屋」ほど漏れるノイズの絶対量が小さいという自己制限的な性質があるため、Reviewer自身がブロッキング指摘としないことを推奨し、Managerもこれに従った。
- Windows実機・Discordでの実際の聞こえ方(特に今回のバックグラウンド/インパクト分離、真の無音からの立ち上がり)は、このLinux環境では引き続き検証不可能。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での確認が必要。

### 次回開始位置
- GitHub ActionsのCI実行結果を確認し、成功していればPRをマージして最終Artifact(`SoloClarity-v1.2.0-{ビルド日}`)のダウンロードリンクをユーザーへ案内する。

---

## 2026-08-13 T-006実装(ノイズ処理2系統分離、詳細設定スライダーのライブ反映UX・スクロール対応)

### 実施内容
- D-012(Manager確定済み)の設計をそのまま実装した。
  - `app/soloclarity/dsp/transient.py`(新規): `TransientDetector`クラス(fast_env/slow_envのEMA比からtransient_scoreを算出、無音フロア-45dBFS)。
  - `app/soloclarity/presets.py`: `NoiseStage`を`background_wet_dry_mix`/`impact_wet_dry_mix`の2フィールドへ変更、`NOISE_STAGES`をD-012の表どおり再定義、`quiet_low_voice`の`label_ja`更新。
  - `app/soloclarity/dsp/chain.py`: `VoiceChain`に`TransientDetector`を統合。Highpass後・RNNoise前の信号に対し毎フレーム`transient_score`を計算し、`mix = background*(1-score) + impact*score`で混合比を算出するよう変更。処理順序は無変更。
  - `app/soloclarity/gui/app.py`: `noise_wet_dry_mix`スライダーを`noise_background_mix`/`noise_impact_mix`の2つに分割(D-012の文言をそのまま使用)。
  - `app/tests/test_transient.py`(新規4件)・`app/tests/test_chain.py`(14条件テストへ再構成、条件8/10/11/13/14を新設)を追加。
- Manager追加指摘2件に対応した。
  1. 詳細設定スライダーのライブ反映: xvfb環境でAudioEngineを直接駆動して調査した結果、設計・配線自体は正しく機能していることを確認(`engine.chain is app.chain`)。調査過程で、詳細設定パネルを初めて開いた際に`tk.Scale`が一部スライダーの`-command`を自動発火させる副作用(Tkinter固有の挙動)を発見し、`_updating_from_code`ガードで無視するよう対応した。あわせて「設定を反映しました」という短いフィードバック表示を追加した(専用の「適用」ボタンは既存の即時反映という設計を後退させるため不採用)。
  2. 詳細設定パネルの縦スクロール対応: パネルを開いた状態のウィンドウ高さが1567px(xvfb実測)あり一般的なノートPC画面に収まらない問題を、`tk.Canvas`+`ttk.Scrollbar`によるラップで解消(修正後635px)。
- `docs/decisions.md`にD-013として実装詳細・14条件テストの実測結果・bench/soak再測定値を記録した。

### 結果
- `pytest tests/`(このLinux環境): **118 passed**(D-011時点100件から18件増: test_transient.py新規4件、test_chain.pyの14条件テスト純増5件、test_app_gui.py新規9件)。5回連続実行でフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- `python -m tests.bench_chain`: 平均0.7171〜0.7549ms/フレーム(10ms予算の7.1〜7.5%、閾値30%を大きく下回る)。
- `python -m tests.soak_chain`(10万フレーム): RSS成長率1.007倍、処理時間比率1.035倍(いずれも閾値を大きく下回り、新たな問題なし)。
- xvfb環境で実際にウィンドウを起動し、詳細設定パネルの「周囲の音を減らす」「打鍵音などを減らす」の表示・スクロール・スライダー変更→フィードバック表示→chain反映を確認した。
- `app/はじめにお読みください.txt`・`app/WINDOWS_VERIFICATION_CHECKLIST.md`にDiscord自体のノイズ抑制と併用しないことを推奨する旨を追記し、古いプリセット名表記も更新した。
- `docs/tasks.md`のT-006を「レビュー中」に更新した。

### 次回開始位置
- Reviewerによる敵対的検証を依頼する。特に14条件テストの閾値・警告(D-013記載のウォームアップに関する設計判断)、ライブ反映調査の結論、スクロール実装の妥当性を確認してもらう。
- Windows実機・Discordでの実際の聞こえ方(インパクト音が「自然な範囲で残る」という主観評価を含む)は、この環境では引き続き検証不可能。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での最終確認が必要。

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

## 2026-08-13 T-004・T-005完了、version 1.1.0確定

### 実施内容
- Reviewerが両タスクとも承認(T-004: Medium/Low指摘とも解消CONFIRMED、T-005: D-010との数値・文言一致、9条件テストの妥当性等をすべてCONFIRMED)したことを受け、`docs/tasks.md`のT-004・T-005を完了に更新した。
- `app/soloclarity/__init__.py`の`__version__`を`1.0.0`→`1.1.0`へ変更(D-008で確立したバージョニング方針を踏襲。T-004はバグ修正、T-005はプリセット構成・UI文言というユーザー向け機能変更のため、パッチではなくマイナーバージョンを上げる判断)。
- コミット・プッシュ後、PRを作成しGitHub Actions(windows-latest)でのビルド成功を確認する(次回開始位置参照)。

### 結果
- このLinux環境での最終確認: `pytest tests/` 100 passed、`pyflakes soloclarity tests` 警告0件。
- T-004: AudioEngineの二重ストリーム構成+クリーンアップ強化により、実機報告のあったPaErrorCode -9993の原因(異なるデバイスを単一の双方向ストリームで結合)をコードレベルで解消。Reviewer所見「原因を論理的に取り除く変更」。
- T-005: 既定プリセットを「小さくて低い声＋高品質ノイズ除去」(`quiet_low_voice`)へ置き換え、ノイズ除去3段階を除去品質維持・ゲート緩和の方向で再調整、詳細設定15項目を分かりやすい日本語表現へ全面改訂。Reviewerが独自の合成信号(ファン音風の定常ノイズ)で、ゲート緩和後も定常ノイズ抑制比が99.8%以上を維持していることを確認済み。
- Windows実機・Discordでの実際の聞こえ方(特に今回変更したノイズ抑制・プリセットの主観評価)は、このLinux環境では引き続き検証不可能。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での確認が必要。

### 次回開始位置
- GitHub ActionsのCI実行結果を確認し、成功していればPRをマージして最終Artifact(`SoloClarity-v1.1.0-{ビルド日}`)のダウンロードリンクをユーザーへ案内する。

---

## 2026-08-13 T-005 実装完了(プリセット・詳細設定UIの再調整)

### 実施内容
- docs/decisions.md D-010(Manager確定表)の内容をそのまま実装した(独自の言い換え・再設計はしていない)。詳細はD-011参照。
  1. `app/soloclarity/presets.py`: `discord_call`→`quiet_low_voice`へキー変更、D-010の表どおりのパラメータ(clarity=strong, noise=strong, compressor/agc値)に変更。`DEFAULT_PRESET`/`PRESET_ORDER`も更新。`natural`/`low_voice`/`quiet_voice`は無変更。
  2. `NOISE_STAGES`をD-010の表どおりに再調整(weak/standard/strongのgate_threshold・gate_release_ms、standardのwet_dry_mixのみ変更)。`tests/test_chain.py`・`tests/soak_chain.py`・`tests/bench_chain.py`内の`"discord_call"`をすべて`"quiet_low_voice"`へ置き換えた。`tests/test_gate.py`は`presets.NOISE_STAGES`経由で値を動的参照する設計のためコード変更不要だった。
  3. `app/soloclarity/gui/app.py`の`ADVANCED_SLIDER_SPECS`を`SliderSpec`(NamedTuple)へ拡張し、D-010の説明文・目安ラベルをそのまま埋め込んだ。`_build_advanced_panel`を、ラベル+左右目安+スケールの行と、その下の説明文の行という2行構成に変更。既存の`_ADVANCED_SLIDER_RANGES`/`_clamp`/config.jsonキー名は無変更。
  4. `presets.py`に`LEVEL_LABELS_JA`(弱/標準/強)を追加し、`app.py`の明瞭度・ノイズ除去コンボボックスを日本語表示化。既存の`preset_label_to_name`パターンを踏襲した逆引きで内部キーへ変換。
  5. `tests/test_chain.py`に`TestQuietLowVoicePresetRealWorldScenarios`(9メソッド、Issueが挙げた9つの想定利用シーンに対応)を追加した。

### 結果
- `pytest tests/`(このLinux環境): **100 passed**(T-004時点の91件 + 今回の新規9件)。5回連続実行でフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- xvfb環境で`App()`を起動し、詳細設定パネル(75ウィジェット=15スライダー×5)・プリセット/明瞭度/ノイズ除去の日本語コンボボックス表示がクラッシュなしで動作することを確認した。
- 9条件テストの実測値はdocs/decisions.md D-011に記録した。実際に聞いて確認したものではなく、この環境で実行できる自動テスト・合成信号による検証結果のみ。
- `app/WINDOWS_VERIFICATION_CHECKLIST.md`のプリセット名表記(「Discord通話」→新しい表示名)も合わせて更新した。

### 次回開始位置
- Reviewerによる敵対的検証を受ける(T-005を「レビュー中」に更新済み)。承認後、コミット。Windows実機でのプリセット・詳細設定表示の最終確認は引き続きユーザー側の作業として残る。

---

## 2026-08-13 T-004 Reviewer指摘対応(Medium1件, Low1件)

### 実施内容
- 別セッションのReviewerによるT-004実装(コミットa57977f)への敵対的検証で、Medium(CONFIRMED)1件・Low(CONFIRMED)1件の指摘を受け対応した。
- **Medium**: `app/soloclarity/audio/engine.py`の`start()`(出力側失敗時の入力側後始末)・`stop()`(入力/出力それぞれの後始末)が、各ストリームの`stop()`/`close()`自体をtry/exceptで囲んでおらず、片方が例外を送出すると後始末が連鎖的にスキップされる(stop()側: 出力側のstop/closeが一切実行されない。start()側: 入力側close()がスキップされ、しかも本来伝えるべき出力側の`Pa_StartStream`失敗理由が入力側の`Pa_StopStream`失敗でマスクされる)問題を修正した。`_safe_close`/`_safe_stop_and_close`という2つのヘルパー(標準`logging`でログに残すだけで例外を伝播させない)を追加し、`_open_and_start`の失敗時close・`start()`の入力側後始末・`stop()`の両ストリーム後始末をすべてこの経由に統一した。
- **Low**: `app/WINDOWS_VERIFICATION_CHECKLIST.md`の「7. 遅延の実測」に、ジッタバッファ(最大4フレーム=40ms)による追加遅延の可能性と、旧バージョンとの体感比較確認項目を追記した。
- `app/tests/test_engine.py`に、Reviewerが使ったのと同様の「stop()自体が例外を送出するフェイクストリーム」による回帰テストをstart()側・stop()側の両方に追加した(`_FakeStream`に`stop_should_fail`/`close_should_fail`オプションを追加)。
- `docs/decisions.md` D-009に今回の修正内容を追記し、記述と実装の食い違いを解消した。

### 結果
- このLinux環境: `pytest tests/` **91 passed**(前回89件 + 今回の回帰テスト2件)。`pyflakes soloclarity tests` 警告0件。
- Windows実機での動作確認は本セッションでは未実施(D-001の既知の制約)。

### 次回開始位置
- Reviewerによる再検証を受ける(T-004を「レビュー中」に更新済み)。承認後、コミット・GitHub Actions(windows-latest)でのビルド確認、ユーザーへ新しいexeでの実機再検証を依頼する。

---

## 2026-08-12 T-004 実装完了(AudioEngineをInputStream/OutputStream+リングバッファへ書き直し)

### 実施内容
- D-009の決定に従い、`app/soloclarity/audio/engine.py`の`AudioEngine`を、単一の双方向`sd.Stream`から、独立した`sd.InputStream`(SoloCast側)と`sd.OutputStream`(CABLE Input側)を有界リングバッファ(ジッタバッファ、`_FrameRingBuffer`、`collections.deque(maxlen=4)`)で橋渡しする構成へ書き直した。
  - `_input_callback`: フレーム読み取り→入力メーター更新→`chain.process()`(例外時はbypass+`on_error`、既存契約を維持)→リングバッファへ非ブロッキングpush(満杯時は最古を自動破棄)。
  - `_output_callback`: リングバッファから非ブロッキングpop、空ならゼロ埋めの無音を出力。出力メーターは実際に書き出す値(アンダーラン時の無音を含む)を測定する設計にした(理由はD-009追記参照)。
  - `start()`: 入力ストリームを先に開始し、出力ストリームの開始に失敗した場合は入力側をstop/closeしてから例外を再送出(D-006のリーク防止パターンを2ストリームへ拡張)。入力側自体の開始が失敗した場合は出力側を一切生成しない。
  - `stop()`: 入力・出力を独立したブロックでstop/close/参照クリアする。`is_running()`は両方の参照が非Noneであることを条件にした(意味は維持)。
  - `record_and_process_preview`/`play_preview`(テスト再生ボタン用)は変更対象外のため無変更。GUI(`app.py`)側のAudioEngine呼び出しインターフェース(コンストラクタ引数、`bypass`/`start()`/`stop()`/`is_running()`)も無変更。
- `app/tests/test_engine.py`を新アーキテクチャに合わせて全面的に書き直した。既存の例外保護(bypass+on_error)テストを`_input_callback`/`_output_callback`の組み合わせへ移植した上で、リングバッファの順序保持・満杯時の破棄・空時の無音出力、出力側メーターがアンダーラン時に入力レベルへ引きずられないこと、`start()`の3パターン(両成功/入力失敗/出力失敗)でのリーク防止・後始末、`stop()`の両ストリーム後始末を新規に追加した。

### 結果
- このLinux環境: `pytest tests/` **89 passed**(D-007時点の82件 + 今回のtest_engine.py書き直しによる純増7件)。`pyflakes soloclarity tests` 警告0件。
- 実オーディオデバイス・Windows実機での動作確認はこの環境では実施不可能(D-001の既知の制約)。「動作確認した」とは主張せず、上記の自動テスト結果のみを記録する。SoloCast→CABLE Inputの組み合わせで実際にストリームが開けるかは、ユーザーによるWindows実機での再検証が必要。
- `docs/decisions.md` D-009に、ジッタバッファサイズ(4フレーム=40ms)・メーター計測タイミング(出力側で実測)・`start()`/`stop()`の実装詳細を追記した。

### 次回開始位置
- Reviewerによる敵対的検証を受ける(T-004を「レビュー中」に更新済み)。承認後、コミット・GitHub Actions(windows-latest)でのビルド確認、ユーザーへ新しいexeでの実機再検証を依頼する。

---

## 2026-08-12 T-003 完了(version 1.0.0確定・最終ビルド)

### 実施内容
- Reviewerの最終所見(3巡の敵対的検証で合計6件の指摘すべて解消(CONFIRMED)、「このまま配布できる」)を受け、Managerとして以下を実施した。
  - `app/soloclarity/__init__.py`の`__version__`を`0.1.0`→`1.0.0`に変更(D-008参照)。
  - `.github/workflows/build-windows.yml`に「Read app version and build date」ステップを追加し、Artifact名を`SoloClarity-v{version}-{build_date}`(例: `SoloClarity-v1.0.0-20260812`)に変更。過去のビルドと混同しないようにする(Issue完成条件)。
  - `docs/tasks.md`のT-003を完了に更新。
- コミット・プッシュ後、PRを作成しGitHub Actions(windows-latest)でのビルド成功を確認する(次回開始位置参照、本エントリ作成時点ではCI結果待ち)。

### 結果
- このLinux環境での再確認: `pytest tests/` 82 passed、`pyflakes soloclarity tests` 警告0件、YAML構文チェックOK。
- T-003全体を通じた最終的な指摘解消状況: D-005で新規発見5件(High×2/Medium×1/Low×2)→D-006で対応→Reviewer再検証で新規1件(Medium)発見→D-007で対応→Reviewer最終再検証で全6件解消(CONFIRMED)確認。DSPロジック本体(`dsp/`配下)は今回の一連の修正で無変更、ソークテスト・音質関連の検証結果(D-005記載)に影響なし。
- Windows実機・Discordでの実際の動作確認は、このLinux環境では引き続き実施不可能(D-001記載の既知の制約)。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での最終確認が必要。

### 次回開始位置
- GitHub ActionsのCI実行結果を確認し、成功していればPRをマージして最終Artifact(`SoloClarity-v1.0.0-{ビルド日}`)のダウンロードリンクをユーザーへ案内する。失敗していれば原因を調査・修正する。

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
