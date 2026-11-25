import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from maxbot.callbacks import CallbackResponder


class CallbackRateTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_chat_answers_are_spaced_by_at_least_half_a_second(self):
        times = []
        async def record(*args, **kwargs):
            times.append(asyncio.get_running_loop().time())
        client = Mock(answer_callback=AsyncMock(side_effect=record))
        responder = CallbackResponder()
        await asyncio.gather(*(responder.answer(client, ("chat", 7), str(index), "Done") for index in range(3)))
        self.assertEqual(len(times), 3)
        self.assertTrue(all(right - left >= 0.49 for left, right in zip(times, times[1:])))

    async def test_slow_answer_in_one_chat_does_not_block_another_chat(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def hold(*args, **kwargs):
            started.set()
            await release.wait()
        responder = CallbackResponder()
        slow = Mock(answer_callback=AsyncMock(side_effect=hold))
        fast = Mock(answer_callback=AsyncMock())
        task = asyncio.create_task(responder.answer(slow, ("chat", 1), "first", "Done"))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            await asyncio.wait_for(responder.answer(fast, ("chat", 2), "second", "Done"), timeout=2)
            fast.answer_callback.assert_awaited_once()
            self.assertFalse(task.done())
        finally:
            release.set()
            await task
