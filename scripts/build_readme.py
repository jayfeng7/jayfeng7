#!/usr/bin/env python3
"""Rebuild README.md from profile.yml — profile.yml is the single source of truth."""
import json
import os
import re
import urllib.request
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((ROOT / "profile.yml").read_text(encoding="utf-8"))

_readme_path = ROOT / "README.md"
_existing_readme = _readme_path.read_text(encoding="utf-8") if _readme_path.exists() else ""

user = cfg["username"]
header = cfg.get("header") or {}
stats_cfg = cfg.get("stats") or {}
social = cfg.get("social") or {}

title = header.get("title") or f"Hi, I'm {user}"
subtitle = (header.get("subtitle") or "").strip()
theme = stats_cfg.get("theme") or "tokyonight"


def badge(label: str, color: str, logo: str | None = None, logo_color: str = "white") -> str:
    text = quote(str(label).replace("-", "--").replace(" ", "_"))
    extra = f"&logo={logo}&logoColor={logo_color}" if logo else ""
    return f"https://img.shields.io/badge/{text}-{str(color).lstrip('#')}?style=flat-square{extra}"


def img(src: str, alt: str, extra: str = "") -> str:
    return f'<img src="{src}" alt="{alt}"{extra} />'


def md_to_html(s: str) -> str:
    """Footer lives in an HTML block: convert the few Markdown bits we support."""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


# ---- open source: merged-PR showcase (auto-counted from the GitHub API) ----
LANG_STYLE = {
    "Python": ("3776AB", "python"),
    "TypeScript": ("3178C6", "typescript"),
    "JavaScript": ("F7DF1E", "javascript"),
    "Go": ("00ADD8", "go"),
    "Rust": ("DEA584", "rust"),
    "Java": ("007396", "java"),
    "C": ("555555", "c"),
    "C++": ("00599C", "cplusplus"),
    "C#": ("239120", "csharp"),
    "Shell": ("89E051", "gnubash"),
    "Vue": ("41B883", "vuedotjs"),
    "Kotlin": ("7F52FF", "kotlin"),
    "Swift": ("F05138", "swift"),
    "Jupyter Notebook": ("DA5B0B", "jupyter"),
}


def fmt_k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def stat_badge(label: str, value, color: str) -> str:
    left = quote(label.replace(" ", "_"))
    right = quote(str(value).replace(" ", "_"))
    # shields path form only supports label-message-color; labelColor must be a query param
    return f"https://img.shields.io/badge/{left}-{right}-{color}?style=flat-square&labelColor=24292F"


def lang_badge(lang: str | None) -> str:
    if not lang:
        return "—"
    color, logo = LANG_STYLE.get(lang, ("6E7681", None))
    text = quote(lang.replace("-", "--").replace(" ", "_"))
    extra = f"&logo={logo}&logoColor=white" if logo else ""
    return f"https://img.shields.io/badge/{text}-{color}?style=flat-square{extra}"


