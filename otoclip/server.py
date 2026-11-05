"""OtoClip の Web サーバー。PC のブラウザと、同じ Wi-Fi のスマホから使える。"""
from __future__ import annotations

import ipaddress
import json
import os
import secrets
import socket
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, request, send_from_directory

from . import __version__
from .downloader import DownloadManager, extract_url

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATE_DIR = ROOT_DIR / ".otoclip"
CONFIG_PATH = STATE_DIR / "config.json"
COOKIE = "otoclip_token"


def load_config() -> dict:
    STATE_DIR.mkdir(exist_ok=True)
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cfg = {}
    changed = False
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(16)
        changed = True
    if not cfg.get("download_dir"):
        music = Path.home() / "Music"
        cfg["download_dir"] = str((music if music.is_dir() else ROOT_DIR / "downloads") / "OtoClip")
        changed = True
    cfg.setdefault("port", 8765)
    if changed:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # 環境変数で上書き可能
    if os.environ.get("OTOCLIP_DIR"):
        cfg["download_dir"] = os.environ["OTOCLIP_DIR"]
    if os.environ.get("OTOCLIP_PORT"):
        cfg["port"] = int(os.environ["OTOCLIP_PORT"])
    cfg["allow_any_site"] = os.environ.get("OTOCLIP_ALLOW_ANY") == "1"
    return cfg


def lan_ip() -> str:
    """スマホから接続するための PC の LAN 内 IP を推定する（実際には送信しない）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def create_app(cfg: dict) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["JSON_AS_ASCII"] = False
    manager = DownloadManager(Path(cfg["download_dir"]).expanduser())
    token = cfg["token"]
    static_dir = APP_DIR / "static"

    def is_local() -> bool:
        try:
            return ipaddress.ip_address(request.remote_addr or "").is_loopback
        except ValueError:
            return False

    @app.before_request
    def auth():
        # PC 本体からは無条件で許可。スマホなど他端末は QR コードの合言葉が必要。
        if is_local():
            return None
        t = request.args.get("t")
        if t and secrets.compare_digest(t, token):
            args = {k: v for k, v in request.args.items() if k != "t"}
            from urllib.parse import urlencode

            target = request.path + ("?" + urlencode(args) if args else "")
            resp = redirect(target)
            resp.set_cookie(COOKIE, token, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax")
            return resp
        c = request.cookies.get(COOKIE, "")
        if c and secrets.compare_digest(c, token):
            return None
        if request.path.startswith("/api/"):
            return jsonify(error="unauthorized"), 401
        return (
            "<meta name=viewport content='width=device-width'>"
            "<p style='font-family:sans-serif;padding:16px'>PC の OtoClip 画面に出ている QR コードから開いてください。</p>",
            401,
        )

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    # ---------- 画面 ----------
    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html", max_age=0)

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(static_dir, name, max_age=0)

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(static_dir, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.get("/sw.js")
    def sw():
        return send_from_directory(static_dir, "sw.js", mimetype="text/javascript", max_age=0)

    # ---------- API ----------
    @app.get("/api/info")
    def info():
        ip = lan_ip()
        phone_url = f"http://{ip}:{cfg['port']}/?t={token}"
        data = {
            "version": __version__,
            "is_local": is_local(),
            "download_dir": str(manager.out_dir) if is_local() else "",
            "ffmpeg": bool(manager.ffmpeg),
            "js_runtime": bool(manager.deno),
        }
        if is_local():
            import segno

            data["phone_url"] = phone_url
            data["qr_svg"] = segno.make(phone_url, error="m").svg_inline(scale=5, dark="#111", light="#fff")
        return jsonify(data)

    @app.post("/api/jobs")
    def create_job():
        body = request.get_json(silent=True) or {}
        url = extract_url(str(body.get("url", "")), cfg["allow_any_site"])
        if not url:
            return jsonify(error="YouTube の URL が見つかりません。"), 400
        job = manager.submit(url, str(body.get("quality", "192")), bool(body.get("playlist")))
        return jsonify(job.to_dict()), 201

    @app.get("/api/jobs")
    def list_jobs():
        return jsonify(manager.list_jobs())

    @app.delete("/api/jobs/<job_id>")
    def delete_job(job_id):
        return jsonify(ok=manager.remove_job(job_id))

    @app.get("/api/library")
    def library():
        return jsonify(manager.library())

    @app.get("/files/<path:name>")
    def get_file(name):
        if "/" in name or "\\" in name or not name.endswith(".mp3"):
            abort(404)
        as_attachment = request.args.get("dl") == "1"
        return send_from_directory(manager.out_dir, name, as_attachment=as_attachment, mimetype="audio/mpeg")

    @app.delete("/files/<path:name>")
    def delete_file(name):
        if "/" in name or "\\" in name or not name.endswith(".mp3"):
            abort(404)
        p = (manager.out_dir / name).resolve()
        if p.parent != manager.out_dir.resolve() or not p.exists():
            abort(404)
        p.unlink()
        return jsonify(ok=True)

    @app.post("/api/open-folder")
    def open_folder():
        if not is_local():
            abort(403)
        import subprocess
        import sys

        path = str(manager.out_dir)
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return jsonify(ok=True)

    app.manager = manager  # テスト用
    return app
