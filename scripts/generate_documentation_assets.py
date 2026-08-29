"""Generate reproducible diagrams and charts for the final project guide."""

from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "tmp" / "docs_assets"
PRODUCTION_JSON = ROOT / "tmp" / "production" / "contour-auto.json"
FONT_REGULAR = Path("C:/Windows/Fonts/segoeui.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")

INK = "#0B2B24"
DEEP = "#073C32"
GREEN = "#16C79A"
MINT = "#DDF8EE"
CYAN = "#35B8E6"
GOLD = "#E5AA17"
RED = "#D65C5C"
PAPER = "#F7FBF9"
MUTED = "#55756D"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size=size)


def canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1600, 900), PAPER)
    draw = ImageDraw.Draw(image)
    draw.text((52, 42), title, fill=INK, font=font(35, bold=True))
    draw.text((52, 94), subtitle, fill=MUTED, font=font(19))
    return image, draw


def wrap_lines(text: str, width: int) -> str:
    return "\n".join(textwrap.fill(line, width=width) for line in text.splitlines())


def box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str = "",
    *,
    fill: str = "white",
    edge: str = GREEN,
    title_color: str = INK,
    body_width: int = 30,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=22, fill=fill, outline=edge, width=3)
    draw.text((x1 + 22, y1 + 18), title, fill=title_color, font=font(21, bold=True))
    if body:
        draw.multiline_text(
            (x1 + 22, y1 + 60),
            wrap_lines(body, body_width),
            fill=MUTED,
            font=font(16),
            spacing=7,
        )


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = GREEN,
    label: str | None = None,
) -> None:
    draw.line((start, end), fill=color, width=5)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 18
    wing = 8
    p1 = (
        end[0] - length * math.cos(angle) + wing * math.sin(angle),
        end[1] - length * math.sin(angle) - wing * math.cos(angle),
    )
    p2 = (
        end[0] - length * math.cos(angle) - wing * math.sin(angle),
        end[1] - length * math.sin(angle) + wing * math.cos(angle),
    )
    draw.polygon([end, p1, p2], fill=color)
    if label:
        mx = int((start[0] + end[0]) / 2)
        my = int((start[1] + end[1]) / 2)
        bbox = draw.textbbox((0, 0), label, font=font(14))
        label_width = bbox[2] - bbox[0]
        draw.rounded_rectangle((mx - label_width // 2 - 7, my - 28, mx + label_width // 2 + 7, my - 3), radius=7, fill=PAPER)
        draw.text((mx - label_width // 2, my - 27), label, fill=MUTED, font=font(14))


def save(image: Image.Image, name: str) -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    image.save(ASSET_DIR / name, format="PNG", optimize=True)


def architecture_diagram() -> None:
    image, draw = canvas(
        "JalDrishti system architecture",
        "A thin web client calls one validated API; independent services produce traceable screening evidence.",
    )
    box(draw, (55, 210, 340, 365), "React + Leaflet", "Responsive analysis panel\nInteractive satellite map\nResult layers and warnings", fill=MINT)
    box(draw, (440, 195, 750, 385), "FastAPI boundary", "Pydantic contracts\nUpload and rate limits\nTyped errors + OpenAPI\nNo-store security headers", edge=CYAN)
    box(draw, (850, 210, 1130, 365), "Contour services", "KML/KMZ safety\nGrid reconstruction\nD8 catchment", fill=MINT)
    box(draw, (1210, 210, 1535, 365), "Live-source services", "Elevation + imagery\nRainfall climatology\nSurface screening", fill=MINT)
    box(draw, (440, 570, 750, 735), "Shared science core", "Priority-Flood + D8\nCandidate ranking\nRunoff + pond geometry", fill="#E9F6FB", edge=CYAN)
    box(draw, (850, 570, 1160, 735), "Optional history", "PostgreSQL + Alembic\nDisabled by default\nAPI-key protected", fill="#F4F4F4", edge=MUTED)
    box(draw, (1230, 570, 1535, 735), "External providers", "Open-Meteo / NASA POWER\nEsri imagery / OSM search", fill="#FFF7DE", edge=GOLD)
    arrow(draw, (340, 285), (440, 285), label="HTTPS")
    arrow(draw, (750, 270), (850, 270))
    arrow(draw, (750, 320), (1210, 320))
    arrow(draw, (595, 385), (595, 570))
    arrow(draw, (990, 365), (720, 570))
    arrow(draw, (1210, 365), (750, 640))
    arrow(draw, (1375, 365), (1375, 570), color=GOLD, label="bounded calls")
    arrow(draw, (750, 650), (850, 650), color=MUTED, label="optional")
    draw.text((55, 825), "Deployment: Render static frontend + Render FastAPI service | Reproducible Docker Compose alternative", fill=INK, font=font(17))
    save(image, "architecture.png")


def contour_pipeline_diagram() -> None:
    image, draw = canvas(
        "Contour upload algorithm",
        "Every output is derived from the uploaded geometry and the selected eligible pond cell.",
    )
    steps = [
        ("1  Parse safely", "KML/KMZ limits\nLine elevations\nStudy boundary"),
        ("2  Rebuild terrain", "Metric grid\nFixed contours\nHarmonic interpolation"),
        ("3  Condition surface", "Priority-Flood\nResolve equal flats"),
        ("4  Route flow", "Steepest D8\nFlow accumulation"),
        ("5  Apply safeguards", "Boundary setback\nWater + 60 m buffer\nReject outlet"),
        ("6  Rank options", "Area + flatness\nElevation + clearance\nSpatial separation"),
        ("7  Choose site", "Automatic\nClicked point\nDrawn region"),
        ("8  Recompute outputs", "Selected catchment\nRainfall + runoff\nPond geometry"),
    ]
    positions = [
        (50, 190, 360, 345),
        (445, 190, 755, 345),
        (840, 190, 1150, 345),
        (1235, 190, 1545, 345),
        (1235, 600, 1545, 755),
        (840, 600, 1150, 755),
        (445, 600, 755, 755),
        (50, 600, 360, 755),
    ]
    for index, ((title, body), position) in enumerate(zip(steps, positions, strict=True)):
        box(draw, position, title, body, edge=GOLD if index in {4, 6} else GREEN)
    for index in range(3):
        arrow(draw, (positions[index][2], 268), (positions[index + 1][0], 268))
    arrow(draw, (1390, 345), (1390, 600))
    for index in range(4, 7):
        arrow(draw, (positions[index][0], 678), (positions[index + 1][2], 678))
    draw.text((800, 430), "No hard-coded coordinate or sample result", fill=DEEP, font=font(24, bold=True), anchor="mm")
    draw.text((800, 474), "A different selected point changes the reverse-D8 watershed and every volume derived from it.", fill=MUTED, font=font(18), anchor="mm")
    save(image, "contour_pipeline.png")


def safety_diagram() -> None:
    image, draw = canvas(
        "Pond-candidate safety gates",
        "Hard exclusions run before suitability scoring; a high score can never override a failed safety gate.",
    )
    box(draw, (45, 355, 275, 500), "Candidate cell", "A possible terrain\nlocation from the\nstudy mask", fill=MINT, body_width=20)
    gates = [
        "Inside\nstudy area?",
        "Beyond boundary\nsetback?",
        "Not an outlet\nor terminal?",
        "Outside water\n+ 60 m?",
        "Valid upstream\ncatchment?",
    ]
    x_positions = [325, 570, 815, 1060, 1305]
    for index, (label, x) in enumerate(zip(gates, x_positions, strict=True)):
        edge = CYAN if index == 3 else GREEN
        box(draw, (x, 245, x + 205, 360), label, "YES", edge=edge, body_width=20)
        if index < len(x_positions) - 1:
            arrow(draw, (x + 102, 360), (x + 102, 600), color=RED, label="NO")
        else:
            arrow(draw, (x + 62, 360), (1225, 630), color=RED, label="NO")
        if index < len(x_positions) - 1:
            arrow(draw, (x + 205, 302), (x_positions[index + 1], 302))
    arrow(draw, (275, 425), (325, 302))
    box(draw, (325, 630, 1505, 745), "Rejected with an explicit reason", "Outside area | boundary setback | outlet | detected-water buffer | no valid contributing cells", fill="#FDEAEA", edge=RED, title_color=RED, body_width=105)
    box(draw, (1305, 430, 1510, 555), "Eligible", "Comparative rank\nNot an approval", fill="#E9F6FB", edge=CYAN, body_width=20)
    arrow(draw, (1460, 360), (1460, 430))
    draw.text((48, 830), "Important: satellite colour non-detection cannot prove that a narrow, muddy, shaded, seasonal, or cloud-covered river is absent.", fill=INK, font=font(17))
    save(image, "safety_gates.png")


def workflow_comparison() -> None:
    image, draw = canvas(
        "Two complementary workflows",
        "Contour upload is survey-file driven; live analysis is location driven. Both share hydrology, safeguards, and outputs.",
    )
    box(draw, (70, 205, 745, 440), "Contour upload", "Input: KML/KMZ contour geometry\nStrength: preserves supplied 1 m contour evidence\nTerrain: interpolated between fixed contour cells\nUser choice: automatic, clicked point, or drawn region", fill=MINT, body_width=55)
    box(draw, (855, 205, 1530, 440), "Live analysis", "Input: map/search coordinates + radius\nStrength: works at arbitrary locations\nTerrain: public elevation grid with validated fallback\nUser choice: map click or explicit coordinates", fill="#E9F6FB", edge=CYAN, body_width=55)
    box(draw, (260, 590, 1340, 760), "Shared output contract", "Ranked pond locations | Selected upstream catchment | Monthly and annual rainfall | Annual runoff\nWater clearance | Terrain statistics | Pond capacity and dimensions | Excavation volume\nSources, warnings, and quality status", fill="white", edge=GOLD, body_width=95)
    arrow(draw, (405, 440), (585, 590))
    arrow(draw, (1195, 440), (1015, 590), color=CYAN)
    save(image, "workflow_comparison.png")


def bar_chart(
    title: str,
    subtitle: str,
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    name: str,
) -> None:
    image, draw = canvas(title, subtitle)
    panel_width = 470
    lefts = [55, 565, 1075]
    colors = [GREEN, "#7A69D5", CYAN]
    for (metric, values, unit), left in zip(series, lefts, strict=True):
        draw.rounded_rectangle((left, 180, left + panel_width, 780), radius=20, fill="white", outline="#D7E8E2", width=2)
        draw.text((left + 24, 205), metric, fill=INK, font=font(21, bold=True))
        maximum = max(values) * 1.15
        chart_top, chart_bottom = 285, 710
        bar_width = 96
        gap = 45
        for index, (label, value) in enumerate(zip(labels, values, strict=True)):
            x1 = left + 42 + index * (bar_width + gap)
            height = int((value / maximum) * (chart_bottom - chart_top))
            y1 = chart_bottom - height
            draw.rounded_rectangle((x1, y1, x1 + bar_width, chart_bottom), radius=10, fill=colors[index])
            draw.text((x1 + bar_width // 2, y1 - 35), f"{value:,.1f}", fill=INK, font=font(16, bold=True), anchor="mm")
            draw.text((x1 + bar_width // 2, chart_bottom + 28), label, fill=MUTED, font=font(16), anchor="mm")
        draw.text((left + panel_width - 24, 742), unit, fill=MUTED, font=font(15), anchor="ra")
    save(image, name)


def rainfall_chart(months: list[str], values: list[float], annual: float, valid_years: int) -> None:
    image, draw = canvas(
        "Historical rainfall climatology",
        "NASA POWER fallback at the supplied contour study; only complete calendar years contribute.",
    )
    chart = (90, 210, 1515, 740)
    draw.rounded_rectangle(chart, radius=20, fill="white", outline="#D7E8E2", width=2)
    maximum = max(values) * 1.16
    width = chart[2] - chart[0]
    slot = width / len(values)
    for index, (month, value) in enumerate(zip(months, values, strict=True)):
        bar_width = slot * 0.58
        x1 = chart[0] + index * slot + (slot - bar_width) / 2
        x2 = x1 + bar_width
        height = (value / maximum) * 420
        y1 = 675 - height
        color = GREEN if value >= 100 else CYAN
        draw.rounded_rectangle((int(x1), int(y1), int(x2), 675), radius=7, fill=color)
        draw.text((int((x1 + x2) / 2), int(y1 - 20)), f"{value:.0f}", fill=INK, font=font(14, bold=True), anchor="mm")
        draw.text((int((x1 + x2) / 2), 708), month, fill=MUTED, font=font(15), anchor="mm")
    draw.rounded_rectangle((1150, 235, 1478, 335), radius=16, fill=MINT, outline=GREEN, width=2)
    draw.text((1172, 253), f"Annual mean: {annual:,.2f} mm", fill=INK, font=font(18, bold=True))
    draw.text((1172, 294), f"Valid years: {valid_years}", fill=MUTED, font=font(17))
    draw.text((90, 800), "Values are climatological averages, not a spillway design storm or a guarantee of future rainfall.", fill=INK, font=font(17))
    save(image, "rainfall_climatology.png")


def production_charts() -> None:
    with PRODUCTION_JSON.open(encoding="utf-8") as handle:
        data = json.load(handle)
    options = data["candidate_options"]
    labels = [f"Option {item['rank']}" for item in options]
    bar_chart(
        "Production alternatives from contours_1m.kml",
        "Release 0a385c0 | Automatic ranking after boundary, outlet, and detected-water exclusion.",
        labels,
        [
            ("Suitability score", [item["suitability_score"] for item in options], "/ 100"),
            ("Upstream catchment", [item["contributing_area_hectares"] for item in options], "hectares"),
            ("Water clearance", [item["water_distance_m"] for item in options], "metres"),
        ],
        "production_options.png",
    )
    monthly = data["rainfall_data"]["monthly"]
    rainfall_chart(
        [row["month"][:3] for row in monthly],
        [row["rainfall_mm"] for row in monthly],
        data["rainfall_data"]["annual_avg_mm"],
        data["rainfall_data"]["valid_years"],
    )


def main() -> None:
    architecture_diagram()
    contour_pipeline_diagram()
    safety_diagram()
    workflow_comparison()
    production_charts()
    print(f"Generated documentation assets in {ASSET_DIR}")


if __name__ == "__main__":
    main()
