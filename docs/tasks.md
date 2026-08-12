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
| T-003 | 最終総点検・完成化（性能・音質・機能・UI/UX・安定性・敵対的検証） | 高 | 実装中 | claude | Manager調査で4件の具体的な改善点（config非アトミック保存/型未検証、コールバック内例外未捕捉、エラー表示の混在、Windows DPI未対応）を特定しDeveloperへ委任。詳細はdocs/progress.md参照 |

## バックログ（未着手・優先度未確定）

- GUI(app.py)のadvanced_overrides反映ロジックに対する自動回帰テストの追加（Reviewer提案、Low/任意、要件・セキュリティに影響しないため見送り中）
- WINDOWS_VERIFICATION_CHECKLIST.mdに沿ったユーザー側でのWindows実機・Discord動作確認（未実施）

## メモ

- 新しいタスクを追加したら、必ず優先度と状態を設定すること。
- タスクの状態が変わったら都度このファイルを更新する（作業完了後にまとめて更新しない）。
- 詳細な作業内容や経緯は [progress.md](./progress.md) を参照。
- 設計上の判断が必要になった場合は [decisions.md](./decisions.md) に記録する。
- **状態列の値は必ず「状態の定義」にある6値を完全一致（前後の空白のみ許容）で使うこと**。SessionStart Hookの完了タスクフィルタ（`.claude/settings.json`）が状態列の完全一致で判定しているため、`完了(要再確認)`のような接尾辞付きの値は「未完了」として扱われる（安全側だが、フィルタが効かなくなる）。既知の制約としてT-011のレビューループで確認済み（docs/progress.md参照）。
- **タスク名・備考欄に未エスケープの`|`を含めないこと**。SessionStart Hookは`docs/tasks.md`を`awk -F'|'`で列分割しており、セル内に`|`があると以降の列がずれる。Markdownテーブルとしても不正な記法になるため、通常の運用では発生しない想定。
