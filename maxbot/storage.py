from __future__ import annotations

import json
from pathlib import Path


class UserRegistry:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> list[int]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def add(self, user_id: int) -> bool:
        users = self.load()
        if user_id in users:
            return False
        users.append(user_id)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(users, handle, ensure_ascii=False)
        return True


class AppealLinkRegistry:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {}
        result: dict[str, int] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, int):
                result[key] = value
        return result

    def save_link(self, message_id: str, user_id: int) -> None:
        links = self.load()
        links[message_id] = user_id
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(links, handle, ensure_ascii=False)

    def get_user_id(self, message_id: str) -> int | None:
        return self.load().get(message_id)
