#!/bin/sh
# 把同目录下的 .b64 还原成扩展需要的 .png 图标（克隆后跑一次即可）。
# macOS / Linux 都可用。
cd "$(dirname "$0")"
for b64 in *.png.b64; do
  out="${b64%.png.b64}.png"
  if [ ! -f "$out" ]; then
    base64 -d -i "$b64" -o "$out" 2>/dev/null || base64 -D -i "$b64" -o "$out"
  fi
done
echo "icons ready."
