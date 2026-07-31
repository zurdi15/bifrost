import asyncio
import contextlib
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Event:
    topic: str  # 'node.status' | 'metrics.live' | 'container.event' | ...
    data: dict
    seq: int = 0
    ts: int = field(default_factory=lambda: int(time.time()))


class EventBus:
    """In-process pub/sub. Every state change flows through here exactly once;
    subscribers are the UI broadcaster, the events recorder and (later) alerting.

    Slow subscribers never block publishers: on a full queue the event is dropped
    for that subscriber only, and the resulting seq gap tells the UI to re-snapshot.
    """

    def __init__(self, queue_size: int = 1024) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._seq = 0

    @property
    def seq(self) -> int:
        return self._seq

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def publish(self, topic: str, data: dict) -> Event:
        self._seq += 1
        event = Event(topic=topic, data=data, seq=self._seq)
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)
        return event
