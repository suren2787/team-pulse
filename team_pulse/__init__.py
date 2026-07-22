"""team-pulse: a read-only Jira → Slack morning triage for an engineering lead.

The design contract (see README):
  - Jira is queried deterministically. Python decides what is "stuck".
  - The LLM only writes the short "where I'd focus" note, citing keys it was given.
  - Nothing is ever written back to Jira. Zero blast radius.
"""

__version__ = "0.1.0"