def gh_api(url: str) -> dict:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-readme"}
    )
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_opensource(user: str, os_cfg: dict) -> str:
    """Merged-PR showcase: three stat badges + a per-repo table sorted by stars."""
    top_n = int(os_cfg.get("top", 5))
    min_stars = int(os_cfg.get("min_stars", 0))
    q = quote(f"type:pr author:{user} is:merged")
    data = gh_api(f"https://api.github.com/search/issues?q={q}&per_page=100&sort=created&order=desc")
    per_repo: dict[str, int] = {}
    for it in data.get("items", []):
        repo_url = (it.get("repository_url") or "").rstrip("/")
        if not repo_url:
            continue
        owner, name = repo_url.split("/")[-2:]
        if owner.lower() == user.lower():
            continue  # own repos are not upstream projects
        per_repo[f"{owner}/{name}"] = per_repo.get(f"{owner}/{name}", 0) + 1
    repos = []
    for full, merged in per_repo.items():
        d = gh_api(f"https://api.github.com/repos/{full}")
        stars = int(d.get("stargazers_count") or 0)
        if stars < min_stars:
            continue
        repos.append(
            {
                "full": full,
                "stars": stars,
                "lang": d.get("language"),
                "desc": (d.get("description") or "").strip(),
                "merged": merged,
            }
        )
    repos.sort(key=lambda r: r["stars"], reverse=True)
    if not repos:
        raise RuntimeError("no merged upstream PRs found yet")
    shown, rest = repos[:top_n], repos[top_n:]

    # Upstream reports closed as completed. Closure alone does not prove that
    # a particular fix was implemented; curated evidence below supplies links.
    bugs_accepted = 0
    try:
        qi = quote(f"type:issue author:{user} is:closed is:public")
        idata = gh_api(f"https://api.github.com/search/issues?q={qi}&per_page=100")
        for it in idata.get("items", []):
            repo_url = (it.get("repository_url") or "").rstrip("/")
            owner = repo_url.split("/")[-2] if repo_url else ""
            if it.get("state_reason") == "completed" and owner.lower() != user.lower():
                bugs_accepted += 1
    except Exception as e:
        print(f"opensource: bug-report count failed ({e}); badge omitted")

    badge_specs = [
        ("MERGED PRS", sum(r["merged"] for r in repos), "2EA043", "merged pull requests"),
        ("PROJECTS", len(repos), "0969DA", "projects"),
        ("UPSTREAM STARS", fmt_k(sum(r["stars"] for r in repos)), "B45309", "upstream stars"),
    ]
    if bugs_accepted:
        badge_specs.append(
            ("REPORTS COMPLETED", bugs_accepted, "8957E5", "issue reports closed as completed")
        )
    badges_row = " &nbsp; ".join(
        img(
            stat_badge(label, value, color),
            alt,
        )
        for label, value, color, alt in badge_specs
    )
    rows = []
    for r in shown:
        desc = r["desc"]
        if len(desc) > 100:
            desc = desc[:100].rstrip() + "…"
        link = f'[<b>{r["full"]}</b>](https://github.com/{r["full"]})'
        first_cell = f"{link}<br>{desc.replace('|', chr(92) + '|')}" if desc else link
        rows.append(
            f"| {first_cell} | {fmt_k(r['stars'])} "
            f'| <img src="{lang_badge(r["lang"])}" alt="{r["lang"] or ""}" /> | {r["merged"]} |'
        )
    if rest:
        rows.append(
            f"| … and {len(rest)} more | {fmt_k(sum(r['stars'] for r in rest))} | — "
            f"| {sum(r['merged'] for r in rest)} |"
        )
    scope = f" with ≥{min_stars} stars" if min_stars else ""
    lines = [
        "## 🌱 Open Source",
        "",
        "Projects that have merged my pull requests, refreshed automatically by Actions. "
        "The badges count every merge; the table names the top repositories and the last row "
        "carries the rest. Selected pull requests and reports are linked below.",
        "",
        '<p align="center">',
        f"  {badges_row}",
        "</p>",
        "",
        "| Project | ★ | Language | Merged |",
        "|---|---|---|---|",
        *rows,
        "",
        f"*Merges only, counted across upstream projects{scope}; the report badge counts "
        f"my issue reports closed as completed upstream, not additional merged PRs. "
        f"Auto-refreshed by [.github/workflows/readme.yml](.github/workflows/readme.yml).*",
    ]
    return "\n".join(lines)


sections: list[str] = []
sections.append(
    "<!-- ⚠️ AUTO-GENERATED from profile.yml — do not edit this file by hand.\n"
    "     Edit profile.yml (repo root), push, and Actions rebuilds this page.\n"
    "     本页面由 profile.yml 自动生成：请修改 profile.yml，不要直接改本文件。 -->"
)

# ---- portfolio first, with no third-party image services in the opening section ----
banner = header.get("banner")
sections.append(f"![{title}]({banner})" if banner else f"# {title}")
if subtitle:
    sections.append(f"**{subtitle}**")
if header.get("intro"):
    sections.append(header["intro"])

projects = cfg.get("projects") or []
if projects:
    sections.append("## 个人项目 / Projects")
    for project in projects:
        sections.append(f'### {project["name"]} · {project["status"]}')
        sections.append(project["description"])
        links = " · ".join(
            f'[{link["label"]}]({link["url"]})' for link in (project.get("links") or [])
        )
        sections.append(f'{links}\n\n`{project["stack"]}`' if links else f'`{project["stack"]}`')

evidence = cfg.get("contribution_evidence") or {}
merged_evidence = evidence.get("merged") or []
featured = cfg.get("featured_contributions") or []
if featured:
    evidence_by_url = {item["url"]: item for item in merged_evidence}
    rows = []
    for feature in featured:
        item = evidence_by_url[feature["url"]]
        repo_url, pr_number = item["url"].rsplit("/pull/", 1)
        summary = feature["summary"].replace("|", r"\|")
        rows.append(
            f'| [{item["project"]}]({repo_url}) | {summary} | [#{pr_number}]({item["url"]}) |'
        )
    sections.append(
        "## 开源贡献 / Open Source\n\n"
        "| 上游仓库 | 我的贡献 | 已合并 PR |\n"
        "| --- | --- | --- |\n"
        + "\n".join(rows)
    )

if cfg.get("research"):
    sections.append(cfg["research"])

sections.append("<details>\n<summary>贡献记录与验证链接 / Contribution history</summary>")

