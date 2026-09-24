"""matchapi.py：对外门面（老接口 search/match 的返回结构不能改）。"""
from __future__ import annotations

from regexlite import Regex, RegexError


class Matcher:
    def __init__(self, pattern: str):
        self.regex = Regex(pattern)

    def search(self, text: str):
        return self.regex.search(text)

    def match(self, text: str):
        return self.regex.match(text)

    def error_position(self):
        return self.regex.error_position()


def compile_error(pattern: str):
    try:
        Regex(pattern).error_position()
    except RegexError as error:
        return error.position
    return None
