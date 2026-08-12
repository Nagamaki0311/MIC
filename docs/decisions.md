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
