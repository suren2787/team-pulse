# team-pulse

A read-only **morning triage** for an engineering lead who covers more than one
team. Each weekday it queries Jira across your projects, works out what's *stuck*,
and posts a short digest to Slack so you can see where to spend attention —
**without digging through boards yourself.**

It is **decision support, not a task bot.** It never writes to Jira, never nudges
your engineers, and never decides priorities. It surfaces; you decide.

## What it answers

Each team leads with the questions a lead actually asks, then the detail below:

- **🚧 Any blockers?** — count + the worst one
- **👥 Is the work spread across everyone?** — per-person WIP, with idle members flagged
- **🔥 Is anyone overloaded?** — names over the WIP limit
- **🚦 Where's the bottleneck?** — depth of the review queue
- **🎯 Top risk?** — the single most attention-worthy item (blocker > priority > age)

Across all teams, up top:

- **🔗 Cross-team dependencies** — where a ticket in one project is *blocked by* a
  ticket in another. This is the chain only the multi-team lead sees. Detected from
  Jira **"is blocked by" issue links** that cross project boundaries — so it only
  works if teams actually link blocking tickets.

Aging is **priority-weighted**: a High/Highest ticket (marked `❗`) outranks an older
low-priority one, so the flat-list problem is gone.

Underneath, the itemised detail per project, from one Jira query each:

- **🚫 Blocked** — items in a `Blocked` status, flagged as impediments, or labelled `blocked`
- **🐌 Stale WIP** — In-Progress items untouched for ≥ 3 days
- **👀 In review** — sitting in a review status for ≥ 2 days
- **🫥 Unassigned** — committed to the sprint but nobody owns it

Then one LLM call (via your LiteLLM proxy → Bedrock) adds a short
*"where I'd focus first"* note. Everything above the note is computed
deterministically in Python and is accurate by construction — the model only
writes the prose and cites keys it was handed.

## Design contract (why it's built this way)

1. **Jira's query engine finds the facts; the LLM never decides state.** If the
   digest and the board disagree, the board wins.
2. **The facts post even if the model call fails** — the focus note degrades
   gracefully, the digest doesn't disappear.
3. **Read-only.** Zero blast radius. The worst failure mode is a digest you
   ignore, not a ticket it broke.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your values
```

Edit `team_pulse/config.py`:
- set the three **project keys** to your real Jira keys
- flip `sprint_based=False` for any team on a **rolling Kanban** board
- add each team's **`members`** roster (Jira display names) so idle people show
  up — without it, someone with zero tickets is invisible
- tune `THRESHOLDS` if 3/2/4 days don't match your cadence

See it work with no credentials:

```bash
python -m team_pulse.main --sample              # prints a digest from sample/ fake data
python -m team_pulse.main --sample --html       # writes output/team-pulse-<timestamp>.html
```

### HTML report (no admin / webhook needed)

If Slack app creation is locked down, use the HTML report as delivery in the
meantime — it writes a self-contained file you open in a browser, no Slack, no
Jira write access:

```bash
python -m team_pulse.main --html                 # output/team-pulse-<timestamp>.html
python -m team_pulse.main --html pulse.html      # custom path instead
```

Each bare `--html` run writes a fresh timestamped file into `output/` (gitignored),
so you keep a browsable history rather than overwriting.

Then a real dry run (hits Jira + the LLM, prints instead of posting):

```bash
python -m team_pulse.main --dry-run
```

Go live:

```bash
python -m team_pulse.main               # posts to Slack
```

## Schedule it (laptop, weekday mornings ~08:00)

```cron
0 8 * * 1-5  cd /path/to/team-pulse && /path/to/.venv/bin/python -m team_pulse.main >> pulse.log 2>&1
```

## Setup notes

- **Jira Server/Data Center?** This uses the Cloud enhanced-search endpoint. Swap
  `/rest/api/3/search/jql` in `jira_client.py` for `/rest/api/2/search` and page
  with `startAt`/`total`.
- **Slack:** start with an Incoming Webhook into a private channel (5 min). Moving
  to a bot-token DM later is a one-file change in `slack.py`.
- **Secrets** live in `.env`, which is gitignored. Keep it that way.

## Roadmap (deliberately not in v1)

- **Day-over-day deltas** — "still stuck since yesterday" is where half the value
  is; needs a tiny bit of state between runs.
- **Standing context** — a short "what matters this quarter" note the focus draft
  reasons against, so priorities reflect business value, not just aging.
- **Team-facing version** — anonymised, work-item-focused, never person-focused.
  A separate output with a different social contract, not this one repurposed.
