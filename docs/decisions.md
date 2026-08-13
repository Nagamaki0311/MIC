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

### 追記（2026-08-12・初回CI実行での修正）
- ワークフロー追加直後の初回CI実行（PR #3, run 31609477972）で、`pytest tests/`は26 passedだったが、`python -m PyInstaller`が`ERROR: Unable to find 'D:\a\MIC\MIC\app\build\output\soloclarity\dsp\vendor\rnnoise.dll' when adding binary and data files.`で失敗した。このLinux開発環境ではPyInstallerのビルドフェーズ自体を一度も実行・検証できていなかったため（D-001の既知の制約）、実際にWindows上で走らせて初めて顕在化した問題である。
- 原因: `--add-binary`に渡した相対パス（`soloclarity\dsp\vendor\rnnoise.dll`）を、PyInstallerがカレントディレクトリ（`app`）ではなく`--specpath`（`build\output`）基準で解決していた。`--workpath`/`--specpath`をbuild_windows.bat自身の置き場所（`app\build`）から分離するために導入したこの2オプションが、意図しない形で相対パス解決の基準まで変えてしまっていた。
- 対応: `build_windows.bat`で`set "RNNOISE_DLL=%CD%\soloclarity\dsp\vendor\rnnoise.dll"`により絶対パスへ展開し、`--add-binary`にはその絶対パスを渡すよう修正した。CI（`.github/workflows/build-windows.yml`）を追加した直接の効果として、この問題をmainへ混入させる前にPR上で検出できた。

---

## D-005: T-003 最終総点検・完成化（敵対的検証による堅牢化）

- 日付: 2026-08-12
- 状態: 採用

### 背景
- T-001/T-002完了後、「実際に日常使用できる完成版として総点検し、問題があれば根本修正する」という最終仕上げタスク（T-003）を実施した。Managerの事前調査で、実際にDiscord通話中に困る可能性のある具体的な問題が4件（のちに高DPI対応を加えて5件）特定されていた。
- 本セッションもLinuxのクラウドコンテナであり、D-001記載の制約（Windows実機・Discordクライアント・実オーディオデバイスなし）は変わらない。本エントリの実測値・検証結果はすべてこのLinux環境でのpytest自動テスト・合成信号によるDSP検証・xvfb環境でのGUIロジック検証・長時間ループの実測によるものであり、「Windows実機で確認した」「Discordで確認した」という主張は一切含まない。

### 決定（確定済み5件のバグ修正）

1. **`config.py`の`AppConfig.save()`を非アトミックからアトミックな書き込みへ変更**: `open(path, "w")`直書きを廃止し、同一ディレクトリ内に`tempfile.mkstemp()`で一時ファイルを作成→`json.dump()`→`os.replace()`でアトミックに置き換える方式にした。書き込み中に例外が起きた場合は一時ファイルを削除して再送出する。`tests/test_config.py::TestSaveIsAtomic::test_failed_write_does_not_corrupt_existing_config`で、`json.dump`を失敗させても既存の`config.json`が壊れず、一時ファイルも残らないことを実測確認した。
2. **`AppConfig.load()`が非dict型のJSON（`null`/配列/文字列/数値等）を想定していなかった問題を修正**: `json.load()`成功後に`isinstance(data, dict)`を追加し、非dictならデフォルト設定へフォールバックするようにした。さらに、各フィールドについて型・値の妥当性を検証する`_FIELD_VALIDATORS`（`_is_valid_optional_str`/`_is_valid_preset`/`_is_valid_bool`/`_is_valid_advanced_overrides`）を追加し、型が違う値（例: `processing_enabled`が文字列）や存在しないプリセット名、非数値の`advanced_overrides`値が指定された場合も、そのフィールドだけデフォルト値へフォールバックするようにした（config.jsonは信頼境界の外にある入力のため、AGENTS.md設計原則8に従い検証を省略しなかった）。`tests/test_config.py::TestLoadHandlesCorruptedConfig`（9ケース: 構文エラー/非dict4種/フィールド欠落/型違い/不明プリセット/型違いadvanced_overrides/非数値override値/未知フィールド）ですべてクラッシュせずデフォルト相当へフォールバックすることを確認した。
3. **`AudioEngine._callback`内の`self.chain.process(frame)`を例外から保護**: try/exceptで囲み、失敗時は入力フレームをそのまま出力へ流すバイパスにフォールバックするようにした。あわせて`AudioEngine.__init__`に`on_error`コールバック（`ErrorCallback = Callable[[str], None]`）を追加し、エラーメッセージをコールバックスレッドから呼び出し元へ伝播できるようにした。`tests/test_engine.py`で、`_callback`を実際のPortAudioストリームを介さず直接呼び出し、(a)例外発生時に出力が未加工の入力にフォールバックすること、(b)`on_error`が呼ばれること、(c)1フレームだけ失敗しても次のフレームからは正常に処理が復帰すること、(d)`on_error`未指定でも例外を送出しないこと、(e)通常経路・bypassモードに回帰がないこと、を確認した。
4. **エラー表示の責務分離**: `app.py`にテスト再生ボタン専用の`test_status_var`とは別に、ストリーム全体の状態・エラー専用の`engine_status_var`（初期値「停止中」）を追加した。`_start_engine`のストリーム開始失敗、`AudioEngine.on_error`経由のコールバック内エラー、`_stop_engine`時の状態遷移をすべて`engine_status_var`へ反映し、`test_status_var`には触れないようにした。`tests/test_app_gui.py::TestEngineStatusIsSeparateFromTestStatus`で、エラー発生時に`engine_status_var`のみが変化し`test_status_var`は変化しないことをxvfb環境で実機検証した。
5. **Windows高DPI対応の追加**: `app.py`に`_set_windows_dpi_awareness()`を追加し、`main()`の冒頭（`App()`構築前）で呼び出すようにした。`platform.system() != "Windows"`の時点で即座にreturnするため、Linux上のテスト実行は一切影響を受けない。Windows上では`ctypes.windll.shcore.SetProcessDpiAwareness(1)`（PROCESS_SYSTEM_DPI_AWARE）を試み、失敗しても（古いWindows・権限問題等）例外を握りつぶしてアプリ起動を継続する。`tests/test_app_gui.py::TestWindowsDpiAwareness`で、この関数がLinux上で例外を出さないこと（壊れたら失敗する最小限の確認）を確認した。実際の高DPI表示崩れの有無はこの環境では検証できないため、WINDOWS_VERIFICATION_CHECKLIST.mdに確認項目を追加した（決定内の「追加確認項目」参照）。

### 決定（追加確認項目）

