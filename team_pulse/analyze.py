"""Deterministic triage. This module is the source of truth — no LLM here.

Given the raw issues for a project, it decides what is blocked / stale / waiting
on review / unassigned / overloaded, using Jira's stable `statusCategory`
("To Do" / "In Progress" / "Done") rather than fragile per-workflow status names
wherever possible.
"""

from datetime import datetime, timezone
from dateutil import parser as dtparser

from .config import ProjectConfig


def scope_jql(p: ProjectConfig) -> str:
    """One query per project: everything open in scope. Python does the rest."""
    if p.sprint_based:
        return f'project = "{p.key}" AND sprint in openSprints() AND statusCategory != Done'
    return f'project = "{p.key}" AND statusCategory != Done'


def _age_days(ts: str) -> int:
    dt = dtparser.parse(ts).astimezone(timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def analyze_project(p: ProjectConfig, issues, thresholds, flagged_field=None) -> dict:
    stale, review, unassigned, blocked = [], [], [], []
    wip_by_assignee: dict[str, int] = {}

    for it in issues:
        f = it["fields"]
        status = f["status"]["name"]
        category = f["status"]["statusCategory"]["name"]  # To Do / In Progress / Done
        assignee = f.get("assignee")
        assignee_name = assignee["displayName"] if assignee else None
        age = _age_days(f["updated"])
        rec = {
            "key": it["key"],
            "summary": f.get("summary", ""),
            "assignee": assignee_name,
            "status": status,
            "age_days": age,
        }

        if category == "In Progress" and age >= thresholds["stale"]:
            stale.append(rec)
        if status in p.review_statuses and age >= thresholds["review"]:
            review.append(rec)
        if p.sprint_based and assignee_name is None:
            # committed to the sprint but nobody owns it
            unassigned.append(rec)

        is_flagged = bool(flagged_field and f.get(flagged_field))
        labels = f.get("labels") or []
        if is_flagged or any(l.lower() == "blocked" for l in labels):
            blocked.append(rec)

        if category == "In Progress" and assignee_name:
            wip_by_assignee[assignee_name] = wip_by_assignee.get(assignee_name, 0) + 1

    overloaded = sorted(
        ({"assignee": a, "wip": n} for a, n in wip_by_assignee.items()
         if n >= thresholds["overload"]),
        key=lambda x: -x["wip"],
    )
    for lst in (stale, review, unassigned, blocked):
        lst.sort(key=lambda x: -x["age_days"])

    return {
        "project": p.name,
        "key": p.key,
        "total_open": len(issues),
        "blocked": blocked,
        "stale_wip": stale,
        "review_wait": review,
        "unassigned": unassigned,
        "overloaded": overloaded,
    }
