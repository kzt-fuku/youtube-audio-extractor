#!/bin/bash
# OtoClip の起動（macOS / Linux）。start_mac.command からも呼ばれます。
cd "$(dirname "$0")" || exit 1

find_python() {
  local c
  for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python; do
    case "$c" in
      /*) [ -x "$c" ] || continue ;;
      *)
        command -v "$c" >/dev/null 2>&1 || continue
        # Xcode コマンドラインツール未導入の /usr/bin/python3 は導入ダイアログが出るだけなので除外
        if [ "$(uname)" = Darwin ] && [ "$(command -v "$c")" = "/usr/bin/$c" ] && ! xcode-select -p >/dev/null 2>&1; then
          continue
        fi
        ;;
    esac
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

PY=$(find_python) || {
  echo "Python 3.10 以上が見つかりません。"
  echo "https://www.python.org/downloads/ からインストールしてから、もう一度開いてください。"
  read -r -p "Enter キーで閉じます "
  exit 1
}
exec "$PY" start.py
