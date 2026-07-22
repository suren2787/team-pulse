"""Post the digest to a Slack Incoming Webhook (a private channel, to start)."""

import os
import requests


def post(text: str) -> None:
    url = os.environ["SLACK_WEBHOOK_URL"]
    resp = requests.post(url, json={"text": text}, timeout=15)
    resp.raise_for_status()
