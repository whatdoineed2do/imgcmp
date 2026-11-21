#!/usr/bin/env python3
"""Compare CIELAB, chroma/saturation, and sharpness metrics between two images."""

import argparse
import json
import sys
import numpy as np
from skimage import color, filters, io


def load_rgb_float(path: str) -> np.ndarray:
    img = io.imread(path)
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    elif img.shape[-1] == 4:
        img = img[..., :3]
    if np.issubdtype(img.dtype, np.integer):
        max_val = float(np.iinfo(img.dtype).max)
        return img.astype(np.float64) / max_val
    return np.clip(img.astype(np.float64), 0.0, 1.0)


def analyze_image(path: str) -> dict:
    rgb = load_rgb_float(path)
    lab = color.rgb2lab(rgb)  # D65 standard illuminant
    hsv = color.rgb2hsv(rgb)

    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    chroma = np.hypot(a, b)
    hsv_sat = hsv[..., 1]

    # Luminance-based sharpness/micro-contrast proxies
    lum = np.clip(L / 100.0, 0.0, 1.0)
    sobel_mag = filters.sobel(lum)
    laplacian = filters.laplace(lum)

    return {
        "L_mean": float(np.mean(L)),
        "L_median": float(np.median(L)),
        "a_mean": float(np.mean(a)),
        "a_median": float(np.median(a)),
        "b_mean": float(np.mean(b)),
        "b_median": float(np.median(b)),
        "chroma_mean": float(np.mean(chroma)),
        "chroma_median": float(np.median(chroma)),
        "chroma_p90": float(np.percentile(chroma, 90)),
        "hsv_sat_mean": float(np.mean(hsv_sat)),
        "hsv_sat_p90": float(np.percentile(hsv_sat, 90)),
        "sobel_mean": float(np.mean(sobel_mag)),
        "sobel_p90": float(np.percentile(sobel_mag, 90)),
        "laplacian_var": float(np.var(laplacian)),
    }


def build_comparison(path_a: str, path_b: str) -> dict:
    stats_a = analyze_image(path_a)
    stats_b = analyze_image(path_b)
    deltas = {}

    for key in stats_a:
        val_a = stats_a[key]
        val_b = stats_b[key]
        diff = val_a - val_b
        pct = ((val_a - val_b) / abs(val_b) * 100.0) if abs(val_b) > 1e-12 else 0.0
        deltas[key] = {
            "diff_a_minus_b": diff,
            "pct_diff_a_vs_b": pct,
        }

    return {
        "image_a": path_a,
        "image_b": path_b,
        "metrics_a": stats_a,
        "metrics_b": stats_b,
        "deltas": deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute and compare CIELAB, saturation, and sharpness metrics for two images."
    )
    parser.add_argument("image_a", help="First image path (e.g., 55mmf35.jpg)")
    parser.add_argument("image_b", help="Second image path (e.g., 55mmf28.jpg)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of a formatted table.",
    )
    args = parser.parse_args()

    result = build_comparison(args.image_a, args.image_b)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    stats_a = result["metrics_a"]
    stats_b = result["metrics_b"]

    print(f"Image A: {args.image_a}")
    print(f"Image B: {args.image_b}")
    print("-" * 78)
    print(f"{'Metric':<18} {'Image A':>14} {'Image B':>14} {'Diff (A - B)':>16} {'% Diff (A vs B)':>14}")
    print("-" * 78)

    for key in stats_a:
        val_a = stats_a[key]
        val_b = stats_b[key]
        diff = result["deltas"][key]["diff_a_minus_b"]
        pct = result["deltas"][key]["pct_diff_a_vs_b"]
        print(f"{key:<18} {val_a:>14.4f} {val_b:>14.4f} {diff:>+16.4f} {pct:>+13.2f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())