# Lens Comparison Toolset (`compare_lenses.sh` & `lens_compare.py`)

## Intent & Overview

These scripts provide a repeatable, objective way to compare two lens test images (such as two macro shots taken with different lenses at the same aperture and lighting). Rather than relying solely on subjective visual impressions, the toolset:

1. **Verifies capture consistency** by extracting key EXIF metadata (`exiftool`) and embedding it directly into the structured JSON output alongside image identifiers and crop info.
2. **Isolates matched regions of interest (ROIs)** via optional ImageMagick (`magick`) cropping so framing shifts or field curvature differences do not skew the comparison.
3. **Measures global and per-color perceptual metrics** in Python (`lens_compare.py`) using the **CIELAB** color space (D65 standard illuminant), hue-sector partitioning, HSV saturation, and luminance edge-gradient filters.
4. **Generates automated bias summaries** (e.g., warmer vs. cooler, higher vs. lower chroma, and which color sector shifted the most).
5. **Outputs either a formatted report or structured JSON** (`--json`) for logging, scripting, or `jq` queries.

## Requirements

* **Bash**
* **ExifTool** (`exiftool`)
* **ImageMagick** (`magick`) — required only when passing crop geometries
* **Python 3** with `numpy` and `scikit-image`

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

### Direct Python CLI Options

When calling `lens_compare.py` directly, you can also adjust the minimum chroma threshold, supply source paths/labels/crops, or pass pre-extracted EXIF JSON:

```bash
python3 lens_compare.py --min-chroma 8.0 --json 55mmf35.jpg 55mmf28.jpg
```

## JSON Structure: `image_a` & `image_b` Objects

In the JSON output, `image_a` and `image_b` are objects describing each input image, any applied crop, and extracted EXIF metadata:

```json
{
  "image_a": {
    "name": "55mmf35.jpg",
    "path": "55mmf35.jpg",
    "analyzed_path": "55mmf35.jpg",
    "crop": null,
    "exif": {
      "FileName": "55mmf35.jpg",
      "Make": "NIKON CORPORATION",
      "Model": "NIKON D800",
      "FocalLength": 55,
      "FNumber": 4,
      "ExposureTime": 0.005,
      "ISO": 100,
      "WhiteBalance": 0,
      "Flash": 1
    }
  }
}
```

* **`name`**: Display name or filename of the image (custom label if provided, otherwise `FileName` from EXIF or the source basename).
* **`path`**: Path to the original source image being compared.
* **`analyzed_path`**: Path to the actual image file read for pixel analysis (which may be a temporary cropped PNG when ROI cropping is used).
* **`crop`**: ImageMagick crop geometry (`WxH+X+Y`) applied to this image, or `null` when analyzing full-frame/un-cropped input.
* **`exif`**: Dictionary of relevant EXIF/file tags retrieved via `exiftool -j -n` (such as `Model`, `LensInfo`, `FocalLength`, `FNumber`, `ExposureTime`, `ISO`, `WhiteBalance`, `ColorSpace`, `Flash`, and `DateTimeOriginal`), or an empty object `{}` if unavailable.

## Metric Definitions

### 1. Global CIELAB Lightness & Color Axes (`metrics_a.global`, `metrics_b.global`)

CIELAB separates perceptual brightness from color chromaticity, making it far more consistent for optical comparisons than raw RGB values.

| Metric | Range / Units | Meaning |
| :--- | :--- | :--- |
| **`L_mean`** | `0` to `100` | **Average perceptual lightness ($L^*$).** `0` is pure black and `100` is diffuse white. Useful for verifying that exposure equalisation between two frames is closely matched. |
| **`L_median`** | `0` to `100` | **Median perceptual lightness ($L^*$).** Less sensitive than `L_mean` to small specular highlights (e.g., flash glints on metal) or deep pin-prick shadows. |
| **`a_mean`** | Roughly `-128` to `+127` | **Average green–red color balance ($a^*$).** Negative values lean toward green/cyan; positive values lean toward magenta/red. |
| **`a_median`** | Roughly `-128` to `+127` | **Median green–red color balance ($a^*$).** Shows the central tendency of the $a^*$ axis without extreme color outliers. |
| **`b_mean`** | Roughly `-128` to `+127` | **Average blue–yellow color balance ($b^*$).** Negative values lean toward blue; positive values lean toward yellow/warm amber. |
| **`b_median`** | Roughly `-128` to `+127` | **Median blue–yellow color balance ($b^*$).** Shows the central tendency of the $b^*$ axis without extreme color outliers. |

### 2. Global Chroma, Saturation & Sharpness (`metrics_a.global`, `metrics_b.global`)

