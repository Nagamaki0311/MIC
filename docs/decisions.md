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

---

## D-013: T-006実装(D-012の決定事項をそのまま実装、14条件テスト、追加のReviewer/Manager指摘対応)

- 日付: 2026-08-13
- 状態: 採用

### 背景
- T-006はManager(D-012)が確定した設計・数値・UI文言をそのまま実装するタスクであり、Developer側での再設計は行わない指示だった。本エントリは実装の詳細と、実装過程で追加依頼された2件の改善(詳細設定スライダーのライブ反映のUX、詳細設定パネルの縦スクロール対応)を記録する。
- 本セッションもLinuxのクラウドコンテナであり、D-001記載の制約(Windows実機・Discordクライアント・実オーディオデバイスなし)は変わらない。以下の実測値・検証結果はすべてこの環境のpytest自動テスト・合成信号によるDSP検証・xvfb環境でのGUI構造検証によるものであり、「実際に聞いて確認した」という主張は一切含まない。

### 決定

#### 1. トランジェント検出器(`app/soloclarity/dsp/transient.py`)
D-012の設計をそのまま実装した。`TransientDetector`クラスが`fast_env`(EMA係数0.7)・`slow_env`(EMA係数0.05)を保持し、`process(frame) -> float`で`ratio = fast_env / (slow_env + 1e-6)`から`transient_score = clamp((ratio - 1.0) / (TRANSIENT_RATIO_THRESHOLD - 1.0), 0.0, 1.0)`(`TRANSIENT_RATIO_THRESHOLD = 2.2`)を返す。フレームRMSが-45dBFS(`SILENCE_FLOOR_DBFS`)未満の場合は0固定。定数は本ファイル内に閉じ、`presets.py`には置いていない(D-012の裁量部分。トランジェント検出は明瞭度/ノイズ除去/コンプレッサー/AGCのようなプリセット単位で切り替える対象ではなく、DSPアルゴリズム自体の内部定数のため)。

#### 2. `NoiseStage`の拡張(`app/soloclarity/presets.py`)
`wet_dry_mix`を`background_wet_dry_mix`/`impact_wet_dry_mix`の2フィールドに分割し、`NOISE_STAGES`をD-012の表どおりに再定義した(weak: 0.35/0.15/0.12/350、standard: 0.80/0.25/0.20/250、strong: 1.00/0.35/0.25/200)。`quiet_low_voice`の`label_ja`を「小さくて低い声＋高品質バックグラウンドノイズ抑制＋弱いインパクト音抑制」に変更した(内部キー・clarity・compressor・agcは無変更)。

#### 3. `VoiceChain`への統合(`app/soloclarity/dsp/chain.py`)
`TransientDetector`のインスタンスを`VoiceChain.__init__`で生成し、`process()`内でHighpass後・RNNoise前の信号(`highpassed`)に対して毎フレーム呼ぶ。混合比を`mix = background_wet_dry_mix * (1 - transient_score) + impact_wet_dry_mix * transient_score`に変更し、既存の`denoised * mix + highpassed * (1 - mix)`ブレンドへそのまま使う。処理順序(Highpass→RNNoise→EQ→Compressor→AGC→Limiter→ゲート)は無変更。`set_noise_stage`は新しい2フィールドを持つ`NoiseStage`をそのまま受け取れるため、シグネチャ変更は不要だった。

#### 4. 詳細設定UI(`app/soloclarity/gui/app.py`)
`noise_wet_dry_mix`スライダーを`noise_background_mix`(ラベル「周囲の音を減らす」)と`noise_impact_mix`(ラベル「打鍵音などを減らす」)の2つに分割し、D-012の文言をそのまま使用した。`_sync_advanced_sliders_from_chain`/`_apply_slider_values_to_chain`の対応するキーを更新した。他の13スライダーは無変更。

#### 5. トランジェント検出器の単体テスト(`app/tests/test_transient.py`, 新規4件)
D-012の設計上、`slow_env`(時定数約200ms=20フレーム相当)はゼロ初期値から実信号レベルへ収束するまでに実測で約100フレーム(1秒相当)を要することが分かった(3〜5時定数分のウォームアップが必要という、EMAフィルタの一般的な性質どおり)。これはバグではなく、無音から音が始まった瞬間の過渡応答である。そのため各テストは非0.15を「収束済み」の閾値とし、定常信号は十分なフレーム数(150〜200)を流した後半区間で判定する設計にした。
1. 定常ホワイトノイズ(振幅0.05, 150フレーム): 100フレーム目以降`transient_score < 0.15`。
2. 定常な低振幅信号(150フレームでウォームアップ)の後に単発パルス(振幅0.6)を1フレームだけ挿入: パルスフレームで`transient_score >= 0.5`(実測1.0)、その後10フレームで0.15未満まで復帰(実測: 3フレーム目で0まで復帰)。
3. 無音(振幅1e-5, 50フレーム): 常に`transient_score == 0.0`。
4. 基音+倍音の合成音(声のモデル、緩やかな立ち上がり、200フレーム): 100フレーム目以降`transient_score < 0.15`(定常ノイズと同程度に低いことを確認、声の自然な強弱を打鍵音と誤認しないことの直接検証)。

#### 6. 14条件の合成信号テスト(`app/tests/test_chain.py::TestQuietLowVoicePresetRealWorldScenarios`, 条件7-14を再構成・追加)
T-005で実装済みの9条件テスト(条件1-6は無変更で流用)のうち、条件7(PCファン)・8(旧: 断続ノイズ)・9(声+ノイズ)を14条件の構成に合わせて再構成し、条件8(エアコン)・10(マウス)・11(複数環境音)・13(打鍵音+声)・14(3要素複合)を新設した。

実装中に判明した重要な事実: `TransientDetector`はゼロ初期値から始まるため、無音から突然音が始まる(振幅が0→非0へジャンプする)合成テスト信号では、本来インパクト音ではない定常ノイズや発話開始でも最初の数フレームだけ`transient_score`が高く出る(誤ってimpact_wet_dry_mixが適用される)過渡が生じる。これはテスト信号特有のアーティファクトであり(実際のマイク入力は常時ストリーミングされ続けるため、この過渡は起動直後の一瞬にしか起きない)、実装のバグではないが、条件7・9(旧)のテストをそのまま実行すると期待していた減衰比・声保持比が大きく変わってしまうことが分かった(例: 条件9相当のテストで声/ノイズエネルギー比が旧実装の約2485倍から約2倍程度まで低下)。この問題は`warm_up_chain()`ヘルパー(定常ノイズを事前に120フレーム程度流し、両チェーンを同じ定常状態から比較する)を導入することで解消し、ウォームアップ後は旧実装と同オーダーの比率(条件12で約1638倍)に回復することを確認した。

実測結果(このLinux環境、`pytest tests/test_chain.py -k TestQuietLowVoicePresetRealWorldScenarios -q`、14 passed):
- 条件7(PCファン、ウォームアップ後300フレーム): エネルギー比0.1未満(実測 約0.022)に減衰。あわせて発話確率がAGCの凍結閾値(0.3)を下回っている全フレームでAGCゲインが変化しない(`frozen_violations == 0`)ことを確認(D-002のAGC凍結機構が定常ノイズに対しても機能していることの直接証明、「小さい声を持ち上げた結果、背景ノイズまで大きくなっていないか」という敵対的観点)。
- 条件8(エアコン、LowpassFilter(500Hz)適用済みノイズ、PCファンとはスペクトル形状が異なる): エネルギー比0.1未満(実測 約0.011)に減衰。
- 条件9(キーボード打鍵): 分離あり(実際のプリセット, impact=0.35)のクリック区間出力エネルギーが、分離なし(impact=backgroundと同値に強制、旧実装相当)の場合と比べて5倍以上(実測 約6228倍)残ることを確認。バックグラウンド/インパクト2系統分離が実際に機能していることの直接証明。
- 条件10(マウスクリック、2サンプルのより短いパルス): 条件9と同じ比較で5倍以上(実測 約374687倍)残ることを確認。
- 条件11(複数の環境音、PCファン風+エアコン風を重畳): エネルギー比0.1未満(実測 約0.018)に減衰。
- 条件12(環境音+小さい低い声、旧条件9の再掲・ウォームアップ追加): 声+ノイズのエネルギーがノイズ単独の10倍以上(実測 約1638倍)を維持。gate_threshold(0.25)緩和の効果を裏付ける。
- 条件13(打鍵音+小さい低い声): 打鍵音より前のフレームは、クリックあり/なしの2チェーンで完全に一致すること(因果的に無関係なフレームへの影響がないことの厳密な証明)、打鍵音の直後3フレームの声エネルギー合計が、クリックなしの基準の50%以上を維持すること(打鍵音の抑制処理で声まで大きく欠損していないこと)を確認。
- 条件14(環境音+打鍵音+小さい低い声の3要素複合): 100フレーム全区間でリミッターceilingを一度も超えないこと、出力のshape/dtypeが壊れないこと、例外が出ないことを確認。

