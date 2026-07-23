"""Render the digest as a self-contained, modern HTML dashboard.

Tabbed per team, clickable ticket links, workload bars, KPI summary. No infra,
no network — open the file in a browser. Colours follow a validated status
palette (good / serious / warning / critical) and are light/dark aware.
"""

import html
from datetime import datetime

# (findings key, label, emoji, category css class)
_CATEGORIES = [
    ("blocked", "Blocked", "🚫", "cat-blocked"),
    ("stale_wip", "Stale WIP", "🐌", "cat-stale"),
    ("review_wait", "In review", "👀", "cat-review"),
    ("unassigned", "Unassigned", "🫥", "cat-unassigned"),
]

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
     font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
     -webkit-font-smoothing:antialiased}
.app{--plane:#f4f4f2;--surface:#fcfcfb;--raised:#fff;--ink:#0b0b0b;--ink2:#52514e;
     --muted:#898781;--border:rgba(11,11,11,.10);--hair:#e6e5df;
     --good:#0ca30c;--warn:#fab219;--crit:#d03b3b;--serious:#ec835a;--blue:#2a78d6;
     --shadow:0 1px 2px rgba(11,11,11,.04),0 2px 8px rgba(11,11,11,.06);
     color-scheme:light;max-width:960px;margin:0 auto;padding:2rem 1.15rem 3rem}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .app{
     --plane:#0b0d10;--surface:#161a1f;--raised:#1b2027;--ink:#f2f4f7;--ink2:#c3c2b7;
     --muted:#8b949e;--border:rgba(255,255,255,.10);--hair:#2a2f37;
     --shadow:0 1px 2px rgba(0,0,0,.3),0 2px 10px rgba(0,0,0,.35);color-scheme:dark}}
:root[data-theme="dark"] .app{
     --plane:#0b0d10;--surface:#161a1f;--raised:#1b2027;--ink:#f2f4f7;--ink2:#c3c2b7;
     --muted:#8b949e;--border:rgba(255,255,255,.10);--hair:#2a2f37;
     --shadow:0 1px 2px rgba(0,0,0,.3),0 2px 10px rgba(0,0,0,.35);color-scheme:dark}

.top{display:flex;align-items:center;gap:.6rem;margin-bottom:.15rem}
.top .logo{font-size:1.5rem}
.top h1{font-size:1.35rem;font-weight:680;margin:0;letter-spacing:-.01em}
.date{color:var(--ink2);font-size:.9rem;margin:0 0 1.4rem 2.1rem}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
      gap:.7rem;margin-bottom:1.3rem}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;
     padding:.85rem .95rem;box-shadow:var(--shadow)}
.kpi .n{font-size:1.9rem;font-weight:700;line-height:1;letter-spacing:-.02em}
.kpi .l{color:var(--muted);font-size:.72rem;text-transform:uppercase;
        letter-spacing:.05em;margin-top:.4rem;font-weight:600}