- **RNNoiseライブラリが見つからない場合のエラー導線**: `App.__init__`で`VoiceChain(...)`の生成をtry/exceptで囲み、失敗時はウィンドウを`destroy()`した上で分かりやすいメッセージの`RuntimeError`を送出するようにした。`main()`側は`App()`構築を丸ごとtry/exceptし、失敗時は`tkinter.messagebox.showerror`で日本語のエラーダイアログを表示してから正常にreturnする（意味不明なスタックトレースで落ちない）。`tests/test_app_gui.py::TestVoiceChainInitFailureIsReportedClearly`で、RNNoiseライブラリ不在を模したケースが分かりやすい`RuntimeError`として起動シーケンスに伝播することを確認した。また本セッションのLinux環境自体、`soloclarity/dsp/vendor/`にRNNoise共有ライブラリが配置されていない（Windows配布時のみbuild_windows.batが配置する）ため、無加工で`App()`を構築するとこの経路が実際に発火することを手動検証でも確認した（意図的な開発環境の欠落であり、バグではない）。
- **デバイス0件のハンドリング**: `tests/test_devices.py`で`sd.query_devices`が空リストを返すケースをモックし、`list_devices`/`list_input_devices`/`list_output_devices`/`guess_solocast_device`/`guess_cable_output_device`がクラッシュせず空/Noneを返すことを確認した。あわせて`tests/test_app_gui.py::TestZeroDevices`で、`device_lib.list_devices`をモンキーパッチしてデバイス0件の状態から`App()`を構築してもクラッシュせず、デバイス選択欄が空のままになることをxvfb環境で確認した。なお、この開発環境自体`sd.query_devices()`が実際に0件を返す（コンテナにオーディオハードウェアがない）ため、`_start_engine`が`PortAudioError: Error querying device -1`で失敗する経路を実機的にも確認できた（修正4のエラー表示先が正しく機能することの確認を兼ねる）。
- **長時間動作の安定性（ソークテスト）**: `app/tests/soak_chain.py`を追加した。音声らしいsin波+ノイズ混合区間・無音区間・ノイズのみ区間を3秒周期で切り替える合成信号を10万フレーム（1000秒相当）処理し、10,000フレームごとにRSS（`resource.getrusage(...).ru_maxrss`、POSIX限定でWindowsでは自動skip）を記録、先頭1万フレームと末尾1万フレームの平均処理時間を比較した。**実測結果（このLinux環境、`python -m tests.soak_chain`）**: RSSはウォームアップ後（10%地点）54,784KBから最終55,168KBまで**成長率1.007倍**（閾値1.3倍を大きく下回る）、フレーム処理時間は先頭1万フレーム平均0.6945ms、末尾1万フレーム平均0.6958msで**比率1.002倍**（閾値1.5倍を大きく下回る）。無制限なメモリ増加・処理時間劣化は確認されなかった。実行時間は約71秒。
- **プリセット・詳細設定の高頻度切り替え**: `tests/test_chain.py::TestHighFrequencyParameterSwitching`で、`set_preset`/`set_clarity`/`set_noise`/`set_compressor`/`set_agc`をランダムに3,000回呼び出すループを追加し、例外が出ないこと、および`chain._rnnoise_state`/`chain._rnnoise_library`のオブジェクトIDが呼び出し前後で完全に同一である（再作成されていない）ことを確認した。コードレビューでも、`VoiceChain.set_preset`等の実装（`app/soloclarity/dsp/chain.py`）が`_rnnoise_state`/`_rnnoise_library`に一切触れていないこと（`__init__`でのみ生成、`close()`でのみ破棄）を確認済み。
- **音質: ノイズゲートの語尾・小さい声の欠落**: `tests/test_gate.py::TestGateAgainstNoiseStagePresets`で、実際の3段階ノイズ除去プリセット（`presets.NOISE_STAGES`）それぞれの`gate_threshold`/`gate_release_ms`を使い、(a)発話確率が閾値をわずかに超える程度の小さい声を想定した信号が5フレーム（50ms）以内に十分開くこと（頭の欠落がないこと）、(b)発話確率が閾値を割った直後の1フレームで無音まで落ちない（release_msに応じて緩やかに減衰する、語尾が唐突に切れない）ことを、弱/標準/強すべてで確認した。
- **音質: コンプレッサーの急激な音量変化**: `tests/test_chain.py::TestCompressorSmoothness`で、小（peak -26dBFS相当）→大（peak -6dBFS相当）→小の音量ジャンプを含む信号を`discord_call`プリセットのコンプレッサー単体（`_build_compressor_board`）に通し、フレーム間（10ms）のRMS dB変化量の最大値が、無加工の生信号におけるフレーム間dB変化量の最大値を上回らないことを確認した（コンプレッサーが変化をより急激にしていないことの直接的な検証）。
- **音質: リミッターの発動頻度**: `tests/test_chain.py::TestLimiterEngagementFrequency`で、ceiling（-1.0dBFS）より十分低いpeak -10dBFS相当の通常音量の信号をリミッター単体（`_build_limiter_board`）に通し、出力RMSが入力RMSの98%を上回る（ほぼ減衰なし=gain reductionがほぼ0）ことを確認した。
- **設計の整理**: `app/soloclarity/`を通読し、未使用コードを2件発見・削除した。(1) `app/soloclarity/gui/app.py`の`METER_UPDATE_INTERVAL_MS`定数（定義のみでどこからも参照されていなかった。メーター更新は`AudioEngine.on_meter_update`経由でオーディオコールバックが直接駆動しており、ポーリング用のこの定数は使われていなかった）。(2) `app/soloclarity/dsp/gate.py`の`SpeechProbabilityGate.reset()`メソッド（`VoiceChain.set_noise_stage`はゲートインスタンスを毎回新規生成しており、既存インスタンスをリセットする経路がどこにも存在しなかった）。それ以外の関数・メソッドはすべて呼び出し元が存在することを`grep`で確認した（判定ラダー1: YAGNI）。
- **依存関係の再確認**: `requirements.txt`（sounddevice/pedalboard/numpy）、`requirements-dev.txt`（pytest/pyrnnoise追加）は実際のimport文（`grep -rhoE "^import ...|^from ... import" soloclarity`）と一致しており、未使用の依存は無かった。新規パッケージは追加していない。
- **バージョン表示**: `app/soloclarity/__init__.py`の`__version__`をウィンドウタイトルへ表示するようにした（`"SoloClarity" → f"SoloClarity v{__version__}"`）。バージョン番号自体（`0.1.0`）は変更していない。
- **WINDOWS_VERIFICATION_CHECKLIST.mdの拡充**: この環境では実施不可能な確認観点（高DPI環境での表示崩れ、デバイスの抜き差し、Discordとの起動順序、スリープ・スタンバイからの復帰、Windows起動直後の動作、長期間の実運用）を新たに10〜15節として追加した。既存の1〜9節（ビルド・デバイス認識・仮想マイク出力・Discordでの聞き取りやすさ・テストボタン・CPU/メモリ実測・遅延実測・設定の保存復元・アンインストール）と重複する項目（CPU/メモリのタスクマネージャ確認、遅延の体感、Discordからの認識）は追加していない。

### 理由
- 判定ラダー（AGENTS.md）の「バグは根本原因を直す」に従い、いずれの修正も症状（config.jsonが壊れる、音が止まる、エラーメッセージがどこに出るか分からない）ではなく構造上の原因（非アトミック書き込み、無防備な型仮定、例外の握りつぶし不在、責務混在、DPI非対応）を直した。
- 追加確認項目は、Issueが求める「実際に日常使用できる完成版」という完了基準に対し、この環境で実際に実行・実測できる範囲（pytest自動テスト・合成信号によるDSP検証・xvfbでのGUIロジック検証・長時間ループの実測）で敵対的検証（REVIEW.md）の観点を先取りして潰したもの。Windows実機・Discord経由の主観評価はD-001の制約により引き続きユーザーの最終確認が必要。

### 影響
- `pytest tests/`（このLinux環境）: **66 passed**（既存26件 + 新規40件、`tests/bench_chain.py`・`tests/soak_chain.py`は従来どおりファイル名が`test_*.py`パターンに一致しないため`pytest tests/`の既定収集対象外。個別に`pytest tests/bench_chain.py`/`pytest tests/soak_chain.py`または`python -m tests.bench_chain`/`python -m tests.soak_chain`で実行する既存の運用を踏襲）。
- `pyflakes soloclarity tests`: 警告0件。
- `python -m tests.bench_chain`（1000フレーム、この修正後の再測定）: 平均0.6991ms/フレーム（10ms予算の7.0%）。
- 新規テストファイル: `app/tests/test_config.py`（12件）、`app/tests/test_engine.py`（5件）、`app/tests/test_devices.py`（2件）、`app/tests/test_app_gui.py`（7件、xvfb環境）、`app/tests/soak_chain.py`（1件、個別実行）。既存ファイルへの追加: `test_chain.py`（+3件）、`test_gate.py`（+6件）。
- `app/tests/conftest.py`に`gui_display`フィクスチャを追加した。`DISPLAY`が未設定でもLinux上に`Xvfb`があれば自動的に一時ディスプレイを起動し、無ければGUIテストをスキップする（新規pip依存を追加せず、既存のシステムバイナリのみで完結させる設計）。
- 今後、config.jsonのフィールドを追加する場合は`_FIELD_VALIDATORS`にも対応するバリデータを追加すること。AudioEngineに新しいコールバックを追加する場合も、GUI側のスレッド安全性（`self.after(0, ...)`経由でのメインスレッド復帰）を踏襲すること。

---

## D-006: T-003 Reviewer指摘対応（High×2, Medium×1, Low×2, すべてCONFIRMED）

- 日付: 2026-08-12
- 状態: 採用

### 背景
- D-005の実装（コミット913189c）に対し、別セッションのReviewerが独立に敵対的検証を行い、5件の指摘（High×2, Medium×1, Low×2）を返した。いずれも実際にコード・挙動を確認した上でのCONFIRMED判定であり、Managerの指示に従いすべて対応した。

### 決定

