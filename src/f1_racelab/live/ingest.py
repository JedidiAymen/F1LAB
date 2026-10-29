"""Single-ingest WebSocket fan-out for live (or simulated-live) race data.

Architecture:
- One `LiveSession` object owns the upstream feed per session key.
- Multiple browser WebSocket connections subscribe to that session.
- On each tick the session advances its clock and emits a RaceState delta.
- All subscribers receive the same snapshot+delta; reconnects get a full snapshot.
- When a real OpenF1 WebSocket subscription is unavailable, the session can
  run in SIMULATED_LIVE mode: it replays a cached pack at real-time speed,
  emitting events as if they had just arrived.

Limitations (included in every snapshot):
- Simulated live is NOT real-time data; the badge SIMULATED LIVE must be
  shown in the UI whenever this mode is active.
- Real OpenF1 live requires a valid subscription not available in the OSS repo;
  the adapter interface is provided but no credentials are included.
- Reconnect delivers the most recent snapshot, not event history.
- WebSocket backpressure is handled by dropping stale messages to slow clients;
  no guaranteed delivery.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Literal, Self

from f1_racelab.session.replay_source import ReplaySource

SIMULATED_LIVE_BADGE = 'SIMULATED LIVE'

PACK_ROOT = Path(__file__).resolve().parents[3] / 'data/processed/replay_packs'


class LiveSession:
    """One upstream feed + subscriber fan-out for a session.

    Usage:
        session = LiveSession('monza-2025', mode='simulated', speed=1.0)
        await session.start()
        async for snapshot in session.subscribe():
            ...  # send to one WebSocket client
    """

    def __init__(
        self,
        session_slug: str,
        *,
        mode: Literal['simulated', 'real'] = 'simulated',
        speed: float = 1.0,
        pack_root: Path = PACK_ROOT,
    ) -> None:
        self.session_slug = session_slug
        self.mode = mode
        self.speed = max(0.1, min(speed, 16.0))
        self.pack_root = pack_root
        self._replay: ReplaySource | None = None
        self._subscribers: list[asyncio.Queue] = []
        self._task: asyncio.Task | None = None
        self._last_snapshot: dict | None = None
        self._session_time = 0.0
        self._running = False

    def _load_replay(self) -> ReplaySource:
        candidates = list(self.pack_root.glob(
            f'{self.session_slug.replace("-", "_")}_race.json.gz'
        ))
        if not candidates:
            raise FileNotFoundError(f'No pack found for {self.session_slug!r}')
        return ReplaySource.from_file(candidates[0])

    def _build_snapshot(self, session_time: float) -> dict:
        assert self._replay is not None
        state = self._replay.state_at(session_time)
        return {
            'type': 'snapshot',
            'session_slug': self.session_slug,
            'session_time_seconds': round(session_time, 3),
            'mode': self.mode,
            'badge': SIMULATED_LIVE_BADGE if self.mode == 'simulated' else None,
            'state': state.model_dump(
                mode='json',
                exclude={'applied_event_ids', 'applied_event_hashes',
                         'event_log', 'race_control_messages'},
            ),
            'limits': [
                'Simulated live replays cached historical data at real-time speed.',
                'Data is NOT real-time; display the SIMULATED LIVE badge in the UI.',
                'Reconnect delivers the latest snapshot, not full event history.',
                'Backpressure protection may drop stale frames for slow clients.',
            ] if self.mode == 'simulated' else [],
        }

    async def _run_simulated(self) -> None:
        assert self._replay is not None
        duration = self._replay.duration_seconds
        tick = 0.5  # real-world seconds between ticks
        real_start = time.monotonic()

        while self._running and self._session_time < duration:
            snapshot = self._build_snapshot(self._session_time)
            self._last_snapshot = snapshot
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(snapshot)
                except asyncio.QueueFull:
                    dead.append(q)  # slow client; drop
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

            await asyncio.sleep(tick)
            elapsed_real = time.monotonic() - real_start
            self._session_time = elapsed_real * self.speed

        # Emit a terminal message
        final = {'type': 'end', 'session_slug': self.session_slug,
                 'session_time_seconds': self._session_time}
        for q in self._subscribers:
            try:
                q.put_nowait(final)
            except asyncio.QueueFull:
                pass
        self._running = False

    async def start(self, *, session_time_start: float = 0.0) -> None:
        """Load the pack and start the background ingest task."""
        if self._running:
            return
        self._replay = self._load_replay()
        self._session_time = session_time_start
        self._running = True
        self._task = asyncio.create_task(self._run_simulated())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def subscribe(self) -> LiveSubscription:
        """Return a context-manager that yields snapshots from this session."""
        q: asyncio.Queue = asyncio.Queue(maxsize=4)
        self._subscribers.append(q)
        if self._last_snapshot is not None:
            q.put_nowait(self._last_snapshot)
        return LiveSubscription(q, self)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class LiveSubscription:
    """Context manager for one subscriber queue."""

    def __init__(self, queue: asyncio.Queue, session: LiveSession) -> None:
        self._q = queue
        self._session = session

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args) -> None:
        self._session.unsubscribe(self._q)

    def __aiter__(self) -> LiveSubscription:
        return self

    async def __anext__(self) -> dict:
        msg = await asyncio.wait_for(self._q.get(), timeout=30.0)
        if msg.get('type') == 'end':
            raise StopAsyncIteration
        return msg


class LiveRegistry:
    """Global registry: one LiveSession per active session slug."""

    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        session_slug: str,
        *,
        speed: float = 1.0,
        pack_root: Path = PACK_ROOT,
    ) -> LiveSession:
        async with self._lock:
            if session_slug not in self._sessions or not self._sessions[session_slug]._running:
                session = LiveSession(session_slug, mode='simulated',
                                      speed=speed, pack_root=pack_root)
                await session.start()
                self._sessions[session_slug] = session
            return self._sessions[session_slug]

    async def stop_all(self) -> None:
        async with self._lock:
            for session in self._sessions.values():
                await session.stop()
            self._sessions.clear()


_registry = LiveRegistry()