.n.crit{color:var(--crit)}.n.warn{color:#c77f0a}.n.blue{color:var(--blue)}.n.ok{color:var(--good)}
@media (prefers-color-scheme:dark){.n.warn{color:var(--warn)}}

.focus{background:linear-gradient(180deg,rgba(42,120,214,.08),rgba(42,120,214,.03));
       border:1px solid rgba(42,120,214,.25);border-radius:14px;padding:.9rem 1.1rem;
       margin-bottom:1.3rem}
.focus h2{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;
          color:var(--blue);margin:0 0 .45rem;font-weight:700}
.focus p{margin:0;white-space:pre-wrap;color:var(--ink)}

.tabs{display:flex;gap:.3rem;background:var(--surface);border:1px solid var(--border);
      border-radius:12px;padding:.3rem;margin-bottom:1.1rem;box-shadow:var(--shadow)}
.tab{flex:1;display:flex;align-items:center;justify-content:center;gap:.45rem;
     border:0;background:transparent;color:var(--ink2);font:inherit;font-weight:600;
     font-size:.9rem;padding:.55rem .5rem;border-radius:9px;cursor:pointer;
     transition:background .15s,color .15s}
.tab:hover{color:var(--ink)}
.tab.active{background:var(--raised);color:var(--ink);box-shadow:var(--shadow)}
.tab .dot{width:8px;height:8px;border-radius:50%;flex:none}
.dot.ok{background:var(--good)}.dot.att{background:var(--crit)}

.panel{display:none}.panel.active{display:block}
.panel .head{display:flex;align-items:baseline;gap:.55rem;margin:.2rem 0 .9rem}
.panel .head .key{font:600 .68rem/1 ui-monospace,SFMono-Regular,Menlo,monospace;
     background:var(--surface);color:var(--muted);border:1px solid var(--border);
     padding:.22rem .45rem;border-radius:6px}
.panel .head .cnt{margin-left:auto;color:var(--muted);font-size:.85rem}

.answers{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
         gap:.7rem;margin-bottom:1.1rem}
.acard{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--muted);
       border-radius:12px;padding:.75rem .85rem;box-shadow:var(--shadow)}
