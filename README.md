# MIC

HyperX SoloCastを入力デバイスとする軽量ボイスプロセッサ。低い声・小さい声でもDiscord通話相手に聞き取りやすくすることに特化し、ノイズ抑制・EQ・コンプレッサー等の処理を行った音声を仮想マイク経由でDiscordへ渡す。

開発方針・タスク管理・レビュー手順は[project001](https://github.com/nagamaki0311/project001)テンプレート（AGENTS.md / REVIEW.md / CLAUDE.md）を踏襲する。

## セットアップ

1. `git clone`等でこのリポジトリを取得する。
2. （任意）`bash .claude/bootstrap.sh`を実行し、Optional Dependency（Agent-Reach/Code Review Graph/Context7/GitHub CLI等）の導入状況を確認する。インストールは行わず案内のみを表示するため、実行しなくても本リポジトリの開発フローは完全に動作する。
3. AGENTS.mdの開発フロー（User → Manager → Planner → Developer → Reviewer → Manager → Complete）に従って進める。

## 使い方

アプリ本体の使い方（動作環境・インストール手順・操作方法）は、実装が固まった時点で本節に追記する。現時点ではdocs/tasks.mdの進行中タスクを参照。

## 構成

- AGENTS.md
  - 開発方針・設計原則・ワークフロー（全AIエージェント共通、最優先で読む）

- REVIEW.md
  - レビュー方針（敵対的検証 / Adversarial Review）。reviewer Agentが従う

- CLAUDE.md
  - Claude Code固有の設定・運用ルール（AGENTS.mdをimportする）

- .claude/agents
  - planner / researcher / developer / reviewer

- .claude/settings.json
  - SessionStart / PreCompact Hook（セッション継続性の補助）、subagentStatusLine（サブエージェント進捗の可視化）。詳細はdocs/agents.md

- .claude/bootstrap.sh
  - Optional Dependency（Capability Layer）の導入状況を案内のみで表示する検出スクリプト。インストールは行わない

- .claude/commands/init-project.md
  - `/init-project`コマンド。新規プロジェクトでの初期化手順（本READMEの該当節）を実行する

- docs
  - tasks.md: タスクと状態管理
  - progress.md: 作業履歴
  - decisions.md: 設計判断の記録
  - agents.md: Agent構成・モデル構成・Hook/Status Line構成の詳細
  - agent-reach.md: [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 対応（Optional Dependency、検出・フォールバック方針）
  - code-review-graph.md: [Code Review Graph](https://github.com/tirth8205/code-review-graph) 対応（Optional Dependency、影響範囲解析）
  - context7.md: [Context7](https://github.com/upstash/context7) 対応（Optional Dependency、ライブラリドキュメント確認）
  - capability-layer.md: 外部ツール検出の共通規約（Capability Layer）
  - research-workflow.md: 外部調査ワークフロー
  - status-line.md: サブエージェント進捗の可視化（Status Line）の仕様

## 開発フロー

User → Manager → Planner → Developer → Reviewer → Manager → Complete
（外部調査が必要な場合のみResearcherが加わる）

詳細は AGENTS.md・REVIEW.md・docs/agents.md を参照。