1. **advanced_overridesへのNaN混入によるアプリ恒久起動不能（High, CONFIRMED）**: `config.py`の`_is_valid_advanced_override_value`（旧`_is_valid_advanced_overrides`）に`math.isfinite(value)`チェックを追加し、NaN/Infinity/-Infinityをすべて拒否するようにした。JSONの`NaN`/`Infinity`/`-Infinity`トークンはPythonの`json.load`のデフォルト設定でそのまま`float('nan')`等として読み戻され、`tk.Scale.set(nan)`が`TclError`を送出して`App.__init__`から`main()`の`except Exception`まで伝播していた（起動失敗はするが、config.json側のNaN値を修復する処理が無いため次回起動時も確実に再現していた）。あわせて`AppConfig.save()`側にも`json.dump(..., allow_nan=False)`を追加し、書き込み・読み込み両方の信頼境界で有限性を防御するようにした（万一有限でない値がセルフに紛れ込んでも、書き込み時点で早期に`ValueError`となり、壊れた`config.json`が生成されることはない）。`tests/test_config.py::TestAdvancedOverridesRejectNonFiniteValues`（NaN/Infinity/-Infinityそれぞれの読み込み側フォールバック、save側のValueError）で確認した。
2. **`AudioEngine.start()`でのPa_StartStream失敗時のストリームハンドルリーク（High, CONFIRMED）**: `start()`を、`sd.Stream(...)`(Pa_OpenStream相当)をローカル変数`stream`に受け、`.start()`(Pa_StartStream相当)をtry/exceptで囲み、失敗時は`stream.close()`してから例外を再送出し、成功時のみ`self._stream = stream`とする実装に変更した。`sounddevice.Stream`に`__del__`は無くGCでも解放されないため、修正前は開いたストリームがリークし、`self._stream`への参照も残らないため追跡・再利用の手段が完全に失われていた。Issueが名指しした「エンジンの高頻度start/stop」で他アプリとのデバイス排他競合等によりPa_StartStreamのみが繰り返し失敗するケースを想定し、`tests/test_engine.py::TestStartClosesStreamOnPaStartStreamFailure`で、単発の失敗時に`close()`が呼ばれ`self._stream`が`None`のままであること、成功時は`close()`が呼ばれないこと、50回連続で失敗させても毎回`close()`されリークが蓄積しないことを確認した（`sd.Stream`をフェイクに差し替えて検証）。
3. **テストボタンworker threadのTkinter操作がself.after()経由でない（Medium, CONFIRMED/PLAUSIBLE）**: `_on_test_clicked`のworker関数内`self.test_status_var.set(...)`/`self.test_button.configure(...)`をすべて`self.after(0, lambda: ...)`経由に変更し、`_on_meter_update`/`_on_engine_error`と同じスレッドセーフなパターンに統一した。あわせて`_on_close()`で、テストボタンのworker threadが実行中の場合は`self.chain.close()`する前に完了を待つようにし、`chain.process()`(worker内)と`chain.close()`(メインスレッド)が競合する構造的リスクを避けた。
   - **実装上の重要な追加検証**: 当初`self._test_thread.join(timeout=...)`という単純なブロッキング待機で実装したところ、Reviewerとの往復（コンテキスト切れによる引き継ぎを含む）の中で、xvfb実機検証により**単純な`join()`では正しく機能しないことが判明した**。Tkinterの`self.after(0, ...)`をバックグラウンドスレッドから呼ぶには、メインスレッドが実際に`mainloop()`でTclのイベントループを処理している必要があり、メインスレッドが素の`Thread.join()`でブロックしている間はworker側の`after()`呼び出しがメインスレッドの応答を待って停止する（実測: `join(timeout=2)`のケースで、workerの`after()`呼び出しがまさに2秒間ブロックし、joinがタイムアウトして初めて解放された）。この状態が続くと`_on_close()`が無意味に最大タイムアウト分(11秒)ブロックし、その後`self.destroy()`で対象のTclインタプリタが破棄されるとworker側のブロックが恒久的に解消しない可能性があった。
   - **最終対応**: `_on_close()`のworker待機を、単純な`join()`ではなく`self.update()`を挟みながらポーリングするループ（`while thread.is_alive() and time.monotonic() < deadline: self.update(); time.sleep(0.01)`）に変更した。`self.update()`がTclのイベントループを処理することでworker側の`after()`呼び出しが解放され、正しく完了する。実機検証で、この修正により`_on_close()`が実際のworker処理時間（例: 0.2秒程度のダミー再生)とほぼ同じ時間で返ることを確認した(修正前の単純joinでは最大タイムアウトの11秒までブロックしていた)。
   - **テスト設計上の教訓**: 上記と同じ理由で、`tests/test_app_gui.py`のテストコード自体も`app.mainloop()`を実際に走らせる必要がある(単に`app.update()`をポーリングするだけのテストでは、workerスレッド側の最初の`self.after(0, ...)`呼び出し自体が`RuntimeError: main thread is not in main loop`になる)。最終的に、`app.mainloop()`をテストのメインスレッドで実際に走らせ、workerの完了を監視する別スレッド(watcher)が`app.after(0, app.quit)`でmainloopを止める構成にした(安全弁として`app.after(タイムアウトms, app.quit)`も設定)。`tests/test_app_gui.py::TestTestButtonThreadSafety`の2ケース(通常完了、テストボタン直後にウィンドウを閉じるケース)で確認した。
4. **advanced_overridesのバリデーションがall-or-nothing（Low, CONFIRMED）**: `config.py`の`AppConfig.load()`で、`advanced_overrides`のみ`_FIELD_VALIDATORS`の対象外とし、`_sanitize_advanced_overrides()`でキー単位に検証するよう再設計した。1項目でも不正なら辞書全体を破棄していた挙動を、不正なキーだけを取り除き正当な値は保持する挙動に変更した。`tests/test_config.py::TestAdvancedOverridesPartialValidity`で、1件の不正値が他の正当な設定を巻き込んで破棄しないこと、複数の不正値・正常値が混在する場合も個別に判定されることを確認した。
5. **極端値への安全性がTkinterのclamp挙動という暗黙の実装詳細にのみ依存（Low, CONFIRMED）**: `app.py`に`_ADVANCED_SLIDER_RANGES`(`ADVANCED_SLIDER_SPECS`のmin/maxから構築)と`_clamp()`ヘルパーを追加し、`_apply_advanced_overrides()`でconfig由来の値を`tk.Scale.set()`へ渡す前に明示的にクランプするようにした。`tests/test_app_gui.py::TestExtremeAdvancedOverrideValuesAreClamped`で、`1e9`・`-1e9`・`1e12`等の極端な値を注入してもスライダー値・`VoiceChain`側の実パラメータ(`chain.agc.target_linear`等)が仕様範囲内かつ有限であることを直接検証した。

### 理由
- いずれもAGENTS.md「バグは根本原因を直す」に従い、信頼境界（config.json、PortAudioのネイティブAPI境界、Tkinterのスレッド境界）での検証・後始末の欠落という構造的原因を直した。
- 指摘3の対応過程で発覚した「単純な`Thread.join()`はTkinterのバックグラウンドスレッド`after()`呼び出しと相互にブロックし得る」という事実は、Reviewer指摘自体が言及していなかった追加のリスクだったが、実装時の実機検証(xvfb)で発見したため、症状を隠す表面的な修正（例えばjoinのタイムアウトを単に伸ばす等）ではなく、根本原因（Tclのメインループ要求とブロッキング待機の非両立）に対処する形にした。

### 影響
- `pytest tests/`（このLinux環境）: **81 passed, 0 failed**(D-005時点の66件 + 今回の新規15件。内訳: `test_config.py` 17→25件(+8、指摘1・4対応)、`test_engine.py` 5→8件(+3、指摘2対応)、`test_app_gui.py` 7→11件(+4、指摘3・5対応))。`tests/bench_chain.py`・`tests/soak_chain.py`は引き続き個別実行(このLinux環境で両方とも再実行し、リグレッションがないことを確認: `bench_chain`平均約0.7ms/フレーム、`soak_chain`はRSS成長率・処理時間比率とも安定した範囲内)。
- `pyflakes soloclarity tests`: 警告0件。
- `app/soloclarity/config.py`・`app/soloclarity/audio/engine.py`・`app/soloclarity/gui/app.py`を変更。DSPロジック本体(`app/soloclarity/dsp/`配下)には一切手を入れていない。
- 今後、`self.after(0, ...)`をバックグラウンドスレッドから呼ぶコードを追加する場合、そのスレッドの完了を待つ側(メインスレッド)は単純な`Thread.join()`ではなく、`self.update()`を挟むポーリングパターンを使うこと(本エントリの指摘3対応・`_on_close()`実装を参照)。同様に、この種のスレッド間協調をxvfb環境でテストする場合は、`app.mainloop()`を実際に走らせるテスト構成(`tests/test_app_gui.py::TestTestButtonThreadSafety`参照)が必要であり、`app.update()`のポーリングだけでは代替できない。

---

## D-007: T-003 Reviewer再指摘対応（`_on_close()`の再入によるTclError, Medium, CONFIRMED）

- 日付: 2026-08-12
- 状態: 採用

### 背景
- D-006の修正（コミットedd73b2）をReviewerが再検証し、指摘1・2・4・5は解消をCONFIRMEDした。一方、指摘3の対応そのもの（`_on_close()`を`self.update()`ポーリング待機に変更したこと）が新たな問題を持ち込んでいることが判明した。
- `_on_close()`はworker thread完了待ちの間、最大`TEST_THREAD_JOIN_TIMEOUT_SECONDS`(11秒)`self.update()`をポーリングし続けるが、この待機ループ中はTclのイベントループが実際に回っている。そのため、ユーザーが待機中にもう一度閉じる操作(ウィンドウのXボタン等)をすると`_on_close()`が再入(nested)呼び出しされ得る。Reviewerは`app.after()`で`_on_close`を2回ディスパッチする形で実際に再現し、内側の呼び出しが先に`self.destroy()`まで完了した後、外側の呼び出しが自分の`self.destroy()`に到達した時点で`_tkinter.TclError: can't invoke "destroy" command: application has been destroyed`が発生することを確認した(mainloop()自体はクラッシュせず正常終了し、`_stop_engine()`/`chain.close()`は多重呼び出しに対して既に安全だったため実害は限定的だが、未処理例外のログが出る)。

### 決定
- `App.__init__`に`self._closing = False`を追加し、`_on_close()`冒頭で`if self._closing: return`(多重実行防止フラグ)を追加した。フラグを立てた後に`_save_config()`・worker待機ループ・`_stop_engine()`・`chain.close()`・`self.destroy()`を実行する構成にすることで、待機ループの`self.update()`経由で`_on_close()`が再入されても、2回目以降の呼び出しは即座にreturnし、`self.destroy()`が二重に呼ばれることがなくなる。
- `tests/test_app_gui.py::TestTestButtonThreadSafety::test_reentrant_close_while_waiting_for_worker_does_not_raise`を追加した。Reviewerの再現方法(`app.after()`で`_on_close`を2回ディスパッチする)を踏襲し、`app.mainloop()`を実際に走らせながらworker実行中(0.3秒のダミー再生)に`_on_close()`を`app.after(0, ...)`と`app.after(20, ...)`の2回スケジュールし、いずれの呼び出しも例外を出さないことを確認する。
- **検証**: このテストが実際に指摘内容を再現・検出できることを、ガード(`if self._closing: return`)を一時的に取り除いたコードに対して同テストを実行することで確認した。ガード無しでは`errors == [TclError('can\'t invoke "destroy" command: application has been destroyed')]`となりテストが失敗し、ガードを戻すとpassすることを確認した(テストの実効性そのものを検証する二重チェック)。