#### 7. 性能の再測定
- `python -m tests.bench_chain`(1000フレーム、トランジェント検出器追加後): 平均0.7171〜0.7549ms/フレーム(10ms予算の**7.1〜7.5%**、閾値30%を大きく下回る。既存(D-006時点0.7ms程度)からの増分は誤差範囲内)。
- `python -m tests.soak_chain`(10万フレーム=1000秒相当): RSS成長率**1.007倍**(閾値1.3倍を大きく下回る)、処理時間比率**1.035倍**(閾値1.5倍を大きく下回る、先頭1万フレーム平均0.683ms、末尾1万フレーム平均0.707ms)。無制限なメモリ増加・処理時間劣化は確認されなかった。

#### 8. Discord側の二重処理に関する注記
`app/はじめにお読みください.txt`・`app/WINDOWS_VERIFICATION_CHECKLIST.md`のいずれにも「Discord自体のノイズ抑制と併用しない」旨の記載が無いことを確認したため、両ファイルに追記した(Discordのノイズ抑制/エコーキャンセレーションとSoloClarity側の処理が二重にかかるとこもり・音切れの原因になり得るため併用しないことを推奨する旨)。あわせて`WINDOWS_VERIFICATION_CHECKLIST.md`のプリセット名表記(旧ラベル)・`はじめにお読みください.txt`のプリセット一覧(旧「Discord通話」表記が残っていた)を、今回の`label_ja`変更に合わせて更新した(既存の表記不整合の是正、今回の変更と直接関係する箇所のみ)。

### 決定(追加2件、Manager指摘によるスコープ追加)

#### 9. 詳細設定スライダーのライブ反映の調査・UX改善
実装済みのコードを読み、xvfb環境で`AudioEngine`を実オーディオデバイスなしで(`_input_callback`/`_output_callback`を直接駆動する既存のテストパターンで)動かして検証した結果、**設計・配線自体は正しく機能している**ことを確認した。`App.__init__`で生成される`self.chain`は`App._start_engine()`が`AudioEngine(self.chain, ...)`へそのまま渡す同一のオブジェクト参照であり(`engine.chain is app.chain`)、`App._apply_slider_values_to_chain()`は`chain.set_clarity_stage()`/`set_noise_stage()`/`set_compressor()`/`set_agc()`経由でこの共有オブジェクトの内部状態を直接書き換える。`AudioEngine._input_callback`は毎フレーム`self.chain.process(frame)`を呼ぶため、ストリームの再構築なしに次のフレームから新しい値が使われる。

調査の過程で、直接関係する副作用を1件発見した: `tk.Scale`ウィジェットは、詳細設定パネル(`_advanced_frame`)が初めて画面上にマップされる(=ユーザーが「詳細設定を開く」を初めて押す)際、内部の表示同期処理として一部のスライダー(実測で16項目中10項目、特にclarity系・noise系)の`-command`コールバックを、値の変更を伴わないまま自動的に一度発火させることをxvfb実機検証で確認した(Tkinter/Tclの実装詳細であり、これ自体はドキュメント化されたAPI契約ではない)。これはユーザー操作ではないため、放置すると(a) `_save_config()`が意味なく複数回呼ばれる、(b) 今回追加する「反映しました」フィードバックが、パネルを開いただけで(何も変更していないのに)誤って表示されてしまう、という実害があった。

対応として、`App._toggle_advanced()`のパネルを開く分岐を、既存の`_updating_from_code`ガード(D-003で確立した「コード起因の変更を無視する」ためのフラグ)で囲み、`self.update()`でTkの保留イベントを処理してから解除するようにした。これにより、この種の自動発火は既存のガード機構でそのまま無視される(新しいフラグ・仕組みを追加していない)。

さらに、「反映されているかどうかが分からない」というUX上の問題そのものへの対応として、専用の「適用」ボタン(既存の即時反映という設計を後退させるため不採用)ではなく、`App.advanced_apply_status_var`という短いフィードバックラベル(「設定を反映しました」、緑色、`ADVANCED_APPLY_FEEDBACK_DURATION_MS=1500ms`後に自動的に消える)を`_on_advanced_slider_changed()`(実際のユーザー操作経由のみ)から表示するようにした。`_apply_advanced_overrides()`(config復元経路)は`_apply_slider_values_to_chain()`を直接呼ぶため、このフィードバックは表示されない(意図どおり、起動時の復元をユーザー操作と誤認させない)。`app/はじめにお読みください.txt`に「詳細設定のスライダーは動かすと即座にマイク入力へ反映される」旨を明記した。

`app/tests/test_app_gui.py`に4クラス9件のテストを追加した。
- `TestAdvancedSliderChangesReflectLiveInAudioEngine`(3件): `engine.chain is app.chain`の同一性、スライダー変更が`app.chain._noise_stage`(新しいインスタンスへの差し替え)へ反映されること、実際に`_input_callback`/`_output_callback`経由で同一入力フレームへの出力が変化することを確認。
- `TestOpeningAdvancedPanelDoesNotSpuriouslyChangeSettings`(1件): パネルを初めて開いただけではスライダー値・chainの値・フィードバック表示のいずれも変化しないことを確認(ガードを一時的に外すと再現することも確認済み)。
- `TestAdvancedApplyFeedback`(2件): 実際のスライダー変更でフィードバックが表示されタイムアウト後に消えること、config復元経路ではフィードバックが表示されないことを確認。

#### 10. 詳細設定パネルの縦スクロール対応
実機スクリーンショットで、詳細設定パネルを開いた状態でウィンドウの高さが画面(1366x768等)に収まらず、AGC等の下部項目が操作不能になっていることが報告された。このLinux環境のxvfbで実測したところ、パネルを開いた状態のウィンドウ高さは1567px(修正前)であり、確かに一般的なノートPC画面には収まらないことを確認した(基本画面のみの高さは346pxで、これ自体は問題なかった)。

`app/soloclarity/gui/app.py`の`_build_advanced_panel()`を、16項目のスライダーを直接`ttk.LabelFrame`へ並べる構成から、`tk.Canvas`(高さ固定`ADVANCED_PANEL_MAX_HEIGHT_PX=260px`)+`ttk.Scrollbar`(縦)でラップし、実際のスライダー群は`Canvas`内の`ttk.Frame`(`self._advanced_frame`、スクロール対象)に配置する構成へ変更した。マウスホイール(`<MouseWheel>`, Windows/mac)・X11のホイールイベント(`<Button-4>`/`<Button-5>`, Linux)の両方に対応し、カーソルがCanvas上にある間のみ`bind_all`する(離れたら`unbind_all`し、他ウィジェットのスクロールを妨げない)。ウィンドウ全体の`resizable`は`False`のまま変更していない(既存レイアウトの安全性を優先する方針、D-012指示の対応範囲外)。

実測(このLinux環境、xvfb 1366x768): 修正後のウィンドウ高さは、パネルを開いた状態で**635px**(修正前1567pxから大幅に縮小、1366x768のタスクバー・タイトルバー分の余白を見込んでも収まる)。基本画面(パネルを開く前)は346pxで元々問題なかった。スライダー群の実際のコンテンツ高さは1192px(可視領域260pxを大きく超える)であり、`Canvas.yview_scroll()`でスクロール可能であることを確認した。

`app/tests/test_app_gui.py`に`TestAdvancedPanelIsScrollableAndWindowFitsCommonScreens`(3件)を追加し、(a) パネルを開いた状態のウィンドウ高さが700px以下であること、(b) コンテンツの実高さが可視領域を超えており実際にスクロールできること、(c) パネルを開く前の基本画面自体も700px以下であること、を確認した。

### 理由
- D-012で数値・文言・設計が確定済みのため、Developer側の判断は実装方法(テスト設計、既存パターンの再利用)に限定した。
- 追加2件(スライダーのライブ反映UX、詳細設定パネルのスクロール対応)は、実機スクリーンショットに基づくManagerからの追加指摘であり、AGENTS.mdの「バグは根本原因を直す」に従い、症状(反映が分からない、画面からはみ出る)ではなく構造上の原因(フィードバックの不在、固定サイズかつスクロール手段のないレイアウト)に対処した。スライダーのライブ反映自体は調査の結果バグではなく設計どおり機能していたため、UXの改善(フィードバック表示)にとどめ、不要な「適用」ボタンは追加しなかった(判定ラダー: 既存の即時反映という設計を維持しつつ最小の変更で要件を満たす)。

