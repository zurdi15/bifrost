import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.engine import send_notification
from app.bus import Event
from app.db import get_session, session_scope
from app.models import AlertRule

router = APIRouter()

VALID_KINDS = {
    "*",
    "node.status",
    "container.event",
    "k8s.cronjob.run",
    "disk.updated",
    "endpoint.status",
    "k8s.cluster.discovered",
    "image.update",
}


def _rule_to_dict(rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "kind": rule.kind,
        "min_severity": rule.min_severity,
        "notifier": rule.notifier,
        "target": rule.target,
        "cooldown_s": rule.cooldown_s,
        "enabled": rule.enabled,
    }


@router.get("/alert-rules")
def list_rules(session: Session = Depends(get_session)) -> list[dict]:
    return [_rule_to_dict(r) for r in session.scalars(select(AlertRule).order_by(AlertRule.id))]


class RuleCreate(BaseModel):
    name: str
    kind: str = "*"
    min_severity: str = "warning"
    notifier: str
    target: str
    cooldown_s: int = 300


def _validate(body: RuleCreate) -> None:
    if body.kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"unknown kind {body.kind}")
    if body.notifier not in ("ntfy", "webhook", "telegram"):
        raise HTTPException(status_code=422, detail="notifier must be ntfy, webhook or telegram")
    if body.min_severity not in ("info", "warning"):
        raise HTTPException(status_code=422, detail="min_severity must be info or warning")


@router.post("/alert-rules", status_code=201)
def create_rule(body: RuleCreate, session: Session = Depends(get_session)) -> dict:
    _validate(body)
    rule = AlertRule(**body.model_dump())
    session.add(rule)
    session.flush()
    return _rule_to_dict(rule)


class RulePatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    target: str | None = None
    min_severity: str | None = None
    cooldown_s: int | None = None


@router.patch("/alert-rules/{rule_id}")
def patch_rule(
    rule_id: int, body: RulePatch, session: Session = Depends(get_session)
) -> dict:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    session.flush()
    return _rule_to_dict(rule)


@router.delete("/alert-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)) -> None:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)


@router.post("/alert-rules/{rule_id}/test")
async def test_rule(rule_id: int) -> dict:
    with session_scope() as session:
        rule = session.get(AlertRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        session.expunge(rule)
    event = Event(
        topic="node.status",
        data={"uuid": "test-node", "status": "offline"},
        seq=0,
        ts=int(time.time()),
    )
    try:
        await send_notification(rule, event)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"delivery failed: {exc}") from exc
    return {"sent": True}