### 理由
- AGENTS.md「バグは根本原因を直す」に従い、`_on_close()`という単一のエントリポイントに再入防止フラグを置くことで、Xボタン連打・ウィンドウマネージャからの複数回のクローズイベント等、どの経路から再度`_on_close()`が呼ばれても一箇所で確実に防げるようにした(個々の呼び出し元にガードを分散させない)。
- D-006の対応(`self.update()`ポーリング)自体は、Tkinterのバックグラウンドスレッド`after()`呼び出しの要求(メインスレッドが実際にイベントループを処理していること)を満たすために必要な変更であり、撤回はしない。今回はその変更が新たに開けた「待機ループ中はイベントループが回っている」という窓に対して、再入防止フラグで閉じる形にした。

### 影響
- `pytest tests/`(このLinux環境): **82 passed, 0 failed**(D-006時点の81件 + 今回の新規1件、`tests/test_app_gui.py`)。5回連続実行してもフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- `app/soloclarity/gui/app.py`のみ変更(`App.__init__`への1行追加、`_on_close()`冒頭への6行のガード追加)。DSPロジック・config.py・engine.pyには手を入れていない。
- 今後、`_on_close()`のように「待機中に`self.update()`等でイベントループを回す」実装を追加する場合、同じエントリポイントが待機中に再入され得ることを前提に、多重実行防止フラグを併せて検討すること。

---

## D-008: T-003完了に伴うversion 1.0.0への確定とビルドArtifactの命名強化

- 日付: 2026-08-12
- 状態: 採用

### 背景
- D-005〜D-007の3巡にわたる敵対的検証（合計6件の指摘、すべてCONFIRMEDで解消）を経て、Reviewerの最終所見は「このまま配布できる」となった。Issueの完成条件は「完成した最新版をビルドし、実際に利用できる配布ファイルを生成する」「古いビルドと混同しないようバージョン番号またはビルド日時を明確にする」ことを求めている。
- `app/soloclarity/__init__.py`の`__version__`はD-001実装時点から`"0.1.0"`のままであり、GUIのウィンドウタイトルに表示されてはいた（D-005）が、値自体は開発中のプレースホルダのままだった。GitHub Actionsのビルド成果物（Artifact）名も`SoloClarity-windows-exe`固定で、過去のビルドと見分けがつかなかった。

### 決定
- `app/soloclarity/__init__.py`の`__version__`を`"0.1.0"`から`"1.0.0"`へ変更した。これは今回の総点検（T-003）を経て「配布可能」と判断された最初のバージョンであることを表す。
- `.github/workflows/build-windows.yml`に「Read app version and build date」ステップを追加し、`soloclarity.__version__`とビルド日(UTC、`YYYYMMDD`)を取得。`actions/upload-artifact`のArtifact名を`SoloClarity-v{version}-{build_date}`（例: `SoloClarity-v1.0.0-20260812`）に変更し、過去のビルドと混同しないようにした。PyInstaller自体が生成するexeファイル名(`SoloClarity.exe`、`build_windows.bat`の`--name`指定)は変更していない（Artifact名で十分に区別可能であり、既に一度CI失敗・修正を経て安定しているビルドスクリプトへの変更を避けるため）。

### 理由
- バージョン番号は、開発中を示す`0.x`系から、最初の配布可能版であることを示す`1.0.0`への変更が、Semantic Versioningの慣例（`1.0.0`=最初の安定版）とも一致する。
- Artifact名にバージョンとビルド日を含めることで、ユーザーがGitHub ActionsのArtifact一覧から最新版を一目で識別できるようになる。exeファイル名自体は変更せず、Artifactというダウンロード単位の命名だけで要件を満たすことで、変更範囲を最小限に抑えた（判定ラダー: 最小実装）。

### 影響
- 今後`app/`に変更を加えて新しいバージョンをリリースする場合は、`__version__`の更新を忘れないこと（GUIタイトル・Artifact名の両方に反映される）。
- 本コミットのpushにより、GitHub Actionsで`v1.0.0-{ビルド日}`のArtifactが生成される。これが本Issue（総点検・完成化）の最終成果物となる。

### 追記（2026-08-12・PR #4のCI実行での修正）
- PR #4のCI（windows-latest、run 31643953024）で、`tests/test_app_gui.py::TestWindowsDpiAwareness::test_no_op_and_does_not_raise_on_linux`が`AssertionError: assert 'Windows' != 'Windows'`で失敗した。このテストは「`_set_windows_dpi_awareness()`がLinux上でno-opであること」を検証する意図で、テスト自体の前提確認として`assert platform.system() != "Windows"`を書いていたが、T-003でCIをwindows-latestでも実行するようになった結果、Windows上でこのテスト自体が実行され、前提確認が自己矛盾で失敗する状態になっていた（D-005実装時点ではこのテストはこのLinux開発環境でしか実行されていなかったため、Windows上での実行は今回のCI実行が初めてだった）。
- テストをプラットフォームに依存しない形（`_set_windows_dpi_awareness()`がどのプラットフォームでも例外を送出しないことのみを確認）に修正した。Linux上では既存どおりno-opパス、Windows上では実際のDPI awareness試行パス（失敗しても例外を握りつぶす、D-005参照）をそれぞれ検証する形になり、むしろWindows実機での初めての実行検証という副次的な価値も得られた。
- このLinux環境で`pytest tests/test_app_gui.py`を再実行し12件すべてpassすることを確認済み（Windows上での再実行結果はCIの次回実行で確認する）。

---

## D-009: SoloCast→CABLE Input間のストリーム開始エラー(PaErrorCode -9993)の原因特定

- 日付: 2026-08-12
- 状態: 採用

### 背景
- ユーザーがv1.0.0のexeをWindows実機で実際に起動し、マイク(HyperX SoloCast)と出力先(CABLE Input, VB-Audio Virtual Cable)を選んで処理を開始したところ、「ストリーム開始エラー: Error opening Stream: Illegal combination of I/O devices [PaErrorCode -9993]」が発生し、コア機能(SoloCast入力→処理→仮想マイク出力)が動作しないことが判明した。これはこのLinux開発環境では実オーディオデバイスがないため一度も検出できなかった不具合であり、D-001に記載した既知の制約（Windows実機での動作確認が必要）がまさに顕在化した事例である。
- PaErrorCode -9993はPortAudioの`paBadIODeviceCombination`に対応する。`app/soloclarity/audio/engine.py`の`AudioEngine.start()`は、`sd.Stream(device=(input_device, output_device), channels=1, callback=self._callback)`という単一の双方向(full-duplex)ストリームで、入力(SoloCast、実ハードウェア)と出力(CABLE Input、VB-Audio製の仮想デバイス)という**別々の物理・仮想デバイス**を結合しようとしていた。WASAPIでは、異なるデバイス同士(特に別クロックドメインを持つデバイス)を1本のフルデュプレックスストリームに結合することは一般的にサポートされておらず、この組み合わせで`paBadIODeviceCombination`が返るのはPortAudio/sounddeviceのよく知られた制約である。

### 決定
- `AudioEngine`の内部実装を、単一の`sd.Stream`から、独立した`sd.InputStream`(SoloCast側)と`sd.OutputStream`(CABLE Input側)の2本構成に変更する。両ストリームはそれぞれ別デバイス・別クロックで動作するため、小さな有界のリングバッファ(ジッタバッファ)で橋渡しする。
  - 入力側コールバック: フレームを読み取り、入力メーターを更新し、`chain.process()`(または`bypass`)を実行し、処理後フレームをリングバッファへpushする。バッファが満杯(出力側の消費が追いついていない)の場合は最も古いフレームを破棄して詰まりを回避する。
  - 出力側コールバック: リングバッファから次のフレームをpopしてそのまま出力する。バッファが空(アンダーラン、起動直後やクロックドリフトで一時的に発生し得る)の場合は無音を出力し、ノイズや未初期化メモリの出力を避ける。
  - 既存の例外保護(`chain.process()`のtry/except→bypass+`on_error`)・スレッドセーフなエラー伝達の契約は維持する。
  - `start()`/`stop()`は両ストリームをセットで管理し、一方が開けても他方が失敗した場合は、開いた方を`close()`してから例外を再送出する(D-006で確立した単一ストリームのリーク防止パターンを2ストリームへ拡張する)。

### 理由（検討した代替案）
- **単一`sd.Stream`のまま設定を調整する案(例: WASAPI排他モード指定等)は不採用**: 異なる物理・仮想デバイスを1本のフルデュプレックスストリームで結合すること自体がPortAudio/WASAPIの一般的な制約であり、設定の調整では根本的に解決しない可能性が高い。実際に多くのsounddeviceベースの「仮想オーディオケーブル」アプリケーションが、入出力デバイスが異なる場合は2本の独立ストリーム+バッファという構成を採用しており、確立された標準的な解決策である。
- **バッファをブロッキングキュー(`queue.Queue.put`のブロッキング)にする案は不採用**: オーディオコールバックスレッド内でブロッキング待機すると、PortAudioのリアルタイム制約(コールバックは短時間で返る必要がある)に違反し、別種のグリッチ・アンダーラン・場合によってはストリーム自体のエラーを招く。非ブロッキングかつ満杯時は最も古いフレームを破棄する設計とする。

