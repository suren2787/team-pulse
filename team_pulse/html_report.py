"""Render the digest as a self-contained HTML file — a no-infra interim delivery.

Open the output in any browser. No Slack, no Jira write, no network. Same
findings as the Slack digest, just laid out visually.
"""

import html
from datetime import datetime

# (findings key, label, emoji, css class)
_CATEGORIES = [
    ("blocked", "Blocked", "🚫", "blocked"),
    ("stale_wip", "Stale WIP", "🐌", "stale"),
    ("review_wait", "In review", "👀", "review"),
    ("unassigned", "Unassigned", "🫥", "unassigned"),
]

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem; font: 15px/1.5 -apple-system, BlinkMacSystemFont,
       "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       background: #f6f7f9; color: #1f2328; }
.wrap { max-width: 820px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.sub { color: #6b7280; margin: 0 0 1.5rem; font-size: .9rem; }
.focus { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 10px;
         padding: 1rem 1.25rem; margin: 0 0 1.5rem; }
.focus h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em;
            color: #4338ca; margin: 0 0 .5rem; }
.focus p { margin: 0; white-space: pre-wrap; }
.project { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
           padding: 1rem 1.25rem; margin: 0 0 1rem; }
.project > header { display: flex; align-items: baseline; gap: .5rem; margin-bottom: .5rem; }
.project h2 { font-size: 1.1rem; margin: 0; }
.key { font: 600 .7rem/1 ui-monospace, SFMono-Regular, Menlo, monospace;
       background: #f3f4f6; color: #6b7280; padding: .2rem .4rem; border-radius: 5px; }
.meta { margin-left: auto; color: #9ca3af; font-size: .85rem; }
.bucket { padding: .5rem 0; border-top: 1px dashed #eceef1; }
.bucket:first-of-type { border-top: none; }
.bucket h3 { font-size: .8rem; text-transform: uppercase; letter-spacing: .03em;
             color: #6b7280; margin: 0 0 .4rem; }
.cat { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin: .25rem 0; }
.cat-label { font-size: .8rem; font-weight: 600; margin-right: .25rem; }
.chip { display: inline-flex; gap: .3rem; align-items: center; font-size: .82rem;
        padding: .2rem .5rem; border-radius: 999px; border: 1px solid transparent; }
.chip strong { font: 600 .8rem ui-monospace, SFMono-Regular, Menlo, monospace; }
.blocked   .cat-label, .chip.blocked   { color: #b42318; }
.chip.blocked   { background: #fef3f2; border-color: #fecdca; }
.stale     .cat-label, .chip.stale     { color: #b54708; }
.chip.stale     { background: #fffaeb; border-color: #fedf89; }
.review    .cat-label, .chip.review    { color: #175cd3; }
.chip.review    { background: #eff8ff; border-color: #b2ddff; }
.unassigned .cat-label, .chip.unassigned { color: #475467; }
.chip.unassigned { background: #f2f4f7; border-color: #d0d5dd; }
.ok { color: #067647; font-size: .85rem; }
.load { margin-top: .6rem; font-size: .85rem; color: #6941c6;
        background: #f9f5ff; border: 1px solid #e9d7fe; border-radius: 8px;
        padding: .4rem .6rem; display: inline-block; }
footer { color: #9ca3af; font-size: .78rem; text-align: center; margin-top: 1.5rem; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #e6edf3; }
  .project { background: #161b22; border-color: #30363d; }
  .sub, .meta, .bucket h3, .cat-label { color: #8b949e; }
  .key { background: #21262d; color: #8b949e; }
  .bucket { border-top-color: #21262d; }
  .focus { background: #1c2333; border-color: #2f3b54; }
  footer { color: #6e7681; }
}
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _chip(item, css) -> str:
    bits = [f"<strong>{_esc(item['key'])}</strong>"]
    if item.get("age_days") is not None:
        bits.append(f"{item['age_days']}d")
    if item.get("assignee"):
        bits.append(_esc(item["assignee"]))
    return (f'<span class="chip {css}" title="{_esc(item.get("summary", ""))}">'
            f'{" · ".join(bits)}</span>')


def _cat_row(fp, cat_key, label, emoji, css, keep) -> str:
    items = [i for i in fp[cat_key] if keep(i)]
    if not items:
        return ""
    chips = "".join(_chip(i, css) for i in items)
    return (f'<div class="cat {css}"><span class="cat-label">{emoji} {label}</span>'
            f'{chips}</div>')


def _rows(fp, keep) -> str:
    return "".join(_cat_row(fp, ck, lbl, emo, css, keep)
                   for ck, lbl, emo, css in _CATEGORIES)


def _project(fp) -> str:
    buckets = fp.get("component_buckets") or []
    body = ""
    if buckets:
        for b in buckets:
            rows = _rows(fp, lambda i, b=b: b in i["components"])
            inner = rows or '<span class="ok">✅ nothing flagged</span>'
            body += f'<div class="bucket"><h3>{_esc(b)}</h3>{inner}</div>'
        other = _rows(fp, lambda i: not (set(i["components"]) & set(buckets)))
        if other:
            body += f'<div class="bucket"><h3>(other)</h3>{other}</div>'
    else:
        body = _rows(fp, lambda i: True) or '<span class="ok">✅ nothing flagged</span>'

    if fp["overloaded"]:
        load = ", ".join(f'{_esc(o["assignee"])} ({o["wip"]} WIP)' for o in fp["overloaded"])
        body += f'<div class="load">⚖️ Load: {load}</div>'

    return (f'<section class="project"><header>'
            f'<h2>{_esc(fp["project"])}</h2><span class="key">{_esc(fp["key"])}</span>'
            f'<span class="meta">{fp["total_open"]} open</span></header>{body}</section>')


def render(all_findings, focus=None) -> str:
    today = datetime.now().strftime("%A %d %B %Y")
    focus_block = ""
    if focus:
        focus_block = (f'<div class="focus"><h2>Where I\'d focus — suggestion, '
                       f'you make the call</h2><p>{_esc(focus)}</p></div>')
    projects = "".join(_project(fp) for fp in all_findings)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Team Pulse — {today}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>🌅 Team Pulse</h1><p class="sub">{today}</p>
{focus_block}{projects}
<footer>Read-only triage · facts computed from Jira · you make the calls</footer>
</div></body></html>"""


def write(all_findings, path, focus=None) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(all_findings, focus=focus))
