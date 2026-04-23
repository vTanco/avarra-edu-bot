import asyncio
import pytest

from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue


async def test_add_and_snapshot_returns_inserted_ids():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121777")
    assert await q.snapshot() == ["121776", "121777"]


async def test_add_deduplicates():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121776")
    assert await q.snapshot() == ["121776"]


async def test_drain_returns_and_clears():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121777")
    drained = await q.drain()
    assert drained == ["121776", "121777"]
    assert await q.snapshot() == []


async def test_size_reflects_queue_length():
    q = ThursdayQueue()
    assert await q.size() == 0
    await q.add("121776")
    assert await q.size() == 1


async def test_concurrent_adds_are_safe():
    q = ThursdayQueue()
    await asyncio.gather(*(q.add(f"id{i}") for i in range(50)))
    snap = await q.snapshot()
    assert len(snap) == 50
    assert set(snap) == {f"id{i}" for i in range(50)}
