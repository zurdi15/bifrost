"""Tailnet section feed: the device graph the poller derived.

GET serves the cached snapshot — request handlers never talk to the admin
API. POST /refresh forces a sweep for the UI's re-sync control; with no key
and no fixture it stays a cheap no-op returning the unconfigured shape."""

from fastapi import APIRouter, Request

from app.tailnet import poller

router = APIRouter()


@router.get("/tailnet")
def tailnet_state() -> dict:
    return poller.current()


@router.post("/tailnet/refresh")
async def tailnet_refresh(request: Request) -> dict:
    await poller.sweep_once(request.app.state.bus)
    return poller.current()
