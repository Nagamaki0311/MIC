# Agent構成とモデル・Hook詳細

Agent構成、モデル構成（Model Routing）、オーケストレーションの技術的根拠、Hook構成を記録する。開発方針・設計原則はAGENTS.mdを、レビュー方針はREVIEW.mdを、Agent-Reach対応の詳細はdocs/agent-reach.md・docs/research-workflow.mdを、Capability Layer/Code Review Graphの詳細はdocs/capability-layer.md・docs/code-review-graph.mdを、進捗の可視化の詳細はdocs/status-line.mdを参照（本ファイルでは扱わない）。AGENTS.md/CLAUDE.mdから参照される。

## Agent構成

| Agent | 定義ファイル | 役割 | 起動元 |
|-------|-------------|------|--------|
| Manager | なし（このセッション自身の役割。CLAUDE.md参照） | タスク管理・Agent割当・優先順位判断・レビュー依頼・完了判定 | User |
| Planner | `.claude/agents/planner.md` | 現状分析・実装計画の作成 | Manager |
| Developer | `.claude/agents/developer.md` | 実装・バグ修正 | Manager |
| Reviewer | `.claude/agents/reviewer.md` | コードレビュー・敵対的検証（REVIEW.md参照） | Manager |
| Researcher | `.claude/agents/researcher.md` | 外部情報収集・重複除去・信頼性評価（Agent-Reach対応） | Manager（Plannerが必要と判断した場合のみ） |

## モデル構成（Model Routing）

各Agentの`model`は`inherit`（Managerのセッションモデルに追従）を使わず、役割ごとに固定している。`inherit`のままだと、Managerが使っているチャットモデル次第でPlanner/Developer/Reviewerの品質・コストが意図せず変動してしまい、Model Routingの前提（役割に応じた予測可能な品質・コスト）が崩れるため。

| Agent | モデル | 選定理由 |
|-------|--------|----------|
| Manager | セッションの既定モデル（上書きしない） | ルートセッション＝Userが選んだ対話モデルそのもの。判断・Agent割当・状態管理という業務内容自体は既存の推論力で十分であり、`.claude/settings.json`でproject001が対話モデルを強制すると、このリポジトリでの作業全体（Manager業務に限らない）に影響してしまうため上書きしない |
| Planner | `opus` | 設計判断の質は下流（Developer/Reviewer）の手戻り量に直結し、起動頻度は低い（タスクごとに1回程度）。品質を安易に落とさない方針（Definition of Done参照）に従い、最も推論力の高いモデルを固定する |
| Developer | `sonnet` | Anthropicのコーディング用途の標準モデルであり、既存コード規約に沿った実装・根本原因修正に十分な理解力を持つ。Opus常用ほどの必要性はなく、Haikuでは複雑な既存コードの理解漏れリスクがあるため中間の`sonnet`を固定する |
| Reviewer | `sonnet`（既定） | project001は不特定多数の個別アプリのテンプレートであり、そこにコピーされた先ではセキュリティ・正確性に関わるコードレビューが行われる。テンプレートの既定は下げすぎない |
| Researcher | `sonnet` | 複数チャネルの検索結果の重複除去・信頼性評価には一定の推論力が要るが、Plannerほどの開放的な設計判断は不要。検索・要約が中心の作業内容とコストのバランスを取る |

### 軽量レビューの扱い（新規Agentを追加しない理由）

Markdown/README/docsの体裁確認など、コード品質やセキュリティに関わらない軽量なレビューについては、専用の軽量Agentを新設せず、Managerがreviewerを起動する際にAgent呼び出しの`model`パラメータで`haiku`等へ一時的に上書きする運用とする。Claude Code側に「呼び出し時のモデル上書き」という既存機能があるため、これに専用Agentファイルを追加するのはPonytailの判定ラダー（3: 標準ライブラリ/既存機能で足りるか）に反する。reviewer.md自体は変更せず、既定(`sonnet`)のまま維持する。

## オーケストレーションルール

Manager起動の制約・開発フロー・修正ループはAGENTS.mdの「ワークフロー」を参照（重複記載しない）。ここでは技術的な補足のみを記す。

- 各Agentはタスク終了後、変更点と結果を要約してManagerに返す。詳細な作業ログはdocs/progress.mdに記録し、会話コンテキストには要約のみ残す。

### Hookとの接続（なぜManagerを独立subagentにしないか、その2つ目の根拠）

SessionStart/PreCompactのHook出力は、常にManager（ルートセッション）のコンテキストにのみ注入される。Planner/Developer/Reviewerはsubagentとして隔離されたコンテキストで動くため、これらのHook出力を直接受け取ることはない。したがって

- SessionStart Hook → Manager（タスク状況を把握してから Planner を起動）
- PreCompact Hook → Manager（サイクルの任意の時点で発火。docsへの記録を判断・実行してから圧縮を許容する）

という流れは、Managerをsubagent化しない限りにおいて技術的に自然に成立する。これはD-004でManagerを独立subagentにしなかった判断（公式推奨のオーケストレーション構成）に加え、Hookとの統合という観点からも同じ結論を補強する。
なお、PreCompact Hookは「Reviewerの後」等の固定ステップではなく、コンテキストサイズに応じて任意のタイミングで発火するイベントである。開発フローの図はあくまで論理的な作業順序を示すものであり、PreCompactは並行して発火し得る点に注意する。

## 採用しなかったAgent

