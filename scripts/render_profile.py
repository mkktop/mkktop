#!/usr/bin/env python3
"""Render the profile's theme-aware toolbox and GitHub activity artwork."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
USERNAME = "mkktop"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans CJK SC',Arial,sans-serif"
PALETTES = {
    "light": {
        "surface": "#FFFFFF", "border": "#E1E6EF", "ink": "#243047",
        "muted": "#7B879A", "label": "#617087", "chip": "#F5F7FB",
        "blue": "#4774D9", "purple": "#9368CB", "mint": "#288F7C",
        "blue_soft": "#EDF2FF", "purple_soft": "#F4EEFC", "mint_soft": "#EAF6F1",
        "bar": "#DDE7FA", "bar_recent": "#A6BFED", "rule": "#EDF0F5",
    },
    "dark": {
        "surface": "#111A28", "border": "#2A3649", "ink": "#E5ECF6",
        "muted": "#8291AA", "label": "#ADBDD4", "chip": "#192437",
        "blue": "#91B2FF", "purple": "#C5A3F1", "mint": "#78CEB8",
        "blue_soft": "#1C2C48", "purple_soft": "#2A233E", "mint_soft": "#18332F",
        "bar": "#273A57", "bar_recent": "#45648E", "rule": "#263247",
    },
}
GROUPS = [
    ("01", "LANGUAGES", "语言与系统", "blue", ["C", "Rust", "Python", "TypeScript", "JavaScript"], "Go · Java · Bash"),
    ("02", "INTERFACES", "应用与界面", "purple", ["React", "Vue", "Electron", "Tauri", "Node.js"], "HTML · CSS"),
    ("03", "TOOLING", "开发与部署", "mint", ["Linux", "Docker", "Git", "GitHub Actions"], "Nginx · MySQL · Redis"),
]


class Contributions(HTMLParser):
    """Read the dates and accessible counts from GitHub's public calendar."""

    def __init__(self):
        super().__init__()
        self.dates = {}
        self.counts = {}
        self.total = None
        self._tooltip = None
        self._heading = False
        self._text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-date") and attrs.get("id"):
            self.dates[attrs["id"]] = date.fromisoformat(attrs["data-date"])
        if tag == "tool-tip" and attrs.get("for"):
            self._tooltip = attrs["for"]
            self._text = []
        if tag == "h2" and attrs.get("id") == "js-contribution-activity-description":
            self._heading = True
            self._text = []

    def handle_data(self, data):
        if self._tooltip or self._heading:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self._tooltip:
            text = " ".join(self._text).strip()
            match = re.match(r"([\d,]+) contributions?\b", text)
            if text.startswith("No contributions"):
                self.counts[self._tooltip] = 0
            elif match:
                self.counts[self._tooltip] = int(match[1].replace(",", ""))
            self._tooltip = None
            self._text = []
        if tag == "h2" and self._heading:
            match = re.search(r"([\d,]+)\s+contributions?\b", " ".join(self._text))
            if match:
                self.total = int(match[1].replace(",", ""))
            self._heading = False
            self._text = []

    def calendar(self):
        missing = set(self.dates) - self.counts.keys()
        if missing:
            raise ValueError(f"GitHub calendar has {len(missing)} unreadable day counts")
        if self.total is None or len(self.dates) < 350:
            raise ValueError("GitHub did not return a complete contribution calendar")
        days = {day: self.counts[key] for key, day in self.dates.items()}
        if sum(days.values()) < self.total:
            raise ValueError("Calendar counts do not cover the reported contribution total")
        return days


def streaks(days, end):
    cursor = end if days.get(end, 0) else end - timedelta(days=1)
    current = 0
    while days.get(cursor, 0):
        current += 1
        cursor -= timedelta(days=1)
    longest = running = 0
    start = end - timedelta(days=364)
    for offset in range(365):
        running = running + 1 if days.get(start + timedelta(days=offset), 0) else 0
        longest = max(longest, running)
    return current, longest


def weekly_counts(days, end, length=16):
    monday = end - timedelta(days=end.weekday())
    start = monday - timedelta(weeks=length - 1)
    return [
        (start + timedelta(weeks=i), sum(days.get(start + timedelta(weeks=i, days=j), 0) for j in range(7)))
        for i in range(length)
    ]


