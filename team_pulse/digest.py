"""Turn findings into a Slack message.

Two layers, on purpose:
  1. render_facts()  -> deterministic, accurate-by-construction. Always posts.
  2. llm_focus()     -> the LLM's short prioritisation note. If the model call
                        fails, the facts still go out — the digest degrades, it
                        doesn't disappear.
"""

import json
import os
from datetime import datetime


# (label, findings key, how to format one item)
_CATEGORIES = [
    ("🚫 Blocked", "blocked", lambda i: f"{i['key']} ({i['age_days']}d)"),
    ("🐌 Stale WIP", "stale_wip",
     lambda i: f"{i['key']} ({i['age_days']}d · {i['assignee'] or 'unassigned'})"),
    ("👀 In review", "review_wait", lambda i: f"{i['key']} ({i['age_days']}d)"),
    ("🫥 Unassigned", "unassigned", lambda i: i["key"]),
]


def _category_rows(fp, keep) -> list:
    """Formatted rows for the items in each category that pass the `keep` filter."""
    rows = []
    for label, field, fmt in _CATEGORIES:
        items = [i for i in fp[field] if keep(i)]
        if items:
            shown = ", ".join(fmt(i) for i in items[:5])
            more = " …" if len(items) > 5 else ""
            rows.append(f"{label}: {shown}{more}")
    return rows


def _distribution(fp) -> str:
    return " · ".join(
        f"{d['assignee']} {d['wip']}" + ("(idle)" if d["idle"] else "")
        for d in fp.get("distribution", []))


def _health_lines(fp) -> list:
    """The four manager questions, answered up top."""
    h = fp.get("health") or {}
    lines = []

    b = h.get("blockers", {})
    if b.get("count"):
        w = b["worst"]
        lines.append(f"    🚧 *Blockers:* {b['count']} — worst {w['key']} ({w['age_days']}d)")
    else:
        lines.append("    🚧 *Blockers:* none ✅")

    dist = _distribution(fp)
    if h.get("balance") == "balanced":
        lines.append(f"    👥 *Workload:* balanced ✅  ·  {dist}")
    else:
        lines.append(f"    👥 *Workload:* ⚠️ {h.get('balance_reason', '')}  ·  {dist}")

    ov = h.get("overloaded") or []
    if ov:
        lines.append("    🔥 *Overloaded:* "
                     + ", ".join(f"{o['assignee']} ({o['wip']} WIP)" for o in ov))
    else:
        lines.append("    🔥 *Overloaded:* no one ✅")

    bn = h.get("bottleneck")
    if bn:
        lines.append(f"    🚦 *Bottleneck:* {bn['count']} in review (oldest {bn['oldest_days']}d)")
    else:
        lines.append("    🚦 *Bottleneck:* none ✅")
    return lines


def render_facts(all_findings) -> str:
    lines = []
    for fp in all_findings:
        lines.append(f"*{fp['project']}* ({fp['key']}) — {fp['total_open']} open")
        lines += _health_lines(fp)

        buckets = fp.get("component_buckets") or []
        detail = []
        if buckets:
            for b in buckets:
                rows = _category_rows(fp, lambda i, b=b: b in i["components"])
                if rows:
                    detail.append(f"    • *{b}*: " + " · ".join(rows))
            other = _category_rows(fp, lambda i: not (set(i["components"]) & set(buckets)))
            if other:
                detail.append("    • *(other)*: " + " · ".join(other))
        else:
            detail += [f"    • {row}" for row in _category_rows(fp, lambda i: True)]

        if detail:
            lines.append("    _detail:_")
            lines += detail
        lines.append("")
    return "\n".join(lines).strip()


def llm_focus(all_findings) -> str:
    """Ask the model (via the LiteLLM proxy) for a short 'where to focus' note."""
    from openai import OpenAI  # imported lazily so --sample needs no network

    client = OpenAI(
        base_url=os.environ["LITELLM_BASE_URL"],
        api_key=os.environ["LITELLM_API_KEY"],
    )
    system = (
        "You are a delivery-triage assistant for an engineering lead who covers "
        "three teams. You are handed structured findings ALREADY VERIFIED from Jira. "
        "Write a short prioritisation note (max ~120 words) on where to spend "
        "attention first this morning. Rules: reference only ticket keys that appear "
        "in the data — never invent tickets, people, or facts. Weight blockers and "
        "review bottlenecks above general staleness. Note any cross-team pattern. "
        "Phrase it as a suggestion (\"I'd start with…\") — the lead makes the call. "
        "Use Slack mrkdwn. No preamble, no headings."
    )
    user = "Findings JSON:\n" + json.dumps(all_findings, indent=2)
    resp = client.chat.completions.create(
        model=os.environ.get("LITELLM_MODEL", "bedrock-claude"),
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=400,
    )
    return resp.choices[0].message.content.strip()


def get_focus(all_findings):
    """The LLM focus note, or None if the call fails (e.g. proxy off-VPN)."""
    try:
        return llm_focus(all_findings)
    except Exception:
        return None


def build_message(all_findings, focus=None) -> str:
    today = datetime.now().strftime("%a %d %b %Y")
    parts = [f":sunrise: *Team Pulse — {today}*", "", render_facts(all_findings)]
    if focus:
        parts += ["", "─────────",
                  "*Where I'd focus* — suggestion, you make the call:", focus]
    return "\n".join(parts)