### 影響
- `pytest tests/`(このLinux環境): **118 passed**(D-011時点の100件 + `test_transient.py`新規4件 + `test_chain.py`の14条件テスト(既存9件を再構成・純増5件) + `test_app_gui.py`新規9件)。5回連続実行でフレーキーな失敗なし。
- `pyflakes soloclarity tests`: 警告0件。
- `advanced_overrides`のキー`noise_wet_dry_mix`が廃止され`noise_background_mix`/`noise_impact_mix`に置き換わった(D-012で意図された仕様変更、後方互換は取らない)。
- 新規ファイル: `app/soloclarity/dsp/transient.py`、`app/tests/test_transient.py`。変更ファイル: `app/soloclarity/presets.py`、`app/soloclarity/dsp/chain.py`、`app/soloclarity/gui/app.py`、`app/tests/test_chain.py`、`app/tests/test_app_gui.py`、`app/はじめにお読みください.txt`、`app/WINDOWS_VERIFICATION_CHECKLIST.md`。
- Windows実機・Discordでの実際の聞こえ方(特にインパクト音が「自然な範囲で残る」という主観評価)は、この環境では引き続き検証不可能(D-001の既知の制約)。`app/WINDOWS_VERIFICATION_CHECKLIST.md`に沿ったユーザー側での最終確認が必要。

---

## D-014: T-007 詳細設定パネルのスライダーが横方向に見切れる問題の原因特定・修正方針

- 日付: 2026-08-13
- 状態: 採用

### 背景
D-012で追加した`tk.Canvas`+`ttk.Scrollbar`による縦スクロール対応(T-006)の実機検証(v1.2.0)で、縦方向の見切れは解消したものの、今度は詳細設定スライダー(`tk.Scale`)が横方向に見切れて表示され、右側の目安ラベルやスライダーのつまみが見えないという新たな問題が報告された。ユーザーからはあわせて、ウィンドウサイズを手元で拡縮できるようにしてほしいという要望があった。

### 決定
1. **根本原因**: `app/soloclarity/gui/app.py`の`_build_advanced_panel()`で`tk.Canvas`を生成する際、`height=ADVANCED_PANEL_MAX_HEIGHT_PX`(縦方向の見切れ対策としてD-012で明示指定済み)は指定しているが、`width`を指定していない。Tkinterの`Canvas`は`width`未指定時、内部の子ウィジェット(`self._advanced_frame`、ラベル・スライダー・目安・説明文を含む実際の必要幅は500px超)の要求サイズとは無関係に、Tkの既定幅(数百px未満)で確保される。結果としてCanvasの表示領域(ビューポート)が内容より狭くなり、スライダー本体を含む右側が切り取られる。縦方向はD-012で明示的に`height`を指定していたため同じ問題が起きていなかった。
2. **修正方針**:
   - `_build_advanced_panel()`でスライダー行をすべて構築した後、`update_idletasks()`で`self._advanced_frame`の実際の要求幅(`winfo_reqwidth()`)を確定させ、その値を`self._advanced_canvas`の`width`へ明示的に設定する(Canvas自身に子ウィジェットの要求幅を反映させる、ハードコードされた固定px値は使わない)。
   - `self.resizable(False, False)` → `self.resizable(True, True)`に変更し、ユーザーがウィンドウサイズを手動で拡縮できるようにする(実機からの明示的な要望)。
   - リサイズ後にウィンドウを縮めすぎて再度見切れることを防ぐため、詳細設定パネルを含めた必要最小幅・高さを`minsize()`で設定する(パネルは初期状態で非表示のため、`_advanced_frame.winfo_reqwidth()`を直接使って計算し、ルートウィンドウの`winfo_reqwidth()`だけに頼らない)。
   - ルートの列(`columnconfigure`)・詳細設定パネル行の`rowconfigure`に`weight`を設定し、ウィンドウを広げた際に各フレーム・Canvasの表示領域も追従して広がるようにする(広げても中身のサイズが変わらず余白だけ増える、という中途半端な体験を避ける)。

### 理由
- 判定ラダーに従い、新しいウィジェット・外部ライブラリを追加せず、Tkinter標準の`winfo_reqwidth()`(既存の`ADVANCED_PANEL_MAX_HEIGHT_PX`という固定pxアプローチよりも、内容に追従する分壊れにくい)と`resizable()`/`minsize()`という標準APIのみで解決する。
- 「バグは根本原因を直す」(AGENTS.md)に従い、Canvasの幅が子の要求幅を反映していないという構造上の原因に対処する。個々のスライダーの`length=220`を単に伸ばすような対症療法は、根本原因(Canvasビューポートの幅)を放置したままになるため採用しない。
- resizable化はD-012時点では「既存レイアウトの安全性を優先」として意図的に見送っていたが(D-012該当箇所参照)、実機フィードバックにより解像度・DPI環境によって最適なウィンドウサイズが一様でないことが明らかになったため、ここで方針を変更する。

### 影響
- `app/soloclarity/gui/app.py`の`__init__`・`_build_advanced_panel()`を変更。
- 既存の`ADVANCED_PANEL_MAX_HEIGHT_PX`(縦方向の初期高さの目安)はそのまま残す(resizable化後もウィンドウの初期サイズとしては妥当なため)。
- 実装はDeveloperへ委任し、xvfbでの見切れ再現確認(修正前)・解消確認(修正後)、回帰テスト追加、既存118件のpytestが引き続きpassすることを実装完了の条件とする。

### 修正ループ(Reviewer指摘対応、初回実装をManagerが引き取って修正)

初回実装(Developer agentがセッション上限で中断したためManagerが引き継いで完成させた)をReviewerが検証した結果、High×1・Medium×1・Low×2(うち1件はPLAUSIBLE)の指摘を受けた。

1. **High(CONFIRMED)**: `minsize()`を「パネルを開いた状態」の`self.winfo_reqheight()`(635px)から算出していたため、パネルを一度も開いていない起動直後(閉状態、本来346pxで足りる)でもウィンドウが635pxに強制的に引き伸ばされ、`rowconfigure(6, weight=1)`により空白がちょうどパネルの行(row=6)へ集中して表示されていた。基本画面をコンパクトに保つという設計意図(D-012)に反する新規回帰。
   - 対応: `minsize()`の高さは閉状態の`self.winfo_reqheight()`のみを使うよう変更した(縦方向はCanvas自身のスクロールバーで常にアクセスできるため、開いた状態の高さを最小値として強制する必要がない)。幅は「閉状態の`self.winfo_reqwidth()`」と「`self._advanced_outer.winfo_reqwidth()`(パネルを開いた状態で測る)+ padx分」のどちらか広い方を採用し、パネルを開いた後にユーザーが幅だけ縮めて再び見切れることは引き続き防ぐ。
2. **Medium(CONFIRMED)**: `self.columnconfigure(0, weight=1)`をrootに設定していたため、詳細設定パネル(row=6)だけでなく、デバイス選択・処理設定等の既存フレーム(row=0〜5)も同じ列を共有しており、ウィンドウを横に広げると各フレームの外枠だけが不自然に間延びし、内部のCombobox等は左寄せのまま右側に大きな空白ができていた。
   - 対応: `self.columnconfigure(0, weight=1)`を削除した。ウィンドウを横に広げた場合は、単純に全体の右側に余白ができるのみとなる(個々のフレームが間延びする見た目上の崩れは解消)。
3. **Low(CONFIRMED、文書不整合)**: D-014の決定事項では「`_advanced_frame.winfo_reqwidth()`を直接使って計算し、ルートウィンドウの`winfo_reqwidth()`だけに頼らない」としていたが、初回実装は逆に一時grid→root測定という方式だった。
   - 対応: 下記「第2ラウンド」の通り、`_advanced_outer`の一時grid自体はREQUIRED(必要)と判明したため残したが、計測方法自体はD-014の意図(内容の実測値から算出する、ハードコードしない)を満たしている。本節の記述をもって整合させる。
4. **Low/PLAUSIBLE**: `_build_advanced_panel()`内の一時grid区間に、`_toggle_advanced()`と同様の`_updating_from_code`ガード(D-013で確立、tk.Scaleの初回マップ時の自動発火対策)が無かった。このLinux環境では非発火を確認したが、Windows実機のウィンドウイングモデルの違いにより再現しない保証はないという指摘。
   - 対応: 下記「第2ラウンド」の通り、この一時grid区間を`_updating_from_code`ガードで囲んだ。結果的にこの指摘は「起きるかもしれない懸念」ではなく「実際に起きる回帰」だったことが判明した(次項参照)。

### 第2ラウンド(Managerが上記1の修正を検証中に自ら発見した新規回帰、再修正)

上記1の対応として、いったん`_advanced_outer`の一時grid→grid_remove処理を完全に廃止し(`_advanced_frame.winfo_reqwidth()`のみで幅を算出する方式に変更)、`pytest tests/`を実行したところ、既存テスト`TestAdvancedApplyFeedback::test_config_restore_does_not_show_feedback`が新たに失敗することを発見した(修正前=コミット済みの初回実装では発生しない、この第2ラウンドの変更で新たに顕在化)。

