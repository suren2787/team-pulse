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


# Jira default priority names → rank (higher = more urgent). Unknown ≈ Medium.
_PRIORITY_RANK = {"Highest": 5, "High": 4, "Medium": 3, "Low": 2, "Lowest": 1}


def _prank(name) -> int:
    return _PRIORITY_RANK.get(name, 3)


def _project_of(key: str) -> str:
    return key.split("-")[0] if key else ""


def _cross_team_deps(it, this_project: str) -> list:
    """Blocking links from this issue to an issue in a *different* project.

    Returns normalised blocker→blocked edges. Both ends of a Jira link report it,
    so callers should de-dupe by (blocker, blocked).
    """
    edges = []
    this = it["key"]
    this_summary = it["fields"].get("summary", "")
    for link in it["fields"].get("issuelinks") or []:
        t = link.get("type", {})
        inward = (t.get("inward") or "").lower()
        outward = (t.get("outward") or "").lower()
        # this issue is blocked by the inward issue
        if link.get("inwardIssue") and inward.startswith("is blocked"):
            other = link["inwardIssue"]
            blocker, blocked, bsum = other, {"key": this, "fields": it["fields"]}, None
            blocked_summary = this_summary
            blocker_summary = other["fields"].get("summary", "")
        # this issue blocks the outward issue
        elif link.get("outwardIssue") and outward.startswith("blocks"):
            other = link["outwardIssue"]
            blocker, blocked = {"key": this, "fields": it["fields"]}, other
            blocker_summary = this_summary
            blocked_summary = other["fields"].get("summary", "")
        else:
            continue

        bk, dk = blocker["key"], blocked["key"]
        if _project_of(bk) == _project_of(dk):
            continue  # same team — not the cross-team signal we're after
        bstatus = (blocker["fields"].get("status") or {}).get("name", "")
        edges.append({
            "blocker_key": bk, "blocker_project": _project_of(bk),
            "blocker_status": bstatus, "blocker_summary": blocker_summary,
            "blocked_key": dk, "blocked_project": _project_of(dk),
            "blocked_summary": blocked_summary,
        })
    return edges


def analyze_project(p: ProjectConfig, issues, thresholds, flagged_field=None) -> dict:
    stale, review, unassigned, blocked = [], [], [], []
    wip_by_assignee: dict[str, int] = {}
    deps = []

    for it in issues:
        f = it["fields"]
        status = f["status"]["name"]
        category = f["status"]["statusCategory"]["name"]  # To Do / In Progress / Done
        assignee = f.get("assignee")
        assignee_name = assignee["displayName"] if assignee else None
        age = _age_days(f["updated"])
        priority = (f.get("priority") or {}).get("name")
        rec = {
            "key": it["key"],
            "summary": f.get("summary", ""),
            "assignee": assignee_name,
            "status": status,
            "age_days": age,
            "priority": priority,
            "prank": _prank(priority),
            "components": [c["name"] for c in (f.get("components") or [])],
        }
        deps += _cross_team_deps(it, p.key)

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

    # priority first, then age — so a High priority item outranks an older Low one
    for lst in (stale, review, unassigned, blocked):
        lst.sort(key=lambda x: (-x["prank"], -x["age_days"]))

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

    # --- top risk: the single most attention-worthy flagged item --------------
    # blocked weighs heaviest, then priority, then age.
    def _risk(rec, kind):
        base = {"blocked": 100, "review": 10, "stale": 10}[kind]
        return base + rec["prank"] * 20 + rec["age_days"]

    candidates = ([(r, "blocked") for r in blocked]
                  + [(r, "review") for r in review]
                  + [(r, "stale") for r in stale])
    top_risk = None
    if candidates:
        rec, kind = max(candidates, key=lambda c: _risk(*c))
        top_risk = {"key": rec["key"], "priority": rec["priority"],
                    "age_days": rec["age_days"], "kind": kind}

    health = {
        "blockers": {"count": len(blocked), "worst": blocked[0] if blocked else None},
        "balance": balance,                # balanced | check | imbalanced
        "balance_reason": reason,
        "overloaded": overloaded,
        "idle": idle_names,
        "bottleneck": ({"count": len(review), "oldest_days": review[0]["age_days"]}
                       if review else None),
        "top_risk": top_risk,
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
        "deps": deps,
    }
