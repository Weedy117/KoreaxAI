from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"C:\Users\ASUS\Desktop\SAIS Playground\ROKxAI")
DATA = ROOT / "korea-ai-industry-dashboard" / "data" / "consolidated" / "master_observations_canonical.csv"
FIG_DIR = ROOT / "outputs" / "korea_ai_strategy" / "figures"


COLORS = {
    "teal": "#1F6F83",
    "blue": "#4B7DB3",
    "red": "#C44E52",
    "green": "#59A14F",
    "orange": "#F28E2B",
    "gray": "#706B5A",
    "light": "#EEF4F6",
    "dark": "#1F2933",
}


def font(size: int, bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


TITLE = font(28, True)
SUBTITLE = font(17, True)
BODY = font(14)
SMALL = font(11)
TINY = font(10)


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], width: int, fill: str, fnt, line_gap: int = 4):
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=fill, font=fnt)
        y += fnt.size + line_gap
    return y


def line_chart(draw, box, series, x_min, x_max, y_min, y_max, color, label_fmt="{:.0f}"):
    x0, y0, x1, y1 = box
    draw.line((x0, y1, x1, y1), fill="#9AA6AC", width=1)
    draw.line((x0, y0, x0, y1), fill="#9AA6AC", width=1)
    points = []
    for year, value in series:
        x = x0 + (year - x_min) / (x_max - x_min) * (x1 - x0)
        y = y1 - (value - y_min) / (y_max - y_min) * (y1 - y0)
        points.append((x, y, year, value))
    if len(points) > 1:
        draw.line([(p[0], p[1]) for p in points], fill=color, width=3)
    for x, y, year, value in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
    for year in sorted({int(p[2]) for p in points}):
        x = x0 + (year - x_min) / (x_max - x_min) * (x1 - x0)
        draw.text((x - 14, y1 + 8), str(year), fill="#4B5563", font=TINY)
    first = points[0]
    last = points[-1]
    draw.text((first[0] - 18, first[1] - 22), label_fmt.format(first[3]), fill=color, font=SMALL)
    draw.text((last[0] - 18, last[1] - 22), label_fmt.format(last[3]), fill=color, font=SMALL)


def make_policy_timeline():
    img = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(img)
    draw.text((80, 55), "Korea shifted from digital catch up to sovereign AI statecraft", fill=COLORS["dark"], font=TITLE)
    draw.text((80, 100), "Selected national policy moves and their strategic function", fill="#56616A", font=BODY)
    events = [
        (2019, "National AI Strategy", "AI ecosystem, utilization, and people centered AI"),
        (2020, "Data Dam", "Digital New Deal data and AI infrastructure"),
        (2022, "Digital Strategy", "AI, AI chips, data, platform government, and talent"),
        (2024, "AI Basic Act Passed", "National Assembly creates legal basis for promotion and trust"),
        (2025, "AI Strategy Committee", "Presidential control tower and AI G3 political objective"),
        (2025.5, "Supplementary AI Budget", "Public GPUs, sovereign models, talent, and AI semiconductors"),
        (2025.8, "K AI Model Project", "Five teams and public support for domestic foundation models"),
        (2026, "Act and Work Plan", "Implementation, AI Highway, and larger public budget"),
    ]
    x_line = 185
    y0 = 170
    row_gap = 78
    draw.line((x_line, y0 + 20, x_line, y0 + row_gap * (len(events) - 1) + 20), fill=COLORS["teal"], width=5)
    for idx, (year, title, detail) in enumerate(events):
        y = y0 + idx * row_gap
        box_fill = COLORS["light"] if idx % 2 == 0 else "#F7FAFB"
        draw.ellipse((x_line - 13, y + 7, x_line + 13, y + 33), fill=COLORS["teal"])
        draw.rounded_rectangle((235, y - 9, 1260, y + 58), radius=8, fill=box_fill, outline="#B8C5CC")
        year_text = str(int(year)) if float(year).is_integer() else "2025"
        draw.text((95, y + 3), year_text, fill=COLORS["teal"], font=SUBTITLE)
        draw.text((260, y + 6), title, fill=COLORS["dark"], font=SUBTITLE)
        draw_wrapped(draw, detail, (565, y + 8), 620, "#56616A", BODY, 3)
    draw.text((80, 840), "Source: MSIT releases and ROKxAI policy source collection.", fill="#56616A", font=SMALL)
    img.save(FIG_DIR / "figure_4_policy_timeline.png", quality=95)