### 影響
- `app/soloclarity/audio/engine.py`の実装が変更される。既存の`tests/test_engine.py`(単一`sd.Stream`のフェイクを前提にしたテスト)は新しいアーキテクチャに合わせて書き直しが必要。
- このLinux環境では実デバイスでの動作確認はできないため、新しいリングバッファのロジック(順序保持、満杯時の破棄、空時の無音出力)は合成コールバック呼び出しによるユニットテストで検証する。実際にWindows実機でSoloCast→CABLE Inputの組み合わせが起動できるかは、ユーザーによる再検証が必要。
- 本Issueは実機フィードバックによって発見された初めての具体的な不具合であり、Windows実機検証の重要性を裏付けている。今後同種の「異なる入出力デバイスの組み合わせ」に起因する問題がないか、`app/WINDOWS_VERIFICATION_CHECKLIST.md`に確認項目として明記する。

### 追記（2026-08-12・実装時に確定した詳細）

- **ジッタバッファサイズ**: `app/soloclarity/audio/engine.py`の`JITTER_BUFFER_FRAMES = 4`(1フレーム=10ms・48kHz・480サンプルのため40ms相当)。決定時に挙げた目安(2〜6フレーム=20〜60ms)の中間値を採用した。バッファ実装は`collections.deque(maxlen=JITTER_BUFFER_FRAMES)`を薄くラップした内部クラス`_FrameRingBuffer`(同ファイル内、新規ファイルは作らない)。`push()`は`deque`の`maxlen`超過時の自動先頭破棄をそのまま利用し、`pop()`は空なら`None`を返す。両方とも`threading.Lock`で保護しているが、クリティカルセクションは`append`/`popleft`のO(1)操作のみであり、PortAudioコールバック内でのブロッキング待機(バッファの空き/データ待ち)は一切行わない。
- **メーター計測タイミング**: 入力メーター(`in_rms`/`in_peak`)は入力側コールバック(`_input_callback`)で処理直後に測定し、出力メーター(`out_rms`/`out_peak`)は出力側コールバック(`_output_callback`)で実際に書き出す値(アンダーラン時の無音を含む)を測定する設計にした。入力側で両方を測ると、ジッタバッファの空(アンダーラン)でフレームが実際には出力されなかった場合でも「処理はできていた」ことになり、Discord側へ実際に届く音量と表示上のメーターが乖離するため、出力側の実測値を使う方を選んだ。入力メーターの値は`self._last_input_levels`(タプル)経由で出力側コールバックへ橋渡ししている(タプルの再代入はCPythonでは単一のSTORE_ATTR/LOAD_ATTRで完結し部分更新を観測しないため、追加のロックは設けていない)。`tests/test_engine.py::TestMeterMeasuresActualOutput`で、アンダーラン発生時に出力メーターがfloor_db(無音)を反映し、直前の入力レベルへ引きずられないことを確認した。
- **`start()`の順序**: 入力(`sd.InputStream`)を先に開いてから出力(`sd.OutputStream`)を開く順序にした。出力側の開始が失敗した場合は、開始済みの入力側を`stop()`→`close()`してから例外を再送出する。入力側の開始自体が失敗した場合は、出力側は一切生成されない(`_open_and_start`が入力側の失敗時点で例外を再送出するため)。`tests/test_engine.py::TestStartOpensBothStreamsAndCleansUpOnFailure`の3ケース(両方成功/入力失敗/出力失敗)で、開いた方だけが正しくclose/stopされ、失敗するたびに参照が蓄積しないこと(50回連続失敗のケース)を確認した。
- **`stop()`**: 入力・出力それぞれ独立した`if`ブロックでstop/close/Noneクリアを行う(D-006の単一ストリーム版と同じ「片方の失敗が他方の後始末をスキップさせない」構造を踏襲)。`tests/test_engine.py::TestStop`で両ストリームが確実にstop/closeされることを確認した。

### 追記（2026-08-13・Reviewer再指摘対応: `start()`/`stop()`の後始末が片方の失敗で連鎖的にスキップされる, Medium, CONFIRMED）

- **指摘内容**: 直上の追記時点の実装は、`start()`(出力側失敗時に入力側を後始末する経路)・`stop()`(入力/出力それぞれの後始末)のいずれも、各ストリームの`.stop()`/`.close()`自体をtry/exceptで囲んでいなかった。そのため(a)`stop()`側で入力ストリームの`.stop()`が例外を送出すると、`.close()`はおろか出力ストリーム側のstop/close/参照クリアも一切実行されない、(b)`start()`側で出力の`.start()`失敗をトリガに入力側を後始末する際、`input_stream.stop()`自体が例外送出すると`input_stream.close()`が呼ばれず、しかも最終的に伝播する例外が入力側の`Pa_StopStream failed`になり、ユーザーへ伝えるべき本来の原因(出力側の`Pa_StartStream failed`)が完全にマスクされる、という2つの実害をReviewerがフェイクストリームで再現した。この時点の本ドキュメントの記述(「片方の失敗が他方の後始末をスキップさせない」)と実装(例外の伝播を止めていない)も不一致だった。
- **対応**: `AudioEngine`に`_safe_close(stream)`(close()の例外をログに残すだけで伝播させない)・`_safe_stop_and_close(stream)`(stop()を試み、失敗してもログに残すだけで必ず`_safe_close`へ進む)を追加し、`_open_and_start`の失敗時close・`start()`の入力側後始末・`stop()`の入力/出力それぞれの後始末をすべてこの2ヘルパー経由に統一した。ログは標準の`logging`モジュール(`logging.getLogger(__name__)`、新規依存なし)で`logger.exception(...)`により残す。
  - `start()`: 出力側の`Pa_StartStream`失敗時、入力側の`stop()`/`close()`が失敗しても、伝播する例外は常に出力側の元の失敗理由のまま(`raise`で再送出、cleanup側の例外はログのみに留める)。
  - `stop()`: 入力・出力それぞれの参照を先にクリアしてから`_safe_stop_and_close`で後始末するため、一方の失敗が他方の後始末をスキップさせることはなく、`stop()`自体も例外を送出しない(呼び出し元`app.py`の`_stop_engine()`/`_on_close()`/`_on_device_changed()`は今回変更不要のまま、途中で止まらず`self.engine = None`まで到達できる)。
- **テスト**: `tests/test_engine.py`にReviewerの再現方法を踏襲した回帰テストを追加した。`TestStartOpensBothStreamsAndCleansUpOnFailure::test_input_cleanup_stop_failure_does_not_mask_original_output_failure`(出力失敗+入力stop()失敗の組み合わせで、入力の`close()`は実行され、伝播する例外は出力側の`Pa_StartStream failed`のままで`Pa_StopStream`という文字列を含まないこと)、`TestStop::test_input_stream_stop_failure_does_not_skip_output_stream_cleanup`(入力の`stop()`失敗時も出力側のstop/closeが実行され、`stop()`自体は例外を送出しないこと)。
- **影響**: `pytest tests/`(このLinux環境): **91 passed**(前回89件 + 今回の回帰テスト2件)。`pyflakes soloclarity tests`: 警告0件。`app/WINDOWS_VERIFICATION_CHECKLIST.md`の「7. 遅延の実測」に、ジッタバッファ(最大4フレーム=40ms)による追加遅延が生じ得る旨と、旧バージョンとの体感比較確認項目を追記した(Low, CONFIRMED)。

---

## D-010: プリセット・詳細設定UIの再調整（「小さくて低い声＋高品質ノイズ除去」）

- 日付: 2026-08-12
- 状態: 採用

### 背景
- Issue要件: 「小さくて低い声でも明瞭に聞こえること」「高品質なノイズ抑制」を最優先に、既定プリセット「Discord通話」を「小さくて低い声＋高品質ノイズ除去」へ置き換える。詳細設定UIの15スライダーを、専門用語ではなく「上げる/下げるとどうなるか」が分かる日本語表現へ全面的に書き換える。
- 現状のプリセット4種(`natural`/`low_voice`/`quiet_voice`/`discord_call`)を確認したところ、`低い声`(clarity=strong偏重)と`小さい声`(agc偏重)はそれぞれ別の軸を強調する設計であり、完全な重複はない。ただし両方の性質を併せ持つ「小さくて低い声」という組み合わせに最適化されたプリセットはこれまで存在しなかった。
- 現状のノイズ除去3段階(`weak`/`standard`/`strong`)は、RNNoiseの適用量(`wet_dry_mix`)とゲートの積極性(`gate_threshold`/`gate_release_ms`)が同じ方向に連動する設計になっており、「ノイズ除去の質(wet_dry_mix)を上げつつ、小さい声を誤って消さない(ゲートは緩やかに)」という今回の目標を、既存の3段階のいずれでも同時に満たせないことが判明した。特に`strong`(wet_dry_mix=1.00, gate_threshold=0.45, gate_release_ms=120ms)は、ノイズ除去量自体は最大だが、ゲート閾値が高く反応も速いため、小さい声・語尾を誤って削る可能性が高い。

### 決定

#### 1. プリセット構成
既存4プリセットの数は維持しつつ、内部キー`discord_call`を`quiet_low_voice`に、表示名を「Discord通話」から「小さくて低い声＋高品質ノイズ除去」に変更し、これを引き続き既定(`DEFAULT_PRESET`)とする。既存の`config.json`に保存された`preset: "discord_call"`は`_is_valid_preset`で不正値として扱われデフォルト(新キー)へ自動フォールバックするため、移行は自然に行われる(意図的な挙動)。

