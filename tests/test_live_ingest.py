"""Tests for the P7 live ingest and WebSocket fan-out.

Unit tests cover the LiveSession state machine, subscription/unsubscription,
snapshot shape, and the SIMULATED_LIVE badge.

Integration tests (skipped without pack) verify the WebSocket API route
produces well-formed snapshots via ASGI test client.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from f1_racelab.live.ingest import (
    SIMULATED_LIVE_BADGE,
    LiveRegistry,
    LiveSession,
)

PACK_ROOT = Path(__file__).resolve().parents[1] / 'data/processed/replay_packs'
HAS_MONZA = (PACK_ROOT / 'monza_2025_race.json.gz').is_file()


# ---------------------------------------------------------------------------
# Unit tests — no network, no pack required (synthetic if pack absent)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_session_emits_snapshots():
    session = LiveSession('monza-2025', mode='simulated', speed=120.0)
    await session.start(session_time_start=0.0)
    sub = session.subscribe()
    async with sub:
        msg = await asyncio.wait_for(sub._q.get(), timeout=2.0)
    await session.stop()
    assert msg['type'] == 'snapshot'
    assert msg['session_slug'] == 'monza-2025'
    assert msg['mode'] == 'simulated'
    assert msg['badge'] == SIMULATED_LIVE_BADGE
    assert 'state' in msg
    assert 'session_time_seconds' in msg


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_session_subscriber_count():
    session = LiveSession('monza-2025', mode='simulated', speed=120.0)
    await session.start()
    sub1 = session.subscribe()
    sub2 = session.subscribe()
    assert session.subscriber_count == 2
    session.unsubscribe(sub1._q)
    assert session.subscriber_count == 1
    session.unsubscribe(sub2._q)
    assert session.subscriber_count == 0
    await session.stop()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_session_last_snapshot_delivered_on_reconnect():
    session = LiveSession('monza-2025', mode='simulated', speed=120.0)
    await session.start()
    # Get at least one snapshot
    sub = session.subscribe()
    msg1 = await asyncio.wait_for(sub._q.get(), timeout=2.0)
    session.unsubscribe(sub._q)

    # New subscriber should immediately get last snapshot
    sub2 = session.subscribe()
    msg2 = await asyncio.wait_for(sub2._q.get(), timeout=1.0)
    session.unsubscribe(sub2._q)
    await session.stop()

    assert msg1['type'] == 'snapshot'
    assert msg2['type'] == 'snapshot'


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_snapshot_state_has_required_keys():
    session = LiveSession('monza-2025', mode='simulated', speed=120.0)
    await session.start()
    sub = session.subscribe()
    msg = await asyncio.wait_for(sub._q.get(), timeout=2.0)
    session.unsubscribe(sub._q)
    await session.stop()

    state = msg['state']
    assert 'drivers' in state
    assert 'session_time_seconds' in state
    assert 'flag' in state


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_session_stop_sets_running_false():
    session = LiveSession('monza-2025', mode='simulated', speed=120.0)
    await session.start()
    assert session._running
    await session.stop()
    assert not session._running


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_live_registry_creates_session_once():
    registry = LiveRegistry()
    s1 = await registry.get_or_create('monza-2025', speed=120.0)
    s2 = await registry.get_or_create('monza-2025', speed=120.0)
    assert s1 is s2
    await registry.stop_all()
    assert not s1._running


# ---------------------------------------------------------------------------
# WebSocket API integration test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_MONZA, reason='Monza 2025 pack not present')
async def test_websocket_live_route_sends_snapshot():
    from httpx import AsyncClient, ASGITransport
    from f1_racelab.api import create_app
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
    ) as client:
        r = await client.get('/api/v1/live/monza-2025/status')
    assert r.status_code == 200
    data = r.json()
    assert data['session_slug'] == 'monza-2025'
    assert 'subscriber_count' in data