def make_research_model_trends():
    df = pd.read_csv(DATA)
    kor = df[df.country_iso3 == "KOR"]
    pubs = kor[kor.indicator_id == "ai_research_publications_count"]
    pubs = [(int(r.year), float(r.value_numeric)) for r in pubs.itertuples() if 2020 <= int(r.year) <= 2025]
    pubs.sort()
    models = kor[kor.indicator_id == "notable_ai_models_count"]
    models = [(int(r.year), float(r.value_numeric)) for r in models.itertuples() if 2017 <= int(r.year) <= 2025]
    models.sort()
    img = Image.new("RGB", (1400, 760), "white")
    draw = ImageDraw.Draw(img)
    draw.text((80, 55), "Korea has broad research volume and uneven model output", fill=COLORS["dark"], font=TITLE)
    draw.text((80, 100), "Publications show a durable research base, while notable models spike with coordinated public and private effort", fill="#56616A", font=BODY)
    draw.text((125, 160), "AI research publications", fill=COLORS["blue"], font=SUBTITLE)
    line_chart(draw, (135, 205, 640, 575), pubs, 2020, 2025, 0, 21000, COLORS["blue"], "{:.0f}")
    draw.text((780, 160), "Notable AI models", fill=COLORS["orange"], font=SUBTITLE)
    line_chart(draw, (790, 205, 1295, 575), models, 2017, 2025, 0, 9, COLORS["orange"], "{:.0f}")
    draw.text((80, 700), "Source: ROKxAI dashboard using OpenAlex and Epoch AI data.", fill="#56616A", font=SMALL)
    img.save(FIG_DIR / "figure_5_research_models_trend.png", quality=95)


def make_adoption_skill_trends():
    df = pd.read_csv(DATA)
    kor = df[df.country_iso3 == "KOR"]
    robots = kor[kor.indicator_id == "ai_index_fig_4_5_5_number_of_industrial_robots_installed_in_thousands"]
    robots = [(int(r.year), float(r.value_numeric)) for r in robots.itertuples()]
    robots.sort()
    skills = kor[kor.indicator_id == "ai_index_fig_7_4_3_skills_diffusion_index_ai_engineering_skills"]
    skills = [(int(r.year), float(r.value_numeric)) for r in skills.itertuples()]
    skills.sort()
    img = Image.new("RGB", (1400, 760), "white")
    draw = ImageDraw.Draw(img)
    draw.text((80, 55), "The adoption base is physical, while software skills are still diffusing", fill=COLORS["dark"], font=TITLE)
    draw.text((80, 100), "Robot installation depth and AI engineering skill diffusion point to a strategy built around industrial absorption", fill="#56616A", font=BODY)
    draw.text((125, 160), "Industrial robots installed in thousands", fill=COLORS["teal"], font=SUBTITLE)
    line_chart(draw, (135, 205, 640, 575), robots, 2011, 2024, 0, 45, COLORS["teal"], "{:.0f}")
    draw.text((780, 160), "AI engineering skills diffusion", fill=COLORS["green"], font=SUBTITLE)
    line_chart(draw, (790, 205, 1295, 575), skills, 2016, 2025, 0, 18, COLORS["green"], "{:.1f}")
    draw.text((80, 700), "Source: ROKxAI dashboard using Stanford AI Index and IFR data.", fill="#56616A", font=SMALL)
    img.save(FIG_DIR / "figure_6_adoption_skills_trend.png", quality=95)


if __name__ == "__main__":
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    make_policy_timeline()
    make_research_model_trends()
    make_adoption_skill_trends()
