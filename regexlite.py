"""regexlite.py：匹配内核（Thompson NFA + 多线程模拟，无回溯）。

支持子集：`.`、字符类 `[abc]`/`[a-z]`、量词 `* + ?`、分支 `|`、
分组 `()`、反斜杠转义。search 按最左最长语义返回
(开始下标, 结束下标, 匹配文本, 分组列表)。
"""
from __future__ import annotations


class RegexError(Exception):
    def __init__(self, position: int, message: str = "bad pattern"):
        super().__init__("%s at %d" % (message, position))
        self.position = position


# ---------- 模式解析 ----------

class _Parser:
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.pos = 0
        self.ngroups = 0

    def parse(self):
        node = self.parse_alt()
        if self.pos < len(self.pattern):
            raise RegexError(self.pos, "unmatched )")
        return node

    def parse_alt(self):
        branches = [self.parse_concat()]
        while self.pos < len(self.pattern) and self.pattern[self.pos] == "|":
            self.pos += 1
            branches.append(self.parse_concat())
        if len(branches) == 1:
            return branches[0]
        return ("alt", branches)

    def parse_concat(self):
        items = []
        while self.pos < len(self.pattern) and self.pattern[self.pos] not in "|)":
            items.append(self.parse_repeat())
        return ("cat", items)

    def parse_repeat(self):
        atom = self.parse_atom()
        while self.pos < len(self.pattern) and self.pattern[self.pos] in "*+?":
            atom = ("rep", atom, self.pattern[self.pos])
            self.pos += 1
        return atom

    def parse_atom(self):
        char = self.pattern[self.pos]
        if char in "*+?":
            raise RegexError(self.pos, "quantifier without target")
        if char == "(":
            start = self.pos
            self.pos += 1
            self.ngroups += 1
            index = self.ngroups
            node = self.parse_alt()
            if self.pos >= len(self.pattern):
                raise RegexError(start, "unclosed (")
            self.pos += 1  # 吃掉 ')'
            return ("grp", index, node)
        if char == "[":
            return self.parse_class()
        if char == ".":
            self.pos += 1
            return ("any",)
        if char == "\\":
            start = self.pos
            self.pos += 1
            if self.pos >= len(self.pattern):
                raise RegexError(start, "trailing backslash")
            escaped = self.pattern[self.pos]
            self.pos += 1
            return ("char", escaped)
        self.pos += 1
        return ("char", char)

    def parse_class(self):
        start = self.pos  # 指向 '['
        self.pos += 1
        chars = set()
        first = True
        while True:
            if self.pos >= len(self.pattern):
                raise RegexError(start, "unclosed [")
            char = self.pattern[self.pos]
            if char == "]" and not first:
                self.pos += 1
                return ("class", frozenset(chars))
            first = False
            if char == "\\":
                self.pos += 1
                if self.pos >= len(self.pattern):
                    raise RegexError(start, "unclosed [")
                low = self.pattern[self.pos]
                self.pos += 1
            else:
                low = char
                self.pos += 1
            if (
                self.pos < len(self.pattern)
                and self.pattern[self.pos] == "-"
                and self.pos + 1 < len(self.pattern)
                and self.pattern[self.pos + 1] != "]"
            ):
                self.pos += 1
                high = self.pattern[self.pos]
                if high == "\\":
                    self.pos += 1
                    if self.pos >= len(self.pattern):
                        raise RegexError(start, "unclosed [")
                    high = self.pattern[self.pos]
                self.pos += 1
                for code in range(ord(low), ord(high) + 1):
                    chars.add(chr(code))
            else:
                chars.add(low)


# ---------- NFA 编译 ----------

class _State:
    __slots__ = ("kind", "chars", "out", "out2", "slot", "idx")

    def __init__(self, kind: str):
        self.kind = kind  # 'char' | 'any' | 'split' | 'save' | 'accept'
        self.chars = None
        self.out = None
        self.out2 = None
        self.slot = -1
        self.idx = -1