`quiet_low_voice`のパラメータ:
- `clarity = "strong"`(既存の強レベルをそのまま使用。120Hz付近を触らず厚みを残しつつ200/300Hzのこもりを削り、2〜4kHzで子音を持ち上げる設計は今回の目標と一致するため変更不要)
- `noise = "strong"`(ただし下記の通り`strong`段階自体の値を再調整する)
- `compressor = CompressorParams(threshold_db=-23.0, ratio=2.8, attack_ms=10.0, release_ms=200.0)`(`low_voice`と`quiet_voice`の中間、小さい声を早めに拾いつつ`quiet_voice`よりわずかに緩やかにして不自然な潰れを避ける)
- `agc = AgcParams(target_dbfs=-17.0, max_gain_db=12.0)`(target値は旧`discord_call`を踏襲、max_gainは`quiet_voice`と同じ12dBまで持ち上げ可能にする)

`natural`/`low_voice`/`quiet_voice`は既存のまま維持する(それぞれ「ほぼ無加工」「低い声のみに最適化(小さくない声向け)」「小さい声のみに最適化(低くない声向け)」という独立したユースケースを持ち、新プリセットとの完全な重複はないと判断)。

#### 2. ノイズ除去3段階(`NOISE_STAGES`)の再調整
RNNoise適用量(除去の質)とゲートの積極性(声を消さない)を分離する方向で、3段階すべてを見直す。

| 段階 | wet_dry_mix (旧→新) | gate_threshold (旧→新) | gate_release_ms (旧→新) |
|---|---|---|---|
| weak | 0.30→0.30(変更なし) | 0.15→0.12 | 300→350 |
| standard | 0.70→0.78 | 0.30→0.20 | 200→250 |
| strong | 1.00→1.00(変更なし) | 0.45→0.25 | 120→200 |

方針: `wet_dry_mix`(除去の質)は据え置き〜微増し、`gate_threshold`/`gate_release_ms`(声を誤って消さないための余裕)は全段階で緩める。「ノイズ除去は強くしても、声を消しにくくする」という今回の要件は特定のプリセット固有ではなく全ユーザーに関わる一般改善のため、段階自体を調整することにした(新プリセット専用の4段階目を追加する案は、基本画面の「ノイズ除去」ドロップダウンが全プリセット共通の3段階である現状の一貫性を崩すため不採用)。

#### 3. 詳細設定UI: 15スライダーの日本語ラベル・説明・目安表現
`app/soloclarity/gui/app.py`の`ADVANCED_SLIDER_SPECS`を、(キー, ラベル, 最小, 最大, 刻み)に加えて説明文・両端の目安ラベルを持つ形へ拡張する。以下の表がラベル・説明・目安(最小側→最大側)の確定値。Developerはこの表の文言をそのまま使うこと(表現の意図は方向性の正確さを含めて確認済みのため、独自の言い換えはしないこと)。

| キー | ラベル | 説明 | 目安(最小→最大) |
|---|---|---|---|
| clarity_highpass_hz | 低い雑音をカットする | 上げるほど、机の振動音や部屋の低い音を減らします。上げすぎると声の低さまで一緒に削れることがあります。 | 低音を残す → 低音をカット |
| clarity_200hz_gain_db | 声のこもりを減らす(低め) | 下げるほどこもりが減ります。下げすぎると声が薄く感じることがあります。 | こもり軽減 → 厚み重視 |
| clarity_300hz_gain_db | 声のこもりを減らす(中低め) | 下げるほどこもりが減ります。下げすぎると声が薄く感じることがあります。 | こもり軽減 → 厚み重視 |
| clarity_2000hz_gain_db | 発音をはっきりさせる(低め) | 上げるほど発音がはっきりします。上げすぎると声が硬く感じることがあります。 | やわらか → はっきり |
| clarity_3000hz_gain_db | 発音をはっきりさせる(中) | 上げるほど発音がはっきりします。上げすぎると声が硬く感じることがあります。 | やわらか → はっきり |
| clarity_4000hz_gain_db | 発音をはっきりさせる(高め) | 上げるほど発音がはっきりします。上げすぎると声が硬く、またはサ行が刺さる感じになることがあります。 | やわらか → はっきり |
| noise_wet_dry_mix | 周囲の音を減らす | 上げるほど周囲の雑音が減ります。上げすぎると声が不自然になることがあります。 | 自然さ重視 → 除去重視 |
| noise_gate_threshold | 無音時の雑音を抑える | 上げるほど小さな雑音を消します。上げすぎると小さい声まで消えることがあります。 | 残す → 消す |
| noise_gate_release_ms | 声が終わった後の消え方 | 上げるほど声の余韻がゆっくり自然に消えます。下げすぎると声の語尾が急に切れることがあります。 | サッと消える → ゆっくり消える |
| compressor_threshold_db | 音量差を整える(効き始め) | 下げるほど、小さい声にも早く効果がかかります。下げすぎると常に効果がかかった不自然な声になることがあります。 | 効きにくい → 効きやすい |
| compressor_ratio | 音量差を整える(強さ) | 上げるほど、声の大小の差が小さくなります。上げすぎると声が不自然に潰れて聞こえることがあります。 | ゆるやか → 強力 |
| compressor_attack_ms | 音量差を整える(反応の速さ) | 下げるほど、大きな声にすぐ反応します。下げすぎると声の出始めが不自然にへこむことがあります。 | 素早く反応 → ゆっくり反応 |
| compressor_release_ms | 音量差を整える(戻る速さ) | 下げるほど、効果からすぐ元の音量に戻ります。下げすぎると音量の変化がせわしなく感じ、上げすぎると次の声まで音量が低いままになることがあります。 | 素早く戻る → ゆっくり戻る |
| agc_target_dbfs | 小さい声を持ち上げる(目標の大きさ) | 上げるほど声がしっかり届く大きさになります。上げすぎると無音時のノイズが目立つことがあります。 | 控えめ → しっかり持ち上げる |
| agc_max_gain_db | 小さい声を持ち上げる(最大の強さ) | 上げるほど、とても小さい声も持ち上げられます。上げすぎると無音時のノイズが目立つことがあります。 | 控えめ → 最大まで持ち上げる |

両端の目安ラベルは各スライダーの左右(最小値側/最大値側)に小さく表示する。既存の`tk.Scale`自体が視覚的なつまみ位置を示すため、追加のグラフィック要素は作らず、テキストラベルのみで十分とする(過剰な視覚化はしない)。

#### 4. 基本画面の「明瞭度」「ノイズ除去」ドロップダウン
現状、`presets.CLARITY_LEVELS`/`NOISE_LEVELS`の内部キー(`weak`/`standard`/`strong`)がそのままコンボボックスに表示されており、日本語UIの中に英単語が混在している。`弱`/`標準`/`強`という表示用ラベルへの対応表を追加し、他の日本語UIと一貫させる(プリセットの`label_ja`と同じ「内部キー⇔表示名」パターンを踏襲する)。

### 理由（検討した代替案）
- **新プリセット専用のノイズ除去4段階目を追加する案は不採用**: 基本画面の「ノイズ除去」ドロップダウンは全プリセット共通の3段階という一貫したメンタルモデルを既に確立しており、特定プリセットのみ4段階目が現れる設計は「設定項目を増やさない」というIssueの方針、およびAGENTS.mdの「機能追加を目的に複雑化させない」に反する。3段階自体を再調整する方が影響範囲が明確で、全ユーザーに一般的な改善として届く。
- **`natural`/`low_voice`/`quiet_voice`を統合・削除する案は不採用**: 「小さくて低い声」以外の単一条件(低いだけ、小さいだけ)に最適化したいユーザーのユースケースが残っており、Issueも「必要であれば整理してよい」という任意の許可であって削除を必須としていない。重複がないことを確認した上で維持する判断とした。
- **詳細設定のパラメータ数を減らす(例: コンプレッサー4項目を1項目に統合)案は不採用**: Issoの要求は「専門用語を分かりやすい日本語にする」ことであり、パラメータの技術的な粒度(数)自体を変える指示ではない。統合は`VoiceChain`側のマッピングロジックを追加する必要があり、要求されていない複雑化になる。

### 影響
- 既存の`config.json`に保存された`advanced_overrides`のキー名(`clarity_200hz_gain_db`等)はプログラム側の識別子のまま変更しないため、既存ユーザーの詳細設定保存値に影響はない(表示ラベルのみの変更)。
- `preset: "discord_call"`を保存済みのユーザーは、次回起動時に自動的に新デフォルト(`quiet_low_voice`)へフォールバックする。
- ノイズ除去3段階の再調整により、既存の`tests/test_gate.py`等の期待値(閾値・release_ms)を使ったテストは新しい数値に合わせて更新が必要。

---

## D-011: T-005実装（D-010の確定表をそのまま実装、9条件の合成信号テスト）

- 日付: 2026-08-13
- 状態: 採用

### 背景
- T-005はManager(D-010)が確定した数値・文言をそのまま実装するタスクであり、Developer側での言い換え・再設計は行わない指示だった。本エントリはD-010の表を実装した際の実装詳細と、Issueが要求する9つの想定利用シーンに対する自動テストの実測結果を記録する。
- 本セッションもLinuxのクラウドコンテナであり、D-001記載の制約（Windows実機・Discordクライアント・実オーディオデバイスなし）は変わらない。以下の実測値はすべてこの環境のpytest自動テスト・合成信号によるDSP検証・xvfb環境でのGUI構造検証によるものであり、「実際に聞いて確認した」という主張は一切含まない。

