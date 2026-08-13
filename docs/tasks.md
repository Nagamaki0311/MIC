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
| T-004 | 実機報告: SoloCast→CABLE Input間のストリーム開始エラー(PaErrorCode -9993)の修正 | 高 | レビュー中 | claude | AudioEngineを単一sd.StreamからInputStream/OutputStream+リングバッファ(ジッタバッファ)構成へ書き直し完了。Reviewer指摘(Medium: start()/stop()のクリーンアップ連鎖失敗、Low: チェックリスト記載漏れ)へ対応済み(_safe_close/_safe_stop_and_close追加、回帰テスト2件追加)。pytest 91 passed、pyflakes警告0件。再レビュー待ち。詳細はdocs/decisions.md D-009、docs/progress.md参照 |
| T-005 | プリセット・詳細設定UIの再調整（「小さくて低い声＋高品質ノイズ除去」） | 高 | レビュー中 | claude | D-010の確定表どおりに実装完了。discord_call→quiet_low_voiceへ置き換え、ノイズ除去3段階再調整、詳細設定15項目の日本語ラベル・説明・目安表示、明瞭度/ノイズ除去ドロップダウンの日本語化、9条件の合成信号テスト追加。pytest 100 passed、pyflakes警告0件。詳細はdocs/decisions.md D-011参照 |

## バックログ（未着手・優先度未確定）

- GUI(app.py)のadvanced_overrides反映ロジックに対する自動回帰テストの追加（Reviewer提案、Low/任意、要件・セキュリティに影響しないため見送り中）
- WINDOWS_VERIFICATION_CHECKLIST.mdに沿ったユーザー側でのWindows実機・Discord動作確認（T-004の原因となった項目以外は依然未実施）

## メモ

- 新しいタスクを追加したら、必ず優先度と状態を設定すること。
- タスクの状態が変わったら都度このファイルを更新する（作業完了後にまとめて更新しない）。
- 詳細な作業内容や経緯は [progress.md](./progress.md) を参照。
- 設計上の判断が必要になった場合は [decisions.md](./decisions.md) に記録する。
- **状態列の値は必ず「状態の定義」にある6値を完全一致（前後の空白のみ許容）で使うこと**。SessionStart Hookの完了タスクフィルタ（`.claude/settings.json`）が状態列の完全一致で判定しているため、`完了(要再確認)`のような接尾辞付きの値は「未完了」として扱われる（安全側だが、フィルタが効かなくなる）。既知の制約としてT-011のレビューループで確認済み（docs/progress.md参照）。
- **タスク名・備考欄に未エスケープの`|`を含めないこと**。SessionStart Hookは`docs/tasks.md`を`awk -F'|'`で列分割しており、セル内に`|`があると以降の列がずれる。Markdownテーブルとしても不正な記法になるため、通常の運用では発生しない想定。
