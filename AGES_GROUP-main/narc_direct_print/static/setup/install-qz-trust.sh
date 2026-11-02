#!/bin/bash
set -euo pipefail
QZDIR="/opt/qz-tray"
SRC="$(cd "$(dirname "$0")" && pwd)/override.crt"
if [ ! -d "$QZDIR" ]; then
    echo "Install QZ Tray first: wget -qO - qz.sh | bash"
    exit 1
fi
if [ ! -f "$SRC" ]; then
    echo "override.crt is missing next to this script."
    exit 1
fi
sudo cp "$SRC" "$QZDIR/override.crt"
echo "Trusted Odoo for silent print: $QZDIR/override.crt"
echo "Restart QZ Tray: pkill -f qz-tray.jar; /opt/qz-tray/qz-tray"