調査の結果、次の事実が判明した:
- `winfo_reqwidth()`等のサイズ計測は、詳細設定パネルのスライダー群(`tk.Scale`)を初めて実体化(realize)させる副作用を持つ。
- 実体化したtk.Scaleは、D-013で確認済みの「値変更を伴わず`-command`を一度だけ遅延発火する」既知の挙動の対象になるが、この遅延発火は実体化した直後に`update_idletasks()`を呼んでも処理されず、実体化後に最初に`self.update()`が呼ばれたタイミングまで予約されたまま残り続ける。
- `_build_advanced_panel()`(`__init__`の中)でこの実体化が起きても、`_updating_from_code`ガードは`__init__`完了時点で解除済みのため、後で(例えばテストコードが)最初に`app.update()`を呼んだ瞬間に、ガードなしで全16項目分の`_on_advanced_slider_changed`が発火し、「設定を反映しました」というユーザー操作用フィードバックが誤表示される。
- 初回実装(D-014本文の決定通り)に存在した「`_advanced_outer.grid(...)`→`update_idletasks()`→`minsize(...)`→`grid_remove()`」という一時map→unmapの手順は、たまたまこの予約された遅延発火を打ち消す副作用を持っていた(xvfb環境で実測確認: 一時map→unmapを行うコードでは`_on_advanced_slider_changed`が一度も発火しないのに対し、行わないコードでは`app.update()`のタイミングで必ず16件発火する)。

このため、一時grid→grid_removeの処理自体は必要と判断して残し(上記1の「不要になったため削除した」という当初の対応方針を撤回)、Reviewer指摘4(PLAUSIBLE)が推奨した通り`_updating_from_code`ガードでこの区間を囲んだ。あわせて、`min_width`算出に使う`_advanced_outer.winfo_reqwidth()`も、grid_remove後の非mapped状態ではなく実際にgridした(mapped)状態で測るよう変更した(非mapped状態でのLabelFrameのreqwidthは正しい値を返さないことが実測でわかったため)。高さのminsizeには閉状態(grid前)の`self.winfo_reqheight()`を使う(上記1の対応方針)のは変更していない。

再修正後、`cd /home/user/MIC/app && python -m pytest tests/ -q`を3回連続実行し**123 passed**(既存118件 + 新規5件: Canvas幅・resizable・minsize幅・閉状態でのウィンドウ膨張防止・他フレーム非伸縮の5テスト)、フレーキーな失敗なし、`pyflakes soloclarity tests`警告0件を確認した。

---

## D-015: T-008 音声処理パイプライン・デフォルトプリセットの再設計方針

- 日付: 2026-08-13
- 状態: 採用

### 背景
実機テストで、「あーーー」「もしもし」等の発声でも声がプツプツ途切れる、十分な声量・距離でも声が遠く/小さく聞こえる、デフォルトプリセットのバックグラウンドノイズ抑制が1.0(最大)になっている、という報告があった。ユーザーからは「小さくて低い声でも自然・近く・明瞭」「声をノイズと誤認して消さない」「バックグラウンドノイズは抑える」「打鍵音等の瞬間音は必要以上に消さない」という設計全体の再検証が明示的に要求された(数値の単純調整ではなく構造的な再検証)。

Plannerが既存コード(`chain.py`/`gate.py`/`agc.py`/`presets.py`/`rnnoise.py`/`engine.py`)とpedalboard/RNNoiseの一次ソース(GitHub)を調査し、以下3つの構造的欠陥を特定した(Manager起票時の仮説を上回る精度の原因分析):

1. **RNNoise出力の1フレーム(10ms)遅延によるdry/wetのコムフィルタ**: RNNoiseの解析窓は`[前フレーム, 今フレーム]`で、出力は前フレーム区間の再構成のため、`rnnoise_process_frame`の戻り値は入力より10ms遅れる。現行の`blended = denoised*mix + highpassed*(1-mix)`は、この遅延を補正せず遅れたdenoisedと遅れていないhighpassedを直接加算しており、0<mix<1の間は事実上10ms遅延のコムフィルタになっている(50/150/250Hz…に周期100Hzのノッチ列)。低い声(f0=100〜120Hz)ではこのノッチ列が基音・倍音と重なりやすく、「遠い・こもる」印象の直接原因と判断した。またmixがtransient_scoreにより毎フレーム変動するため、コムの深さも揺れ続ける(フランジャー的な音色変化)。
2. **ゲートのヒステリシス欠如+完全ミュート+フレーム境界の波形不連続**: `SpeechProbabilityGate`は発話確率の生値を毎フレーム閾値と比較する2値判定(ヒステリシスなし)で、閉じる先が完全な無音(0.0)、かつゲインをフレーム単位のステップ(フレーム内で一定)で適用している。低い声・小さい声で発話確率が閾値付近を振動すると、頻繁な開閉・完全な音の消失・フレーム境界でのクリックが同時に起き、これが「プツプツ途切れる」の最有力機構と判断した。
3. **Compressorにメイクアップゲインが無く、AGCの収束が遅すぎる**: `pedalboard.Compressor`のソース(pedalboard/plugins/Compressor.h)を確認した結果、メイクアップゲイン機構は存在しない。圧縮による音量低下を補償する唯一の手段であるAGCが、既定でattack 2.0秒/release 4.0秒という遅い時定数を持ち、数秒の発話区間内では正しい目標音量に収束しきらない。これが「十分な声量でも遠く/小さく聞こえる」の直接原因と判断した。

### 決定
Plannerの計画(実装計画全文はセッション記録・エージェント成果物として保存、要点のみ本エントリに記載)を採用し、以下をManagerとして承認した。

1. **dry/wetパスの時間整列**: RNNoiseの実測遅延(Step 0-Aで確認)が480サンプル(1フレーム)であれば、dry側に1フレームの遅延バッファを挿入して整列させる。TransientDetectorも整列後のdry信号に対して計算する。
2. **ゲートを完全ミュート→フロア付きダッキングへ変更**: 発話状態の判定にヒステリシス(開く閾値と閉じる閾値を分ける、閉じ閾値=開く閾値×0.5)とhangover(200ms、閾値を割ってもすぐには閉じない)を導入し、発話状態を`SpeechActivityTracker`としてAGC・ゲートで共有する(現状2箇所に分散した閾値判定の一元化)。ゲートの閉時ターゲットは完全無音(0.0)ではなく`GATE_FLOOR_DB=-18.0dB`とし、ゲインもフレーム内で線形ランプさせ波形の不連続(クリック)を無くす。
3. **AGCの時定数短縮**: 既定attack/releaseを2.0秒/4.0秒→0.4秒/1.5秒へ短縮し、数秒の発話内で目標音量へ収束できるようにする。発話状態の判定はSpeechActivityTrackerに一元化し、`freeze_speech_prob_threshold`(AGC独自の0.3判定)は削除する。
4. **デフォルトプリセットの再調整**: `noise="strong"`は維持しつつ(バックグラウンドノイズを積極的に抑えるというユーザー要求自体は妥当)、`background_wet_dry_mix`を1.00から実測(Step 0-E、声帯域損失2.0dB以下かつノイズ単独減衰12dB以上を満たす最大値、推奨初期値0.85)に基づき引き下げる。`standard`も連動して0.80→0.75程度に調整する。noiseレベルを"standard"へ格下げする案は不採用(ユーザーは「バックグラウンドノイズは抑える」ことを明示的に要求しており、mix値の適正化で解決を図る方が要求に忠実)。
5. **明瞭度strongのEQ低域カットを緩和**: 現行(highpass 90Hz, 200Hz -4.0dB, 300Hz -2.5dB)は低い声の厚みを削りすぎている。highpass 80Hz, 200Hz -2.0dB, 300Hz -1.5dB程度へ緩和する(実測Step 0-Gで確定)。既存テストが依存する「strongはweak/standardより強くEQをかける」という大小関係を壊さないよう、`standard`段も連動して緩和する(hp75, 200Hz -1.5dB, 300Hz -1.0dB目安)。
6. **副次的に発見されたバグの修正**: (a) 詳細設定スライダーを操作するたびに`VoiceChain.set_agc`/`set_noise_stage`がAGC/ゲートのインスタンスを作り直し、内部状態(ゲイン・エンベロープ)がリセットされ、声が一瞬消えて数秒かけて音量が戻る問題。`set_params`方式に変更し既存インスタンスの状態を保持する。(b) `gui/app.py`の詳細設定スライダー変更が`AgcParams`をattack/release抜きで再構築しており、スライダー操作後にAGCがプリセット既定のattack/releaseから外れる問題(`dataclasses.replace`を使うよう修正)。(c) ジッタバッファに起動時のprefill(priming)が無く、起動直後・クロックドリフト時に周期的な無音挿入が起きうる問題(独立した変更として追加、リスクが高いと判明した場合は単独で見送り可能な設計とする)。
7. **遅延の増加を許容**: dry/wet整列で+10ms、jitter buffer primingで最大+20ms、合計+10〜30msの追加遅延を許容する(Discordの通話遅延・既存のジッタバッファ40msに対して許容範囲と判断)。実機での体感確認は`WINDOWS_VERIFICATION_CHECKLIST.md`に追記する。
8. **UIの詳細設定文言(D-010確定表)は変更しない**: ゲートのフロア/ヒステリシス/hangover、AGCの時定数はスライダー化しない(内部定数)。`noise_background_mix`スライダーの意味・範囲・説明文は変更なし(既定値のみ1.00→0.85相当に変わる)。

