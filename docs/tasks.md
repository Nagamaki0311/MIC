# タスク管理

現在のタスク、優先順位、状態を管理する。

## 状態の定義

- `未着手`: まだ着手していない
- `計画中`: plannerによる計画作成中/完了
- `調査中`: researcherによる外部情報収集中（外部調査が必要なタスクのみ）
- `実装中`: developerによる実装中
- `レビュー中`: reviewerによる確認中
- `完了`: 完了条件（AGENTS.md参照）を満たした

## タスク一覧

| ID | タスク | 優先度 | 状態 | 担当エージェント | 備考 |
|----|--------|--------|------|------------------|------|
| T-001 | HyperX SoloCast向け軽量ボイスプロセッサの開発 | 高 | 完了 | claude | Reviewer再検証で修正2件（High/Low）とも解消(CONFIRMED)、回帰なし、自動テスト26件pass。Windows実機・Discordでの動作確認はこのLinux環境では実施不可能なため未実施、WINDOWS_VERIFICATION_CHECKLIST.mdに沿ったユーザー側での最終確認が別途必要（D-001〜D-003参照） |
| T-002 | GitHub Actionsによるexeビルドの自動化 | 中 | 完了 | claude | このLinux環境ではWindows向けexeをビルドできないため、windows-latestランナー上でpytest実行→PyInstallerビルド→Artifact公開を行うワークフローを追加（D-004参照） |
| T-003 | 最終総点検・完成化（性能・音質・機能・UI/UX・安定性・敵対的検証） | 高 | 完了 | claude | Reviewerによる3巡の敵対的検証（D-005実装→High×2/Medium×1/Low×2発見→D-006対応→再検証で新規Medium1件発見→D-007対応→最終再検証）を経て、合計6件すべて解消(CONFIRMED)。Reviewer最終所見「このまま配布できる」。pytest 82 passed、pyflakes警告0件。version 1.0.0として確定・GitHub Actionsでビルド済み（D-008参照）。Windows実機・Discordでの最終確認はWINDOWS_VERIFICATION_CHECKLIST.mdに沿ってユーザー側で別途必要 |
| T-004 | 実機報告: SoloCast→CABLE Input間のストリーム開始エラー(PaErrorCode -9993)の修正 | 高 | 完了 | claude | AudioEngineをInputStream/OutputStream+リングバッファ構成へ書き直し、Reviewer指摘(Medium: クリーンアップ連鎖失敗、Low: チェックリスト記載漏れ)も解消(CONFIRMED)。Reviewer所見「原因を論理的に取り除く変更」。pytest 100 passed。詳細はdocs/decisions.md D-009参照 |
| T-005 | プリセット・詳細設定UIの再調整（「小さくて低い声＋高品質ノイズ除去」） | 高 | 完了 | claude | discord_call→quiet_low_voiceへ置き換え、ノイズ除去3段階再調整（除去量維持・ゲート緩和）、詳細設定15項目の日本語ラベル・説明・目安表示、9条件の合成信号テストをReviewerが独自検証しCONFIRMED。Reviewer最終所見「このまま次のビルドへ進めて問題ない」。詳細はdocs/decisions.md D-010・D-011参照 |
| T-006 | ノイズ処理のバックグラウンド/インパクト2系統分離・最終総点検 | 高 | 完了 | claude | TransientDetector新設、NoiseStage2分割、詳細設定スライダーのライブ反映確認・縦スクロール対応も実施。ReviewerがMedium指摘1件(無音からの立ち上がり時、トランジェント検出器が約120ms背景抑制を弱める既知の限界、声自体は欠落せず自己制限的)を発見したがリリースをブロックしないと判断、その他はすべてCONFIRMED。Reviewer最終所見「このまま次のビルドへ進めて問題ない」。pytest 118 passed。詳細はdocs/decisions.md D-012・D-013参照 |
| T-007 | 実機報告: 詳細設定パネルのスライダーが横方向に見切れる問題の修正・ウィンドウのリサイズ可能化 | 高 | 完了 | claude | 原因(Canvasのwidth未指定)を特定・修正、resizable化・minsize設定も実施。Reviewer1巡目でHigh×1・Medium×1・Low×2を指摘、Manager対応中に新規回帰(D-013の遅延発火がガードなしで露出)を自ら発見し修正。Reviewer2巡目で全指摘の解消・新規回帰なしをCONFIRMED、「このままマージしてよい」。pytest 123 passed(3回連続)、pyflakes警告0件。version 1.2.1として確定。詳細はdocs/decisions.md D-014参照 |
| T-008 | 実機報告: 音声処理パイプライン・デフォルトプリセットの実運用品質不足(声の途切れ・遠い/小さい・過剰ノイズ抑制)の再検証・再設計 | 高 | 実装中 | claude | ReviewerがCritical1件(RNNoise遅延測定がin-placeエイリアシングのバグで常に0サンプルを返しており、実際は約2フレーム=20msの遅延がある。D-015 Step0-1「遅延なし」の結論が誤りで、dry/wet整列(Step1)が未実施のまま残っている)・Medium1件(プリセット切替直後、非発話中はAGCゲインが新しいmax_gain_dbでクランプされずフリーズする)を指摘、差し戻し。Developerへ再修正を委任。詳細はdocs/decisions.md D-015参照 |

