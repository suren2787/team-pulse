"""Project + threshold configuration.

Replace the placeholder project keys with your real Jira keys, and flip
`sprint_based` to False for any team that runs a rolling Kanban board (then
"stuck" is measured by how long an item has aged in-status, not by sprint
commitment).
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class ProjectConfig:
    key: str                 # Jira project key, e.g. "ARCH"
    name: str                # human label used in the digest
    sprint_based: bool = True
    # Status names that mean "waiting for review". Jira has no built-in
    # category for this, so it must be spelled out per your workflow.
    review_statuses: Tuple[str, ...] = ("In Review", "Code Review", "Review")
    # Status names that mean "blocked / impeded". An item is also treated as
    # blocked if it carries the Flagged field or a `blocked` label.
    blocked_statuses: Tuple[str, ...] = ("Blocked",)
    # Jira components used as task buckets. If set, this project's digest is
    # grouped under these headings; if empty, it renders as one flat list.
    components: Tuple[str, ...] = ()


# --- EDIT THESE: real project keys, and board type per team ------------------
PROJECTS = [
    ProjectConfig(key="ARCH", name="Architecture", sprint_based=False),
    ProjectConfig(key="APP",  name="App Services", sprint_based=True,
                  components=("BAU", "notifications", "shared", "iam")),
    ProjectConfig(key="OAPI", name="OpenAPI",      sprint_based=True),
]

# --- Thresholds (in days, except overload which is a WIP count) --------------
THRESHOLDS = {
    "stale":    3,   # In-Progress item not updated in >= N days -> stale WIP
    "review":   2,   # sitting in a review status >= N days -> review bottleneck
    "overload": 4,   # a person with >= N in-progress items -> overloaded
}