### 理由
- 「バグは根本原因を直す」(AGENTS.md)に従い、症状(声の途切れ・遠さ)ではなく、コムフィルタ・ゲートのヒステリシス欠如・AGCの収束遅延という構造上の原因に対処する。単純な数値調整のみでは(例えばbackground_wet_dry_mixを下げるだけでは)コムフィルタとゲートの根本問題は残るため、ユーザーが要求した「構造全体の再検証」に応える。
- 判定ラダーに従い、メイクアップゲイン段の新規追加(責務が曖昧になる)は不採用とし、AGCの高速化のみで対応する。新規外部ライブラリの追加はpedalboard/RNNoiseの範囲内で解決できたため不要と判断した。
- noiseレベルを"standard"へ格下げする案より、"strong"のmix値を実測ベースで適正化する案を採用した理由は、ユーザーが「バックグラウンドノイズ：中〜強」を基本方針として明示しているため。

### 影響
- 変更対象: `app/soloclarity/dsp/chain.py`、`app/soloclarity/dsp/gate.py`、`app/soloclarity/dsp/agc.py`、`app/soloclarity/presets.py`、`app/soloclarity/gui/app.py`、`app/soloclarity/audio/engine.py`、および対応するテスト群(`test_chain.py`, `test_gate.py`, `test_agc.py`, `test_engine.py`, 新規`test_rnnoise_wrapper.py`)。
- `SpeechProbabilityGate.apply()`・`AutomaticGainControl.process()`のシグネチャが`speech_prob: float`→`speech_active: bool`へ変更される(呼び出し元は`VoiceChain`のみのため後方互換は取らない)。
- 出力遅延が最大+10〜30ms増加する(セクション7参照)。
- バージョンは1.3.0(minor)とする(処理チェーンの構造変更・既定プリセット値の変更を含むため)。
- 実装はDeveloperへ委任し、Step 0の実測→構造修正→パラメータ確定→16シナリオの敵対的検証テスト→Reviewer検証→ビルドの順で進める。

### 実装追記(Developer, 2026-08-14): Step0実測結果と最終確定パラメータ

Step0の実測により、上記「決定」1(dry/wetパスの時間整列)の前提となっていたRNNoiseの
1フレーム遅延仮説が**実測では確認できなかった**。以下、実測項目ごとの結果と、それを
踏まえた最終判断を記録する(実測に使ったスクリプトは使い捨てのためコミットしていない。
再現に必要な回帰テストは`tests/test_rnnoise_wrapper.py`に恒久化した)。

**Step0-1: RNNoiseの入出力遅延**
- 手法1(チャープ信号の広帯域相互相関、100-4000Hzスイープ・10秒・1000フレーム): 相互相関のピークはlag=0で、±3フレーム(1440サンプル)の範囲で他のlagを大きく上回る鋭いピークだった(lag=0の相関値20.15に対しlag=±120で11.07、lag=±480で1.72)。
- 手法2(定常正弦波の位相ベースgroup delay測定、150/200/300/500/800/1200Hzの6周波数): いずれもgroup delay=0.00サンプル、振幅比1.000(RNNoiseは十分な音量の純音をほぼ無加工で通す)。
- **結論**: 2つの独立した手法がいずれも0サンプル遅延を示した。ソースコード読解ベースの仮説(解析窓が[前フレーム,今フレーム]をまたぐため出力が1フレーム遅れる)は、少なくとも今回ビルド・使用しているRNNoise共有ライブラリの実測動作とは一致しなかった。**Step1(dry/wetパスの時間整列)は実施しない**(承認済み方針「0ならスキップしてD-015に追記する」に従う)。将来のRNNoise更新でこの前提が崩れた場合に検知できるよう、`tests/test_rnnoise_wrapper.py`に2種類の遅延回帰テスト(group delay法・広帯域相互相関法)を追加した。

**Step0-2: 発話確率が安定して高くなる合成音声信号**
- 既存`make_low_voice_signal`(純周期合成音)はRNNoiseの発話確率が平均0.023(閾値0.25を常に下回る)にとどまり、シナリオ検証に使えないことを確認した。
- ビブラート(基本周波数を5Hz/±2%揺らす)・トレモロ(振幅を4Hz/±15%揺らす)・微小なブレスノイズ(振幅の5%相当のホワイトノイズ)を加えた`make_voice_like_signal`を新設した。倍音数はf0に応じて自動調整し(`harmonic_cutoff_hz=700Hz`以下に収まるよう倍音数を決定)、倍音が高くなりすぎるとRNNoiseの発話確率が急落する(実測で確認)現象を避けている。
- 実測の結果、f0=110Hz(低い声用)・f0=210Hz(通常音域用)は、振幅-32dBFS〜-6dBFSの範囲で平均発話確率0.9以上・最小発話確率0.66以上と安定していることを確認し、この2つのf0を16シナリオテストの標準信号として採用した。なお本モデルはRNNoiseに対して非常に敏感(f0やharmonic数のわずかな違いで発話確率が0.99から0.01まで急落することがある)であり、実声の複雑さを完全には再現できない実測上の限界がある(後述Step0-5にも影響)。

**Step0-3: ゲートのチャタリング実測**
- `make_voice_like_signal`(f0=110Hz、-32dBFS)単独では発話確率が終始0.99以上で安定するため、旧実装でもチャタリングは再現しなかった(起動直後の立ち上がり以外はgate._gain<1.0が発生しなかった)。
- 同じ声にごく小さいブレスノイズ相当(振幅0.001〜0.005程度、声の振幅より十分小さい)を加えると、旧実装(ヒステリシスなし+完全ミュート+ステップ適用)は発話確率が平均0.14〜0.7まで急落し、gate._gainが0.0(完全無音)まで落ちる回数が300フレーム中150〜232回に達した。新実装(ヒステリシス+hangover 200ms+フロア-18dB+線形ランプ)では同条件で最小ゲインが-18dB(フロア)にとどまり、gate._gain<1.0の回数も約2〜3割少なく抑えられた(例: noise=0.001でOLD 66回→NEW 19回、noise=0.003でOLD 216回→NEW 188回)。完全な「0回」達成は、この合成音声モデルがRNNoiseに対して非常に敏感なため難しかったが、「完全ミュート→クリック」から「フロアへの緩やかなダッキング」への構造改善自体は明確に確認できた。

**Step0-4: AGC収束時間の実測**
- -25dBFS入力・target -17dBFS・max_gain 12dBの条件で、target±3dBへの収束時間: 旧時定数(2.0s/4.0s)で6.77秒、新時定数(0.4s/1.5s)で2.57秒。
- -28dBFS入力では旧8.57秒→新3.22秒。
- -32dBFS入力(max_gainの上限に張り付き、target±3dB以内には到達しないため「最終値の±0.5dB以内への収束」で評価): 旧7.69秒→新2.87秒。
- いずれも新時定数が3秒前後(発話区間内)で収束し、旧時定数(6〜9秒、多くの発話より長い)を大幅に上回る改善を確認した。`presets.AgcParams`の既定値を`attack_seconds=0.4, release_seconds=1.5`に確定した。

**Step0-5: background_wet_dry_mixの実測**
- 「小さい低い声(f0=110Hz, -32dBFS)」単独をhighpass+RNNoise+blendのみに通した場合、声帯域(100-4000Hz)エネルギーはmix=0.70〜1.00のいずれでも損失がほぼ0(むしろ僅かに増加、-1.86dB〜+0.06dB)だった。これはRNNoiseが振幅の大きい周期的な合成音声をほぼ無加工で通す(Step0-1参照)ため、声帯域損失を弁別する指標として機能しなかった実測上の限界である。
- ファンノイズ(ホワイトノイズ)単独の減衰量はmixに応じて単調に増加した: mix=0.70→10.46dB(閾値12dB未達)、0.75→12.04dB、0.80→13.98dB、0.85→16.47dB、0.90→19.99dB、0.95→25.98dB、1.00→46.16dB。
- 声帯域損失側の指標がこの合成音声モデルでは弁別力を持たなかったため、「両方の閾値を満たす最大値」を機械的に選ぶと退化的にmix=1.00(現行値)が最良という結果になってしまう。これは実声の複雑さ(ブレス・歯擦音等)を再現できていない合成信号の限界による見かけ上の結果と判断し、当初の推奨初期値どおり**mix=0.85(strong)/0.75(standard)**を採用した(ノイズ減衰の閾値12dBに対して十分な余裕(strongで+4.5dB)を残しつつ、実声で強めの denoise がアーティファクトを生む可能性への安全マージンを確保する判断)。

