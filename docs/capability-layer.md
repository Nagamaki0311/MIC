# Capability Layer

project001における「利用可能な外部ツールを自動検出し、あれば優先利用・なければ既存フローへフォールバックする」という共通規約を定義する。

## 位置づけ

Capability Layerの本体は、以下の**Agentへの指示規約**である。`.claude/bootstrap.sh`はこの規約自体を置き換えるものではなく、規約が定める検出手順（手順1）を1箇所にまとめて事前実行するキャッシュ最適化の実装に過ぎない。project001はアプリケーションランタイムを持たないテンプレートであり、検出ロジックをコードとして実装すること自体が正当化できない新規依存にならないよう、`bootstrap.sh`は`command -v`のみに依存し新規の外部依存を一切持たない（AGENTS.mdの判定ラダー3〜5段目を満たす）。

1. 該当ツールの検出コマンドを`command -v <ツール名>`（または同等の軽量チェック）で実行する
2. 利用可能なら、そのツールが提供する機能を優先利用する
3. 利用不可、またはコマンドが失敗した場合は、即座に既存フロー（Read/Grep/Bash等の標準ツール）へフォールバックする。インストールを促したり、タスクを止めたりしない
4. ツール固有の仕様・コマンドは、そのツール専用のdocsファイル（例: docs/agent-reach.md）にのみ記載し、複製しない

当初はこの検出手順（手順1）を`.claude/settings.json`のSessionStart Hookコマンド文字列に直接列挙していたが、検出対象が増えるにつれ1行コマンドが線形に長大化し可読性が落ちる問題があった。判定ラダー6段目（1行で書けるか）を再評価した結果、「1行では収まらない」という結論に至ったため、`.claude/bootstrap.sh`という専用スクリプトへ切り出した（D-013で`subagentStatusLine`用のスクリプトファイルを新設した際と同じ判断基準）。検出対象リストはスクリプト内1箇所にまとめており、追加は1行で完結する。

## キャッシュ効率: bootstrap.sh経由の事前検出

利用可否はセッション中に変化しないため、`.claude/settings.json`のSessionStart Hookが`bash "$CLAUDE_PROJECT_DIR/.claude/bootstrap.sh" --check`を一度だけ実行し、結果をManagerのコンテキストに表示する（`.claude/settings.json`参照）。Managerは、Planner/Researcher/Developer/Reviewerを起動する際にこの結果をタスク説明に含めてよい（各Agentが同じ検出コマンドを繰り返し実行する無駄を避ける）。Plannerは自身でBashを実行できないため、この共有が実質的な唯一の入手手段になる。

ただし、Hookが発火しない実行環境が存在すること（docs/agents.md「運用上の注意」参照）から、**各Agent自身も`command -v`による自己検出を維持する**。Hookのキャッシュはあくまで最適化であり、それに依存しないと機能しない設計にはしない。

## Capability一覧（3階層）

### Tier1: 統合済み（Agentの振る舞いに組込み）

| Capability | 検出コマンド | 利用するAgent | フォールバック | 詳細 |
|---|---|---|---|---|
| Agent-Reach | `command -v agent-reach`（詳細な健全性確認含め各docs参照） | Researcher | WebFetch/WebSearch | docs/agent-reach.md |
| Code Review Graph | `command -v code-review-graph` | Developer, Reviewer | Read/Grep/Bashによる呼び出し元検索 | docs/code-review-graph.md |
| Context7 | `command -v ctx7` | Planner, Developer, Reviewer, Researcher | Planner・Researcher→WebFetch/WebSearch、Developer・Reviewer→既存のRead/Grep/Bashによる調査（`tools`にWebFetch/WebSearchを持たないため） | docs/context7.md |
| GitHub CLI (`gh`) | `command -v gh` | Researcher | WebFetch/WebSearch | 個別調査での`gh`活用はResearcherの既存フロー（WebFetch/WebSearch）に対する追加の情報源であり、専用docsは設けず本表とresearcher.mdの参照のみで完結させる |

### Tier2: 検出のみ（Agentの振る舞いには未組込み）