## バックログ（未着手・優先度未確定）

- GUI(app.py)のadvanced_overrides反映ロジックに対する自動回帰テストの追加（Reviewer提案、Low/任意、要件・セキュリティに影響しないため見送り中）
- natural/low_voiceプリセットに対する、ノイズ除去再調整後の専用回帰テスト追加（Reviewer提案、Low/任意。ゲートを緩める変更は原理的に新たなクリップ・無音化を生みにくいため実害の懸念は低いと判断し見送り中）
- トランジェント検出器: 真の無音(-45dBFS未満)から声/ノイズが立ち上がる際、約120ms(fast/slow envelopeが揃うまでの過渡)だけバックグラウンドノイズ抑制が意図(strong時background=1.00)より弱く(impact寄りの最大0.35程度まで)なる既知の限界（T-006 Reviewer指摘Medium、CONFIRMED）。声自体の欠落はなく、背景ノイズが元々少ない静かな環境ほど影響が自己制限的なためリリースはブロックしないが、無音復帰直後の数フレームをtransient_score=0扱いにする等の改善余地あり。回帰テスト追加も未着手
- WINDOWS_VERIFICATION_CHECKLIST.mdに沿ったユーザー側でのWindows実機・Discord動作確認（T-004の原因となった項目以外は依然未実施。特に今回のノイズ除去・プリセット変更後の主観評価が必須）

## メモ

- 新しいタスクを追加したら、必ず優先度と状態を設定すること。
- タスクの状態が変わったら都度このファイルを更新する（作業完了後にまとめて更新しない）。
- 詳細な作業内容や経緯は [progress.md](./progress.md) を参照。
- 設計上の判断が必要になった場合は [decisions.md](./decisions.md) に記録する。
- **状態列の値は必ず「状態の定義」にある6値を完全一致（前後の空白のみ許容）で使うこと**。SessionStart Hookの完了タスクフィルタ（`.claude/settings.json`）が状態列の完全一致で判定しているため、`完了(要再確認)`のような接尾辞付きの値は「未完了」として扱われる（安全側だが、フィルタが効かなくなる）。既知の制約としてT-011のレビューループで確認済み（docs/progress.md参照）。
- **タスク名・備考欄に未エスケープの`|`を含めないこと**。SessionStart Hookは`docs/tasks.md`を`awk -F'|'`で列分割しており、セル内に`|`があると以降の列がずれる。Markdownテーブルとしても不正な記法になるため、通常の運用では発生しない想定。
