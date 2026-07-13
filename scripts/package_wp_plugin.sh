#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_SRC="$ROOT_DIR/modules/exchange_rates/wp-plugin-exchange"
BUILD_DIR="$ROOT_DIR/dist/wp-plugin"
PACKAGE_NAME="ratehubfx-exchange-rates"
PACKAGE_DIR="$BUILD_DIR/$PACKAGE_NAME"
ZIP_PATH="$BUILD_DIR/$PACKAGE_NAME.zip"

rm -rf "$BUILD_DIR"
mkdir -p "$PACKAGE_DIR"

rsync -a \
  --exclude='.DS_Store' \
  --exclude='*.log' \
  "$PLUGIN_SRC/" "$PACKAGE_DIR/"

(
  cd "$BUILD_DIR"
  zip -qr "$ZIP_PATH" "$PACKAGE_NAME"
)

echo "Built $ZIP_PATH"