`.claude/bootstrap.sh`の検出対象には含めるが、project001自体に消費するタスクがまだ具体化していないため、Agent定義ファイルへの振る舞い統合は行わない。

| Capability | 検出コマンド | 検出のみに留める理由 |
|---|---|---|
| Node.js | `command -v node` | Context7 CLI（`ctx7`）の実行にNode.js 18+が前提となるため、関連ツールとして検出対象に含めている |
| Python | `command -v python3` | Agent-Reach・Code Review GraphがいずれもpipでCLIを配布しているため、関連ツールとして検出対象に含めている |
| Playwright | `command -v playwright` | project001自体にブラウザ操作対象のUIコードが存在しない。個別アプリのリポジトリでUIが実装された時点で、そちらでTier1へ昇格させる出発点として検出のみ用意している |

### 対象外（検出対象にしない）

| 項目 | 対象外とする理由 |
|---|---|
| MCP Server | 個別ツールではなくClaude Code本体の接続機構であり、`command -v`で検出する対象と同列ではない。加えてproject001のsubagent（`.claude/agents/*.md`）は`tools`フロントマターがallowlist方式であり、現状Planner/Developer/Reviewer/ResearcherからMCPサーバーのツールを呼び出せない。追加する場合は、対象subagentの`tools`にMCPツール名を追記した上で、当該Agent定義ファイルとdocs/capability-layer.mdの両方を更新する手順が必要になる |
| Claude Design `/design-sync` | Claude Code本体のスラッシュコマンドであり`command -v`で検出する対象ではない。project001自体にUIコードが存在せず、同期対象のデザインが存在しない |
| Ponytail | AGENTS.mdの設計原則1〜8として本文へ統合済み（D-003、D-014）であり、`command -v`で検出する外部コマンドではないため検出対象にしない |
| Claude Codeプラグイン全般 | project scopeでは既定で有効化しない。プラグインはユーザー個人のインストール状況に依存し、project001をコピーした派生プロジェクトすべてに強制されるべきものではないため。派生プロジェクトで有効化する場合は、`.claude/settings.json`にプラグインmarketplace/インストール設定を追加し（`enabledPlugins`等、Claude Code公式ドキュメントのキー構成に従う）、user scope（個人環境全体）ではなくproject scope（このリポジトリ配下のみ）に限定した上で、docs/capability-layer.mdに追加したプラグイン名と用途を記録する |

個別アプリのリポジトリ（project001から作成された別リポジトリ）で、Tier2のツールを実際に使うタスクが発生した時点で、下記「新しいCapabilityを追加する手順」に沿ってTier1へ昇格させる。

## 新しいCapabilityを追加する手順

1. `.claude/bootstrap.sh`の`CAPABILITIES`に1行追加する
2. `docs/<tool>.md`を新設し、ツールの正体・検出方法・フォールバック方針・疎結合設計を記載する
3. 利用するAgent（`.claude/agents/*.md`）に、優先利用する旨の参照1行を追加する
4. 本ファイルのTier表に1行追加する
5. `docs/decisions.md`に記録する

## アーキテクチャ

```
Agent起動時（Researcher/Developer/Reviewer）
        │
        ▼
   command -v <tool>?
   ├─ Yes → <tool> doctor/version等で健全性を確認
   │         ├─ 成功 → 対応機能を優先利用
   │         └─ 失敗 → フォールバック
   └─ No  → フォールバック（Read/Grep/Bash/WebFetch等の標準ツール）
        │
        ▼
   結果を要約してManagerへ返す（生の出力はコンテキストに残さない）
```

`.claude/bootstrap.sh --check`での事前検出も同じ`command -v`判定を使うため、Agent起動時の自己検出と矛盾しない（同じ規約の二重適用であり、結果は常に一致する）。

## 関連

- Agent-Reach: docs/agent-reach.md
- Code Review Graph: docs/code-review-graph.md
- Context7: docs/context7.md
- 調査ワークフロー: docs/research-workflow.md
- レビュー方針: REVIEW.md