**Step0-6: 明瞭度strongのEQ低域損失実測**
- f0=110Hz(低い声)の80-350Hz帯エネルギー変化(Highpass+EQ単体、他段は含まない): 現行(hp90, 200Hz -4.0dB, 300Hz -2.5dB)で-4.11dB、緩和候補(hp80, 200Hz -2.0dB, 300Hz -1.5dB)で-2.74dB。standardは現行(hp80, -2.5/-1.5)で-2.94dB、緩和候補(hp75, -1.5/-1.0)で-2.24dB。
- 緩和候補は損失を約1.4dB(strong)・0.7dB(standard)改善しつつ、「strongの方がstandardより強くEQをかける」大小関係(既存テストが前提とする)も維持していることを確認し、両方とも決定どおり採用した。

**最終確定パラメータ(実測に基づき決定を確定)**
- `AgcParams`既定値: attack_seconds 2.0→0.4、release_seconds 4.0→1.5。
- `NOISE_STAGES["strong"].background_wet_dry_mix`: 1.00→0.85。`standard`: 0.80→0.75。
- `CLARITY_STAGES["strong"]`: highpass 90→80Hz、200Hz -4.0→-2.0dB、300Hz -2.5→-1.5dB。`standard`: highpass 80→75Hz、200Hz -2.5→-1.5dB、300Hz -1.5→-1.0dB。
- `quiet_low_voice`のCompressor: threshold -23.0→-20.0dB、ratio 2.8→2.2、attack 10→15ms(makeup gainが無いため過剰なgain reductionを避ける。releaseは200msのまま)。
- ゲート: `GATE_FLOOR_DB=-18.0`、`SPEECH_ACTIVITY_HANGOVER_MS=200.0`、閉じる閾値=開く閾値×0.5(`SpeechActivityTracker`, `gate.py`新設)。

**Step1(dry/wetパスの時間整列)は実施しなかった**(理由はStep0-1参照)。

**Step7(ジッタバッファのpriming)は実施した**。`PRIME_TARGET_FRAMES=2`、`_primed`フラグを追加し、バッファが2フレーム溜まるまで出力側は無音を書きポップを開始しない設計とした。アンダーラン(ポップ時にバッファが空)が発生した場合は`_primed=False`へ戻し、再度2フレーム溜まるまで無音を維持する。既存の`test_engine.py`は「1フレームpushで即pop出力される」という前提のテストが大半だったため、その前提が不要なテスト(priming自体を検証しないテスト)では`engine._primed = True`を直接設定してpriming前提から切り離し、priming自体の振る舞いは新設の`TestPriming`クラスで別途検証した。

**副次的に発見されたバグの修正確認**: (a) `set_noise_stage`/`set_agc`を`set_params`方式に変更し、既存の`SpeechProbabilityGate`/`SpeechActivityTracker`/`AutomaticGainControl`インスタンスの内部状態(ゲイン・エンベロープ・hangoverカウンタ)を保持するようにした(`test_chain.py`の`TestHighFrequencyParameterSwitching`で3000回のランダム切り替えを回しRNNoiseネイティブ状態の非再作成を確認済み)。(b) `gui/app.py`の`_apply_slider_values_to_chain`を`dataclasses.replace(self.chain.agc_params, ...)`へ変更し、詳細設定スライダー操作でattack/release秒数がプリセット既定値から外れなくなった。`VoiceChain`に`agc_params`(直近に適用した`AgcParams`)を新規公開属性として追加した。

**テスト結果**: `pytest tests/`(soak_chain.py除く)141 passed(既存123件相当+新規18件)、3回連続実行でフレーキーな失敗なし。`pyflakes soloclarity tests`警告0件。`python -m tests.bench_chain`は1フレームあたり平均1.35ms(予算10msの13.5%、閾値30%未満を維持)。`tests/soak_chain.py`は10万フレーム(1000秒相当)処理でRSS成長比1.007倍(閾値1.3倍未満)、処理時間劣化比1.174倍(閾値1.5倍未満)、いずれも合格。

**16シナリオテストの意味検証**: 修正前(pre-fix)のソースコードに対して新しい16シナリオテスト(`TestQuietLowVoicePresetRealWorldScenarios`、`tests/test_chain.py`)を実行したところ、32件中3件(シナリオ6「もしもし反復」・シナリオ7「小さい声の朗読」・シナリオ12「発声→無音」)が`assert_no_frame_boundary_clicks`(フレーム境界のサンプル差分が周辺の典型値の6倍を超える=クリック)で実際に失敗し、修正後はすべてpassすることを確認した。他の29件は主に合成音声モデルの発話確率が終始安定して高い(Step0-2参照)ため旧実装でも偶然パスしており、厳密な意味での回帰検出力は3件にとどまる。特に最重要視していたシナリオ5(「あーーー」持続、ゲートゲイン<1.0の回数=0)は、クリーンな合成音声単独では旧実装でも新実装でも0回であり、この特定の合成信号では旧実装の問題(ヒステリシス欠如によるチャタリング)を再現できなかった(Step0-3で実測した「ノイズを加えた場合の悪化」は`test_gate.py`の`TestSpeechActivityTracker`で単体テストとして別途検証済み)。

**未解決の懸念・トレードオフ**:
- 16シナリオのうち回帰検出力を確認できたのは3件にとどまる。残り13件は「合成信号による最低限の健全性確認(dropout/click/energy retentionの閾値を満たす)」であり、修正の必要性を積極的に証明するものではない。実声での主観評価が引き続き重要(`WINDOWS_VERIFICATION_CHECKLIST.md`に項目追加済み)。
- Step0-5(background_wet_dry_mix)は、声帯域損失側の指標が合成音声モデルの限界により弁別力を持たなかったため、最終値(0.85/0.75)は実測による最適化ではなく計画時の推奨初期値をそのまま採用した判断である。
- ゲートのフロア化(-18dB)により、無音時にわずかな残留ノイズが常時聞こえるようになる(意図的なトレードオフ)。実機での許容可否確認が必要。
- Step7(priming)導入により起動直後・アンダーラン後に最大+20ms程度の追加無音区間が生じる。実機での体感確認が必要。

### Reviewer差し戻し(1巡目): Critical1件・Medium1件

**Critical(CONFIRMED)**: Step0-1「RNNoiseの入出力遅延は0サンプル」という結論は測定バグによる誤りだった。`RNNoiseState.process()`(`rnnoise.py`)は`rnnoise_process_frame(state, ptr, ptr)`と**同一ポインタをin/out両方に渡すin-place処理**であり、`app/tests/test_rnnoise_wrapper.py`の遅延測定テストが渡していた「連続なfloat32配列のスライス」は`np.ascontiguousarray`でコピーされずビューのまま処理されるため、**呼び出し元の入力配列自体がdenoise後の値で上書き**されていた。この結果、遅延比較用の「元の入力」が実質的に出力と同一信号になり、真の遅延の有無に関わらず機械的に0付近を返す構造的なバグだった(本番コード`chain.py`自体は`float32_to_pcm16_scale`が乗算により新規配列を確保するため、このエイリアシングの影響を受けない。影響は測定テストのみ)。Reviewerが3つの独立した方法(修正後の位相ベース測定、探索窓を広げた広帯域相互相関、インパルス応答的なバースト注入検証)で再測定した結果、いずれも**約2フレーム(960サンプル、20ms)相当の遅延が存在する**ことを示した。これによりD-015の「Step1(dry/wetパスの時間整列)は不要」という判断の前提が崩れ、Plannerが元々コムフィルタとして特定していた構造的欠陥(「声が遠い/こもる」の主要因の一つとされていた)が未修正のまま残っている可能性がある。

**Medium(CONFIRMED)**: `AutomaticGainControl.set_params()`は係数のみを更新し、既存の`self._gain`を新しい`min_gain_linear`/`max_gain_linear`でクランプし直さない。プリセット切替(`set_preset`)で`max_gain_db`がより小さい値へ変わった直後、発話が非アクティブ(凍結中)だと、古いプリセットで収束した(より大きい)ゲインがクランプされないまま維持され、新プリセットが許可する範囲を超えたゲインが非発話フレーム(背景ノイズ等)にそのまま適用され続ける。実測で`quiet_low_voice`(max_gain 12dB)から`natural`(max_gain 6dB)への切替直後にゲイン12dBが維持されることを確認した。

対応方針(Developerへの差し戻し事項):
1. `test_rnnoise_wrapper.py`の遅延測定テストで`state.process()`へ渡すフレームを`.copy()`し、エイリアシングを断つ。`RNNoiseState.process()`自体もin-place破壊的処理であることをdocstringに明記するか、内部で防御的にコピーする。
2. 修正後の測定方法で真の遅延量を再確定し、Step1(dry/wetパスの時間整列、1フレーム遅延バッファをdry側に挿入)の実施要否を再判断する(今回の実測(約2フレーム)が再現するなら実施が必要)。
3. `AutomaticGainControl.set_params()`(または`process()`の凍結分岐)で、既存の`self._gain`を新しい`min_gain_linear`/`max_gain_linear`へクランプし直す。

