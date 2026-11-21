#!/usr/bin/env python3
"""Compare CIELAB, per-color sector saturation, sharpness, and EXIF metadata."""

import argparse
import json
import os
import subprocess
import sys
import numpy as np
from skimage import color, filters, io

# Hue angle sectors in degrees [0, 360), computed via atan2(b*, a*) mod 360
COLOR_SECTORS = [
    ("red_magenta", 330.0, 30.0),
    ("warm_yellow_amber", 30.0, 105.0),
    ("green", 105.0, 165.0),
    ("cyan_blue", 165.0, 255.0),
    ("violet_purple", 255.0, 330.0),
]

RELEVANT_EXIF_TAGS = [
    "FileName",
    "FileSize",
    "ImageSize",
    "Make",
    "Model",
    "LensInfo",
    "LensID",
    "LensSpec",
    "FocalLength",
    "FocalLengthIn35mmFormat",
    "FNumber",
    "ApertureValue",
    "ExposureTime",
    "ShutterSpeedValue",
    "ISO",
    "ExposureCompensation",
    "ExposureProgram",
    "MeteringMode",
    "WhiteBalance",
    "ColorSpace",
    "Flash",
    "DateTimeOriginal",
]


def extract_exif(image_path: str) -> dict:
    """Extract relevant EXIF/metadata tags via exiftool as a clean dictionary."""
    try:
        proc = subprocess.run(
            ["exiftool", "-j", "-n", *[f"-{tag}" for tag in RELEVANT_EXIF_TAGS], image_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            records = json.loads(proc.stdout)
            if isinstance(records, list) and records:
                raw = dict(records[0])
                raw.pop("SourceFile", None)
                return raw
    except FileNotFoundError:
        pass
    return {}


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


def sector_mask(hue_deg: np.ndarray, chroma: np.ndarray, min_chroma: float, start: float, end: float) -> np.ndarray:
    active = chroma >= min_chroma
    if start <= end:
        in_hue = (hue_deg >= start) & (hue_deg < end)
    else:
        in_hue = (hue_deg >= start) | (hue_deg < end)
    return active & in_hue


def summarize_sector(
    mask: np.ndarray,
    total_pixels: int,
    L: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    chroma: np.ndarray,
) -> dict:
    count = int(np.count_nonzero(mask))
    pixel_pct = (count / total_pixels * 100.0) if total_pixels > 0 else 0.0
    if count == 0:
        return {
            "pixel_count": 0,
            "pixel_pct": 0.0,
            "L_mean": None,
            "a_mean": None,
            "b_mean": None,
            "chroma_mean": None,
            "chroma_p90": None,
        }
    return {
        "pixel_count": count,
        "pixel_pct": float(pixel_pct),
        "L_mean": float(np.mean(L[mask])),
        "a_mean": float(np.mean(a[mask])),
        "b_mean": float(np.mean(b[mask])),
        "chroma_mean": float(np.mean(chroma[mask])),
        "chroma_p90": float(np.percentile(chroma[mask], 90)),
    }


def analyze_image(path: str, min_chroma: float) -> dict:
    rgb = load_rgb_float(path)
    lab = color.rgb2lab(rgb)  # D65 standard illuminant
    hsv = color.rgb2hsv(rgb)

    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    chroma = np.hypot(a, b)
    hue_deg = np.mod(np.degrees(np.arctan2(b, a)), 360.0)
    hsv_sat = hsv[..., 1]

    lum = np.clip(L / 100.0, 0.0, 1.0)
    sobel_mag = filters.sobel(lum)
    laplacian = filters.laplace(lum)

    total_pixels = L.size
    by_color = {}
    for name, start, end in COLOR_SECTORS:
        mask = sector_mask(hue_deg, chroma, min_chroma, start, end)
        by_color[name] = summarize_sector(mask, total_pixels, L, a, b, chroma)

    colored_pixels = int(np.count_nonzero(chroma >= min_chroma))

    return {
        "global": {
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
            "colored_pixel_pct": float(colored_pixels / total_pixels * 100.0) if total_pixels > 0 else 0.0,
            "sobel_mean": float(np.mean(sobel_mag)),
            "sobel_p90": float(np.percentile(sobel_mag, 90)),
            "laplacian_var": float(np.var(laplacian)),
        },
        "by_color": by_color,
    }


def classify_bias(diff: float, threshold: float, pos_label: str, neg_label: str, neutral_label: str) -> str:
    if diff > threshold:
        return pos_label
    if diff < -threshold:
        return neg_label
    return neutral_label


def build_summary(stats_a: dict, stats_b: dict, color_deltas: dict) -> dict:
    ga = stats_a["global"]
    gb = stats_b["global"]

    diff_b = ga["b_mean"] - gb["b_mean"]
    diff_a = ga["a_mean"] - gb["a_mean"]
    diff_L = ga["L_mean"] - gb["L_mean"]
    diff_chroma = ga["chroma_mean"] - gb["chroma_mean"]
    diff_sharp = ga["sobel_mean"] - gb["sobel_mean"]

    warmth_bias = classify_bias(
        diff_b, 0.25, "A warmer / more yellow than B", "A cooler / more blue than B", "Neutral warmth balance"
    )
    red_green_bias = classify_bias(
        diff_a, 0.20, "A leans more red/magenta than B", "A leans more green than B", "Neutral red-green balance"
    )
    lightness_bias = classify_bias(
        diff_L, 0.50, "A brighter/higher L* than B", "A darker/lower L* than B", "Similar overall lightness (L*)"
    )
    chroma_bias = classify_bias(
        diff_chroma, 0.35, "A higher overall chroma than B", "A lower overall chroma than B", "Similar overall chroma"
    )
    sharpness_bias = classify_bias(
        diff_sharp, 0.0015, "A higher edge gradient/micro-contrast than B", "A lower edge gradient/micro-contrast than B", "Similar edge gradient"
    )

    best_sector = None
    best_abs_delta = 0.0
    best_direction = None
    for sector, info in color_deltas.items():
        c_delta = info["chroma_mean"]["diff_a_minus_b"]
        if c_delta is not None and abs(c_delta) > best_abs_delta:
            best_abs_delta = abs(c_delta)
            best_sector = sector
            best_direction = "higher chroma in A" if c_delta > 0 else "higher chroma in B"

    favors = []
    if diff_chroma > 0.35:
        favors.append("higher saturation/chroma")
    elif diff_chroma < -0.35:
        favors.append("softer/more muted saturation")
    if diff_b > 0.25:
        favors.append("warmer yellow/amber tones")
    elif diff_b < -0.25:
        favors.append("cooler blue/cyan tones")
    if diff_sharp > 0.0015:
        favors.append("stronger local micro-contrast")
    elif diff_sharp < -0.0015:
        favors.append("gentler local micro-contrast")

    summary_text = (
        f"Image A tends to favour {', '.join(favors)} relative to Image B."
        if favors
        else "Image A and Image B are closely matched across global chroma, warmth, and micro-contrast."
    )
    if best_sector and best_abs_delta >= 0.25:
        summary_text += f" Largest per-color chroma shift: {best_sector} ({best_direction}, {best_abs_delta:+.4f})."

    return {
        "warmth_bias": warmth_bias,
        "red_green_bias": red_green_bias,
        "lightness_bias": lightness_bias,
        "chroma_bias": chroma_bias,
        "sharpness_bias": sharpness_bias,
        "largest_chroma_shift": {
            "sector": best_sector,
            "diff_a_minus_b": (
                color_deltas[best_sector]["chroma_mean"]["diff_a_minus_b"] if best_sector else None
            ),
            "direction": best_direction,
        },
        "narrative": summary_text,
    }


def make_delta(val_a, val_b) -> dict:
    if val_a is None or val_b is None:
        return {"diff_a_minus_b": None, "pct_diff_a_vs_b": None}
    diff = val_a - val_b
    pct = ((val_a - val_b) / abs(val_b) * 100.0) if abs(val_b) > 1e-12 else 0.0
    return {"diff_a_minus_b": float(diff), "pct_diff_a_vs_b": float(pct)}


def build_image_descriptor(
    analyzed_path: str,
    source_path: str | None = None,
    label: str | None = None,
    crop: str | None = None,
    exif_override: dict | None = None,
) -> dict:
    orig = source_path or analyzed_path
    exif_data = exif_override if exif_override is not None else extract_exif(orig)
    name = label or exif_data.get("FileName") or os.path.basename(orig)
    return {
        "name": name,
        "path": orig,
        "analyzed_path": analyzed_path,
        "crop": crop,
        "exif": exif_data,
    }


def build_comparison(
    path_a: str,
    path_b: str,
    min_chroma: float,
    source_a: str | None = None,
    source_b: str | None = None,
    label_a: str | None = None,
    label_b: str | None = None,
    crop_a: str | None = None,
    crop_b: str | None = None,
    exif_a: dict | None = None,
    exif_b: dict | None = None,
) -> dict:
    stats_a = analyze_image(path_a, min_chroma)
    stats_b = analyze_image(path_b, min_chroma)

    global_deltas = {
        key: make_delta(stats_a["global"][key], stats_b["global"][key])
        for key in stats_a["global"]
    }

    color_deltas = {}
    for sector, _, _ in COLOR_SECTORS:
        sa = stats_a["by_color"][sector]
        sb = stats_b["by_color"][sector]
        color_deltas[sector] = {
            metric: make_delta(sa[metric], sb[metric])
            for metric in ("pixel_pct", "L_mean", "a_mean", "b_mean", "chroma_mean", "chroma_p90")
        }

    summary = build_summary(stats_a, stats_b, color_deltas)

    return {
        "image_a": build_image_descriptor(path_a, source_a, label_a, crop_a, exif_a),
        "image_b": build_image_descriptor(path_b, source_b, label_b, crop_b, exif_b),
        "min_chroma_threshold": min_chroma,
        "summary": summary,
        "metrics_a": stats_a,
        "metrics_b": stats_b,
        "deltas": {
            "global": global_deltas,
            "by_color": color_deltas,
        },
    }


def parse_exif_arg(raw: str | None) -> dict | None:
    if not raw:
        return None
    if os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute and compare CIELAB, per-color sector saturation, and sharpness metrics."
    )
    parser.add_argument("image_a", help="First image path (e.g., 55mmf35.jpg)")
    parser.add_argument("image_b", help="Second image path (e.g., 55mmf28.jpg)")
    parser.add_argument("--source-a", default=None, help="Original source path for Image A if cropped.")
    parser.add_argument("--source-b", default=None, help="Original source path for Image B if cropped.")
    parser.add_argument("--label-a", default=None, help="Display name for Image A.")
    parser.add_argument("--label-b", default=None, help="Display name for Image B.")
    parser.add_argument("--crop-a", default=None, help="Crop geometry applied to Image A.")
    parser.add_argument("--crop-b", default=None, help="Crop geometry applied to Image B.")
    parser.add_argument("--exif-a", default=None, help="JSON string or file path with pre-extracted EXIF for A.")
    parser.add_argument("--exif-b", default=None, help="JSON string or file path with pre-extracted EXIF for B.")
    parser.add_argument(
        "--min-chroma",
        type=float,
        default=8.0,
        help="Minimum CIELAB chroma C* to include a pixel in color sector stats (default: 8.0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    args = parser.parse_args()

    result = build_comparison(
        path_a=args.image_a,
        path_b=args.image_b,
        min_chroma=args.min_chroma,
        source_a=args.source_a,
        source_b=args.source_b,
        label_a=args.label_a,
        label_b=args.label_b,
        crop_a=args.crop_a,
        crop_b=args.crop_b,
        exif_a=parse_exif_arg(args.exif_a),
        exif_b=parse_exif_arg(args.exif_b),
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    ga = result["metrics_a"]["global"]
    gb = result["metrics_b"]["global"]
    summary = result["summary"]

    print(f"Image A: {result['image_a']['name']} ({result['image_a']['path']})")
    print(f"Image B: {result['image_b']['name']} ({result['image_b']['path']})")
    print(f"Min Chroma Threshold: {args.min_chroma:.1f}")
    print("-" * 78)
    print(f"{'Global Metric':<20} {'Image A':>13} {'Image B':>13} {'Diff (A-B)':>15} {'% Diff':>13}")
    print("-" * 78)
    for key in ga:
        va = ga[key]
        vb = gb[key]
        d = result["deltas"]["global"][key]
        print(f"{key:<20} {va:>13.4f} {vb:>13.4f} {d['diff_a_minus_b']:>+15.4f} {d['pct_diff_a_vs_b']:>+12.2f}%")

    print("\n" + "-" * 78)
    print(f"{'Color Sector':<20} {'%Px A':>8} {'%Px B':>8} {'Chroma A':>11} {'Chroma B':>11} {'dChroma':>11}")
    print("-" * 78)
    for sector, _, _ in COLOR_SECTORS:
        ca = result["metrics_a"]["by_color"][sector]
        cb = result["metrics_b"]["by_color"][sector]
        dc = result["deltas"]["by_color"][sector]["chroma_mean"]["diff_a_minus_b"]
        c_a_str = f"{ca['chroma_mean']:>11.2f}" if ca["chroma_mean"] is not None else f"{'n/a':>11}"
        c_b_str = f"{cb['chroma_mean']:>11.2f}" if cb["chroma_mean"] is not None else f"{'n/a':>11}"
        dc_str = f"{dc:>+11.2f}" if dc is not None else f"{'n/a':>11}"
        print(f"{sector:<20} {ca['pixel_pct']:>7.1f}% {cb['pixel_pct']:>7.1f}% {c_a_str} {c_b_str} {dc_str}")

    print("\n=== Summary & Bias ===")
    print(f"Narrative    : {summary['narrative']}")
    print(f"Warmth       : {summary['warmth_bias']}")
    print(f"Red-Green    : {summary['red_green_bias']}")
    print(f"Lightness    : {summary['lightness_bias']}")
    print(f"Chroma       : {summary['chroma_bias']}")
    print(f"Sharpness    : {summary['sharpness_bias']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