def request(url):
    headers = {"User-Agent": f"{USERNAME}-profile", "Accept": "application/json" if "api.github.com" in url else "text/html"}
    token = os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return response.read().decode("utf-8")


def collect(snapshot_dir=None):
    if snapshot_dir:
        html = (snapshot_dir / "calendar.txt").read_text()
        repos = json.loads((snapshot_dir / "repos.txt").read_text())
    else:
        html = request(f"https://github.com/users/{USERNAME}/contributions")
        repos = []
        for page in range(1, 100):
            batch = json.loads(request(f"https://api.github.com/users/{USERNAME}/repos?type=owner&per_page=100&page={page}"))
            if not isinstance(batch, list):
                raise ValueError("GitHub did not return a repository list")
            repos.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise ValueError("Repository pagination did not finish")
    calendar = Contributions()
    calendar.feed(html)
    days = calendar.calendar()
    end = max(days)
    if abs((date.today() - end).days) > 2:
        raise ValueError("The returned GitHub calendar is out of date")
    current, longest = streaks(days, end)
    public = [repo for repo in repos if not repo.get("private") and not repo.get("fork") and repo.get("owner", {}).get("login", "").lower() == USERNAME]
    return {
        "total": calendar.total, "current": current, "longest": longest,
        "repos": len(public), "stars": sum(repo["stargazers_count"] for repo in public),
        "weekly": weekly_counts(days, end),
        "updated": datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y.%m.%d"),
    }


def text(x, y, value, size, color, weight=400, anchor="start", spacing=None):
    extra = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{extra}>{escape(str(value))}</text>'


def rect(x, y, w, h, fill, radius=0, stroke=None):
    extra = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{radius:g}" fill="{fill}"{extra}/>'