def _build(node, nxt, states):
    tag = node[0]
    if tag == "cat":
        for child in reversed(node[1]):
            nxt = _build(child, nxt, states)
        return nxt
    if tag == "alt":
        entry = None
        for branch in node[1]:
            target = _build(branch, nxt, states)
            if entry is None:
                entry = target
            else:
                split = _State("split")
                split.out = target
                split.out2 = entry
                states.append(split)
                entry = split
        return entry
    if tag == "rep":
        kind = node[2]
        if kind == "?":
            split = _State("split")
            body = _build(node[1], nxt, states)
            split.out = body
            split.out2 = nxt
            states.append(split)
            return split
        split = _State("split")
        states.append(split)
        body = _build(node[1], split, states)
        split.out = body
        split.out2 = nxt
        if kind == "+":
            return body
        return split
    if tag == "grp":
        index = node[1]
        end = _State("save")
        end.slot = 2 * (index - 1) + 1
        end.out = nxt
        states.append(end)
        body = _build(node[2], end, states)
        begin = _State("save")
        begin.slot = 2 * (index - 1)
        begin.out = body
        states.append(begin)
        return begin
    state = _State("any" if tag == "any" else "char")
    if tag == "char":
        state.chars = frozenset((node[1],))
    elif tag == "class":
        state.chars = node[1]
    state.out = nxt
    states.append(state)
    return state


# ---------- 匹配器 ----------

class Regex:
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.visits = 0
        parser = _Parser(pattern)
        ast = parser.parse()
        self._ngroups = parser.ngroups
        accept = _State("accept")
        states = [accept]
        self._start = _build(ast, accept, states)
        for index, state in enumerate(states):
            state.idx = index
        self._states = states

    def search(self, text: str):
        """最左最长：起点最靠左（允许空匹配），该起点上取最长。"""
        return self._run(text, anchored=False)

    def match(self, text: str):
        """锚定在 0 号位的匹配（允许空匹配）。"""
        return self._run(text, anchored=True)

    def error_position(self) -> int:
        # 构造时已完整解析，非法模式会在 __init__ 抛出 RegexError。
        return None

    def stats(self) -> dict:
        return {
            "pattern": self.pattern,
            "visits": self.visits,
            "nodes": len(self._states),
        }

    def _add(self, thread_list, mark, gen, state, start, caps, pos):
        stack = [(state, caps)]
        while stack:
            current, current_caps = stack.pop()
            if mark[current.idx] == gen:
                continue
            mark[current.idx] = gen
            kind = current.kind
            if kind == "save":
                slot = current.slot
                new_caps = current_caps[:slot] + (pos,) + current_caps[slot + 1:]
                stack.append((current.out, new_caps))
            elif kind == "split":
                stack.append((current.out2, current_caps))
                stack.append((current.out, current_caps))
            else:
                thread_list.append((current, start, current_caps))

    def _run(self, text: str, anchored: bool):
        length = len(text)
        mark = [-1] * len(self._states)
        gen = 0
        empty_caps = (None,) * (2 * self._ngroups)
        best = None
        clist = []
        for pos in range(length + 1):
            if best is None and (not anchored or pos == 0):
                gen += 1
                for state, _, _ in clist:
                    mark[state.idx] = gen
                self._add(clist, mark, gen, self._start, pos, empty_caps, pos)
            for state, start, caps in clist:
                self.visits += 1
                if state.kind == "accept" and (best is None or start <= best[0]):
                    best = (start, pos, caps)
            if best is not None:
                clist = [thread for thread in clist if thread[1] <= best[0]]
                if not clist:
                    break
            if pos == length:
                break
            char = text[pos]
            gen += 1
            nlist = []
            for state, start, caps in clist:
                self.visits += 1
                if state.kind == "any" or (
                    state.kind == "char" and char in state.chars
                ):
                    self._add(nlist, mark, gen, state.out, start, caps, pos + 1)
            clist = nlist
        if best is None:
            return None
        start, end, caps = best
        groups = []
        for index in range(self._ngroups):
            group_start = caps[2 * index]
            group_end = caps[2 * index + 1]
            if group_start is not None and group_end is not None:
                groups.append(text[group_start:group_end])
        return (start, end, text[start:end], groups)
