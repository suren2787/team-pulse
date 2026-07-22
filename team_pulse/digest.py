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


def render_facts(all_findings) -> str:
    lines = []
    for fp in all_findings:
        lines.append(f"*{fp['project']}* ({fp['key']}) — {fp['total_open']} open")

        def row(title, items, fmt):
            if items:
                shown = ", ".join(fmt(i) for i in items[:5])
                more = " …" if len(items) > 5 else ""
                lines.append(f"    • {title}: {shown}{more}")

        row("🚫 Blocked", fp["blocked"],
            lambda i: f"{i['key']} ({i['age_days']}d)")
        row("🐌 Stale WIP", fp["stale_wip"],
            lambda i: f"{i['key']} ({i['age_days']}d · {i['assignee'] or 'unassigned'})")
        row("👀 In review", fp["review_wait"],
            lambda i: f"{i['key']} ({i['age_days']}d)")
        row("🫥 Unassigned", fp["unassigned"], lambda i: i["key"])
        if fp["overloaded"]:
            load = ", ".join(f"{o['assignee']} ({o['wip']} WIP)" for o in fp["overloaded"])
            lines.append(f"    • ⚖️ Load: {load}")

        if not any((fp["blocked"], fp["stale_wip"], fp["review_wait"],
                    fp["unassigned"], fp["overloaded"])):
            lines.append("    • ✅ nothing flagged")
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


def build_message(all_findings, with_focus: bool = True) -> str:
    today = datetime.now().strftime("%a %d %b %Y")
    parts = [f":sunrise: *Team Pulse — {today}*", "", render_facts(all_findings)]
    if with_focus:
        try:
            focus = llm_focus(all_findings)
            parts += ["", "─────────",
                      "*Where I'd focus* — suggestion, you make the call:",
                      focus]
        except Exception as exc:  # never let the model break the digest
            parts += ["", f"_(focus note unavailable: {exc})_"]
    return "\n".join(parts)
