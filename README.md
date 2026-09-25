# regexlite

纯 Python 标准库的 regexlite（Thompson NFA + 多线程模拟，无回溯，
匹配访问量随文本长度线性增长）。

## 支持的模式子集

- 字面量与反斜杠转义（如 `\*`、`\\`）
- `.` 任意字符
- 字符类 `[abc]` 与区间 `[a-z]`（类内支持转义）
- 量词 `*`、`+`、`?`（可作用于字符、字符类或分组）
- 分支 `|`、分组 `()`（捕获按左括号顺序编号）

## 语义

- `Regex(pattern).search(text)`：最左最长——起点取最靠左（允许空匹配），
  该起点上取最长匹配；返回 `(开始下标, 结束下标, 匹配文本, 分组列表)`，
  无匹配返回 `None`。未参与匹配的可选分组不进分组列表。
- `Regex(pattern).match(text)`：锚定在 0 号位的匹配，返回结构同上。
- 非法模式抛 `RegexError`，`error.position` 给出位置：未闭合的 `(`/`[`
  报自身下标；出现在开头或紧跟 `(`、`|` 之后的量词报量词下标。
- `Matcher`（matchapi.py）是对外门面，`search`/`match` 返回结构不变。

## 测试

    python3 -m unittest discover -s tests -v

## 场景自检

    python3 check_sample.py
