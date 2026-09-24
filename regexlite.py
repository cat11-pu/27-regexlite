"""regexlite.py：匹配内核（基线：只支持字面量）。"""
from __future__ import annotations


class RegexError(Exception):
    def __init__(self, position: int, message: str = "bad pattern"):
        super().__init__("%s at %d" % (message, position))
        self.position = position


class Regex:
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.visits = 0

    def search(self, text: str):
        """基线：按字面量找子串（最左优先）。"""
        index = text.find(self.pattern)
        self.visits += len(text)
        if index < 0:
            return None
        return (index, index + len(self.pattern), self.pattern, [])

    def match(self, text: str):
        return self.search(text) if text.startswith(self.pattern) else None

    def error_position(self) -> int:
        raise NotImplementedError("模式校验还没实现")

    def stats(self) -> dict:
        return {"pattern": self.pattern, "visits": self.visits, "nodes": 0}