### 決定

#### 1. プリセット再構成
`app/soloclarity/presets.py`の`discord_call`キーを`quiet_low_voice`に変更し、D-010の表どおりのパラメータ(`clarity="strong"`, `noise="strong"`, `compressor=CompressorParams(-23.0, 2.8, 10.0, 200.0)`, `agc=AgcParams(target_dbfs=-17.0, max_gain_db=12.0)`)を設定した。`DEFAULT_PRESET`・`PRESET_ORDER`も新キー名に更新した。`natural`/`low_voice`/`quiet_voice`は無変更。

#### 2. ノイズ除去3段階の再調整
`NOISE_STAGES`をD-010の表どおりに変更した(weak: gate_threshold 0.15→0.12, gate_release_ms 300→350。standard: wet_dry_mix 0.70→0.78, gate_threshold 0.30→0.20, gate_release_ms 200→250。strong: gate_threshold 0.45→0.25, gate_release_ms 120→200。wet_dry_mixのweak/strongは据え置き)。既存の`tests/test_chain.py`・`tests/soak_chain.py`・`tests/bench_chain.py`内の`"discord_call"`をすべて`"quiet_low_voice"`へ置き換えた。`tests/test_gate.py`は`presets.NOISE_STAGES[level]`経由で値を動的に参照する設計のため、コード自体の変更は不要だった(ハードコードされた閾値なし)。`tests/test_chain.py`内の1箇所、コメントで「ゲート閾値0.30」と旧standard値を参照していた箇所を「ゲート閾値0.20」に修正した(アサーション自体は数値非依存だったため実害はないが、コメントの正確性のため修正)。

#### 3. 詳細設定UIの日本語化
`app/soloclarity/gui/app.py`の`ADVANCED_SLIDER_SPECS`を`tuple[tuple[str, str, float, float, float], ...]`から`SliderSpec`(NamedTuple、`key`/`label`/`lo`/`hi`/`resolution`/`description`/`hint_low`/`hint_high`)のタプルへ拡張し、D-010の表の文言(ラベル・説明・両端目安)をそのまま埋め込んだ(意訳・言い換えなし)。`_build_advanced_panel`を、各スライダーにつき2行(ラベル+左目安+スケール+右目安の行、その下に説明文の行)を割り当てる構成に変更した。説明・目安ラベルは`ttk.Label`に`font=("TkDefaultFont", 8)`(説明文はさらに`foreground="gray"`、`wraplength=420`)を指定し、過剰なグラフィック要素は追加していない(D-010「テキストラベルのみで十分」の方針どおり)。既存の`_ADVANCED_SLIDER_RANGES`(クランプ用)・`_clamp`関数・`advanced_overrides`のキー名(内部識別子)は無変更。`tests/test_app_gui.py`の`ADVANCED_SLIDER_SPECS`の5要素タプル分解を`spec.key`/`spec.lo`/`spec.hi`属性アクセスへ更新した。

#### 4. 基本画面ドロップダウンの日本語化
`presets.py`に`LEVEL_LABELS_JA = {"weak": "弱", "standard": "標準", "strong": "強"}`を追加した(明瞭度・ノイズ除去は同じキー集合のため対応表を1つに共通化)。`app.py`の`clarity_combo`/`noise_combo`の`values`をこの対応表経由の表示名にし、`_restore_from_config`/`_on_preset_selected`での`clarity_var.set()`/`noise_var.set()`、`_on_clarity_selected`/`_on_noise_selected`での逆引き(表示名→内部キー)も、既存の`preset_label_to_name`パターンを踏襲して実装した。内部キー(`weak`/`standard`/`strong`)・config.jsonとの整合性は変更していない(表示層のみの変更)。

#### 5. 9条件の合成信号テスト
`tests/test_chain.py`に`TestQuietLowVoicePresetRealWorldScenarios`(9メソッド)を追加した。既存の`make_low_voice_signal`(基本周波数+倍音の合成、f0パラメータで音域を可変)・`band_energy`(FFTでの帯域エネルギー比較)・`chain_factory`フィクスチャをそのまま踏襲した。

実測結果(このLinux環境、`pytest tests/test_chain.py -k TestQuietLowVoicePresetRealWorldScenarios -q`、9 passed):

1. **小さい＋低い声**(peak -32dBFS, f0=110Hz): AGC内部ゲインが80フレーム処理後に初期値1.0から約1.113(+0.9dB相当)まで増加する方向に働くことを確認。EQ単体(Highpass+PeakFilter)では200-300Hz帯エネルギーが減少、2-4kHz帯エネルギーが増加することを確認。
2. **普通の声量＋低い声**(peak -11dBFS, f0=120Hz): 80フレーム処理後もリミッターceiling(線形0.891)を一度も超えず(実測peak 0.820)、AGCゲインは1.089(+0.7dB)止まりで、閾値として設定した1.5倍(+3.5dB)を大きく下回ることを確認(既にちょうど良い音量の声を不自然に大きくしすぎない)。
3. **小さい声＋通常の音域**(peak -32dBFS, f0=220Hz): AGCゲインが1.0から約1.163まで増加することを確認。
4. **普通の声量(基準ケース)**(peak -18dBFS, f0=220Hz): 起動直後15フレーム(150ms)のウォームアップを除いた区間で、出力RMS比0.34・出力ピーク比0.59倍が、常識的な範囲として設定した0.1〜10倍の範囲に収まることを確認。ピークはリミッターceilingを一度も超えないことも確認。
5. **突然大きな声**: フルチェーン(振幅0.05→0.999の急変)でリミッターceilingを一度も超えないこと(既存の`TestCompressorAgcLimiter`と同じ手法)、およびコンプレッサー単体(RNNoise/ゲートの合成音特有の揺らぎを排除、既存`TestCompressorSmoothness`と同じ手法)で出力側のdB/frame最大変化量(19.16dB)が入力側(20.0dB)を上回らないことを確認。
6. **無音状態**: 振幅0.002のガウスノイズ(ほぼ無音)200フレームに対し、出力エネルギーが入力エネルギーの0.05倍未満(実測比率約0.00015)に減衰することを確認。
7. **PCファン等の連続ノイズ**: 振幅0.05のホワイトノイズ300フレームに対し、出力エネルギーが入力エネルギーの0.1倍未満(実測比率約0.0019)に減衰することを確認。
8. **キーボード/マウス等の断続的ノイズ**: 200フレーム中20フレームに5サンプルの鋭いパルス(振幅0.3〜0.6)を混ぜた合成音で、クリック区間の出力エネルギーが入力エネルギーの0.1倍未満(実測比率約0.00013)に抑制され、かつ処理全体が例外なく完走することを確認。
9. **声とノイズが同時に存在する状態**(声: peak -20dBFS, f0=150Hz + 定常ノイズ振幅0.03、ノイズ系列はnoise-only側と同一の乱数シードで再現して条件を揃えた): 声+ノイズ区間の出力エネルギーが、同一ノイズ単独区間の出力エネルギーの10倍を上回る(実測比率約2485倍)ことを確認。新しいgate_threshold(strong: 0.45→0.25)が緩和されたことで、声がノイズに埋もれてもゲートで丸ごと消されないことを裏付ける、9条件のうち最も重要な検証。

いずれもRNNoiseが完全に周期的な合成音を数十フレーム後に「非音声寄り」と判定していく既知の挙動(D-002)を踏まえ、AGCゲインの方向性検証はn_frames=80のうち発話確率が閾値を上回る前半区間を含む形にし、条件4のRMS/ピーク比較はウォームアップ区間を除いた上で桁単位の広い許容範囲(0.1〜10倍)を設定することで、実装のバグではなく合成テスト信号特有の揺らぎによる誤検出を避けた。

### 理由
- D-010で数値・文言が確定済みのため、Developer側の判断は「実装方法」(データ構造の選び方、テスト設計)のみに限定した。判定ラダーに従い、`ADVANCED_SLIDER_SPECS`の拡張は新規ファイル・新規抽象化を増やさずNamedTupleへの置き換えのみで対応した。
- 9条件のテストは、既存の合成信号パターン(`make_low_voice_signal`・`band_energy`・compressor board単体でのdB jump比較・RNNoiseラッパーの定常ノイズ減衰確認)をすべて踏襲し、新しいヘルパー関数やテストファイルを追加していない(既存パターンの再利用を優先)。

### 影響
- `pytest tests/`(このLinux環境): **100 passed**(D-009時点の91件 + 今回の新規9件)。5回連続実行でフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- 既存の`config.json`に保存された`preset: "discord_call"`は、`_is_valid_preset`により不正値としてデフォルト(新キー`quiet_low_voice`)へ自動フォールバックする(D-010で意図された挙動)。`advanced_overrides`のキー名(`clarity_200hz_gain_db`等)は無変更のため、詳細設定の保存値には影響しない。
- xvfb環境で`App()`を起動し、詳細設定パネルを開いた状態で`_advanced_frame.winfo_children()`が75個(15スライダー×5ウィジェット: ラベル/左目安/スケール/右目安/説明)であること、プリセット・明瞭度・ノイズ除去のコンボボックスがそれぞれ日本語表示(`小さくて低い声＋高品質ノイズ除去`/`弱`/`標準`/`強`等)になっていることをクラッシュなしで確認した。
- Windows実機・Discordでの実際の聞こえ方の確認は、この環境では引き続き実施不可能(D-001の既知の制約)。`app/WINDOWS_VERIFICATION_CHECKLIST.md`のプリセット名表記(「Discord通話」→「小さくて低い声＋高品質ノイズ除去」)も本タスクで合わせて更新した。

