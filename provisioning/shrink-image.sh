#!/bin/bash
# shrink-image.sh - macOS: shrink a captured golden image with PiShrink inside
# a privileged Linux container (Colima). Result flashes to any card >= ~4GB
# and auto-expands on first boot.
#
# Usage:
#   ./shrink-image.sh <image.img.gz> [output.img.gz]
#
# Requires: brew install colima docker   (first run: colima start)

set -euo pipefail

IN="${1:-}"
OUT="${2:-$IN}"
if [[ -z "$IN" || ! -f "$IN" ]]; then
    echo "Usage: $0 <image.img.gz> [output.img.gz]"
    exit 1
fi
IN_ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
IN_DIR="$(dirname "$IN_ABS")"

if ! docker info >/dev/null 2>&1; then
    echo ">>> Starting Colima VM"
    colima start --cpu 4 --memory 4 --disk 60
fi

docker volume create pishrink-scratch >/dev/null
trap 'docker volume rm pishrink-scratch >/dev/null 2>&1 || true' EXIT

docker run --rm --privileged \
    -v "$IN_DIR":/host \
    -v pishrink-scratch:/scratch \
    debian:bookworm-slim bash -c "
set -e
apt-get update -qq && apt-get install -y -qq parted e2fsprogs pigz wget >/dev/null
wget -q https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh -O /usr/local/bin/pishrink.sh
chmod +x /usr/local/bin/pishrink.sh
echo '>>> Decompressing'
pigz -dc '/host/$(basename "$IN_ABS")' > /scratch/img.img
echo '>>> Shrinking'
pishrink.sh -z -a /scratch/img.img
cp /scratch/img.img.gz /host/.shrunk-tmp.img.gz
"
mv "$IN_DIR/.shrunk-tmp.img.gz" "$OUT_ABS"
echo "Shrunk image: $OUT_ABS"
ls -lh "$OUT_ABS"
