@echo off
REM SoloClarity Windows向けビルドスクリプト。
REM Windows実機上で実行すること(このリポジトリのLinux開発環境ではビルドできない)。
REM 前提: Python 3.11 (64bit)がインストール済みで、PATHが通っていること。

setlocal enabledelayedexpansion
cd /d "%~dp0\.."

echo === [1/5] アプリ本体の依存パッケージをインストール ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo === [2/5] PyInstallerをインストール ===
python -m pip install pyinstaller
if errorlevel 1 goto :error

echo === [3/5] RNNoiseの共有ライブラリ(rnnoise.dll)を取得 ===
REM pyrnnoise(開発依存, requirements-dev.txt)を一時的に使い、
REM PyPIのwin_amd64ホイールに同梱されたrnnoise.dllの場所を特定してvendorへコピーする。
REM pyrnnoiseパッケージ自体はアプリ本体からimportしない(D-001参照)。
python -m pip install pyrnnoise
if errorlevel 1 goto :error

if not exist "soloclarity\dsp\vendor" mkdir "soloclarity\dsp\vendor"

python -c "import importlib.metadata as m, shutil; files = m.files('pyrnnoise'); dll = [f for f in files if f.name == 'rnnoise.dll']; assert dll, 'rnnoise.dll not found in pyrnnoise wheel'; shutil.copy(str(dll[0].locate()), 'soloclarity/dsp/vendor/rnnoise.dll'); print('copied:', dll[0].locate())"
if errorlevel 1 goto :error

REM PyInstallerは--add-binaryの相対パスを、cwdではなく--specpathのディレクトリ
REM 基準で解決するため(specpathをbuild\outputに逃がしている都合上)、
REM ここで絶対パスに展開してから渡す。
set "RNNOISE_DLL=%CD%\soloclarity\dsp\vendor\rnnoise.dll"

echo === [4/5] PyInstallerでexeをビルド ===
REM --exclude-module: pyrnnoise本体(audiolab/av/matplotlib/click/tqdmを道連れにする)を
REM 明示的に除外し、軽量な配布バイナリを保つ(D-001参照)。
REM --workpath/--specpathは、このディレクトリ(app\build)にPyInstallerの中間生成物が
REM 混ざらないよう、build_output配下へ逃がす(app\build にはこのスクリプト自体を置くため)。
python -m PyInstaller ^
    --name SoloClarity ^
    --onefile ^
    --windowed ^
    --noconfirm ^
    --distpath dist ^
    --workpath build\output ^
    --specpath build\output ^
    --add-binary "%RNNOISE_DLL%;soloclarity/dsp/vendor" ^
    --exclude-module pyrnnoise ^
    --exclude-module av ^
    --exclude-module audiolab ^
    --exclude-module matplotlib ^
    --exclude-module click ^
    --exclude-module tqdm ^
    soloclarity\__main__.py
if errorlevel 1 goto :error

echo === [5/5] 完了 ===
echo dist\SoloClarity.exe が生成されました。
echo 動作確認手順は WINDOWS_VERIFICATION_CHECKLIST.md を参照してください。
goto :eof

:error
echo ビルドに失敗しました。上記のエラーメッセージを確認してください。
exit /b 1
