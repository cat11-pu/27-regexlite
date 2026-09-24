"""check_sample.py：按 sample/patterns.json 走一圈，打印验收面。"""
import json
import os
import sys
import time

from regexlite import Regex, RegexError


def error_position(pattern):
    try:
        Regex(pattern).error_position()
    except RegexError as error:
        return error.position
    except NotImplementedError:
        return None
    return None


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("sample", "patterns.json")
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    spans = []
    groups = []
    for case in spec["cases"]:
        found = Regex(case["pattern"]).search(case["text"])
        if found is None:
            spans.append((case["pattern"], None, None))
            groups.append((case["pattern"], []))
            continue
        spans.append((case["pattern"], found[0], found[1]))
        groups.append((case["pattern"], found[3] if len(found) > 3 else []))
    bad_positions = [(pattern, error_position(pattern)) for pattern in spec["bad"]]
    budget = spec["budget"]
    started = time.time()
    Regex(budget["pattern"]).search(budget["text"] * budget["repeat"])
    elapsed_ms = int((time.time() - started) * 1000)
    print("匹配区间 =", spans)
    print("分组内容 =", groups)
    print("非法模式的位置 =", bad_positions)
    print("最长匹配（起点最靠左的前提下取最长） =", spec["longest"])
    print("长文本匹配耗时上限（毫秒） =", budget["limit_ms"])
    print("长文本实际耗时（毫秒） =", elapsed_ms)
    print("文本长度 =", len(budget["text"]) * budget["repeat"])
    print("必须用自动机模拟 =", spec["automaton_required"])
    print("访问计数是否随文本线性 =", spec["linear_visits"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
