#!/bin/bash
# capture-image.sh - macOS: read the finalized golden SD card into a gzipped
# image file.
#
# Usage:
#   ./capture-image.sh [--disk diskN] [--out <path.img.gz>]
#
# Default output: ../../trap-installer/images/trap-imx708-golden.img.gz
# (next to the legacy golden images).
#
# Note: the image is full card size (gzip helps a lot since free space is
# mostly zeros after a fresh build). For a truly shrunk image run PiShrink on
# Linux/WSL/Docker - see BUILD.md.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DISK=""
OUT="$SCRIPT_DIR/../../trap-installer/images/trap-imx708-golden.img.gz"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --disk) DISK="$2"; shift 2;;
        --out) OUT="$2"; shift 2;;
        *) echo "Unknown argument: $1"; exit 1;;
    esac
done

if [[ -z "$DISK" ]]; then
    echo ">>> Looking for an external SD card..."
    CANDIDATES=$(diskutil list external physical | awk '/^\/dev\/disk/{print $1}' | sed 's|/dev/||')
    COUNT=$(echo "$CANDIDATES" | grep -c . || true)
    if [[ "$COUNT" -eq 0 ]]; then
        echo "ERROR: no external disk found. Insert the golden SD card (or pass --disk diskN)."
        exit 1
    elif [[ "$COUNT" -gt 1 ]]; then
        echo "ERROR: multiple external disks found; specify one with --disk diskN:"
        echo "$CANDIDATES"
        exit 1
    fi
    DISK="$CANDIDATES"
fi

echo
echo "======================== SOURCE DISK ========================"
diskutil list "/dev/$DISK"
echo "============================================================="
echo "Output: $OUT"
read -r -p "Read this card into the golden image? Type 'yes' to continue: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "Aborted."
    exit 1
fi

mkdir -p "$(dirname "$OUT")"
diskutil unmountDisk "/dev/$DISK"

echo ">>> Reading card (several minutes)..."
sudo dd if="/dev/r$DISK" bs=4m status=progress | gzip > "$OUT"

diskutil eject "/dev/$DISK"
echo
echo "Golden image written to: $OUT"
ls -lh "$OUT"
echo
echo "Flash new trap cards with:"
echo "  gzcat '$OUT' | sudo dd of=/dev/rdiskN bs=4m status=progress"
echo "(or use Raspberry Pi Imager 'Use custom' - skip all customization)"
