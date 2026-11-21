# Lens Comparison Toolset (`compare_lenses.sh` & `lens_compare.py`)

## Intent & Overview
These scripts provide a repeatable, objective way to compare two lens test images (such as two macro shots taken with different lenses at the same aperture and lighting). Rather than relying solely on subjective visual impressions, the toolset:

1. **Verifies capture consistency** by extracting key EXIF metadata (`exiftool`).
2. **Isolates matched regions of interest (ROIs)** via optional ImageMagick (`magick`) cropping so framing shifts or field curvature differences do not skew the comparison.
3. **Measures perceptual color, saturation, and local sharpness** in Python (`lens_compare.py`) using the **CIELAB** color space (D65 standard illuminant), HSV saturation, and luminance edge-gradient filters.
4. **Outputs either a human-readable comparison table or structured JSON** (`--json`) for logging, scripting, or `jq` queries.

---

## Requirements
* **Bash**
* **ExifTool** (`exiftool`)
* **ImageMagick** (`magick`) — required only when passing crop geometries
* **Python 3** with `numpy` and `scikit-image`

---

## Usage

### Full-Frame Comparison
```bash
./compare_lenses.sh 55mmf35.jpg 55mmf28.jpg
```

### Matched-Patch (ROI) Comparison
Recommended for close-up/macro comparisons where slight framing drift or focal-plane tilt occurs. Geometry uses ImageMagick's `WxH+X+Y` format:
```bash
./compare_lenses.sh 55mmf35.jpg 55mmf28.jpg "400x400+300+250" "410x410+295+245"
```

### JSON Output
Pass `--json` to send valid JSON to `stdout` (EXIF and status lines are routed to `stderr`):
```bash
./compare_lenses.sh --json 55mmf35.jpg 55mmf28.jpg > comparison.json
```

---

## Metric Definitions

### 1. CIELAB Lightness & Color Axes
CIELAB separates perceptual brightness from color chromaticity, making it far more consistent for optical comparisons than raw RGB values.

| Metric | Range / Units | Meaning |
| :--- | :--- | :--- |
| **`L_mean`** | `0` to `100` | **Average perceptual lightness ($L^*$).** `0` is pure black and `100` is diffuse white. Useful for verifying that exposure equalisation between two frames is closely matched. |
| **`L_median`** | `0` to `100` | **Median perceptual lightness ($L^*$).** Less sensitive than `L_mean` to small specular highlights (e.g., flash glints on metal) or deep pin-prick shadows. |
| **`a_mean`** | Roughly `-128` to `+127` | **Average green–red color balance ($a^*$).** Negative values lean toward green/cyan; positive values lean toward magenta/red. |
| **`a_median`** | Roughly `-128` to `+127` | **Median green–red color balance ($a^*$).** Shows the central tendency of the $a^*$ axis without extreme color outliers. |
| **`b_mean`** | Roughly `-128` to `+127` | **Average blue–yellow color balance ($b^*$).** Negative values lean toward blue; positive values lean toward yellow/warm amber. |
| **`b_median`** | Roughly `-128` to `+127` | **Median blue–yellow color balance ($b^*$).** Shows the central tendency of the $b^*$ axis without extreme color outliers. |

---

### 2. Chroma & Saturation Metrics
These metrics quantify color intensity independently of hue.

| Metric | Formula / Scale | Meaning |
| :--- | :--- | :--- |
| **`chroma_mean`** | $C^* = \sqrt{(a^*)^2 + (b^*)^2}$ | **Average perceptual chroma.** Measures how far colors sit from neutral grey ($C^* = 0$). Higher values indicate richer, more saturated color rendering overall. |
| **`chroma_median`** | $C^* = \sqrt{(a^*)^2 + (b^*)^2}$ | **Median perceptual chroma.** Reflects typical color intensity across the frame/crop without being pulled upward by a few vividly colored accents. |
| **`chroma_p90`** | 90th percentile of $C^*$ | **Peak color intensity (top 10%).** Captures how strongly a lens renders the most saturated features in the frame (e.g., vibrant banknote ink) while ignoring the top 10% extreme outliers. |
| **`hsv_sat_mean`** | `0.0` to `1.0` | **Average HSV saturation.** A standard cylindrical color-model measure of color purity (`0.0` = greyscale, `1.0` = pure saturated color). |
| **`hsv_sat_p90`** | `0.0` to `1.0` | **90th-percentile HSV saturation.** Indicates the saturation level of the more vivid parts of the image in HSV space. |

---

### 3. Sharpness & Micro-Contrast Proxies
Computed strictly from normalized luminance ($L^* / 100$) so color differences do not bias edge detection.

| Metric | Method | Meaning |
| :--- | :--- | :--- |
| **`sobel_mean`** | Mean Sobel gradient magnitude | **Average edge strength / micro-contrast.** Measures the average rate of brightness change across all pixels. Higher values indicate crisper fine detail and stronger local contrast (assuming identical framing and noise levels). |
| **`sobel_p90`** | 90th-percentile Sobel gradient | **Strong-edge crispness.** Focuses on well-defined edges (engraving, lettering, ruler ticks) rather than smooth background areas. |
| **`laplacian_var`** | Variance of 2D Laplacian filter | **High-frequency edge energy.** Sensitive to rapid second-order intensity transitions (fine texture and sharp boundaries). Higher values generally indicate sharper focus/micro-contrast, though excessive noise or highlight clipping can also raise it. |

---

## Understanding the `deltas` Object (JSON Output)
For every metric above, the JSON output includes a `deltas` entry comparing **Image A** against **Image B**:

```json
"chroma_mean": {
  "diff_a_minus_b": 1.0590,
  "pct_diff_a_vs_b": 7.69
}
```

* **`diff_a_minus_b`**: Raw signed difference ($\text{Image A} - \text{Image B}$). Positive means Image A has a higher value; negative means Image B is higher.
* **`pct_diff_a_vs_b`**: Relative percentage difference:
  $$\frac{\text{Image A} - \text{Image B}}{|\text{Image B}|} \times 100$$
  *(Note: For signed axes like `a_mean` and `b_mean` that can sit close to `0`, `diff_a_minus_b` is more meaningful than `pct_diff_a_vs_b`.)*

---

## Best Practices for Accurate Results
* **Compare matched ROIs, not mismatched full frames:** If one shot includes slightly more bright background or out-of-focus area than the other, full-frame averages will shift even if the lenses render identically.
* **Evaluate sharpness only on in-focus planes:** Because lenses differ in field curvature (e.g., non-CRC vs. CRC macro designs), crop a small patch where both lenses are critically focused before comparing `sobel_*` and `laplacian_var`.
* **Keep RAW conversion and white balance identical:** Apply the exact same color profile, white balance temperature/tint, and exposure adjustment to both files prior to analysis.