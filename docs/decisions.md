# 設計判断記録 (ADR)

設計判断、採用理由、変更履歴を記録する。新しいエントリは末尾に追加する（古い順）。

## 記録フォーマット

```
## D-XXX: タイトル

- 日付: YYYY-MM-DD
- 状態: 採用 / 却下 / 廃止（廃止の場合は後継のDを記載）

### 背景
- なぜこの判断が必要になったか

### 決定
- 何を決定したか

### 理由
- なぜその選択をしたか（検討した代替案があれば併記）

### 影響
- この決定が及ぼす影響、制約
```

---

## D-001: HyperX SoloCast向け軽量ボイスプロセッサのアーキテクチャ決定

- 日付: 2026-08-12
- 状態: 採用

### 背景
- Issueの要件: SoloCast → 音声処理 → 仮想マイク → Discordという構成で、低い声・小さい声でも聞き取りやすくする軽量Windowsアプリを作る。RNNoise等の既存OSSの調査・利用を明示的に求められている。UIは専門知識不要な簡易構成、常駐時の軽量性・低遅延も要件。
- 添付ZIP（`簡単ボイチェン Var1.0`）は「例」として提示された。中身を確認したところ、JUCE Framework（C++の実績ある音声/GUIフレームワーク）を使い、単一exe・日本語readme・LICENSE.txt（AGPLv3）・THIRD-PARTY-NOTICES.txtという構成で配布されている。JUCEはAGPL枠であれば無償利用できるが、その場合自アプリ全体もAGPL相当で配布する必要があり、この例のライセンス選択はそれに従ったものと判明した。
- 本セッションの実行環境はLinuxのクラウドコンテナであり、Windows実機・Discordクライアントが存在しない。`dotnet`・`mingw-w64`は未導入（実機確認済み）で、Windows向けC++/.NETのクロスビルドはこの環境では行えない。従って「実際にDiscordで使用できる状態まで確認する」という完了条件のうち、Windows実機でのデバイスキャプチャ・仮想マイク経由のDiscord動作確認はこのセッション内では実施不可能であり、ユーザー自身による最終確認が必須という制約がある。