| Metric | Formula / Method | Meaning |
| :--- | :--- | :--- |
| **`chroma_mean`** | $C^* = \sqrt{(a^*)^2 + (b^*)^2}$ | **Average perceptual chroma.** Measures how far colors sit from neutral grey ($C^* = 0$). Higher values indicate richer, more saturated color rendering overall. |
| **`chroma_median`** | $C^* = \sqrt{(a^*)^2 + (b^*)^2}$ | **Median perceptual chroma.** Reflects typical color intensity across the frame/crop without being pulled upward by a few vividly colored accents. |
| **`chroma_p90`** | 90th percentile of $C^*$ | **Peak color intensity (top 10%).** Captures how strongly a lens renders the most saturated features in the frame while ignoring extreme outliers. |
| **`hsv_sat_mean`** | `0.0` to `1.0` | **Average HSV saturation.** A standard cylindrical color-model measure of color purity (`0.0` = greyscale, `1.0` = pure saturated color). |
| **`hsv_sat_p90`** | `0.0` to `1.0` | 90th-percentile HSV **saturation.** Indicates the saturation level of the more vivid parts of the image in HSV space. |
| **`colored_pixel_pct`** | `%` of pixels with $C^* \ge \text{min\_chroma}$ | **Non-neutral pixel share.** Shows what percentage of the frame/crop has enough chroma (default $C^* \ge 8.0$) to be classified into the color-sector breakdown. |
| **`sobel_mean`** | Mean Sobel gradient on $L^*/100$ | **Average edge strength / micro-contrast.** Measures the average rate of brightness change across pixels. Higher values indicate crisper fine detail and stronger local contrast. |
| **`sobel_p90`** | 90th-percentile Sobel gradient | Strong-edge **crispness.** Focuses on well-defined edges (engraving, lettering, ruler ticks) rather than smooth background areas. |
| **`laplacian_var`** | Variance of 2D Laplacian on $L^*/100$ | **High-frequency edge energy.** Sensitive to rapid second-order intensity transitions. Higher values generally indicate sharper focus/micro-contrast, though noise or highlight clipping can also raise it. |

### 3. Per-Color Sector Breakdown (`metrics_a.by_color`, `metrics_b.by_color`)

Global averages can mask color-specific behavior when cool and warm tones appear in the same frame. To isolate individual hues, pixels meeting the chroma threshold ($C^* \ge \text{min\_chroma}$) are grouped by CIELAB hue angle $h_{ab} = \operatorname{atan2}(b^*, a^*) \bmod 360^\circ$:

| Color Sector | Hue Angle Range ($h_{ab}$) | Typical Subject Tones |
| :--- | :--- | :--- |
| **`red_magenta`** | $330^\circ \text{ to } 30^\circ$ | Reds, warm skin accents, crimson/magenta inks |
| **`warm_yellow_amber`** | $30^\circ \text{ to } 105^\circ$ | Gold/bronze/copper coins, warm patina, yellows |
| **`green`** | $105^\circ \text{ to } 165^\circ$ | Foliage, greens, yellow-greens |
| **`cyan_blue`** | $165^\circ \text{ to } 255^\circ$ | Cyan banknote guilloché, sky, cool blues |
| **`violet_purple`** | $255^\circ \text{ to } 330^\circ$ | Violet/purple borders, cool magentas |

Each sector reports:

* **`pixel_count` & `pixel_pct`**: Number and percentage of total image pixels falling into that color band.
* **`L_mean`, `a_mean`, `b_mean`**: Mean CIELAB coordinates within that specific color band (or `null` if zero pixels qualify).
* **`chroma_mean` & `chroma_p90`**: Mean and 90th-percentile saturation/chroma within that color band.

### 4. Automated Summary & Bias Fields (`summary`)

The `summary` object translates the numeric deltas between Image A and Image B into human-readable directional findings:

| Field | Meaning |
| :--- | :--- |
| **`warmth_bias`** | Compares `b_mean` ($\Delta b^* > +0.25 \rightarrow$ A is warmer/more yellow; $\Delta b^* < -0.25 \rightarrow$ A is cooler/more blue). |
| **`red_green_bias`** | Compares `a_mean` ($\Delta a^* > +0.20 \rightarrow$ A leans more red/magenta; $\Delta a^* < -0.20 \rightarrow$ A leans more green). |
| **`lightness_bias`** | Compares `L_mean` ($\Delta L^* > +0.50 \rightarrow$ A is brighter; $\Delta L^* < -0.50 \rightarrow$ A is darker). |
| **`chroma_bias`** | Compares `chroma_mean` ($\Delta C^* > +0.35 \rightarrow$ A has higher overall chroma; $\Delta C^* < -0.35 \rightarrow$ A has lower overall chroma). |
| **`sharpness_bias`** | Compares `sobel_mean` ($\Delta \text{sobel} > +0.0015 \rightarrow$ A has stronger local edge gradient/micro-contrast). |
| **`largest_chroma_shift`** | Identifies which color sector (`sector`), raw difference (`diff_a_minus_b`), and direction (`direction`) experienced the largest absolute `chroma_mean` change between the two lenses. |
| **`narrative`** | A concise one- or two-sentence summary stating what Image A tends to favour relative to Image B and highlighting the largest per-color chroma shift. |

## Understanding the `deltas` Object (JSON Output)

`deltas` is split into `deltas.global` and `deltas.by_color`. Every compared metric provides:

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

## Best Practices for Accurate Results

* **Compare matched ROIs, not mismatched full frames:** If one shot includes slightly more bright background or out-of-focus area than the other, full-frame averages and sector pixel percentages will reflect framing differences as well as optical differences.
* **Match focal planes when evaluating sharpness:** At minimum focus distance on macro lenses, small shifts in camera-to-subject distance or tilt change which parts of the coin/surface are in sharpest focus. Compare identically focused features.
* **Keep exposure and white balance consistent:** Equalise brightness and apply consistent color/white-balance adjustments before measuring color bias, and watch out for blown highlights or specular flash reflections that can skew `L_mean`, chroma, and `laplacian_var`.