# ---- open source showcase: live stats, fall back to the previous block on API failure ----
os_cfg = cfg.get("opensource") or {}
if os_cfg.get("enabled", True):
    block = None
    try:
        block = build_opensource(cfg["username"], os_cfg)
    except Exception as e:
        print(f"opensource: stats fetch failed ({e}) — keeping the previous block if present")
        m = re.search(
            r"<!-- opensource:start -->\n(.*?)\n?<!-- opensource:end -->", _existing_readme, re.S
        )
        if m:
            block = m.group(1).rstrip()
    if block:
        sections.append("<!-- opensource:start -->\n" + block + "\n<!-- opensource:end -->")

# ---- concrete contribution evidence (curated in profile.yml) ----
if merged_evidence:
    rows = []
    for item in merged_evidence:
        number = item["url"].rstrip("/").split("/")[-1]
        contribution = item["contribution"].replace("|", r"\|")
        rows.append(
            f'| {item["project"]} | {contribution} '
            f'| [#{number}]({item["url"]}) | {item["merged_on"]} |'
        )
    sections.append(
        "## 🔎 Selected Merged Contributions\n\n"
        "| Project | My contribution | Merged PR | Date (Asia/Shanghai) |\n"
        "|---|---|---|---|\n"
        + "\n".join(rows)
        + f'\n\n*Merge status checked on {evidence["checked_on"]}. '
        "Prepared with AI assistance.*"
    )

integrated_evidence = evidence.get("integrated") or []
if integrated_evidence:
    rows = []
    for item in integrated_evidence:
        original_number = item["original_pr"].rstrip("/").split("/")[-1]
        upstream_number = item["upstream_pr"].rstrip("/").split("/")[-1]
        contribution = item["contribution"].replace("|", r"\|")
        rows.append(
            f'| {item["project"]} | {contribution} '
            f'| [Merged #{upstream_number}]({item["upstream_pr"]}) '
            f'· [Co-authored commit]({item["commit"]}) '
            f'| [#{original_number}]({item["original_pr"]}) | {item["integrated_on"]} |'
        )
    sections.append(
        "## 🤝 Contributions Integrated Upstream\n\n"
        "| Project | My contribution | Integration evidence | Original PR | Date (Asia/Shanghai) |\n"
        "|---|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n\n*Co-authored patches integrated via another upstream PR are tracked separately "
        "from my merged-PR total. Integration verified on "
        + str(evidence["integrated_checked_on"])
        + ".*"
    )

report_evidence = evidence.get("reports") or []
if report_evidence:
    rows = []
    for item in report_evidence:
        links = f'[Issue]({item["issue"]}) · [Upstream fix]({item["fix"]})'
        if item.get("repro"):
            links += f' · [Reproduction]({item["repro"]})'
        contribution = item["contribution"].replace("|", r"\|")
        outcome = item["outcome"].replace("|", r"\|")
        rows.append(f'| {item["project"]} | {contribution} | {outcome} | {links} |')
    sections.append(
        "## 🧪 Bug Reports & Reproductions\n\n"
        "Reports and reproducible diagnostics are contributions too. "
        "The table states who implemented each fix.\n\n"
        "| Project | My contribution | Outcome | Evidence |\n"
        "|---|---|---|---|\n"
        + "\n".join(rows)
    )

# ---- optional custom milestone badges; GitHub's native achievements are in the sidebar ----
ach = cfg.get("achievements") or []
if ach:
    default_url = f"https://github.com/{user}?tab=achievements"
    row = "\n  ".join(
        f'<a href="{a.get("url") or default_url}">'
        + img(
            a.get("badge_url")
            or stat_badge(a["label"], a.get("value", ""), a.get("color", "F7C948")),
            a["label"],
        )
        + "</a>"
        for a in ach
    )
    block = "## 🏅 Achievements\n\n<p align=\"center\">\n  " + row + "\n</p>"
    notes = [str(a["note"]).strip() for a in ach if str(a.get("note") or "").strip()]
    if notes:
        block += "\n\n" + "\n\n".join(notes)
    sections.append(block)

sections.append("</details>")
sections.append("<details>\n<summary>技术栈与 GitHub 活动 / Stack & activity</summary>")

# ---- tech stack ----
icons = [i for i in (cfg.get("skills_icons") or []) if str(i).strip()]
badges = cfg.get("badges") or []
stack: list[str] = []
if icons:
    icons_param = ",".join(icons)
    stack.append(
        '<p align="center">\n  '
        f'<a href="https://github.com/{user}?tab=repositories">\n'
        f"    {img(f'https://skillicons.dev/icons?i={icons_param}', 'skills')}\n  </a>\n</p>"
    )
if badges:
    row = "\n  ".join(
        img(
            badge(b["label"], b.get("color", "36BCF7"), b.get("logo"), b.get("logo_color", "white")),
            b["label"],
        )
        for b in badges
    )
    stack.append(f'<p align="center">\n  {row}\n</p>')
