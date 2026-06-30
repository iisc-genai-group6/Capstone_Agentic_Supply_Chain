from __future__ import annotations

import sys

import httpx

from agentic_scd.config import get_settings
from agentic_scd.ingestion.connectors.synthetic import SyntheticConnector
from agentic_scd.ingestion.webhook import WebhookEvent


def events() -> list[WebhookEvent]:
    connector = SyntheticConnector(name="synthetic_sender", reliability=0.6, count=3)
    return [WebhookEvent(title=item.title, body=item.body, payload=item.payload) for item in connector.fetch()]


def base_url(argv: list[str]) -> str:
    if len(argv) > 1:
        return argv[1].rstrip("/")
    settings = get_settings()
    return f"http://{settings.ingest_host}:{settings.ingest_port}"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    url = f"{base_url(argv)}/signals"
    print(f"POSTing synthetic supplier events to {url}")
    try:
        with httpx.Client(timeout=10.0) as client:
            for event in events():
                resp = client.post(url, json=event.model_dump())
                resp.raise_for_status()
                print(f"  - {event.title[:60]!r}: {resp.json()}")
    except httpx.HTTPError as exc:
        print(f"\nerror: could not reach the ingestion service ({exc}). Is it running? (`agentic-scd-ingest`)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