def svg(width, height, title, description, content):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
<g font-family="{escape(FONT, quote=True)}">{''.join(content)}</g>
</svg>
'''


def stack_art(theme, mobile):
    p = PALETTES[theme]
    width, height = (640, 650) if mobile else (1200, 290)
    out = []
    for index, (number, label, title, accent, tags, secondary) in enumerate(GROUPS):
        x, y = (1, 1 + index * 222) if mobile else (1 + index * 408, 1)
        w, h = (638, 204) if mobile else (382, 288)
        out.append(rect(x, y, w, h, p["surface"], 20, p["border"]))
        out.append(rect(x + 26, y + 24, 38, 38, p[accent + "_soft"], 11))
        out.append(text(x + 45, y + 49, number, 14, p[accent], 600, "middle"))
        out.append(text(x + 78, y + 49, label, 14 if mobile else 13, p["muted"], 600, spacing=1.8))
        out.append(text(x + 26, y + 101 if not mobile else y + 94, title, 29, p["ink"], 650))
        tx, ty = x + 26, y + (118 if mobile else 135)
        size, unit, tag_h = (22, 12, 38) if mobile else (18, 10, 33)
        for tag in tags:
            tag_w = len(tag) * unit + 24
            if tx + tag_w > x + w - 24:
                tx = x + 26
                ty += tag_h + 10
            out.append(rect(tx, ty, tag_w, tag_h, p["chip"], 7))
            out.append(text(tx + 12, ty + tag_h * .7, tag, size, p["label"], 500))
            tx += tag_w + 9
        out.append(text(x + 26, y + h - 23, secondary, 20 if mobile else 17, p["muted"]))
    return svg(width, height, "技术栈 / Toolbox", "语言与系统：C、Rust、Python、TypeScript、JavaScript、Go、Java、Bash；应用与界面：React、Vue、Electron、Tauri、Node.js、HTML、CSS；开发与部署：Linux、Docker、Git、GitHub Actions、Nginx、MySQL、Redis。", out)


def activity_art(theme, mobile, data):
    p = PALETTES[theme]
    width, height = (640, 650) if mobile else (1200, 460)
    out = [rect(1, 1, width - 2, height - 2, p["surface"], 22, p["border"])]
    pad = 26 if mobile else 32
    out.append(text(pad, 37, "GITHUB PULSE", 16 if mobile else 13, p["muted"], 600, spacing=2))
    out.append(text(pad, 79, "持续构建", 31 if mobile else 29, p["ink"], 650))
    out.append(text(width - pad, 37, data["updated"] + " 更新", 16 if mobile else 14, p["muted"], anchor="end"))
    out.append(text(width - pad, 78, "mkktop", 21 if mobile else 19, p["blue"], 500, "end"))
    metrics = [("近一年贡献", data["total"], "blue", ""), ("当前连续", data["current"], "mint", "天"), ("公开项目", data["repos"], "ink", ""), ("累计获星", data["stars"], "ink", "")]
    for i, (label, value, color, unit) in enumerate(metrics):
        if mobile:
            x, y = pad + (i % 2) * 308, 148 + (i // 2) * 119
        else:
            x, y = pad + i * 284, 158
        out.append(text(x, y, f"{value:,}", 55 if mobile else 47, p[color], 650))
        if unit:
            out.append(text(x + len(str(value)) * (34 if mobile else 29) + 10, y - 1, unit, 22 if mobile else 19, p["label"]))
        out.append(text(x, y + 38 if mobile else y + 35, label, 22 if mobile else 18, p["label"]))
    if mobile:
        out.append(f'<path d="M320 111v201M26 217h588M26 342h588" stroke="{p["rule"]}"/>')
        chart_title_y, top, bottom, label_y = 385, 423, 550, 582
    else:
        out.append(f'<path d="M32 225h1136M295 119v76m284-76v76m284-76v76" stroke="{p["rule"]}"/>')
        chart_title_y, top, bottom, label_y = 263, 287, 390, 420
    out.append(text(pad, chart_title_y, "贡献节奏", 23 if mobile else 19, p["ink"], 600))
    out.append(text(width - pad, chart_title_y, "近 16 周 · 每周贡献", 18 if mobile else 15, p["muted"], anchor="end"))
    weekly = data["weekly"]
    maximum = max(1, *(count for _, count in weekly))
    gap = 10 if mobile else 15
    bar_w = (width - 2 * pad - gap * 15) / 16
    for i, (start, count) in enumerate(weekly):
        h = max(2, count / maximum * (bottom - top))
        x = pad + i * (bar_w + gap)
        fill = p["blue"] if i == 15 else p["bar_recent"] if i >= 12 else p["bar"]
        out.append(f'<g><title>{start.isoformat()} 起一周：{count} 次贡献</title>{rect(x, bottom - h, bar_w, h, fill, 5)}</g>')
        if i in [0, 4, 8, 12, 15]:
            out.append(text(x + bar_w / 2, label_y, "本周" if i == 15 else start.strftime("%m.%d"), 18 if mobile else 14, p["muted"], anchor="middle"))
    footer_y = 626 if mobile else 446
    out.append(text(pad, footer_y, f'近一年最长连续 {data["longest"]} 天', 19 if mobile else 14, p["muted"]))
    out.append(text(width - pad, footer_y, "数据来自 GitHub", 19 if mobile else 14, p["muted"], anchor="end"))
    description = f'GitHub 真实记录：近一年 {data["total"]} 次贡献，当前连续 {data["current"]} 天，{data["repos"]} 个原创公开项目，累计 {data["stars"]} 个星标。贡献趋势按周统计，更新于 {data["updated"]}。'
    return svg(width, height, "开发足迹 / GitHub Pulse", description, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, help="Use saved public responses for local rendering")
    args = parser.parse_args()
    data = collect(args.snapshot_dir)
    outputs = {}
    for theme in PALETTES:
        for mobile in [False, True]:
            suffix = ("-mobile" if mobile else "") + "-" + theme
            outputs["stack" + suffix + ".svg"] = stack_art(theme, mobile)
            outputs["activity" + suffix + ".svg"] = activity_art(theme, mobile, data)
    for name, content in outputs.items():
        (ROOT / "assets" / name).write_text(content, encoding="utf-8")
    print(f'Rendered {len(outputs)} SVGs; contributions={data["total"]}, current_streak={data["current"]}, public_projects={data["repos"]}, stars={data["stars"]}')


if __name__ == "__main__":
    main()