if stack:
    sections.append("## 🛠️ Tech Stack\n\n" + "\n\n".join(stack))

# ---- hobbies ----
hobbies = cfg.get("hobbies") or []
if hobbies:
    row = "\n  ".join(
        img(badge(h["label"], h.get("color", "36BCF7")), h["label"]) for h in hobbies
    )
    sections.append(f'## 🏀 Hobbies & Interests\n\n<p align="center">\n  {row}\n</p>')

# ---- social links ----
social_items: list[tuple[str, str, str, str | None]] = []
if social.get("email"):
    social_items.append((f"mailto:{social['email']}", "Email", "0078D4", None))
if social.get("blog"):
    social_items.append((social["blog"], "Website", "000000", "googlechrome"))
if social.get("twitter"):
    social_items.append((f"https://x.com/{social['twitter']}", "X / Twitter", "000000", "x"))
if social.get("linkedin"):
    social_items.append(
        (f"https://www.linkedin.com/in/{social['linkedin']}", "LinkedIn", "0A66C2", None)
    )
if social.get("bilibili"):
    social_items.append(
        (f"https://space.bilibili.com/{social['bilibili']}", "Bilibili", "FB7299", "bilibili")
    )
if social.get("zhihu"):
    social_items.append(
        (f"https://www.zhihu.com/people/{social['zhihu']}", "Zhihu", "0084FF", "zhihu")
    )
if social_items:
    row = "\n  ".join(
        f'<a href="{href}">{img(badge(label, color, logo), label)}</a>'
        for href, label, color, logo in social_items
    )
    sections.append(
        "## 🤝 Connect with Me\n\n<p align=\"center\">\n  " + row + "\n</p>"
    )

# ---- stats ----
show_stats = stats_cfg.get("show_streak", True) or True  # main cards always shown
stat_card = img(
    f"https://github-readme-stats.vercel.app/api?username={user}&show_icons=true&theme={theme}&hide_border=true",
    "GitHub stats",
    ' height="165"',
)
langs_card = img(
    f"https://github-readme-stats.vercel.app/api/top-langs/?username={user}&layout=compact&theme={theme}&hide_border=true&langs_count=8",
    "Top languages",
    ' height="165"',
)
stats_blocks = [
    f'<p align="center">\n  <table>\n    <tr>\n'
    f"      <td align=\"center\">\n        {stat_card}\n      </td>\n"
    f"      <td align=\"center\">\n        {langs_card}\n      </td>\n    </tr>\n  </table>\n</p>"
]
if stats_cfg.get("show_streak", True):
    stats_blocks.append(
        '<p align="center">\n  '
        + img(
            f"https://streak-stats.demolab.com?user={user}&theme={theme}&hide_border=true",
            "GitHub streak",
            ' height="165"',
        )
        + "\n</p>"
    )
if stats_cfg.get("show_trophy", False):
    stats_blocks.append(
        '<p align="center">\n  '
        + img(
            f"https://github-profile-trophy.vercel.app/?username={user}&theme={theme}&no-frame=true&row=1&column=7",
            "Trophies",
            ' width="100%"',
        )
        + "\n</p>"
    )
sections.append("## 📊 GitHub Stats\n\n" + "\n\n".join(stats_blocks))

# ---- snake ----
if stats_cfg.get("show_snake", True):
    base = f"https://raw.githubusercontent.com/{user}/{user}/output"
    sections.append(
        "## 🐍 Contribution Snake\n\n<p align=\"center\">\n  <picture>\n"
        f'    <source media="(prefers-color-scheme: dark)" srcset="{base}/github-contribution-grid-snake-dark.svg" />\n'
        f'    <source media="(prefers-color-scheme: light)" srcset="{base}/github-contribution-grid-snake.svg" />\n'
        f'    <img alt="contribution snake animation" src="{base}/github-contribution-grid-snake.svg" width="100%" />\n'
        "  </picture>\n</p>"
    )

# ---- footer: single centered line with views badge and footer text ----
sections.append("</details>")
foot: list[str] = []
if stats_cfg.get("show_visitors", True):
    foot.append(
        img(
            f"https://api.visitorbadge.io/api/VisitorHit?user={user}&repo={user}&type=ip",
            "profile views",
        )
    )
footer_text = str((cfg.get("footer") or {}).get("text") or "").strip()
if footer_text:
    foot.append(md_to_html(footer_text))
if foot:
    sections.append("---")
    sections.append('<p align="center">\n  ' + " &nbsp; ".join(foot) + "\n</p>")

out = "\n\n".join(sections) + "\n"
readme = ROOT / "README.md"
if readme.exists() and readme.read_text(encoding="utf-8") == out:
    print("README.md already up to date")
else:
    readme.write_text(out, encoding="utf-8", newline="\n")
    print("README.md rebuilt from profile.yml")
