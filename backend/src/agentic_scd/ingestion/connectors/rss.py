from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus

import httpx

from agentic_scd.ingestion.connectors.base import RawItem, SourceType

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
FETCH_TIMEOUT = 8.0


class RssConnector:
    source_type = SourceType.RSS

    def __init__(self, name: str, reliability: float, feeds: list[str], queries: list[str], fallback_path: Path | None = None) -> None:
        self.name = name
        self.reliability = reliability
        self.feeds = list(feeds)
        self.queries = list(queries)
        self.fallback_path = fallback_path

    def feed_urls(self) -> list[str]:
        urls = list(self.feeds)
        urls.extend(GOOGLE_NEWS_RSS.format(query=quote_plus(query)) for query in self.queries)
        return urls

    @staticmethod
    def parse_feed(content: bytes) -> list[RawItem]:
        try:
            import feedparser

            parsed = feedparser.parse(content)
            return [
                RawItem(
                    title=entry.get("title", ""),
                    body=entry.get("summary", "") or entry.get("description", ""),
                    url=entry.get("link"),
                    published=entry.get("published") or entry.get("updated"),
                    payload=dict(entry),
                )
                for entry in parsed.get("entries", [])
            ]
        except Exception:
            root = ET.fromstring(content)
            items: list[RawItem] = []
            for item in root.findall(".//item"):
                value = lambda name: (item.findtext(name) or "").strip()
                items.append(
                    RawItem(
                        title=value("title"),
                        body=value("description"),
                        url=value("link") or None,
                        published=value("pubDate") or None,
                        payload={"title": value("title"), "description": value("description")},
                    )
                )
            return items

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            for url in self.feed_urls():
                response = client.get(url)
                response.raise_for_status()
                items.extend(self.parse_feed(response.content))
        return items

    def fallback(self) -> list[RawItem]:
        if not self.fallback_path or not self.fallback_path.exists():
            return []
        return self.parse_feed(self.fallback_path.read_bytes())