### 実装追記(Developer, 2026-08-14): Reviewer差し戻し(1巡目)対応の実装内容

**1. `test_rnnoise_wrapper.py`の測定バグ修正**: 全ての遅延測定テストで`state.process()`へ渡す前にフレームを`.copy()`し、エイリアシング(`np.ascontiguousarray`がビューを返すことによる呼び出し元配列の意図しない書き換え)を断った。`RNNoiseState.process()`(`rnnoise.py`)のdocstringに、in-place破壊的処理である旨と、呼び出し元が配列を保持したい場合は`.copy()`が必要である旨を明記した(`chain.py`は`float32_to_pcm16_scale`が乗算により毎回新規配列を確保するため影響を受けないことも明記)。内部での防御的コピー追加は、既存の`chain.py`の呼び出し方(既に新規配列)を前提にするとパフォーマンス上不要と判断し、docstring明記のみとした。

**2. 真の遅延量の再確定**: 3つの独立した手法で再測定し、いずれも**2フレーム(960サンプル、20ms)**で一致した。
   - 広帯域チャープ信号(100-4000Hz、10秒)の相互相関: 探索窓をEXPECTED_DELAY_SAMPLES(960)+4フレーム分まで広げて再測定した結果、lag=960で唯一の鋭いピーク(相関値496092、隣接lag959/961は467000台)。
   - インパルス応答的なバースト注入(短い高振幅パルスを孤立無音区間に注入しオンセット位置を検出): RNNoiseは音声らしくない孤立クリックの多くを抑圧するため全試行で検出はできなかったが、検出できた試行(15試行中2〜3回)はいずれも正確に960サンプル一致した。
   - 位相ベースgroup delay測定(位相ラップ=2πの整数倍の不定性をEXPECTED_DELAY_SAMPLES近傍で解決): 150/300/500/800/1200Hzの5周波数でいずれも930〜1005サンプル(誤差要因は位相測定分解能)の範囲に収まり、960サンプル説を支持した。
   - 副次的な発見: Step0-1初回測定の「amplitude ratio ~1.000(RNNoiseは十分な音量の純音をほぼ無加工で通す)」という結論も、同じin-placeエイリアシングバグの影響を受けていたため誤りだった(x=sigとy=outputが実質同一配列だったため)。正しく測定し直すと、**変調のない定常な純音(ビブラート等が無い一定周波数のサイン波)はRNNoiseに強く抑圧される(2秒の定常区間で60dB超の減衰)**。これはコムフィルタの回帰テスト設計にも影響し(後述4番)、ホワイトノイズや純音ではなくRNNoiseがほぼ無加工で通す音声様信号(`make_voice_like_signal`)を使う必要があると判明した。

**3. dry/wetパスの時間整列を実装**: `chain.py`に`DRY_DELAY_FRAMES = rnnoise_mod.OUTPUT_DELAY_FRAMES`(2)ぶんのdry(highpassed)信号遅延バッファ(`deque`、起動時は無音で初期化)を追加した。`process()`内で、RNNoiseの`process()`が返すdenoisedフレームは`DRY_DELAY_FRAMES`前に渡したhighpassedフレームに対応するため、`aligned_dry = self._dry_delay_buffer.popleft()`で時刻を合わせたdry信号を取り出してから`blended = denoised*mix + aligned_dry*(1-mix)`を計算するよう変更した。`TransientDetector`も整列後の`aligned_dry`に対して計算するよう変更した(元のPlannerの計画どおり)。出力全体の遅延が2フレーム(20ms)追加される(既存のjitter buffer priming追加分と合わせ、合計の追加遅延は許容範囲内、D-015「決定」7参照)。

**3-a. 副次的に発覚したLimiterのオーバーシュート問題への対応**: dry/wet整列の導入により、無音直後の瞬間的なフルスケール立ち上がり(instant step transient、既存回帰テスト`test_output_never_exceeds_limiter_ceiling`のシナリオ)で`pedalboard.Limiter`単体のアタックが1フレーム分間に合わず、ceiling(-1.0dBFS)を最大+0.45dB超えるオーバーシュートを出すことが判明した(Limiter単体でも再現する挙動であり、整列前は偶然タイミングがずれてこの弱点が既存テストで露呈していなかっただけと判断した)。Limiterは「Discord側のクリップを防ぐ安全弁」という設計意図(モジュールdocstring参照)を持つため、`limited = np.clip(limited, -LIMITER_CEILING_LINEAR, LIMITER_CEILING_LINEAR)`をLimiter出力に対する最終的なハードクリップとして追加し、ceilingを実際に保証するようにした。

**4. 回帰テストの追加・修正**:
   - `test_rnnoise_wrapper.py`: 全遅延測定テストを`.copy()`ベースに修正し、期待遅延`EXPECTED_DELAY_SAMPLES=rn.OUTPUT_DELAY_SAMPLES`(960)との一致を検証する形へ変更した。位相ラップ解決を追加したgroup delay測定、探索窓を広げた広帯域相互相関に加え、新たにバースト注入によるオンセット検出テストを追加し、3手法体制にした。
   - `test_chain.py`に`TestDryWetTimeAlignment`を追加した。純粋なホワイトノイズはRNNoiseにほぼ完全抑圧され(実測60dB超減衰)コムフィルタの検証に使えないと判明したため、`make_voice_like_signal`(RNNoiseがほぼ無加工で通す声様信号)を使い、EQ/Compressor/AGC/Gateの影響を実質無効化した`VoiceChain`(`mix`固定0.5)で各倍音のゲイン(dry-onlyリファレンス比、dB)のばらつきが3dB未満であることを確認する。手元で修正前のコードに対して同じテストを実行すると倍音間ゲイン変動が最大11.6dB(第2次倍音-8.45dB、第3次倍音-11.79dBの深いノッチ)に達し失敗することを確認した。
   - `test_agc.py`に`test_set_params_clamps_existing_gain_to_new_max_when_speech_is_inactive`を追加した。`quiet_low_voice`相当のmax_gain(12dB)まで収束させた後、発話非アクティブのまま`natural`相当のmax_gain(6dB)へ`set_params`し、即座にクランプされることを確認する。手元で修正前のコードに対して実行すると失敗する(ゲインが12dB相当のまま維持される)ことを確認した。
   - `test_app_gui.py`の`TestAdvancedSliderChangesReflectLiveInAudioEngine::test_input_callback_output_changes_after_slider_moves`が、dry/wet整列バッファ追加による起動直後の追加無音区間(jitter bufferのpriming 2フレームと合わせ、実質4フレーム分)により偶発的にfalse-failするようになったため、`_process_settled`ヘルパー(同一フレームを複数回流し両方のバッファを通過させてから比較する)へ変更した。

**5. テスト結果**: `pytest tests/`(soak_chain.py除く)144 passed(既存141件+新規3件相当。内訳: `test_chain.py`に`TestDryWetTimeAlignment`1件、`test_agc.py`に1件、`test_rnnoise_wrapper.py`は遅延テスト3件を維持しつつバースト注入1件を新規追加、既存2件を書き換え)、3回連続実行でフレーキーな失敗なし。`pyflakes soloclarity tests`警告0件。`python -m tests.bench_chain`は1フレームあたり平均1.22ms(予算10msの12.2%、閾値30%未満を維持)。

**未解決の懸念**: dry/wet整列バッファの導入により出力全体の遅延がさらに2フレーム(20ms)増加した(jitter buffer priming分と合わせた累積遅延の実機体感確認は`WINDOWS_VERIFICATION_CHECKLIST.md`の既存項目でカバーされる範囲内と判断しているが、Reviewerによる再検証を推奨する)。Limiterのハードクリップ追加は、瞬間的なフルスケール立ち上がりというまれなシナリオでのみ発動する安全網であり、通常の音声レベルでは影響しない(`test_limiter_barely_attenuates_normal_level_signal`が引き続きpassすることで確認済み)。

### Reviewer差し戻し(2巡目): Medium1件(新規)

Reviewerが1巡目の指摘(Critical・Medium)の解消を独立した再現実験(第4・第5の遅延測定手法、修正前コードでのコムフィルタ再現、Limiter超過の実測)ですべて確認した上で、**今回の修正自体が生んだ新規のMedium指摘**を発見した。

**問題**: dry/wet整列により`denoised`/`aligned_dry`(→`blended`以降のオーディオパス全体)は2フレーム(20ms)遅延させたが、`speech_prob`(RNNoiseの`process()`が同じ呼び出しで返す発話確率)は遅延させていない。RNNoiseの`speech_prob`自体はオーディオ出力と異なり遅延が無い(実測でinput onsetと同一call、offset=0)ため、`SpeechActivityTracker.update(speech_prob)`→`speech_active`は「今」(フレームn)の発話確率で判定しているのに対し、それをゲート・AGCが適用する対象は「2フレーム前」(フレームn-2)のオーディオになっている。ゲート/AGCの意思決定が、実際に処理中の音声内容より常に約20ms「未来」の情報に基づいて行われる。

