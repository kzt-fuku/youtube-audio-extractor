"""起動: python -m otoclip"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser

from . import __version__
from .server import create_app, lan_ip, load_config


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    port = cfg["port"]
    host = os.environ.get("OTOCLIP_HOST", "0.0.0.0")
    local_url = f"http://localhost:{port}/"
    phone_url = f"http://{lan_ip()}:{port}/?t={cfg['token']}"

    print("=" * 56)
    print(f" OtoClip v{__version__}  起動しました")
    print(f" PC で開く  : {local_url}")
    print(f" スマホで開く: {phone_url}")
    print("   （PC と同じ Wi-Fi に接続し、画面の QR コードを読み取ってください）")
    print(f" 保存先    : {app.manager.out_dir}")
    if not app.manager.ffmpeg:
        print(" [警告] ffmpeg が見つかりません。MP3 変換ができません。")
    print(" 終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。")
    print("=" * 56)

    if os.environ.get("OTOCLIP_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(local_url)).start()

    try:
        from waitress import serve

        serve(app, host=host, port=port, threads=8, _quiet=True)
    except OSError as e:
        print(f"ポート {port} を使用できません（{e}）。すでに起動していないか確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
