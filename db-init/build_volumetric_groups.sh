#!/bin/sh
set -eu
set -o pipefail 2>/dev/null || true

CSV="${1:-}"
if [ -z "$CSV" ] || [ ! -f "$CSV" ]; then
  echo "[build_volumetric_groups] CSV missing"
  exit 1
fi

echo "[build_volumetric_groups] stub ??full CSV parse lands in later phase"
echo "[build_volumetric_groups] skip import for now"
exit 0
