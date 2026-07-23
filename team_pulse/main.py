"""Entry point.

  python -m team_pulse.main --sample     # print a digest from bundled fake data
  python -m team_pulse.main --dry-run     # hit Jira + LLM, print, don't post
  python -m team_pulse.main               # the real thing: post to Slack
"""

import argparse
import json
import os

from dotenv import load_dotenv

from . import analyze, digest, html_report, jira_client, slack
from .config import PROJECTS, THRESHOLDS

_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "sample", "sample_findings.json")

# The Jira fields we actually read. Keep this tight — less to fetch, less to leak.
_FIELDS = ["summary", "status", "assignee", "updated", "labels", "components"]


def gather(sample: bool = False):
    if sample:
        with open(_SAMPLE) as fh:
            return json.load(fh)

    flagged = os.environ.get("JIRA_FLAGGED_FIELD_ID")  # optional customfield_XXXXX
    fields = _FIELDS + ([flagged] if flagged else [])

    results = []
    for p in PROJECTS:
        issues = jira_client.search(analyze.scope_jql(p), fields)
        results.append(analyze.analyze_project(p, issues, THRESHOLDS, flagged))
    return results


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Read-only Jira -> Slack morning triage.")
    ap.add_argument("--sample", action="store_true",
                    help="use bundled fake data; no Jira, no LLM, no Slack")
    ap.add_argument("--dry-run", action="store_true",
                    help="query Jira + LLM but print instead of posting to Slack")
    ap.add_argument("--no-focus", action="store_true",
                    help="skip the LLM focus note (facts only)")
    ap.add_argument("--html", nargs="?", const="team-pulse.html", default=None,
                    metavar="PATH",
                    help="write an HTML report to PATH (default team-pulse.html) "
                         "instead of posting to Slack — no admin/webhook needed")
    args = ap.parse_args()

    findings = gather(sample=args.sample)
    # sample mode stays fully offline (facts only); everything else gets the focus note
    with_focus = not args.no_focus and not args.sample
    focus = digest.get_focus(findings) if with_focus else None

    if args.html is not None:
        html_report.write(findings, args.html, focus=focus)
        print(f"Wrote {args.html}")
        return

    message = digest.build_message(findings, focus=focus)
    if args.sample or args.dry_run:
        print(message)
    else:
        slack.post(message)
        print("Posted to Slack.")


if __name__ == "__main__":
    main()
