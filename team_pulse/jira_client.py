"""Thin Jira Cloud REST client — read only.

Uses the enhanced search endpoint (`/rest/api/3/search/jql`) with token
pagination. If you are on Jira Server/Data Center, swap the URL for
`/rest/api/2/search` and page with `startAt`/`total` instead.
"""

import os
import requests
from requests.auth import HTTPBasicAuth

_SESSION = requests.Session()


def _base() -> str:
    return os.environ["JIRA_BASE_URL"].rstrip("/")


def _auth() -> HTTPBasicAuth:
    # Jira Cloud: email + API token (https://id.atlassian.com/manage/api-tokens)
    return HTTPBasicAuth(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])


def search(jql: str, fields, page_size: int = 100):
    """Run a JQL query and return the full list of issue dicts, following pages."""
    url = f"{_base()}/rest/api/3/search/jql"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    issues = []
    next_token = None
    while True:
        payload = {"jql": jql, "fields": list(fields), "maxResults": page_size}
        if next_token:
            payload["nextPageToken"] = next_token
        resp = _SESSION.post(url, json=payload, auth=_auth(), headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        issues.extend(data.get("issues", []))
        next_token = data.get("nextPageToken")
        if data.get("isLast", True) or not next_token:
            break
    return issues