### 決定
- **言語/配布形態**: Python 3。JUCE(C++)・.NET(C#)は本環境でビルド・検証ができないため不採用（理由参照）。配布はPyInstaller `--onefile`によるポータブルexeとし、ビルド自体はユーザーのWindows環境で1回実行してもらう（クロスビルド不可のため）。
- **音声I/O**: `sounddevice`（PortAudio、WASAPI経由）。
- **フレームサイズ**: 48kHz・480サンプル（10ms）に統一。RNNoiseのネイティブフレームサイズ（480）と完全一致し、SoloCastのネイティブ録音レート（48kHz）とも一致するため、リサンプリングや端数処理を持ち込まずに済む。
- **DSPチェーン本体**: Spotify製`pedalboard`（GPLv3、C++実装のPythonバインディング）のHighpassFilter/PeakFilter(EQ)/Compressor/Limiterを利用。本セッションでpipインストール・importが実機確認済み（Linux上でもnumpy配列のオフライン処理として動作するため、DSPロジック自体はこのサンドボックスでユニットテスト可能）。
- **ノイズ抑制**: RNNoise（Xiph.Org、BSDライセンスのC実装）を使うが、`pyrnnoise`パッケージ本体（Apache-2.0）には依存しない。`pyrnnoise`の宣言依存関係に`audiolab`/`av`(PyAV)/`matplotlib`/`click`/`tqdm`が含まれており、`import pyrnnoise`が`__init__.py`経由でこれらを強制的に読み込むため、PyInstallerが同梱するバイナリサイズが「軽量」要件と衝突することを実機確認した（`pip download`で.whlを取得し中身を検証済み）。代わりに、依存のない自己完結型の低レベルctypesラッパー（`pyrnnoise/rnnoise.py`、Apache-2.0、~90行）と同等のコードを出典明記の上で自前実装し、Windows用コンパイル済み`rnnoise.dll`は公式`pyrnnoise`のwin_amd64ホイール（PyPIで存在確認済み）から取得する。
- **AGC/オートレベラー**: 既存ライブラリに該当機能がないため自前実装（RMSエンベロープに基づく低速ゲイン補正。RNNoiseの発話確率でサイレント時の誤補正を抑制）。
- **ノイズゲート**: `pedalboard.NoiseGate`（レベル閾値）ではなく、RNNoiseが返す発話確率を主信号とするゲートを採用。小さい声をレベル閾値で誤って遮断するリスクを避けるため。
- **仮想マイク**: VB-Audio Virtual Cable（無償、実績のある既存ドライバ）を利用する前提とし、自作の仮想オーディオドライバは開発しない。署名付きカーネルドライバの自作は本Issueの「軽量ボイスプロセッサ」というスコープを大きく超える。
- **GUI**: Tkinter（標準ライブラリ、追加依存なし）。
- **ライセンス**: アプリ全体をGPLv3とする（`pedalboard`がGPLv3のため、配布バイナリに組み込む場合はGPLv3互換が必要）。添付の参考アプリがAGPL枠のJUCEを使いAGPLv3で配布していたのと同型のパターンであり、個人利用目的のツールとしては妥当と判断した。THIRD-PARTY-NOTICES.txtを同梱する。

### 理由（検討した代替案）
- **JUCE(C++)**: 添付の参考アプリと同じ構成だが、本セッションの環境にC++コンパイラ・JUCEビルド環境がなく、ビルド・実機テストが一切できない。判定ラダー上「既存の成熟したライブラリ」ではあるが、この環境で検証不能な選択肢は採用しないと判断した。
- **.NET/C#(NAudio)**: `dotnet publish -r win-x64`はLinuxからのクロスビルドが技術的に可能だが、本環境に`dotnet` SDK自体が未導入（実機確認済み）であり、導入コストとビルド未検証リスクがPythonルートを上回ると判断した。
- **`pyrnnoise`パッケージへの直接依存**: 上記の通りPyAV/matplotlib等の重量級依存を強制するため不採用。ただし、低レベルAPI（`rnnoise.py`）自体は自己完結でありAGPL/AGPLではなくApache-2.0なので、出典を明記した上でのコード再利用は問題ないと判断した。
- **`pedalboard`を使わず全DSPを自前実装**: GPLv3を避けられるが、判定ラダー（既存の成熟した外部ライブラリを優先）に反する。添付の参考アプリ自体がコピーレフトライブラリ（JUCE/AGPL）を使って自アプリをAGPL配布する前例を示しており、個人用ツールとして同型の判断が可能と考え、`pedalboard`利用を優先した。

### 影響
- 実装（Developer）はこのアーキテクチャを前提に行う。DSPロジック（EQ/コンプレッサー/AGC/RNNoise連携/ゲート）は本セッション環境（Linux）でnumpy合成信号によるユニットテストと処理速度ベンチマークが可能。
- 音声デバイスキャプチャ・VB-Cable経由の仮想マイク出力・実際のDiscordでの動作確認は、この環境では実施不可能。ユーザーのWindows環境での最終確認が必須であり、そのための確認手順書を成果物に含める。
- 配布用exeのビルド（PyInstaller）もユーザーのWindows環境で1回実行してもらう必要がある。ビルドスクリプト・手順書を成果物に含める。

---

## D-002: T-001実装時に補った数値パラメータ・テスト設計判断

- 日付: 2026-08-12
- 状態: 採用

### 背景
- D-001で確定した仕様書（docs/tasks.md T-001指示）は、明瞭度・ノイズ除去・コンプレッサー・AGCのtarget/max_gainについては具体的な数値表を与えていたが、以下は「低速」「緩め」等の定性的な指定にとどまり、具体的な数値はDeveloper実装時の判断に委ねられていた。
- また、AGC・発話確率ゲートの効果をpytestで実測する過程で、RNNoiseの発話確率が完全に定常な合成音（周期的なsin波の倍音合成）に対して数十フレーム後に大きく低下する（非音声と判定される）実挙動が確認され、フルチェーンを通したテスト設計にも判断が必要になった。

### 決定
1. **AGCの時定数**: `presets.AgcParams`の`attack_seconds=2.0`, `release_seconds=4.0`をデフォルト値とし、全プリセット共通で使用する（プリセット表はtarget/max_gainのみを指定するため）。RMSエンベロープを目標値に追従させる時定数であり、数秒オーダーの「低速」を意図した値。
2. **AGCのゲイン更新凍結閾値**: 発話確率0.3未満で凍結する（`AutomaticGainControl.freeze_speech_prob_threshold`のデフォルト値）。
3. **ゲートのattack**: 発話確率が閾値を上回った際にゲートが開く速さは全ノイズ除去段階で共通のattack_ms=5.0(SpeechProbabilityGateのデフォルト)とした。仕様書はrelease(閉じる速さ)のみを規定していたため。
4. **共通Limiterのrelease_ms**: 100msとした(仕様書はceiling -1.0dBFSのみ規定)。
5. **AGCとCompressor/Limiterの順序**: 仕様書の「Compressor → 自前AGC → Limiter」の順序どおりに実装（`app/soloclarity/dsp/chain.py`）。
6. **テスト設計(test_chain.py)**: 明瞭度(EQ)のFFT検証は、HighpassFilter+PeakFilter部分のみを単独実行して検証する方式にした。Compressor/AGC/Limiterは全帯域に一様なスカラーゲインしかかけないため、フルチェーンを通しても2帯域間の相対関係(EQの効果そのもの)は変わらない一方、RNNoiseは周波数選択的に動作するため、フルチェーン経由だとRNNoiseの影響がEQ単体の効果に混ざってしまうため。
7. **テスト設計(AGCのRMS上昇の検証)**: AGC単体(test_agc.py)では出力RMSがtarget_dbfsへ近づくことを厳密に数値検証する。フルチェーン(test_chain.py)では、上記の通りRNNoiseが完全に定常な合成音を「非音声」と徐々に判定してしまい、フレームごとの出力振幅が大きく揺らぐため、出力RMSそのものの単調な上昇を安定して検証できなかった。そのため、フルチェーン側ではAGCの内部ゲイン状態(`chain.agc._gain`)が量の小さい入力に対して増加方向に働くことを確認する設計にとどめた（実際の音声はRNNoiseにとって「非音声」化しないため、この制約は合成テスト信号特有の限界であり、実装のバグではない）。

### 理由
- 仕様書に明記されていない数値は、AGENTS.md判定ラダーに従い「要件を過不足なく満たす最小実装」として、一般的なボイスプロセッサのAGC/ゲート挙動（数秒オーダーの緩やかな追従、100ms程度のリミッターリリース）を参考に妥当な値を選んだ。
- テスト設計上の制約(RNNoiseが完全に周期的な合成音を非音声と判定する)は、実装のバグではなくRNNoiseというモデルの実際の挙動である。これはむしろ「本物の音声ではノイズ扱いされない」というRNNoiseの正しい動作を裏付けている。

### 影響
- Reviewerはこれらの数値がAGENTS.md/D-001の要求範囲内(定性的な指定を満たす具体値)であることを確認する。将来ユーザーからのフィードバック(Windows実機確認)で時定数の調整が必要になった場合は、`app/soloclarity/presets.py`の`AgcParams`・`app/soloclarity/dsp/gate.py`・`app/soloclarity/dsp/chain.py`の該当箇所のみを変更すればよい(GUIの詳細設定パネルからはAGCのtarget/max_gainのみ調整可能。attack/release秒数はGUI非公開のプログラム定数)。

---

## D-003: `advanced_overrides`復元時にDSPチェーンへ反映されないバグの修正（Reviewer指摘対応）

- 日付: 2026-08-12
- 状態: 採用

### 背景
- Reviewerが`app/soloclarity/gui/app.py`をxvfb環境で実機検証し、`_restore_from_config`が`self._updating_from_code = True`をセットしたまま`_apply_advanced_overrides`を呼び、その中で各スライダーへ`.set(value)`した後に`_on_advanced_slider_changed(None)`を呼んでchainへ反映しようとしていたが、`_on_advanced_slider_changed`冒頭のガード`if self._updating_from_code: return`により即座にreturnし、chainへの反映が一度も実行されないことを確認した(CONFIRMED, High)。
- 結果として、詳細設定を変更→保存→再起動すると、スライダーの表示は保存値どおりに復元されるが、実際の音声処理を担う`self.chain`側(EQ/コンプレッサー/AGC等)はプリセットデフォルトのまま動作し続けるという、表示と実処理が乖離するバグが発生していた。
- 根本原因は「復元中の誤反応を防ぐガード(`_updating_from_code`)」と「詳細設定変更をchainへ適用する処理」が同一関数(`_on_advanced_slider_changed`)に同居しており、両者を分離できていなかったこと。

### 決定
- `_on_advanced_slider_changed`からchainへの反映ロジックを`_apply_slider_values_to_chain()`という別関数に切り出した。
  - `_on_advanced_slider_changed`はガード判定後に`_apply_slider_values_to_chain()`を呼ぶだけのラッパーとして残す(ユーザーがスライダーを直接操作した際の経路)。
  - `_apply_advanced_overrides`(config復元時の経路)は、`_updating_from_code`の値に関わらず`_apply_slider_values_to_chain()`を直接呼ぶ。
- 併せてLow指摘として、`app/soloclarity/dsp/chain.py`の`_build_limiter_board()`に直書きされていた`release_ms=100.0`を`presets.LIMITER_RELEASE_MS`(`app/soloclarity/presets.py`に新規追加)へ移動した。presets.pyモジュールdocstringの「UIやDSPチェーンはこのモジュールの値のみを参照し、数値をコード中に埋め込まないこと」というルールに沿わせるため。

### 理由
- 判定ラダーの「バグは根本原因を直す」(AGENTS.md)に従い、症状(反映されない)ではなく、ガードが復元経路のchain反映まで無効化してしまっている構造上の原因を直した。ガード自体は「ユーザー操作イベント由来の誤反応防止」という別の役割を持つため、それを維持しつつchain反映ロジックだけを独立させる形にし、既存のイベントハンドラの責務を変えないようにした。

### 影響
- xvfb環境で`advanced_overrides`を含む`config.json`から`App`を復元し、`app.chain.agc.target_linear`が保存値(`agc_target_dbfs=-18.5`)から計算される期待値と一致することを実機検証した(プリセットデフォルトの`-17.0`とは異なる値であることを確認済み)。
- `pytest tests/`は26 passedのまま(リグレッションなし)。
- 今後、詳細設定パネルに新しいスライダーやconfig復元経路を追加する場合も、chainへの反映処理は`_apply_slider_values_to_chain()`に一本化し、`_updating_from_code`ガードを持つイベントハンドラ側からのみ条件付きで呼び出す構造を踏襲すること。

---

## D-004: GitHub Actions（windows-latest）によるexeビルドの自動化

- 日付: 2026-08-12
- 状態: 採用

### 背景
- ユーザーから「実行ファイルは出せるか」と問われた。D-001記載の制約どおり、この開発環境（Linuxのクラウドコンテナ、Wine等のWindows互換レイヤーも未導入であることを実機確認済み）ではPyInstallerがクロスコンパイルに対応していないため、`SoloClarity.exe`をこのセッション内で直接生成することはできない。
- 一方、ユーザーの手元でのビルド（`app/build/build_windows.bat`、README.md記載）は既に用意済みだが、より手間なくexeを入手できる方法として、CI（GitHub Actions）で実際のWindowsランナー上でビルドし、Artifactとして配布する提案をユーザーが了承した。

### 決定
- `.github/workflows/build-windows.yml`を新規作成。`windows-latest`ランナー上で以下を実行する。
  1. Python 3.11をセットアップ
  2. `requirements-dev.txt`をインストールし、`pytest tests/`を実行（このステップにより、これまでLinux環境でしか検証できていなかったRNNoiseラッパー（Windows版`rnnoise.dll`経由）を含むDSPロジックが、実際のWindows上で初めて検証されることになる）
  3. 既存の`app/build/build_windows.bat`をそのまま呼び出してビルド（ビルド手順を複製せず、既存スクリプトを単一の実装として再利用する）
  4. `app/dist/SoloClarity.exe`を`actions/upload-artifact`でArtifactとして公開（保持期間30日）
- トリガーは`push`(mainブランチ、`app/**`または本ワークフロー自体の変更時)、`pull_request`(同条件)、`workflow_dispatch`(手動実行)の3つ。PRトリガーにより、mainへマージする前にWindows上でのビルド・テストが継続的に検証されるようになる。

### 理由（検討した代替案）
- **Wine経由でこのLinux環境からビルドする案は不採用**: このセッションにWineが導入されておらず、導入して試みたとしても、実際のWindows実行環境との差異（DLL・オーディオドライバ周りの挙動）を検証しようがなく、成果物の信頼性を保証できない。判定ラダー（既存の成熟した手段を優先）に照らし、GitHub Actionsの`windows-latest`という公式にサポートされたWindows実行環境を使う方が確実と判断した。
- **ビルド手順を`build_windows.bat`と別にワークフロー内へ再実装する案は不採用**: 同じ手順を2箇所に持つと、将来どちらか一方だけが更新されて食い違うリスクがある（AGENTS.mdの「同じ情報を複数箇所に保存しない」原則）。ワークフローから既存の`.bat`を呼び出す形にした。
- **pull_requestトリガーを追加しない案（push/dispatchのみ）は不採用**: `app/`を変更するPRの時点でWindows上のビルド・テストが継続的に検証できることは、D-001に記載した「Windows実機での検証ができない」という制約を部分的に補う直接的な効果があり、コスト（Windowsランナーの実行時間）に対して価値が大きいと判断した。

### 影響
- 今後`app/`を変更してmainへpush、またはPRを作成すると、自動的にWindows上でのpytest実行とexeビルドが走る。ビルドが失敗すれば、Reviewerによるレビューだけでは検出できなかったWindows固有の問題（依存解決・DLL同梱漏れ等）が可視化される。
- ユーザーは、GitHub ActionsのArtifactから`SoloClarity.exe`をダウンロードするだけで、自分でPythonやビルド手順を用意しなくてもexeを入手できるようになった。
- Windowsランナーの実行時間はGitHub Actionsの無料枠を消費する（Linuxランナーよりも消費係数が大きい）。頻繁に`app/`を変更する場合はコストを意識する必要がある。