---

## D-012: ノイズ処理のバックグラウンド/インパクト2系統分離

- 日付: 2026-08-13
- 状態: 採用

### 背景
- Issue要件: 現在は単一のRNNoise適用量(`wet_dry_mix`)で全ノイズを一律に抑制しているが、これを「バックグラウンドノイズ(PCファン・空調等の定常音)」と「インパクト音(キー打鍵・クリック等の瞬間音)」の2系統に分離し、前者は積極的に抑制、後者は完全に消さず自然な範囲で残すよう再設計する。既定プリセットもこの2系統を反映した設定にする。
- Issueから技術方式の比較検討を明示的に求められたため、以下を調査した。

### 調査内容(技術方式の比較)
- **WebRTC Audio Processing (WebRTC APM)**: `NoiseSuppression`(定常騒音向け、スペクトル減算ベース)と`TransientSuppressor`(打鍵音等の過渡音向け、旧`TypingDetection`の後継)が、実際に独立したモジュールとして存在することを確認した([WebRTC公式ソース](https://chromium.googlesource.com/external/webrtc/+/ad34dbe934/webrtc/modules/audio_processing/ns/noise_suppression.h)、[開発者向け解説記事](https://www.forasoft.com/learn/audio-for-video/articles-audio/webrtc-audio-pipeline-end-to-end))。要件と方向性が一致する既存技術である。
- Python向けバインディングを調査した結果、`pywebrtc-audio`(strands-labs製、pybind11)がPyPIにwin_amd64を含む幅広いプラットフォームの事前ビルド済みwheelを公開していることを確認した(`pip download`せず`pypi.org`のJSON APIで直接確認)。しかし実際にこの環境へ`pip install`し中身を検証したところ、
  - 公開APIは`AudioProcessor`/`EchoCanceller`/`GainController`/`NoiseSuppressor`/`VoiceDetector`の5クラスのみで、**`TransientSuppressor`が一切公開されていない**(まさに今回必要な機能が欠落している)。
  - 全クラス・全メソッドにdocstringが一切なく、`NoiseSuppressor`に抑制強度を指定するパラメータも見当たらない(WebRTC APM本来の0〜3段階の強度指定が露出していない)。
  - PyPIメタデータの`license`が`None`(ライセンス不明)であり、GPLv3で配布する本アプリに組み込む上で法的リスクがある。
  - バージョンが`0.1.0`のみで実績・利用実績が確認できない。
  - これらの理由により**不採用**と判断した。旧来の`webrtc-audio-processing`(xiongyihui製)はPyPI上のwheelがcp27/cp36のlinux_armv7lのみでwin_amd64が存在せず、そもそも導入不可能だった。
- **WebRTC APM本体をソースからビルドしてバインディングを自作する案**: WebRTC本体は巨大なC++コードベースであり、ビルドシステム自体が複雑(depot_tools等が必要)。本アプリの「軽量ボイスプロセッサ」というスコープを大きく超えるため不採用。
- **DeepFilterNet等のより新しいニューラルネット系デノイザーへの置き換え**: RNNoiseより高品質だがモデルサイズ・CPU負荷が大きく、「軽量」「低遅延」要件、およびD-001で確立した48kHz/480サンプル(10ms)フレームとの親和性の面でRNNoiseに劣る。加えてバックグラウンド/インパクトの分離という今回の要件そのものを解決しない(RNNoise同様、単一の統合モデル)。不採用。

### 決定
- **RNNoiseを引き続き採用**する(D-001の判断を維持)。既存の統合実績(T-001〜T-005で実証済みのCPU負荷約0.7ms/フレーム、BSDライセンス、フレームサイズの一致)を活かしつつ、以下を追加する。
- **自前の軽量トランジェント検出器を新設**(`app/soloclarity/dsp/transient.py`予定)。既存ライブラリに要件を満たすものがなかったため(判定ラダー: 既存の依存関係で解決できないため最小実装)、以下の設計とする。
  - 各フレーム(480サンプル=10ms)のRMSに対し、速い時定数のエンベロープ(`fast_env`、EMA係数0.7、時定数約14ms)と遅い時定数のエンベロープ(`slow_env`、EMA係数0.05、時定数約200ms)を追跡する。
  - `ratio = fast_env / (slow_env + 1e-6)`を計算し、`transient_score = clamp((ratio - 1.0) / (TRANSIENT_RATIO_THRESHOLD - 1.0), 0.0, 1.0)`という連続値(0〜1)で「そのフレームがどれだけインパクト音らしいか」を表す(ハードな2値判定ではなく連続値にすることで、切り替わり時の不自然さを避ける)。`TRANSIENT_RATIO_THRESHOLD = 2.2`。
  - 振幅が極小(無音相当、目安-45dBFS未満)の場合は`transient_score`を0に固定し、暗騒音レベルの微小な揺らぎを誤ってインパクト音と判定しないようにする。
- **`NoiseStage`を拡張**し、`wet_dry_mix`(単一)を`background_wet_dry_mix`(定常ノイズ抑制強度)と`impact_wet_dry_mix`(インパクト音抑制強度、常に背景より弱い値を既定とする)の2つに分離する。`gate_threshold`/`gate_release_ms`(発話確率ゲート)は変更しない(声か否かを判定する既存の仕組みであり、定常/インパクトの区別とは直交する軸のため)。
- **`VoiceChain.process()`の混合比計算を変更**: `mix = background_wet_dry_mix * (1 - transient_score) + impact_wet_dry_mix * transient_score`とし、この`mix`を既存の`denoised * mix + highpassed * (1 - mix)`のブレンドにそのまま使う(処理順序 Highpass→RNNoise→EQ→Compressor→AGC→Limiter→ゲート 自体は変更しない、D-001参照)。
- **ノイズ除去3段階(`NOISE_STAGES`)を再定義**:

| 段階 | background_wet_dry_mix | impact_wet_dry_mix | gate_threshold | gate_release_ms |
|---|---|---|---|---|
| weak | 0.35 | 0.15 | 0.12 | 350 |
| standard | 0.80 | 0.25 | 0.20 | 250 |
| strong | 1.00 | 0.35 | 0.25 | 200 |

「強」段階でもインパクト音抑制(0.35)はバックグラウンド抑制(1.00)より大幅に弱く保つことで、「打鍵音は完全に消さず自然な範囲で残す」という方針をすべての段階で一貫させる。詳細設定パネルでは`noise_impact_wet_dry_mix`を独立して0〜1まで調整できるため、より強く消したいユーザーは手動で引き上げられる。

- **既定プリセット(`quiet_low_voice`)の`label_ja`を更新**: 「小さくて低い声＋高品質ノイズ除去」→「小さくて低い声＋高品質バックグラウンドノイズ抑制＋弱いインパクト音抑制」に変更する。内部キー`quiet_low_voice`・`clarity="strong"`・`compressor`/`agc`の数値(D-010参照)は変更しない。`noise="strong"`のままだが、`NOISE_STAGES["strong"]`自体が上記の通り再定義されるため、プリセット側の参照は変更不要。

### 詳細設定UIの変更
- 既存の`noise_wet_dry_mix`スライダー(「周囲の音を減らす」)を、`noise_background_mix`と`noise_impact_mix`の2つに分割する。
  - `noise_background_mix`: ラベル「周囲の音を減らす」、説明「上げるほどPCファンや空調などの連続した音が減ります。上げすぎると声が不自然になることがあります。」、目安「自然さ重視 → 除去重視」、範囲0.0-1.0。
  - `noise_impact_mix`: ラベル「打鍵音などを減らす」、説明「上げるほどキーボードやクリック音が減ります。下げると自然な操作音が少し残ります。」、目安「自然に残す → しっかり減らす」、範囲0.0-1.0。
- 上記以外の既存13スライダー(明瞭度6項目・ゲート2項目・コンプレッサー4項目・AGC2項目、合計から重複を除く)はT-005(D-010)の文言をそのまま維持する。「声の聞き取りやすさ」「低音」「声の音量差」に関するIssue記載の新しい例文は、T-005で実装済みの表現(「発音をはっきりさせる」「声のこもりを減らす」「小さい声を持ち上げる」等)が実質的に同じ意図をすでに満たしていると判断し、文言の作り直しは行わない(確認した上での判断であり、未対応ではない)。

### 影響
- `advanced_overrides`のキー名`noise_wet_dry_mix`が廃止され`noise_background_mix`/`noise_impact_mix`に置き換わる。旧キーを保存済みのユーザーの値は、`config.py`の型検証で単に無視され(不明キーとして無害に無視される、既存のキー単位フィルタリング挙動)、新しい2キーはプリセット既定値から始まる。これは意図的な仕様変更であり、後方互換は取らない(AGENTS.mdの「後方互換性を維持しない」方針、値の意味自体が変わるため中途半端な互換レイヤーは持たない)。
- `pytest`のテストのうち、`noise_wet_dry_mix`を直接参照している既存テストは新しい2キーに合わせて更新が必要。
- CPU負荷: トランジェント検出器はフレームごとにEMA更新2回・除算1回程度の軽量な処理であり、既存のベンチマーク予算(10ms中0.7ms程度)に対する影響は小さいと想定されるが、実際に`bench_chain`を再実行して数値で確認すること。
