from __future__ import annotations

from pydantic import BaseModel, Field

from agentic_scd.config import Settings, get_settings
from agentic_scd.ingestion.connectors.base import RawItem, SourceType

WEBHOOK_SOURCE_NAME = "supplier_webhook"


class WebhookEvent(BaseModel):
    title: str
    body: str = ""
    url: str | None = None
    published: str | None = None
    location: dict | None = None
    payload: dict = Field(default_factory=dict)

    def to_raw_item(self) -> RawItem:
        return RawItem(title=self.title, body=self.body, url=self.url, published=self.published, location=self.location, payload={"webhook_event": self.model_dump(), **self.payload})


class WebhookSource:
    source_type = SourceType.WEBHOOK

    def __init__(self, reliability: float, name: str = WEBHOOK_SOURCE_NAME) -> None:
        self.name = name
        self.reliability = reliability


def webhook_source(settings: Settings | None = None) -> WebhookSource:
    settings = settings or get_settings()
    return WebhookSource(reliability=settings.webhook_source_reliability)
