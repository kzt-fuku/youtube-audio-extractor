"""OtoClip の共通起動処理。

start_windows.bat / start_mac.command / start.sh から呼ばれるほか、
`python start.py` を直接実行しても動きます。

やること:
  1. .venv（アプリ専用の Python 環境）を作る。壊れていれば作り直す
  2. requirements.txt が変わっていればライブラリを入れる
  3. YouTube の仕様変更に追従するため yt-dlp の更新を確認する
  4. アプリ本体 (python -m otoclip) を起動する
"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
IS_WIN = sys.platform.startswith("win")
VENV_PY = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / "requirements.sha256"
PIP = [str(VENV_PY), "-m", "pip", "--disable-pip-version-check"]


def fail(*lines: str) -> None:
    print()
    for line in lines:
        print(line)
    if sys.stdin and sys.stdin.isatty():
        try:
            input("Enter キーで閉じます ")
        except EOFError:
            pass
    sys.exit(1)


def venv_is_healthy() -> bool:
    if not VENV_PY.exists():
        return False
    try:
        subprocess.run([str(VENV_PY), "-c", "import sys"], check=True, capture_output=True, timeout=60)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def create_venv() -> None:
    if VENV.exists():
        print("古い環境を作り直します...")
        shutil.rmtree(VENV, ignore_errors=True)
    print("初回セットアップ中です（1～3 分かかります）...")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    except (OSError, subprocess.CalledProcessError):
        hint = ["Python 環境 (.venv) を作成できませんでした。"]
        if sys.platform.startswith("linux"):
            hint.append("Ubuntu/Debian では `sudo apt install python3-venv` を実行してから再度お試しください。")
        fail(*hint)
    if not venv_is_healthy():
        fail("Python 環境 (.venv) の作成に失敗しました。Python を入れ直してから再度お試しください。")


def install_requirements() -> None:
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == digest:
        return
    print("必要なライブラリを導入しています（ffmpeg も自動で入ります）...")
    try:
        subprocess.run(PIP + ["install", "-r", str(REQUIREMENTS)], check=True)
    except (OSError, subprocess.CalledProcessError):
        fail("ライブラリの導入に失敗しました。ネット接続を確認してから再度お試しください。")
    STAMP.write_text(digest, encoding="utf-8")


def update_ytdlp() -> None:
    # 失敗しても起動は続ける（オフラインなど）
    try:
        subprocess.run(PIP + ["install", "-q", "-U", "yt-dlp[default]"], capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        pass


def run_app() -> None:
    cmd = [str(VENV_PY), "-m", "otoclip"]
    if IS_WIN:
        try:
            sys.exit(subprocess.call(cmd))
        except KeyboardInterrupt:
            sys.exit(0)
    os.execv(cmd[0], cmd)


def main() -> None:
    if sys.version_info < (3, 10):
        fail(
            f"Python 3.10 以上が必要です（現在: {sys.version.split()[0]}）。",
            "https://www.python.org/downloads/ から新しい Python をインストールしてください。",
        )
    os.chdir(ROOT)
    if not venv_is_healthy():
        create_venv()
    install_requirements()
    update_ytdlp()
    run_app()


if __name__ == "__main__":
    main()