- **research（過去に不採用、現在はResearcherとして採用）**: D-004時点では「Plannerが調査を兼ねており役割が重複する」として不採用としていた。Agent-Reach対応（D-009）により、GitHub/Web/RSS/YouTube/Reddit/X等の複数チャネルを横断する調査量・重複除去・信頼性評価という、Plannerの設計判断とは異なる作業が明確になったため判断を見直し、Researcherとして採用した。Plannerは「何をどのチャネルで調べるか」を決める（軽微な確認のためのWebFetch/WebSearchは残す）、Researcherは「実際に集めて評価する」に役割を分離しており、重複しない。
- **UI**: project001自体はアプリケーションコードを持たないテンプレートであり、UIレビューの対象が存在しない。UI固有のAgentが必要になった場合は、本テンプレートから作成した個別アプリのリポジトリ側で追加する。

## コード品質ルール

AGENTS.mdの「設計原則」を参照（判定ラダー、後方互換性を維持しない方針、根本原因修正、`ponytail:`コメント運用など）。本ファイルでは重複記載しない。

## Hook構成（`.claude/settings.json`）

セッション継続性を技術的に担保するため、以下2つのHookを導入している。いずれも新規の外部依存関係は追加していない。Capability Layerの検出手順（`command -v`）は当初`.claude/settings.json`のHookコマンド文字列に標準shellコマンド1行として直接記述していたが、検出対象が増えるにつれ1行コマンドが線形に長大化したため、判定ラダー6段目（1行で書けるか）を再評価し`.claude/bootstrap.sh`という専用スクリプトへ切り出した（経緯の詳細はdocs/capability-layer.md参照）。

- **SessionStart**: セッション開始時に、`.claude/bootstrap.sh --check`によるCapability Layer（Agent-Reach・Code Review Graph・Context7・GitHub CLI等）の検出結果、`docs/tasks.md` のうち未完了タスク（状態列が`完了`の行を除外した行）、`docs/progress.md` の最新エントリを自動表示する。検出対象の追加・変更は`.claude/bootstrap.sh`の1箇所で完結し、`.claude/settings.json`側の変更は不要（`bootstrap.sh`が存在しない場合も`2>/dev/null`によりHook全体は失敗しない）。「セッション開始時にdocs/progress.md・docs/tasks.mdを確認する」という運用ルール（CLAUDE.md参照）を、手動確認任せにせず技術的に補助する。完了タスクを除外するのは、タスクが積み重なるにつれ完了行の表示コスト（トークン消費）が線形に増え続けるのを防ぐため。この除外は`awk -F'|'`で行を列分割した上で状態列（5列目）の値が`完了`かどうかを判定しており、備考欄など他の列に`完了`という文字列が含まれていても影響しない。`docs/tasks.md`のタスク一覧表の列構成（`| ID | タスク | 優先度 | 状態 | 担当エージェント | 備考 |`の6列）を前提とする。Capability検出の規約自体はdocs/capability-layer.mdを参照（本ファイルでは重複記載しない）。
- **PreCompact**: コンテキスト圧縮の直前に、docs/progress.md・docs/tasks.mdへの記録を促すリマインダーを表示する。長時間セッションで未記録の作業がコンテキスト圧縮により失われることを防ぐ。

いずれもコード（アプリケーションロジック）を持たないproject001に合わせ、状態の要約表示・記録の呼びかけに留めている。lintやビルド連携等のHook（PreToolUse/PostToolUse）は、project001自体にアプリケーションコードがなく対象がないため導入していない。個別アプリのリポジトリ側で必要になった場合はそちらで追加する。Stop Hook（応答終了ごとに発火）も検討したが、docs更新のタイミングとしては頻度が高すぎ、毎ターンのリマインダーはトークンの無駄になるため不採用とした。公式が示す「確定的なレビューゲート」としてのStop Hookも検討したが、pass/failを返すスクリプトが前提であり、アプリケーションコードを持たないproject001には機械判定可能なチェックが存在せず、REVIEW.mdの敵対的検証はLLMの判断でありスクリプト化できず、8回連続ブロックでClaude Codeが自動オーバーライドするため「確定的」な保証にもならない。ただし個別アプリのリポジトリではテスト・ビルド等の機械判定可能なチェックが存在するため、そちら側でStop Hookによる確定的ゲートを検討してよい。

### 運用上の注意（環境依存）

- `.claude/settings.json`が存在しない状態で開始したセッションでは、設定の再読み込みに `/hooks` を開くかセッション再起動が必要になる場合がある（Claude Code側の既知の挙動）。
- Claude Code on the web／リモート実行環境では `/hooks` コマンド自体が提供されていないことがある。これはUIコマンドの制約であり、Hook実行機構（`.claude/settings.json`の`hooks`設定）自体はリモート環境でも動作する（`$CLAUDE_CODE_REMOTE`環境変数がHook内で参照可能であることからも裏付けられる）。新規セッション（コンテナの新規起動）では自動的に有効化される。
- Hookが発火しているか不明な場合は、SessionStart Hookのコマンドをターミナルで直接実行し、出力が想定通りか確認する。

## Status Line構成（`.claude/settings.json`）

`subagentStatusLine`により、サブエージェント実行時のみエージェントパネルに進捗を日本語で表示する（`.claude/statusline-subagent.sh`、新規依存なし）。Hookとは異なり会話コンテキストへは注入されないため、LLMトークンを消費しない。stdinスキーマ・出力形式・実装時に発見した問題（マルチバイト文字のtruncationバグ等）の詳細はdocs/status-line.mdを参照（本ファイルでは重複記載しない）。
