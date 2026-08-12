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
| T-001 | 長期開発用AI開発環境の整備（tasks/progress/decisions） | 高 | 完了 | claude | docs配下に3ファイルを作成し、CLAUDE.mdに参照ルールを追加 |
| T-002 | project001を共通AI開発エージェント用テンプレートへ転換 | 高 | 完了 | claude | CLAUDE.mdに「プロジェクトの役割」「トークン効率化ルール」を追加。個別アプリの仕様・コードは保持しない方針を明記（D-002参照） |
| T-003 | ponytail（DietrichGebert/ponytail）のコード品質ルールを導入 | 中 | 完了 | claude | AGENTS.mdの内容をCLAUDE.mdに「コード品質ルール（Ponytail）」として統合（D-003参照） |
| T-004 | AI開発OS化: Manager導入とドキュメント/Agent構成の整理 | 高 | 完了 | claude | CLAUDE.mdを大幅簡潔化し、Manager役割（このセッション自身）を明記。docs/agents.mdを新設しAgent構成とPonytail原則を集約（D-003の内容を移設）（D-004参照） |
| T-005 | SessionStart/PreCompact Hookの導入 | 中 | 完了 | claude | .claude/settings.jsonを新設。tasks.md/progress.mdの自動表示と圧縮前リマインダーを1行shellコマンドで実装（D-005参照） |
| T-006 | AI開発OS全体レビュー（重複排除・Hook環境検証） | 高 | 完了 | claude | CLAUDE.mdのAgent説明重複を除去、Manager-Hook接続を明文化、Hook環境依存性を文書化（D-006参照） |
| T-007 | Agent別モデル最適化（Model Routing）の導入 | 中 | 完了 | claude | Planner=opus/Developer・Reviewer=sonnetに固定。軽量レビューはAgent呼び出し時のmodelパラメータ上書きで対応（D-007参照） |
| T-008 | ルートAGENTS.md新設、CLAUDE.mdとの責務分離 | 高 | 完了 | claude | 新7原則とPonytailを統合したAGENTS.mdを新設。CLAUDE.mdはClaude Code固有設定のみに縮小し@AGENTS.mdをimport（D-008参照） |
| T-009 | Agent-Reach対応（Optional Dependency・Researcher追加） | 高 | 完了 | claude | researcher Agentを新設し、Agent-Reachを検出できれば優先利用・不可なら自動フォールバックする疎結合設計を実装。docs/agent-reach.md・docs/research-workflow.mdを新設（D-009参照） |
| T-010 | レビュー方針を敵対的検証（Adversarial Review）へ変更 | 高 | 完了 | claude | REVIEW.mdを新設し、姿勢・18観点・7手順・重要度分類・検証パス（CONFIRMED/PLAUSIBLE）を集約。reviewer.mdを更新（D-010参照） |
| T-011 | 新規プロジェクト初期化手順の整備とSessionStart Hookの完了タスク除外 | 高 | 完了 | claude | README.mdに初期化手順を新設、AGENTS.mdから参照を追加。SessionStart Hookのcommandを完了タスク除外に変更し、docs/agents.mdの説明を更新（D-011参照） |
| T-012 | Capability Layer（Agent-Reach・Code Review Graphの検出規約）の統合 | 高 | 完了 | claude | SessionStart HookにCapability検出を追加し、planner/developer/reviewer/researcher.md・REVIEW.md・CLAUDE.md・docs/agents.md・docs/research-workflow.mdへ参照を追加。Code Review GraphはCLI直接呼び出しのみ統合（D-012参照） |
| T-013 | サブエージェント進捗の可視化（subagentStatusLine） | 中 | 完了 | claude | .claude/statusline-subagent.shを新設し、エージェントパネルに日本語で進捗表示。当初の実装は公式スキーマの誤認識・マルチバイト文字のtruncationバグがあり、実機検証で発見・修正（D-013参照） |
| T-014 | ユーザー環境のClaude Codeプラグイン導入状況の確認 | 低 | 完了 | claude | 導入済み7プラグインの名前空間衝突・自動起動有無を公式ドキュメントで調査。「Codegraph」プラグインとdocs/code-review-graph.mdが参照するpip製CLIは別プロダクトである旨をdocs/code-review-graph.mdへ追記。Ponytailプラグインとの重複はユーザー環境側の設定判断のためdocsへの反映なし |
| T-015 | AGENTS.md設計原則の圧縮（Ponytailプラグイン重複対応） | 低 | 完了 | claude | Ponytailプラグインとの重複を理由とした「参照のみ」化は、サブエージェントにSkillツールがないこと・このセッションにプラグイン自体が存在しないことの2点から不採用と判断。本文は維持し説明文のみ圧縮（D-014参照） |
| T-016 | project001をClaude Code Starter Kit化（bootstrap.sh・Context7統合） | 高 | 完了 | claude | .claude/bootstrap.shを新設し案内のみのCapability検出に集約。Context7・GitHub CLIをTier1へ追加、Claude Codeプラグインはproject scopeで既定有効化しない方針を維持。/init-projectコマンドを新設（D-015参照） |
| T-017 | Claude Code 2026運用ナレッジの適用（REVIEW.mdの過剰指摘抑制ルール等） | 中 | 完了 | claude | REVIEW.mdへ過剰指摘抑制ルールを追加、CLAUDE.mdへ削除テストと/compact表記を追記、docs/agents.mdのStop Hook不採用理由を補強（D-016参照） |

## バックログ（未着手・優先度未確定）

- （ここに新しいタスク候補を追記する）
- progress.mdが将来肥大化した場合、docs/progress-archive.md等への分割を検討する（D-006時点では未実施・優先度未確定）

## メモ

- 新しいタスクを追加したら、必ず優先度と状態を設定すること。
- タスクの状態が変わったら都度このファイルを更新する（作業完了後にまとめて更新しない）。
- 詳細な作業内容や経緯は [progress.md](./progress.md) を参照。
- 設計上の判断が必要になった場合は [decisions.md](./decisions.md) に記録する。
- **状態列の値は必ず「状態の定義」にある6値を完全一致（前後の空白のみ許容）で使うこと**。SessionStart Hookの完了タスクフィルタ（`.claude/settings.json`）が状態列の完全一致で判定しているため、`完了(要再確認)`のような接尾辞付きの値は「未完了」として扱われる（安全側だが、フィルタが効かなくなる）。既知の制約としてT-011のレビューループで確認済み（docs/progress.md参照）。
- **タスク名・備考欄に未エスケープの`|`を含めないこと**。SessionStart Hookは`docs/tasks.md`を`awk -F'|'`で列分割しており、セル内に`|`があると以降の列がずれる。Markdownテーブルとしても不正な記法になるため、通常の運用では発生しない想定。
