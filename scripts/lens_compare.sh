#!/usr/bin/env bash
set -euo pipefail

JSON_MODE=0
POSITIONAL=()

for arg in "$@"; do
  case "$arg" in
    --json)
      JSON_MODE=1
      ;;
    *)
      POSITIONAL+=("$arg")
      ;;
  esac
done

if [[ "${#POSITIONAL[@]}" -lt 2 ]]; then
  echo "Usage: $0 [--json] <image_a> <image_b> [crop_a_WxH+X+Y] [crop_b_WxH+X+Y]" >&2
  exit 1
fi

IMG_A="${POSITIONAL[0]}"
IMG_B="${POSITIONAL[1]}"
CROP_A="${POSITIONAL[2]:-}"
CROP_B="${POSITIONAL[3]:-}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/lens_compare.py"

for cmd in exiftool python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found." >&2
    exit 1
  fi
done

if [[ -n "$CROP_A" || -n "$CROP_B" ]]; then
  if [[ -z "$CROP_A" || -z "$CROP_B" ]]; then
    echo "Error: provide both crop geometries or neither." >&2
    exit 1
  fi
  if ! command -v magick >/dev/null 2>&1; then
    echo "Error: ImageMagick 'magick' is required for cropping." >&2
    exit 1
  fi
fi

if [[ "$JSON_MODE" -eq 1 ]]; then
  {
    echo "=== EXIF Metadata ==="
    exiftool -s -s -s \
      -FileName -Model -LensInfo -LensID -FocalLength -FNumber \
      -ExposureTime -ISO -WhiteBalance -Flash \
      "$IMG_A" "$IMG_B"
  } >&2
else
  echo "=== EXIF Metadata ==="
  exiftool -s -s -s \
    -FileName -Model -LensInfo -LensID -FocalLength -FNumber \
    -ExposureTime -ISO -WhiteBalance -Flash \
    "$IMG_A" "$IMG_B"
  echo ""
fi

TARGET_A="$IMG_A"
TARGET_B="$IMG_B"
TMP_DIR=""

cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

if [[ -n "$CROP_A" && -n "$CROP_B" ]]; then
  TMP_DIR="$(mktemp -d)"
  TARGET_A="${TMP_DIR}/roi_a.png"
  TARGET_B="${TMP_DIR}/roi_b.png"
  magick "$IMG_A" -crop "$CROP_A" +repage "$TARGET_A"
  magick "$IMG_B" -crop "$CROP_B" +repage "$TARGET_B"
  if [[ "$JSON_MODE" -eq 1 ]]; then
    echo "=== Cropped ROIs: A=$CROP_A, B=$CROP_B ===" >&2
  else
    echo "=== Cropped ROIs: A=$CROP_A, B=$CROP_B ==="
  fi
fi

if [[ "$JSON_MODE" -eq 1 ]]; then
  python3 "$PY_SCRIPT" --json "$TARGET_A" "$TARGET_B"
else
  echo "=== Quantitative Comparison ==="
  python3 "$PY_SCRIPT" "$TARGET_A" "$TARGET_B"
fi