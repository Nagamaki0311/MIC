# MIC

HyperX SoloCastを入力デバイスとする軽量ボイスプロセッサ。低い声・小さい声でもDiscord通話相手に聞き取りやすくすることに特化し、ノイズ抑制・EQ・コンプレッサー等の処理を行った音声を仮想マイク経由でDiscordへ渡す。

開発方針・タスク管理・レビュー手順は[project001](https://github.com/nagamaki0311/project001)テンプレート（AGENTS.md / REVIEW.md / CLAUDE.md）を踏襲する。

## セットアップ

1. `git clone`等でこのリポジトリを取得する。
2. （任意）`bash .claude/bootstrap.sh`を実行し、Optional Dependency（Agent-Reach/Code Review Graph/Context7/GitHub CLI等）の導入状況を確認する。インストールは行わず案内のみを表示するため、実行しなくても本リポジトリの開発フローは完全に動作する。
3. AGENTS.mdの開発フロー（User → Manager → Planner → Developer → Reviewer → Manager → Complete）に従って進める。

## 使い方

アプリ本体（SoloClarity）は `app/` 以下にPython 3実装がある。設計判断はdocs/decisions.md D-001・D-002を参照。

### 開発環境（このリポジトリで完結する範囲）

```
cd app
pip install -r requirements.txt        # sounddevice, pedalboard, numpy
pip install -r requirements-dev.txt    # pytest, pyrnnoise(RNNoiseのテスト専用取得元)
pytest tests/                          # DSPロジックの自動テスト（26件、実デバイス不要）
python -m tests.bench_chain            # 1フレーム(10ms)あたりの処理時間ベンチマーク
```

`pyrnnoise`はテスト専用の開発依存であり、アプリ本体コード（`app/soloclarity/`以下）からは一切importしない（`app/soloclarity/dsp/rnnoise.py`に自前のctypesラッパーを実装している）。

### エンドユーザー向け（Windows実機）

`SoloClarity.exe` の入手方法は2通りある。

- **GitHub Actionsから入手（推奨、ビルド不要）**: このリポジトリの Actions タブ → `Build Windows executable` ワークフローの最新の成功実行 → Artifacts欄の `SoloClarity-windows-exe` をダウンロードする。`main`への変更やPRのたびに`windows-latest`ランナー上で自動ビルドされる（`.github/workflows/build-windows.yml`、D-004参照）。
- **自分でビルドする**: `app/build/build_windows.bat` をWindows上で実行し、`SoloClarity.exe` をビルドする（このLinux開発環境ではビルドできないため、必ずユーザーのWindows環境で実行する）。

入手後の手順:

1. [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) を別途インストールする（本リポジトリには同梱しない）。
2. `SoloClarity.exe` を起動し、マイク・出力先（CABLE Input）・プリセットを選ぶ。

詳しい手順は `app/はじめにお読みください.txt`（日本語マニュアル）を参照。Windows実機での動作確認項目は `app/WINDOWS_VERIFICATION_CHECKLIST.md` にまとめている（このLinux開発環境では自動テスト・ベンチマークまでしか検証できていないため、実機確認が必須）。

ライセンス（GPLv3）・使用OSSの著作権表示は `app/LICENSE` ・ `app/THIRD-PARTY-NOTICES.txt` を参照。

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
