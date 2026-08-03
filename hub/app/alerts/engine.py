"""Alerting: an EventBus subscriber, exactly as the architecture promised —
nothing upstream changes, rules just consume the same events the UI sees.

Rules match by event topic (or '*') and minimum severity; per-(rule, subject)
cooldowns keep a flapping node from flooding the notifier.
"""

import asyncio
import json
import logging
import time

import httpx
from sqlalchemy import select

from app.bus import Event, EventBus
from app.config import settings
from app.db import session_scope
from app.events import _severity
from app.models import AlertRule

logger = logging.getLogger("bifrost.alerts")

SEVERITY_RANK = {"info": 0, "warning": 1}

# Live metric frames never alert.
IGNORED_TOPICS = {"metrics.live"}

# Injectable for tests.
transport: httpx.AsyncBaseTransport | None = None


def render_message(event: Event) -> tuple[str, str]:
    """(title, body) in plain human language per topic."""
    data = event.data
    if event.topic == "node.status":
        status = data.get("status", "?")
        who = data.get("name") or data.get("uuid", "?")[:8]
        return (f"Node {who} is {status.upper()}", f"status → {status}")
    if event.topic == "k8s.cronjob.run":
        name = data.get("cronjob", "?")
        if data.get("succeeded"):
            return (f"CronJob {name} ok", f"finished in {data.get('duration_s')}s")
        return (
            f"CronJob {name} FAILED",
            data.get("failure_reason") or "no reason reported",
        )
    if event.topic == "disk.updated":
        failed = [d["serial"] for d in data.get("disks", []) if d.get("smart_status") == "failed"]
        if failed:
            return ("Disk SMART FAILURE", f"disks: {', '.join(failed)}")
        return ("Disks updated", "")
    if event.topic == "container.event":
        return (
            f"Container {data.get('name', '?')}: {data.get('action', '?')}",
            data.get("image") or "",
        )
    if event.topic == "endpoint.status":
        if data.get("kind") == "cert":
            return (
                f"Certificate for {data.get('host')} expires in {data.get('cert_days')}d",
                "renewal is due",
            )
        ok = data.get("ok")
        if "host" in data:
            status = data.get("status")
            return (
                f"Service {data.get('host')} is {'UP' if ok else 'DOWN'}",
                f"HTTP {status}" if status else "unreachable through the gateway",
            )
        return (f"Endpoint {'up' if ok else 'DOWN'}", data.get("uuid", ""))
    if event.topic == "image.update":
        return (
            f"Update available: {data.get('image')}",
            f"latest {data.get('latest')}",
        )
    return (event.topic, json.dumps(data)[:300])


async def send_notification(rule: AlertRule, event: Event) -> None:
    title, body = render_message(event)
    severity = _severity(event.topic, event.data)
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        if rule.notifier == "ntfy":
            response = await client.post(
                rule.target,
                content=body or title,
                headers={
                    "Title": title,
                    "Priority": "high" if severity == "warning" else "default",
                    "Tags": "warning" if severity == "warning" else "information_source",
                },
            )
        elif rule.notifier == "telegram":
            # rule.target is the chat id; the bot token is hub-level config.
            token = settings.telegram_bot_token
            if not token:
                raise RuntimeError("BIFROST_TELEGRAM_BOT_TOKEN is not set")
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": rule.target, "text": f"{title}\n{body}".strip()},
            )
        else:  # webhook
            response = await client.post(
                rule.target,
                json={
                    "topic": event.topic,
                    "severity": severity,
                    "ts": event.ts,
                    "title": title,
                    "body": body,
                    "data": event.data,
                },
            )
        response.raise_for_status()


def _subject(event: Event) -> str:
    return str(
        event.data.get("uuid") or event.data.get("cronjob") or event.data.get("name") or ""
    )


class AlertEngine:
    def __init__(self) -> None:
        # None-sentinel matters: time.monotonic() is seconds since boot on
        # Linux, so a freshly booted host has small values and a 0.0 sentinel
        # would read as "sent moments ago", muting every alert for the first
        # cooldown window after boot.
        self._last_sent: dict[tuple[int, str, str], float | None] = {}

    def matching_rules(self, event: Event) -> list[AlertRule]:
        severity = _severity(event.topic, event.data)
        with session_scope() as session:
            rules = session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))).all()
            matched = []
            for rule in rules:
                if rule.kind not in ("*", event.topic):
                    continue
                if SEVERITY_RANK[severity] < SEVERITY_RANK.get(rule.min_severity, 1):
                    continue
                matched.append(rule)
            session.expunge_all()
        return matched

    def cooled_down(self, rule: AlertRule, event: Event) -> bool:
        key = (rule.id, event.topic, _subject(event))
        last = self._last_sent.get(key)
        if last is not None and time.monotonic() - last < rule.cooldown_s:
            return False
        self._last_sent[key] = time.monotonic()
        return True

    async def handle(self, event: Event) -> None:
        if event.topic in IGNORED_TOPICS:
            return
        for rule in self.matching_rules(event):
            if not self.cooled_down(rule, event):
                continue
            try:
                await send_notification(rule, event)
            except Exception as exc:
                logger.warning("notification via %s failed: %s", rule.notifier, exc)


async def alerts_engine(bus: EventBus) -> None:
    engine = AlertEngine()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            try:
                await engine.handle(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("alert handling failed for %s", event.topic)
    finally:
        bus.unsubscribe(queue)
