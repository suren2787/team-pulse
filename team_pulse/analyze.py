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
            "components": [c["name"] for c in (f.get("components") or [])],
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
        if (status in p.blocked_statuses
                or is_flagged
                or any(l.lower() == "blocked" for l in labels)):
            blocked.append(rec)

        if category == "In Progress" and assignee_name:
            wip_by_assignee[assignee_name] = wip_by_assignee.get(assignee_name, 0) + 1

    for lst in (stale, review, unassigned, blocked):
        lst.sort(key=lambda x: -x["age_days"])

    # --- workload distribution across the team --------------------------------
    # Start from the roster (so idle members show up), then add anyone holding
    # work who isn't on the roster.
    roster = list(p.members) if p.members else sorted(wip_by_assignee)
    on_roster = set(roster)
    distribution = [{"assignee": m, "wip": wip_by_assignee.get(m, 0)} for m in roster]
    distribution += [{"assignee": m, "wip": n}
                     for m, n in sorted(wip_by_assignee.items()) if m not in on_roster]
    for d in distribution:
        d["idle"] = d["wip"] == 0
        d["overloaded"] = d["wip"] >= thresholds["overload"]
    distribution.sort(key=lambda d: -d["wip"])

    overloaded = [{"assignee": d["assignee"], "wip": d["wip"]}
                  for d in distribution if d["overloaded"]]
    overloaded_names = [d["assignee"] for d in overloaded]
    idle_names = [d["assignee"] for d in distribution if d["idle"]]
    someone_working = any(d["wip"] > 0 for d in distribution)

    if overloaded_names and idle_names:
        balance, reason = "imbalanced", (
            f"{', '.join(overloaded_names)} overloaded while {', '.join(idle_names)} idle")
    elif overloaded_names:
        balance, reason = "imbalanced", f"{', '.join(overloaded_names)} carrying heavy WIP"
    elif idle_names and someone_working:
        balance, reason = "check", f"{', '.join(idle_names)} idle — spare capacity"
    else:
        balance, reason = "balanced", ""

    health = {
        "blockers": {"count": len(blocked), "worst": blocked[0] if blocked else None},
        "balance": balance,                # balanced | check | imbalanced
        "balance_reason": reason,
        "overloaded": overloaded,
        "idle": idle_names,
        "bottleneck": ({"count": len(review), "oldest_days": review[0]["age_days"]}
                       if review else None),
    }

    return {
        "project": p.name,
        "key": p.key,
        "component_buckets": list(p.components),
        "total_open": len(issues),
        "blocked": blocked,
        "stale_wip": stale,
        "review_wait": review,
        "unassigned": unassigned,
        "overloaded": overloaded,
        "distribution": distribution,
        "health": health,
    }