.acard.good{border-left-color:var(--good)}
.acard.warn{border-left-color:var(--warn)}
.acard.crit{border-left-color:var(--crit)}
.acard .q{display:flex;align-items:center;gap:.35rem;color:var(--muted);
          font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
.acard .v{font-size:1.15rem;font-weight:680;margin-top:.35rem;letter-spacing:-.01em}
.acard.good .v{color:var(--good)}.acard.crit .v{color:var(--crit)}
.acard.warn .v{color:#c77f0a}
@media (prefers-color-scheme:dark){.acard.warn .v{color:var(--warn)}}
.acard .s{color:var(--ink2);font-size:.8rem;margin-top:.2rem}

.block{background:var(--surface);border:1px solid var(--border);border-radius:14px;
       padding:1rem 1.1rem;margin-bottom:1rem;box-shadow:var(--shadow)}
.block h4{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;
          color:var(--muted);margin:0 0 .7rem;font-weight:700}
.wrow{display:flex;align-items:center;gap:.7rem;margin:.4rem 0}
.wname{flex:0 0 7.5rem;font-size:.88rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wtrack{flex:1;height:9px;background:var(--hair);border-radius:99px;overflow:hidden}
.wbar{display:block;height:100%;border-radius:99px}
.wbar.norm{background:var(--blue)}.wbar.over{background:var(--crit)}
.wbar.guest{background:#9085e9}
.guest{font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;
       color:#6b5fd6;background:rgba(144,133,233,.16);border-radius:5px;padding:.05rem .3rem}
.wval{flex:0 0 3.6rem;text-align:right;font-size:.82rem;color:var(--ink2);
      font-variant-numeric:tabular-nums}
.wval.idle{color:var(--muted)}

.bucket{padding:.55rem 0;border-top:1px dashed var(--hair)}
.bucket:first-child{border-top:0;padding-top:0}
.bucket h5{font-size:.74rem;text-transform:uppercase;letter-spacing:.03em;
           color:var(--ink2);margin:0 0 .45rem;font-weight:700}
.cat{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem;margin:.35rem 0}
.cat-label{font-size:.8rem;font-weight:600;color:var(--ink2);margin-right:.15rem}
.chip{display:inline-flex;align-items:center;gap:.35rem;text-decoration:none;
      font-size:.82rem;padding:.24rem .55rem;border-radius:99px;color:var(--ink);
      border:1px solid var(--border);transition:transform .1s,box-shadow .1s}
a.chip:hover{transform:translateY(-1px);box-shadow:var(--shadow)}
.chip .k{font:600 .8rem ui-monospace,SFMono-Regular,Menlo,monospace}
.chip .m{color:var(--ink2);font-size:.78rem}
.chip.cat-blocked{background:rgba(208,59,59,.12);border-color:rgba(208,59,59,.3)}
.chip.cat-stale{background:rgba(236,131,90,.14);border-color:rgba(236,131,90,.32)}
.chip.cat-review{background:rgba(42,120,214,.12);border-color:rgba(42,120,214,.3)}
.chip.cat-unassigned{background:rgba(137,135,129,.14);border-color:rgba(137,135,129,.32)}
.chip.hi{box-shadow:inset 3px 0 0 var(--crit)}
.chip.hi .k::after{content:"❗";font-size:.7rem;margin-left:.15rem}
.empty{color:var(--good);font-size:.85rem}

.xblock{background:var(--surface);border:1px solid var(--border);
        border-left:4px solid var(--crit);border-radius:14px;padding:.9rem 1.1rem;
        margin-bottom:1.3rem;box-shadow:var(--shadow)}
.xblock h2{font-size:.95rem;margin:0;font-weight:680}
.xsub{color:var(--muted);font-size:.78rem;margin:.15rem 0 .7rem}
.xrow{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;padding:.4rem 0;
      border-top:1px dashed var(--hair);font-size:.88rem}
.xrow:first-of-type{border-top:0}
.xrow.done{opacity:.55}
.xkey{font:600 .82rem ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--blue);
      text-decoration:none;border-bottom:1px solid transparent}
a.xkey:hover{border-bottom-color:var(--blue)}
.xarr{color:var(--crit);font-size:.78rem;font-weight:600}
.xrow.done .xarr{color:var(--muted)}
.xstatus{color:var(--ink2);font-size:.78rem;background:var(--plane);
         border:1px solid var(--border);border-radius:6px;padding:.1rem .4rem}
.xdone{color:var(--good);font-size:.76rem;font-weight:600}
footer{color:var(--muted);font-size:.76rem;text-align:center;margin-top:1.6rem}
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


# ---------- ticket chips -----------------------------------------------------

def _ticket(item, base, css) -> str:
    meta = []
    if item.get("age_days") is not None:
        meta.append(f"{item['age_days']}d")
    if item.get("assignee"):
        meta.append(_esc(item["assignee"]))
    high = item.get("prank", 3) >= 4          # High / Highest
    cls = f"{css} hi" if high else css
    inner = (f'<span class="k">{_esc(item["key"])}</span>'
             + (f'<span class="m">{" · ".join(meta)}</span>' if meta else ""))
    pri = item.get("priority")
    title = _esc(f'{item.get("summary", "")}' + (f'  [{pri}]' if pri else ""))
    if base:
        href = f'{base}/browse/{_esc(item["key"])}'
        return (f'<a class="chip {cls}" href="{href}" target="_blank" '
                f'rel="noopener" title="{title}">{inner}</a>')
    return f'<span class="chip {cls}" title="{title}">{inner}</span>'


def _cat_row(fp, cat_key, label, emoji, css, base, keep) -> str:
    items = [i for i in fp[cat_key] if keep(i)]
    if not items:
        return ""
    chips = "".join(_ticket(i, base, css) for i in items)
    return f'<div class="cat"><span class="cat-label">{emoji} {label}</span>{chips}</div>'


def _rows(fp, base, keep) -> str:
    return "".join(_cat_row(fp, ck, lbl, emo, css, base, keep)
                   for ck, lbl, emo, css in _CATEGORIES)


# ---------- answer cards -----------------------------------------------------

def _answer_cards(fp) -> str:
    h = fp.get("health") or {}
    cards = []

    b = h.get("blockers", {})
    if b.get("count"):
        w = b["worst"]
        cards.append(("🚧", "Blockers", "crit", str(b["count"]),
                      f'worst {_esc(w["key"])} · {w["age_days"]}d'))
    else:
        cards.append(("🚧", "Blockers", "good", "0", "all clear"))

    bal = h.get("balance")
    if bal == "balanced":
        cards.append(("👥", "Workload", "good", "Even", "spread across the team"))
    else:
        status = "crit" if bal == "imbalanced" else "warn"
        cards.append(("👥", "Workload", status, "Uneven",
                      _esc(h.get("balance_reason", ""))))

    ov = h.get("overloaded") or []
    if ov:
        names = ", ".join(
            f'{_esc(o["assignee"])} ({o["wip"]}){" ·guest" if o.get("guest") else ""}'
            for o in ov)
        cards.append(("🔥", "Overloaded", "crit", str(len(ov)), names))
    else:
        cards.append(("🔥", "Overloaded", "good", "0", "no one over limit"))

    bn = h.get("bottleneck")
    if bn:
        cards.append(("🚦", "Bottleneck", "warn", str(bn["count"]),
                      f'in review · oldest {bn["oldest_days"]}d'))
    else:
        cards.append(("🚦", "Bottleneck", "good", "0", "review queue clear"))

    tr = h.get("top_risk")
    if tr:
        pri = tr.get("priority") or "—"
        cards.append(("🎯", "Top risk", "warn", _esc(tr["key"]),
                      f'{tr["kind"]} · {tr["age_days"]}d · {_esc(pri)}'))

    out = '<div class="answers">'
    for icon, q, status, value, sub in cards:
        out += (f'<div class="acard {status}"><div class="q">{icon} {q}</div>'
                f'<div class="v">{value}</div><div class="s">{sub}</div></div>')
    return out + "</div>"


# ---------- workload bars ----------------------------------------------------

def _workload(fp) -> str:
    dist = fp.get("distribution") or []
    if not dist:
        return ""
    peak = max((d["wip"] for d in dist), default=0) or 1
    rows = ""
    for d in dist:
        if d["wip"]:
            pct = max(round(d["wip"] / peak * 100), 6)
            state = "over" if d["overloaded"] else ("guest" if d.get("guest") else "norm")
            bar = f'<span class="wbar {state}" style="width:{pct}%"></span>'
            val = f'<span class="wval">{d["wip"]}</span>'
        else:
            bar = ""
            val = '<span class="wval idle">idle</span>'
        tag = ' <span class="guest">guest</span>' if d.get("guest") else ""
        rows += (f'<div class="wrow"><span class="wname">{_esc(d["assignee"])}{tag}</span>'
                 f'<span class="wtrack">{bar}</span>{val}</div>')
    return f'<div class="block"><h4>Workload — in-progress items per person</h4>{rows}</div>'


# ---------- detail -----------------------------------------------------------

def _detail(fp, base) -> str:
    buckets = fp.get("component_buckets") or []
    inner = ""
    if buckets:
        for b in buckets:
            rows = _rows(fp, base, lambda i, b=b: b in i["components"])
            body = rows or '<span class="empty">✅ nothing flagged</span>'
            inner += f'<div class="bucket"><h5>{_esc(b)}</h5>{body}</div>'
        other = _rows(fp, base, lambda i: not (set(i["components"]) & set(buckets)))
        if other:
            inner += f'<div class="bucket"><h5>Other</h5>{other}</div>'
    else:
        rows = _rows(fp, base, lambda i: True)
        inner = f'<div class="bucket">{rows}</div>' if rows else \
                '<span class="empty">✅ nothing flagged</span>'
    return f'<div class="block"><h4>Detail</h4>{inner}</div>'


# ---------- assembly ---------------------------------------------------------

def _needs_attention(fp) -> bool:
    h = fp.get("health") or {}
    return bool(h.get("blockers", {}).get("count")
                or h.get("overloaded") or h.get("balance") == "imbalanced")


_DONE_WORDS = ("done", "closed", "resolved")


def _active_dep(e) -> bool:
    return not any(w in (e.get("blocker_status") or "").lower() for w in _DONE_WORDS)


def _kpis(all_findings, cross_team) -> str:
    blockers = sum((fp.get("health", {}).get("blockers", {}).get("count", 0))
                   for fp in all_findings)
    overloaded = sum(len(fp.get("health", {}).get("overloaded", [])) for fp in all_findings)
    idle = sum(len(fp.get("health", {}).get("idle", [])) for fp in all_findings)
    review = sum((fp.get("health", {}).get("bottleneck") or {}).get("count", 0)
                 for fp in all_findings)
    xteam = sum(1 for e in (cross_team or []) if _active_dep(e))
    tiles = [
        (blockers, "Blockers", "crit" if blockers else "ok"),
        (xteam, "Cross-team", "crit" if xteam else "ok"),
        (overloaded, "Overloaded", "crit" if overloaded else "ok"),
        (idle, "Idle", "warn" if idle else "ok"),
        (review, "In review", "blue" if review else "ok"),
    ]
    out = '<div class="kpis">'
    for n, label, cls in tiles:
        out += f'<div class="kpi"><div class="n {cls}">{n}</div><div class="l">{label}</div></div>'
    return out + "</div>"


def _cross_team_block(cross_team, base) -> str:
    if not cross_team:
        return ""
    def link(key):
        if base:
            return (f'<a class="xkey" href="{base}/browse/{_esc(key)}" '
                    f'target="_blank" rel="noopener">{_esc(key)}</a>')
        return f'<span class="xkey">{_esc(key)}</span>'

    rows = ""
    for e in cross_team:
        active = _active_dep(e)
        cls = "xrow" + ("" if active else " done")
        badge = "" if active else '<span class="xdone">resolved ✅</span>'
        rows += (f'<div class="{cls}">{link(e["blocked_key"])}'
                 f'<span class="xarr">⟵ blocked by</span>{link(e["blocker_key"])}'
                 f'<span class="xstatus">{_esc(e["blocker_project"])}: '
                 f'{_esc(e["blocker_status"])}</span>{badge}</div>')
    return (f'<div class="xblock"><h2>🔗 Cross-team dependencies</h2>'
            f'<p class="xsub">Chains only you see across all three teams</p>{rows}</div>')


def _tabs(all_findings) -> str:
    out = '<div class="tabs" role="tablist">'
    for i, fp in enumerate(all_findings):
        dot = "att" if _needs_attention(fp) else "ok"
        active = " active" if i == 0 else ""
        out += (f'<button class="tab{active}" data-tab="{_esc(fp["key"])}">'
                f'<span class="dot {dot}"></span>{_esc(fp["project"])}</button>')
    return out + "</div>"


def _panel(fp, base, active) -> str:
    return (f'<section class="panel{active}" data-panel="{_esc(fp["key"])}">'
            f'<div class="head"><span class="key">{_esc(fp["key"])}</span>'
            f'<span class="cnt">{fp["total_open"]} open</span></div>'
            f'{_answer_cards(fp)}{_workload(fp)}{_detail(fp, base)}</section>')


_JS = """
document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click',function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});
    document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active')});
    t.classList.add('active');
    var p=document.querySelector('[data-panel="'+t.dataset.tab+'"]');
    if(p)p.classList.add('active');
  });
});
"""


def render(all_findings, focus=None, jira_base="", cross_team=None) -> str:
    base = (jira_base or "").rstrip("/")
    today = datetime.now().strftime("%A %d %B %Y")
    focus_block = ""
    if focus:
        focus_block = (f'<div class="focus"><h2>Where I\'d focus — suggestion, you '
                       f'make the call</h2><p>{_esc(focus)}</p></div>')
    panels = "".join(_panel(fp, base, " active" if i == 0 else "")
                     for i, fp in enumerate(all_findings))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Team Pulse — {today}</title><style>{_CSS}</style></head>
<body><div class="app">
<div class="top"><span class="logo">🌤️</span><h1>Team Pulse</h1></div>
<p class="date">{today}</p>
{_kpis(all_findings, cross_team)}
{focus_block}
{_cross_team_block(cross_team, base)}
{_tabs(all_findings)}
{panels}
<footer>Read-only triage · facts computed from Jira · you make the calls</footer>
</div><script>{_JS}</script></body></html>"""


def write(all_findings, path, focus=None, jira_base="", cross_team=None) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(all_findings, focus=focus, jira_base=jira_base,
                        cross_team=cross_team))
