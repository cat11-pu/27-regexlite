"""regexlite.py：匹配内核（Thompson NFA + Pike VM 模拟，无回溯）。"""
from __future__ import annotations


class RegexError(Exception):
    def __init__(self, position: int, message: str = "bad pattern"):
        super().__init__("%s at %d" % (message, position))
        self.position = position


class _Parser:
    """模式 -> AST。非法模式抛 RegexError 并带上位置。"""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.pos = 0
        self.group_count = 0

    def peek(self):
        return self.pattern[self.pos] if self.pos < len(self.pattern) else None

    def parse(self):
        node = self.parse_alt()
        if self.pos < len(self.pattern):
            raise RegexError(self.pos, "unmatched )")
        return node

    def parse_alt(self):
        branches = [self.parse_concat()]
        while self.peek() == "|":
            self.pos += 1
            branches.append(self.parse_concat())
        return branches[0] if len(branches) == 1 else ("alt", branches)

    def parse_concat(self):
        items = []
        while self.pos < len(self.pattern) and self.peek() not in ")|":
            items.append(self.parse_repeat())
        return items[0] if len(items) == 1 else ("concat", items)

    def parse_repeat(self):
        atom = self.parse_atom()
        while self.peek() in ("*", "+", "?"):
            quantifier = self.peek()
            self.pos += 1
            atom = ("rep", atom, quantifier)
        return atom

    def parse_atom(self):
        char = self.peek()
        if char in ("*", "+", "?"):
            raise RegexError(self.pos, "quantifier without target")
        if char == "(":
            start = self.pos
            self.pos += 1
            self.group_count += 1
            index = self.group_count
            node = self.parse_alt()
            if self.peek() != ")":
                raise RegexError(start, "unclosed (")
            self.pos += 1
            return ("group", index, node)
        if char == "[":
            return self.parse_class()
        if char == ".":
            self.pos += 1
            return ("any",)
        if char == "\\":
            backslash = self.pos
            self.pos += 1
            if self.pos >= len(self.pattern):
                raise RegexError(backslash, "trailing backslash")
            escaped = self.pattern[self.pos]
            self.pos += 1
            return ("lit", escaped)
        self.pos += 1
        return ("lit", char)

    def parse_class(self):
        start = self.pos
        self.pos += 1
        ranges = []
        first = True
        while True:
            if self.pos >= len(self.pattern):
                raise RegexError(start, "unclosed [")
            if self.pattern[self.pos] == "]" and not first:
                self.pos += 1
                break
            first = False
            lo = self.class_char(start)
            if (
                self.peek() == "-"
                and self.pos + 1 < len(self.pattern)
                and self.pattern[self.pos + 1] != "]"
            ):
                self.pos += 1
                hi = self.class_char(start)
                if ord(lo) > ord(hi):
                    raise RegexError(start, "bad range")
                ranges.append((lo, hi))
            else:
                ranges.append((lo, lo))
        return ("class", tuple(ranges))

    def class_char(self, start):
        if self.pattern[self.pos] == "\\":
            self.pos += 1
            if self.pos >= len(self.pattern):
                raise RegexError(start, "unclosed [")
        char = self.pattern[self.pos]
        self.pos += 1
        return char