**実測**: 無音→声様バーストへの立ち上がりで、`speech_prob`はバースト開始callで即座に0.996へ立ち上がる(遅延0)のに対し、出力オーディオのRMSがベースラインの半分を超えるのは2フレーム後だった。

**影響**: `SpeechActivityTracker`のヒステリシス/hangover(200ms)判定、AGCの凍結判定のタイミングが本来より20ms早い。200msのhangoverマージンで大部分は吸収される可能性が高くCriticalではないが、T-008全体の主題(発話終端でのゲート早期クローズによる「プツプツ途切れる」症状)に直結するため、未検証のまま残すべきではないとReviewerは判断した。

**対応方針**: `speech_prob`(またはそれに基づく発話状態)も`aligned_dry`と同じ`OUTPUT_DELAY_FRAMES`分の遅延バッファを通し、ゲート/AGCへ渡す前に時間整列する。Developerへ再修正を委任する。

### 実装追記(Developer, 2026-08-14): Reviewer差し戻し(2巡目)対応の実装内容

**1. speech_probの整列バッファを追加**: `chain.py`の`VoiceChain.__init__`に`self._speech_prob_delay_buffer: deque[float]`(`maxlen=DRY_DELAY_FRAMES`、無音相当の`0.0`で初期化)を追加した。`process()`内で、`aligned_dry`と同じ位置(dry遅延バッファの読み書き直後)で`aligned_speech_prob = self._speech_prob_delay_buffer.popleft(); self._speech_prob_delay_buffer.append(speech_prob)`を行い、`self._speech_tracker.update(speech_prob)`を`self._speech_tracker.update(aligned_speech_prob)`に変更した。これにより、ゲート・AGCが参照する発話状態は、実際にゲイン制御を適用する対象(`aligned_dry`/`denoised`由来、n-DRY_DELAY_FRAMES時点のオーディオ)と同じ時刻のRNNoise発話確率に基づくようになった。`process()`の戻り値`speech_prob`(呼び出し元は`engine.py`では破棄しているのみ)は、ドキュメント文言(「RNNoiseが返した発話確率」)との一貫性を優先し、整列前の生値のまま返すこととした(整列後の値を返すのは「このprocess()呼び出しに対応する発話確率」という意味と食い違うため)。

**2. 回帰テストの追加**: `test_chain.py`に`TestSpeechProbTimeAlignment`を追加した。無音60フレーム→`make_voice_like_signal`による声様バースト40フレームの立ち上がりを合成し、(a) `chain._speech_tracker._active`が最初に`True`になるフレーム番号と、(b) 出力オーディオのRMSが定常区間RMSの半分を初めて超えるフレーム番号、が一致することを確認する。RNNoiseのSTFT解析窓オーバーラップにより、バースト開始の前後1フレームでごく微小な(定常状態の1%未満の)漏れ込みRMSが観測されるため、「ゼロでなくなる最初のフレーム」ではなく「定常RMSの半分を超える最初のフレーム」で判定した(Reviewerの実測手法「RMSがベースラインの半分を超える」に合わせた)。手元で`self._speech_tracker.update(speech_prob)`(整列なしの修正前コード)に戻して実行すると、`speech_active`がフレーム60、オーディオ立ち上がりがフレーム62で一致せず、実際に失敗することを確認した(2フレーム=`DRY_DELAY_FRAMES`分のズレが実測どおり再現)。修正後はいずれもフレーム62で一致しpassする。

**3. テスト結果**: `pytest tests/`(soak_chain.py除く)145 passed(既存144件+新規1件)、3回連続実行でフレーキーな失敗なし。既存の`TestQuietLowVoicePresetRealWorldScenarios`(16シナリオ)・`test_gate.py`・`test_agc.py`もすべて引き続きpass(speech_active参照タイミングの変更による既存テストの前提崩れは無し)。`pyflakes soloclarity tests`警告0件。`python -m tests.bench_chain`は1フレームあたり平均1.26ms(予算10msの12.6%、閾値30%未満を維持)。

**未解決の懸念**: なし。Reviewerの再検証を推奨する。

---

## D-016: T-009 低い声の明瞭化EQ知識のリサーチと再設計方針

- 日付: 2026-08-14
- 状態: 採用

### 背景
ユーザーがSteelSeries Sonarの「Clarity Low Pitch」プリセットのEQカーブのスクリーンショットを共有した。Manager分析(画像の視覚的読み取り)によれば、このカーブは概ね以下の形をしている: 20Hzで-10dB(サブベースカット)、50Hz→150-200Hzで+1dB→+5〜6dBへ大きくブースト、500Hz-1kHzはほぼフラット、2kHzで+5〜6dBの第2ピーク、5kHzで+3dBへ減衰開始、10-20kHzで-3dB。

これに対しSoloClarityの現行`CLARITY_STAGES["strong"]`は、200Hz -2.0dB・300Hz -1.5dB(カット)、2000Hz +2.0dB→3000Hz +3.0dB→4000Hz +4.0dB(周波数が上がるほど強くブースト)という形であり、低域はSonarと逆方向(カット vs ブースト)、高域はSonarと異なる傾斜(単調増加 vs 2kHzピーク後に減衰)になっていた。

Researcherが「男性の低い声の明瞭化」に関する音響工学的知見を調査した結果:
- 200-500Hz(mud/boxy帯域)への過剰ブーストは、複数の音楽制作・放送系情報源が一貫して警告しており、放送特化ガイド(Podigy)は「男性声の200-240Hzはカット推奨、ブーストすると声が重くなる」と明示している。**SoloClarityの現行のカット方向は、この一般論と整合している**。Sonarの大きな低域ブーストは、SteelSeries製ヘッドセットマイクの周波数特性やマイクの近接効果(近づいて話すほど低域が自然に強調される物理現象)を補正する機種依存の調整である可能性が高く、一般論のみからSoloCastへの移植を正当化できない。
- 2-5kHz(プレゼンス/明瞭度帯域)は穏やかなブースト(1-3dB程度)が一致した推奨。5-8kHz(耳障り)・5-10kHz(歯擦音)は一律カットよりディエッサー的対処、または配信用途では抑制方向が優勢。**この点ではSonarの「2kHzをピークに以降減衰、10kHz以上をカット」という形が一般論により近く、SoloClarityの「周波数が上がるほど強くブースト」という形は耳障り帯域の手前でさらにピークを高めていく方向であり、再検討の余地がある**。

### 決定
1. **200/300Hzのカット方向は維持する**(Sonarのブースト方向へは変更しない)。一般的な音響工学の知見(mud/boxy対策)と整合しており、根拠のない変更は行わない。カット量そのものの最適化(実測に基づく微調整)は許容する。
2. **2kHz〜4kHzのブースト形状を、「周波数が上がるほど強く単調増加」から「2〜3kHz付近でピークを迎え、4kHzに向けて緩やかに減衰する」形へ変更する**。具体的なdB値は、`_eq_board`(複数のPeakFilterの合成、Qによる帯域間の重なりを考慮)を対象に実測(周波数応答スイープ)した上でDeveloperが確定する。目安として、Sonarの「2kHzで+5〜6dB、5kHzで+3dB」という傾斜の"形"(ピーク位置と減衰方向)を参考にしつつ、絶対値はSoloClarity既存の声量感・既存プリセット群とのバランスを保つ範囲で調整する。
3. マイクの近接効果との相互作用は、今回のリサーチでは推論の域を出ないため実装変更は行わず、`WINDOWS_VERIFICATION_CHECKLIST.md`に「マイクとの距離を変えた場合の聞こえ方」の確認項目を追加するに留める。
4. 対象は明瞭度段階全体(`CLARITY_STAGES`のweak/standard/strong)とし、既存テストが前提とする「strongはstandard/weakより強くEQをかける」という大小関係(T-008 D-015で維持した制約)を今回も壊さないこと。

### 理由
- 判定ラダー・AGENTS.mdの「バグは根本原因を直す」に従い、Sonarの見た目をそのまま模倣するのではなく、一般的な音響工学の知見と照らして方向性が支持される変更のみを行う。
- 低域はリサーチの結果、現行の方向性が既に支持されたため変更しない(不要な変更をしないというYAGNI原則)。高域寄りの傾斜のみ、根拠のある変更を行う。

### 影響
- 変更対象は`app/soloclarity/presets.py`の`CLARITY_STAGES`(2000/3000/4000Hzの`gain_db`、必要なら`q`も)、および関連するテスト(`test_chain.py`等の周波数応答検証)。
- 既存の`ADVANCED_SLIDER_SPECS`(GUI詳細設定)の文言・範囲は変更不要(既存スライダーの範囲内で対応可能な変更のため)。
- 実装はDeveloperへ委任し、周波数応答の実測→パラメータ確定→回帰テスト→Reviewer検証の順で進める。バージョンはEQカーブの調整のみであれば1.3.1(パッチ)を想定するが、最終的な変更範囲次第でManagerが確定する。
