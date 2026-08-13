#!/bin/sh
set -eu
CSV="${1:-}"
if [ -z "$CSV" ] || [ ! -f "$CSV" ]; then
  echo "[build_volumetric_groups] CSV missing"
  exit 0
fi
echo "[build_volumetric_groups] stub — skip for bootstrap"
exit 0
