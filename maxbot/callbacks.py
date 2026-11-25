from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class _AnswerSlot:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_at: float = 0.0
    users: int = 0


class CallbackResponder:
    """Serialize answers per dialog/chat, at no more than two per second."""

    def __init__(self) -> None:
        self._slots: dict[tuple[str, int], _AnswerSlot] = {}

    async def answer(self, client: Any, key: tuple[str, int], callback_id: str, notification: str) -> None:
        loop = asyncio.get_running_loop()
        if len(self._slots) >= 256:
            for old_key, old_slot in list(self._slots.items()):
                if old_slot.users == 0 and old_slot.next_at <= loop.time():
                    del self._slots[old_key]
        slot = self._slots.setdefault(key, _AnswerSlot())
        slot.users += 1
        try:
            async with slot.lock:
                delay = slot.next_at - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    await client.answer_callback(callback_id, notification=notification)
                finally:
                    slot.next_at = loop.time() + 0.5
        finally:
            slot.users -= 1