class _Compiler:
    """AST -> Thompson NFA 指令序列。"""

    def __init__(self):
        self.prog = []

    def emit(self, op):
        self.prog.append(op)
        return len(self.prog) - 1

    def compile(self, node):
        kind = node[0]
        if kind == "lit":
            self.emit(("char", node[1]))
        elif kind == "any":
            self.emit(("any",))
        elif kind == "class":
            self.emit(("class", node[1]))
        elif kind == "concat":
            for child in node[1]:
                self.compile(child)
        elif kind == "alt":
            jumps = []
            branches = node[1]
            for index, branch in enumerate(branches):
                if index < len(branches) - 1:
                    split = self.emit(("split", None, None))
                    self.compile(branch)
                    jumps.append(self.emit(("jmp", None)))
                    self.prog[split] = ("split", split + 1, len(self.prog))
                else:
                    self.compile(branch)
            end = len(self.prog)
            for jump in jumps:
                self.prog[jump] = ("jmp", end)
        elif kind == "group":
            slot = 2 * node[1]
            self.emit(("save", slot))
            self.compile(node[2])
            self.emit(("save", slot + 1))
        elif kind == "rep":
            child, quantifier = node[1], node[2]
            if quantifier == "?":
                split = self.emit(("split", None, None))
                self.compile(child)
                self.prog[split] = ("split", split + 1, len(self.prog))
            elif quantifier == "*":
                split = self.emit(("split", None, None))
                self.compile(child)
                self.emit(("jmp", split))
                self.prog[split] = ("split", split + 1, len(self.prog))
            else:
                start = len(self.prog)
                self.compile(child)
                self.emit(("split", start, len(self.prog) + 1))


def _consumes(op, char):
    kind = op[0]
    if kind == "char":
        return char == op[1]
    if kind == "any":
        return True
    return any(lo <= char <= hi for lo, hi in op[1])


class Regex:
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.visits = 0
        parser = _Parser(pattern)
        ast = parser.parse()
        self.group_count = parser.group_count
        compiler = _Compiler()
        compiler.emit(("save", 0))
        compiler.compile(ast)
        compiler.emit(("save", 1))
        compiler.emit(("match",))
        self.prog = compiler.prog

    def _add_thread(self, thread_list, pc, regs, pos, seen):
        stack = [(pc, regs)]
        while stack:
            pc, regs = stack.pop()
            if pc in seen:
                continue
            seen.add(pc)
            op = self.prog[pc]
            kind = op[0]
            if kind == "jmp":
                stack.append((op[1], regs))
            elif kind == "split":
                stack.append((op[2], regs))
                stack.append((op[1], regs))
            elif kind == "save":
                updated = list(regs)
                updated[op[1]] = pos
                stack.append((pc + 1, updated))
            else:
                thread_list.append((pc, regs))

    def _run(self, text, anchored):
        prog = self.prog
        slot_count = 2 * (self.group_count + 1)
        best = None
        clist = []
        for pos in range(len(text) + 1):
            if best is None and (not anchored or pos == 0):
                seen = set(pc for pc, _ in clist)
                self._add_thread(clist, 0, [None] * slot_count, pos, seen)
            if not clist:
                break
            char = text[pos] if pos < len(text) else None
            nlist = []
            seen_next = set()
            for pc, regs in clist:
                self.visits += 1
                op = prog[pc]
                if op[0] == "match":
                    start = regs[0]
                    if best is None or start < best[0] or (start == best[0] and pos > best[1]):
                        best = (start, pos, regs)
                elif char is not None and _consumes(op, char):
                    self._add_thread(nlist, pc + 1, regs, pos + 1, seen_next)
            if best is not None:
                nlist = [(pc, regs) for pc, regs in nlist if regs[0] <= best[0]]
            clist = nlist
        return best

    def _result(self, text, found):
        if found is None:
            return None
        start, end, regs = found
        groups = []
        for index in range(1, self.group_count + 1):
            group_start = regs[2 * index]
            group_end = regs[2 * index + 1]
            if group_start is not None and group_end is not None:
                groups.append(text[group_start:group_end])
        return (start, end, text[start:end], groups)

    def search(self, text: str):
        """最左最长：起点最靠左（允许空匹配），同起点取最长。"""
        return self._result(text, self._run(text, anchored=False))

    def match(self, text: str):
        return self._result(text, self._run(text, anchored=True))

    def error_position(self) -> int:
        _Parser(self.pattern).parse()
        return None

    def stats(self) -> dict:
        return {"pattern": self.pattern, "visits": self.visits, "nodes": len(self.prog)}
