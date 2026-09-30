#!/usr/bin/env python3
"""要件定義書・基本設計書・実装プランを型と照合し、HTML に変換する。

使い方:
  python3 specdoc.py check [--gate 承認|実装|リリース] [--approved] <ファイルまたはディレクトリ>...
  python3 specdoc.py html <ファイルまたはディレクトリ>...
  python3 specdoc.py hash <ファイル>

型は plugin の formats/ に置く。Python 3.9 以上の標準ライブラリだけで動く。
"""

import argparse
import difflib
import hashlib
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

FORMATS_DIR = Path(__file__).resolve().parent.parent / "formats"
DOC_FILES = ("requirements.md", "design.md", "plan.md")
LEGEND = (
    "R = 要件、AC = 受け入れ基準、S = シナリオ、Q = 要確認。"
    "子の番号は間に子の名前が入る（例: AC-billing-001）"
)
META_KEYS = ("著者", "状態", "承認者", "凡例", "親", "上流", "元の文書")
STATES = ("draft", "approved")
STAGES = ("承認", "実装", "リリース")
SCENARIO_KINDS = ("正常", "異常", "境界")
DIFF_KINDS = ("既存", "追加", "変更", "削除")
TABLE_HEADER = ("意味", "型・長さ", "必須", "制約", "差分")
RESERVED_CHILD_NAMES = ("mocks", "specs")
PARENT_ONLY_KEY = "分割したとき親だけに置く見出し"
SPLIT_SECTION = ("サブ機能分割",)
DATA_USE_SECTION = ("機能設計", "読み書きするデータ")
TABLE_SECTION = ("データ設計", "テーブル定義")

# 番号を定義する見出しと、そこで定義する番号の種類
DEF_SECTIONS = {
    "requirements": {("機能概要",): "R", ("非機能要件",): "R", ("要確認",): "Q"},
    "design": {("受け入れ基準",): "AC", ("要確認",): "Q"},
    "plan": {("シナリオ",): "S", ("要確認",): "Q"},
}
# 番号の下の箇条に書く項目。値は必須かどうか
ID_FIELDS = {
    "R": {},
    "AC": {"要件": True},
    "S": {"受け入れ基準": True, "種別": True, "層": True, "前提": True, "操作": True, "期待": True},
    "Q": {"推奨": False, "確認先": True, "期限": True, "止める工程": True},
}
SPLIT_FIELDS = {"要件": True, "依存": True}

MERMAID_VERSION = "12.0.0"
# MERMAID_URL のファイルの sha384 を base64 にした値。版を上げたら計算し直す:
# curl -sL <MERMAID_URL> | openssl dgst -sha384 -binary | openssl base64 -A
MERMAID_INTEGRITY = "sha384-xzghz1GQ5u9HCpVskeDPqMsdogD1yvuMQbEK53+wi+G70+6J1AG0L2cfi9PHjDWI"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"

CHILD = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)?"
CHILD_RE = re.compile(rf"^{CHILD}$")
ID_RE = re.compile(rf"(?<![A-Za-z0-9-])(R|AC|S|Q)-(?:({CHILD})-)?(\d{{3}})(?![A-Za-z0-9-])")
DEF_RE = re.compile(rf"^((?:R|AC|S|Q)-(?:{CHILD}-)?\d{{3}}):(?: (.*))?$")
KV_RE = re.compile(r"^([^\s:]+):(?: (.*))?$")
UPSTREAM_RE = re.compile(r"^([^\s@]+)@([0-9a-f]{12})$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COLUMN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")
HEADING_RE = re.compile(r"^(#{1,6})(?: +(.*))?$")
LIST_RE = re.compile(r"^( *)-(?: +(.*))?$")
LANG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]*$")
SEPARATOR_CELL_RE = re.compile(r"^-{3,}$")
LINK_DEST_RE = re.compile(r"^[^\s()<>]+$")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
WEB_RE = re.compile(r"^(?:https?|mailto):")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
UNSPLIT_RE = re.compile(r"^分割しない。理由: \S")
ENTITY_RE = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,31}|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6});")
HTML_TAG_RE = re.compile(r"<[A-Za-z/!?]")
BANNED_LINES = (
    (re.compile(r"^ *([-*_])(?: *\1){2,} *$"), "区切り線は使えない"),
    (re.compile(r"^ *\d+[.)](?: |$)"), "番号付きの箇条書きは使えない（- で書く）"),
    (re.compile(r"^ *>"), "引用は使えない"),
    (re.compile(r"^ *[*+](?: |$)"), "箇条書きは - で書く"),
    (re.compile(r"^ *=+ *$"), "見出しは # で書く"),
    (re.compile(r"^ *~~~"), "コードブロックは ``` で囲む"),
)

CSS = """body { margin: 0; padding: 0 16px; background: #ffffff; color: #1f2328; font-family: system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; line-height: 1.7; }
main { max-width: 960px; margin: 32px auto; }
h1, h2 { border-bottom: 1px solid #d0d7de; padding-bottom: 0.3em; }
h2 { margin-top: 2em; }
h3 { margin-top: 1.5em; }
a { color: #0969da; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9em; background: #f6f8fa; padding: 0.1em 0.3em; border-radius: 4px; }
pre { background: #f6f8fa; padding: 12px; overflow-x: auto; border-radius: 6px; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; display: block; overflow-x: auto; }
th, td { border: 1px solid #d0d7de; padding: 4px 10px; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
dl.meta { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; background: #f6f8fa; padding: 12px 16px; border-radius: 6px; }
dl.meta dt { font-weight: 600; }
dl.meta dd { margin: 0; }
dl.meta ul { margin: 0; padding-left: 1.2em; }
li:target { background: #fff8c5; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #e6edf3; }
  a { color: #4493f8; }
  h1, h2, th, td { border-color: #30363d; }
  code, pre, th, dl.meta { background: #161b22; }
  li:target { background: #3b2e00; }
}"""


def blob_hash(data):
    """git の blob hash（ファイルの中身の hash）を返す。"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def split_id(ident):
    m = ID_RE.match(ident)
    return m.group(1), m.group(2)


def banned(line):
    for rx, msg in BANNED_LINES:
        if rx.match(line):
            return msg
    return None


def starts_block(line):
    return (
        line.startswith("```")
        or line.startswith("|")
        or bool(HEADING_RE.match(line))
        or (bool(LIST_RE.match(line)) and not banned(line))
    )


def split_row(line):
    if len(line) < 2 or not line.startswith("|") or not line.endswith("|"):
        return None
    return [cell.strip() for cell in line[1:-1].split("|")]


# ---- 行内の書式 ----
# 字句は ("text", 文字列)・("code", 文字列)・("bold", 字句の列)・("link", 字句の列, 先)


def scan_code(s, i):
    """i から始まるコードの終わりの位置と中身を返す。閉じていなければ -1。"""
    j = i
    while j < len(s) and s[j] == "`":
        j += 1
    run = j - i
    k = j
    while k < len(s):
        if s[k] != "`":
            k += 1
            continue
        m = k
        while m < len(s) and s[m] == "`":
            m += 1
        if m - k == run:
            content = s[j:k]
            if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip(" "):
                content = content[1:-1]
            return m, content
        k = m
    return -1, ""


def find_outside_code(s, target, start):
    k = start
    while k < len(s):
        if s[k] == "`":
            k, _ = scan_code(s, k)
            if k < 0:
                return -1
            continue
        if s.startswith(target, k):
            return k
        k += 1
    return -1


def check_text(text, errors):
    if "*" in text:
        errors.append("コードの外で * を使わない（太字は ** で囲む。記号として書くならコードで囲む）")
    for k, ch in enumerate(text):
        if ch != "_":
            continue
        before = text[k - 1] if k > 0 else ""
        after = text[k + 1] if k + 1 < len(text) else ""
        if not (before.isalnum() and after.isalnum()):
            errors.append("コードの外で語の端に _ を置かない（コードで囲む）")
            break
    if "~~" in text:
        errors.append("打ち消し線は使えない")
    if "\\" in text:
        errors.append("バックスラッシュは使えない（コードで囲む）")
    if ENTITY_RE.search(text):
        errors.append("文字参照は使えない。文字をそのまま書く")
    if HTML_TAG_RE.search(text):
        errors.append("HTML は使えない（< を記号として書くならコードで囲む）")


def link_dest_error(dest):
    """リンク先の書式の誤りを返す。無ければ None。相対パスの先が実在するかは check で見る。"""
    if CONTROL_RE.search(dest):
        return "リンク先に制御文字を入れない"
    if "\\" in dest:
        return "リンク先にバックスラッシュを入れない（区切りは / にする）"
    if dest.startswith("#") or WEB_RE.match(dest):
        return None
    if SCHEME_RE.match(dest):
        return f"リンク先は相対パスか http・https・mailto にする: {dest}"
    if dest.startswith("/"):
        return f"リンク先は相対パスで書く: {dest}"
    return None


def parse_inline(s, errors, in_link=False, in_bold=False):
    tokens = []
    buf = []

    def flush():
        if buf:
            tokens.append(("text", "".join(buf)))
            del buf[:]

    i = 0
    while i < len(s):
        if s[i] == "`":
            end, content = scan_code(s, i)
            if end < 0:
                errors.append("` の対応が取れていない")
                buf.append(s[i:])
                break
            flush()
            tokens.append(("code", content))
            i = end
            continue
        if s.startswith("**", i) and not in_bold:
            close = find_outside_code(s, "**", i + 2)
            if close > i + 2:
                inner = s[i + 2:close]
                if inner != inner.strip():
                    errors.append("太字の内側の端に空白を置かない")
                flush()
                tokens.append(("bold", parse_inline(inner, errors, in_link, True)))
                i = close + 2
                continue
        if s.startswith("![", i):
            errors.append("画像は使えない")
        if s[i] == "[" and not in_link:
            close = find_outside_code(s, "]", i + 1)
            if close > 0 and s.startswith("(", close + 1):
                end = s.find(")", close + 2)
                dest = s[close + 2:end] if end > 0 else ""
                if end < 0 or not LINK_DEST_RE.match(dest) or close == i + 1:
                    errors.append("リンクは [文字](先) の形で書く。先に空白と括弧を入れない")
                else:
                    msg = link_dest_error(dest)
                    if msg:
                        errors.append(msg)
                    flush()
                    tokens.append(("link", parse_inline(s[i + 1:close], errors, True, in_bold), dest))
                    i = end + 1
                    continue
        buf.append(s[i])
        i += 1
    flush()
    for tok in tokens:
        if tok[0] == "text":
            check_text(tok[1], errors)
    return tokens


def iter_tokens(tokens):
    for tok in tokens:
        yield tok
        if tok[0] in ("bold", "link"):
            yield from iter_tokens(tok[1])


def iter_text(tokens):
    for tok in iter_tokens(tokens):
        if tok[0] == "text":
            yield tok[1]


def plain(tokens):
    parts = []
    for tok in tokens:
        parts.append(tok[1] if tok[0] in ("text", "code") else plain(tok[1]))
    return "".join(parts)


def code_name(tokens):
    if len(tokens) == 1 and tokens[0][0] == "code" and NAME_RE.match(tokens[0][1]):
        return tokens[0][1]
    return None


# ---- 塊の書式 ----


class Item:
    def __init__(self, line, text, inline):
        self.line = line
        self.text = text
        self.inline = inline
        self.children = []


class Block:
    def __init__(self, kind, line):
        self.kind = kind  # heading / list / table / code / para
        self.line = line
        self.level = 0
        self.text = ""
        self.inline = []
        self.items = []
        self.header = []  # [(セルの文字, 字句)]
        self.rows = []  # [(行, [(セルの文字, 字句)])]
        self.lang = ""
        self.code = []
        self.lines = []  # [(行, 文字, 字句)]


class Parser:
    """決めた書式だけを読む。外れた箇所は errors に (行, メッセージ) で積む。"""

    def __init__(self, text):
        self.errors = []
        self.blocks = []
        if text.startswith("\ufeff"):
            self.error(1, "BOM を付けない")
            text = text[1:]
        if "\r" in text:
            self.error(1, "改行は LF にする")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.lines = text.split("\n")
        if self.lines and self.lines[-1] == "":
            self.lines.pop()
        self.parse()

    def error(self, line, msg):
        if (line, msg) not in self.errors:
            self.errors.append((line, msg))

    def check_tab(self, i):
        if "\t" in self.lines[i]:
            self.error(i + 1, "タブを使わない")

    def inline(self, text, line):
        msgs = []
        tokens = parse_inline(text, msgs)
        for msg in msgs:
            self.error(line, msg)
        return tokens

    def parse(self):
        i = 0
        need_blank = False
        while i < len(self.lines):
            raw = self.lines[i].rstrip()
            if not raw:
                need_blank = False
                i += 1
                continue
            if need_blank:
                self.error(i + 1, "前の行との間に空行を入れる")
            if raw.startswith("```"):
                i = self.fence(i)
            elif HEADING_RE.match(raw):
                i = self.heading(i)
            elif LIST_RE.match(raw) and not banned(raw):
                i = self.bullets(i)
            elif raw.startswith("|"):
                i = self.table(i)
            else:
                i = self.para(i)
            need_blank = True
        first = self.blocks[0] if self.blocks else None
        if not (first and first.kind == "heading" and first.level == 1 and first.line == 1):
            self.error(1, "1 行目は # の見出しにする")

    def heading(self, i):
        ln = i + 1
        self.check_tab(i)
        m = HEADING_RE.match(self.lines[i].rstrip())
        blk = Block("heading", ln)
        blk.level = len(m.group(1))
        blk.text = (m.group(2) or "").strip()
        if blk.level > 3:
            self.error(ln, "見出しは ### まで")
        if not blk.text:
            self.error(ln, "見出しの文字が空")
        elif re.search(r"(?:^| )#+$", blk.text):
            self.error(ln, "見出しの末尾に # を書かない")
        if blk.level == 1 and ln != 1:
            self.error(ln, "# の見出しは 1 行目に 1 つだけ")
        blk.inline = self.inline(blk.text, ln)
        self.blocks.append(blk)
        return i + 1

    def bullets(self, i):
        blk = Block("list", i + 1)
        while i < len(self.lines):
            raw = self.lines[i].rstrip()
            m = LIST_RE.match(raw) if raw else None
            if not m or banned(raw):
                break
            ln = i + 1
            self.check_tab(i)
            indent = len(m.group(1))
            text = (m.group(2) or "").strip()
            item = Item(ln, text, self.inline(text, ln))
            if not text:
                self.error(ln, "空の箇条")
            elif text.startswith("```") or HEADING_RE.match(text) or LIST_RE.match(text) or banned(text):
                self.error(ln, "箇条の先頭に書式の記号を置かない")
            if indent == 0:
                blk.items.append(item)
            elif indent == 2 and blk.items:
                blk.items[-1].children.append(item)
            elif indent == 2:
                self.error(ln, "字下げした箇条の上に親の箇条が無い")
            else:
                self.error(ln, "箇条の入れ子は 2 段まで。字下げは空白 2 つにする")
            i += 1
        self.blocks.append(blk)
        return i

    def table(self, i):
        blk = Block("table", i + 1)
        self.check_tab(i)
        header = split_row(self.lines[i].rstrip())
        if header is None:
            self.error(i + 1, "表の行は | で始めて | で終える")
            header = []
        blk.header = [(cell, self.inline(cell, i + 1)) for cell in header]
        j = i + 1
        sep = split_row(self.lines[j].rstrip()) if j < len(self.lines) else None
        if sep is not None and len(sep) == len(header) and all(SEPARATOR_CELL_RE.match(c) for c in sep):
            j += 1
        else:
            self.error(i + 1, "表の 2 行目は、見出し行と同じ数の | --- | の区切りにする")
        while j < len(self.lines) and self.lines[j].rstrip().startswith("|"):
            self.check_tab(j)
            cells = split_row(self.lines[j].rstrip())
            if cells is None:
                self.error(j + 1, "表の行は | で始めて | で終える")
                cells = []
            elif len(cells) != len(header):
                self.error(j + 1, "表の列の数が見出し行と違う（セルの中に | を書かない）")
            blk.rows.append((j + 1, [(cell, self.inline(cell, j + 1)) for cell in cells]))
            j += 1
        self.blocks.append(blk)
        return j

    def fence(self, i):
        ln = i + 1
        blk = Block("code", ln)
        blk.lang = self.lines[i].rstrip()[3:].strip()
        if not blk.lang:
            self.error(ln, "コードブロックに言語名を書く")
        elif not LANG_RE.match(blk.lang):
            self.error(ln, "コードブロックの言語名は英数字の 1 語にする")
        j = i + 1
        while j < len(self.lines) and self.lines[j].rstrip() != "```":
            j += 1
        blk.code = self.lines[i + 1:j]
        self.blocks.append(blk)
        if j >= len(self.lines):
            self.error(ln, "コードブロックが閉じていない")
            return j
        return j + 1

    def para(self, i):
        blk = Block("para", i + 1)
        j = i
        while j < len(self.lines):
            raw = self.lines[j].rstrip()
            if not raw or (j > i and starts_block(raw)):
                break
            ln = j + 1
            self.check_tab(j)
            msg = banned(raw)
            text = raw.strip()
            if msg:
                self.error(ln, msg)
                tokens = [("text", text)]
            else:
                if raw[0] == " ":
                    self.error(ln, "行頭に空白を置かない")
                tokens = self.inline(text, ln)
            blk.lines.append((ln, text, tokens))
            j += 1
        self.blocks.append(blk)
        return j


# ---- 型 ----


class Template:
    """formats/ の雛形。見出しの構造と、分割したとき親だけに置く見出しを持つ。"""

    def __init__(self, kind):
        parser = Parser((FORMATS_DIR / f"{kind}.md").read_bytes().decode("utf-8"))
        self.errors = parser.errors
        blocks = parser.blocks
        self.title = blocks[0].text
        self.headings = [(b.level, b.text) for b in blocks if b.kind == "heading" and b.level >= 2]
        self.parent_only = set()
        if len(blocks) > 1 and blocks[1].kind == "list":
            for item in blocks[1].items:
                m = KV_RE.match(item.text)
                if m and m.group(1) == PARENT_ONLY_KEY and m.group(2) and m.group(2) != "なし":
                    self.parent_only = {name.strip() for name in m.group(2).split("、")}

    def expected(self, child):
        """文書が持つべき見出しを (階層, 文字) の列で返す。子は親だけの見出しとその下を除く。"""
        out = []
        cut = 0
        for level, text in self.headings:
            if cut and level > cut:
                continue
            cut = 0
            if child and text in self.parent_only:
                cut = level
                continue
            out.append((level, text))
        return out


def read_fields(item, label, spec, err):
    """番号などの下の `- 項目: 値` を読む。"""
    got = {}
    for c in item.children:
        m = KV_RE.match(c.text)
        if not m or m.group(1) not in spec:
            if spec:
                err(c.line, f"{label} の下に書けるのは {'・'.join(spec)}")
            else:
                err(c.line, f"{label} の下に箇条を書かない")
            continue
        key, value = m.group(1), (m.group(2) or "").strip()
        if key in got:
            err(c.line, f"{key} が重なっている")
            continue
        if not value:
            err(c.line, f"{key} が空")
        got[key] = (c, value)
    for key, required in spec.items():
        if required and key not in got:
            err(item.line, f"{label} の下に {key} が無い")
    return got


def parse_ids(field, key, want, err, allow_none=False):
    """`R-001、R-002` の形の値から番号を取り出す。allow_none なら「なし」を許す。"""
    item, value = field
    if not value or (allow_none and value == "なし"):
        return []
    ids = [m.group(0) for m in ID_RE.finditer(value)]
    if any(not ID_RE.fullmatch(p) for p in value.split("、")) or any(split_id(i)[0] != want for i in ids):
        err(item.line, f"{key} は {want}-001、{want}-002 のように番号を「、」で区切って書く")
    elif len(set(ids)) != len(ids):
        err(item.line, f"{key} に同じ番号を重ねて書かない")
    return [i for i in ids if split_id(i)[0] == want]


def read_columns(value):
    """`` `テーブル.カラム` `` を「、」で区切った値を読む。形が違えば None。"""
    cols = []
    for tok in parse_inline(value, []):
        if tok[0] == "code":
            m = COLUMN_RE.match(tok[1])
            if not m:
                return None
            cols.append((m.group(1), m.group(2)))
        elif tok[0] != "text" or tok[1].replace("、", "").strip():
            return None
    return cols or None


class Doc:
    """specs/ の下の型の文書 1 本。"""

    def __init__(self, path, ws):
        self.path = path
        self.ws = ws
        self.kind = path.stem
        self.root = None
        self.spec_dir = None
        self.child = None
        self.local_errors = []  # この文書だけで分かる誤り
        self.title_block = None
        self.meta_block = None
        self.meta = {}  # 項目 -> (Item, 値)
        self.state = None
        self.sections = []  # [(見出しの鍵, 見出し, [塊])]
        self.section = {}
        self.defs = {}  # 番号 -> Item
        self.anchors = {}  # id(Item) -> 番号
        self.ac_reqs = {}  # AC -> [R]
        self.s_acs = {}  # S -> (行, [AC])
        self.q_stage = {}  # Q -> (行, 止める工程)
        self.refs = []  # [(行, 番号)]
        self.split = None  # 子の名前 -> {"line", "reqs", "deps"}
        self.tables = None  # テーブル名 -> カラム名の集合
        self.data_use = []  # [(行, テーブル, カラム)]
        try:
            data = path.read_bytes()
        except OSError as e:
            self.blocks = []
            self.line_count = 1
            self.syntax_errors = [(1, f"読めない: {e.strerror or e}")]
            return
        try:
            text = data.decode("utf-8")
            decode_error = False
        except UnicodeDecodeError:
            text = data.decode("utf-8", "replace")
            decode_error = True
        parser = Parser(text)
        self.blocks = parser.blocks
        self.line_count = max(len(parser.lines), 1)
        self.syntax_errors = parser.errors
        if decode_error:
            self.syntax_errors.insert(0, (1, "UTF-8 で書く"))
        self.locate()
        if self.root is not None:
            self.analyze()

    @property
    def spec_rel(self):
        return self.spec_dir.relative_to(self.root).as_posix()

    def body(self, key):
        entry = self.section.get(key)
        return entry[2] if entry else None

    def heading_line(self, key):
        entry = self.section.get(key)
        return entry[1].line if entry else 1

    def spec_doc(self, kind, child=None):
        path = self.spec_dir / child / f"{kind}.md" if child else self.spec_dir / f"{kind}.md"
        return self.ws.load(path)

    def resolve(self, ident):
        """番号を定義している文書を返す。無ければ None。"""
        typ, child = split_id(ident)
        if typ == "Q":
            target = self
        elif typ == "R":
            target = None if child else self.spec_doc("requirements")
        else:
            target = self.spec_doc("design" if typ == "AC" else "plan", child)
        if target is not None and ident in target.defs:
            return target
        return None

    def example_id(self, typ):
        if typ in ("AC", "S") and self.child:
            return f"{typ}-{self.child}-001"
        return f"{typ}-001"

    def inlines(self):
        """行内の字句を (行, 字句, Item または None, 塊) で順に返す。"""
        for b in self.blocks:
            if b.kind == "heading":
                yield b.line, b.inline, None, b
            elif b.kind == "para":
                for ln, _, inl in b.lines:
                    yield ln, inl, None, b
            elif b.kind == "table":
                for _, inl in b.header:
                    yield b.line, inl, None, b
                for ln, cells in b.rows:
                    for _, inl in cells:
                        yield ln, inl, None, b
            elif b.kind == "list":
                for item in b.items:
                    for it in [item] + item.children:
                        yield it.line, it.inline, it, b

    def locate(self):
        for anc in self.path.parents:
            if anc.name == "specs":
                parts = self.path.relative_to(anc).parts
                break
        else:
            self.local_errors.append((1, "specs/<id>-<slug>/ の下に置く"))
            return
        if len(parts) not in (2, 3):
            self.local_errors.append((1, "specs/<id>-<slug>/ か、その下の子のディレクトリに置く"))
            return
        if len(parts) == 3:
            if self.kind == "requirements":
                self.local_errors.append((1, "要件定義書は分けない。specs/<id>-<slug>/requirements.md に置く"))
                return
            if not CHILD_RE.match(parts[1]) or parts[1] in RESERVED_CHILD_NAMES:
                self.local_errors.append(
                    (1, "子のディレクトリ名は、英小文字で始まる英小文字・数字の 1〜2 語にする（2 語はハイフンでつなぐ）")
                )
                return
            self.child = parts[1]
        self.root = anc.parent
        self.spec_dir = anc / parts[0]

    def analyze(self):
        def err(line, msg):
            self.local_errors.append((line, msg))

        tpl = self.ws.template(self.kind)
        self.index_blocks(err)
        self.check_title(tpl, err)
        self.read_meta(err)
        self.check_headings(tpl, err)
        self.read_defs(err)
        self.collect_refs()
        if self.kind == "design":
            if self.child is None:
                self.read_split(err)
                self.read_tables(err)
            self.read_data_use(err)
        self.check_links(err)

    def index_blocks(self, err):
        blocks = self.blocks
        k = 0
        if blocks and blocks[0].kind == "heading" and blocks[0].level == 1:
            self.title_block = blocks[0]
            k = 1
        if k < len(blocks) and blocks[k].kind == "list":
            self.meta_block = blocks[k]
            k += 1
        else:
            err(blocks[k].line if k < len(blocks) else 1, "見出しの直後に管理情報（- 著者: …）を書く")
        current = None
        h2 = None
        for b in blocks[k:]:
            if b.kind == "heading" and b.level >= 2:
                if b.level == 2:
                    h2 = b.text
                    key = (b.text,)
                else:
                    key = (h2, b.text)
                current = (key, b, [])
                self.sections.append(current)
                self.section.setdefault(key, current)
            elif current is None:
                err(b.line, "管理情報と最初の ## の間には何も書かない")
            else:
                current[2].append(b)

    def check_title(self, tpl, err):
        b = self.title_block
        m = re.match(r"^(.+?): (.+)$", b.text) if b else None
        if not m or m.group(1) != tpl.title:
            err(1, f"1 行目は `# {tpl.title}: 件名` の形で書く")

    def read_meta(self, err):
        blk = self.meta_block
        if blk is None:
            return
        last = -1
        for item in blk.items:
            m = KV_RE.match(item.text)
            if not m:
                err(item.line, "管理情報は `- 項目: 値` の形で書く")
                continue
            key, value = m.group(1), (m.group(2) or "").strip()
            if key not in META_KEYS:
                err(item.line, f"管理情報に使えない項目: {key}（使えるのは {'、'.join(META_KEYS)}）")
                continue
            if key in self.meta:
                err(item.line, f"管理情報の項目が重なっている: {key}")
                continue
            pos = META_KEYS.index(key)
            if pos < last:
                err(item.line, f"管理情報の順序が違う（{'、'.join(META_KEYS)} の順）")
            last = max(last, pos)
            self.meta[key] = (item, value)
            if item.children and key != "上流":
                err(item.children[0].line, f"{key} の下に箇条を書かない")

        def need(key):
            if key not in self.meta:
                err(blk.line, f"管理情報に {key} が無い")
                return None
            return self.meta[key]

        author = need("著者")
        if author and not author[1]:
            err(author[0].line, "著者が空")
        state = need("状態")
        if state:
            if state[1] in STATES:
                self.state = state[1]
            else:
                err(state[0].line, "状態は draft か approved にする")
        approver = self.meta.get("承認者")
        if self.state == "approved" and (approver is None or not approver[1]):
            err(approver[0].line if approver else state[0].line, "approved のときは承認者を書く")
        if self.state != "approved" and approver is not None:
            err(approver[0].line, "承認者は approved のときだけ書く")
        legend = need("凡例")
        if legend and legend[1] != LEGEND:
            err(legend[0].line, "凡例の文言が違う。common.md の文言をそのまま書く")
        parent = self.meta.get("親")
        if self.child:
            expected = f"{self.spec_rel}/{self.kind}.md"
            if parent is None:
                err(blk.line, f"子の文書には親を書く: {expected}")
            elif parent[1] != expected:
                err(parent[0].line, f"親は {expected} にする")
        elif parent is not None:
            err(parent[0].line, "親は子の文書だけに書く")
        upstream = self.meta.get("上流")
        if self.kind == "requirements":
            if upstream is not None:
                err(upstream[0].line, "要件定義書には上流を書かない")
        elif upstream is None:
            err(blk.line, "管理情報に上流が無い")
        else:
            item, value = upstream
            if value:
                err(item.line, "上流は下の箇条に 1 件ずつ書く")
            if not item.children:
                err(item.line, "上流が空")
            for c in item.children:
                if not UPSTREAM_RE.match(c.text):
                    err(c.line, "上流は `パス@hash` の形で書く（specdoc.py hash の出力）")
        source = self.meta.get("元の文書")
        if source is not None and not source[1]:
            err(source[0].line, "元の文書が空")

    def check_headings(self, tpl, err):
        expected = tpl.expected(self.child is not None)
        dropped = {text for _, text in tpl.headings} - {text for _, text in expected}
        actual = [b for b in self.blocks if b.kind == "heading" and b.level >= 2]
        keys = [(b.level, b.text) for b in actual]
        matcher = difflib.SequenceMatcher(None, keys, expected, autojunk=False)
        for op, a1, a2, b1, b2 in matcher.get_opcodes():
            if op == "equal":
                continue
            for b in actual[a1:a2]:
                if b.text in dropped:
                    err(b.line, f"子の文書には書かない見出し: {'#' * b.level} {b.text}")
                else:
                    err(b.line, f"型に無い見出し: {'#' * b.level} {b.text}")
            at = actual[a1].line if a1 < len(actual) else self.line_count
            for level, text in expected[b1:b2]:
                err(at, f"見出しが無い: {'#' * level} {text}")
        heads = [(k, b) for k, b in enumerate(self.blocks) if b.kind == "heading" and b.level >= 2]
        for n, (k, b) in enumerate(heads):
            nxt = heads[n + 1] if n + 1 < len(heads) else None
            if nxt and nxt[1].level > b.level:
                continue
            end = nxt[0] if nxt else len(self.blocks)
            if end == k + 1:
                err(b.line, f"本文が空: {'#' * b.level} {b.text}。書く内容が無ければ「なし」と書く")

    def read_defs(self, err):
        places = DEF_SECTIONS[self.kind]
        for key, _, body in self.sections:
            want = places.get(key)
            if want is None:
                continue
            for b in body:
                if b.kind != "list":
                    continue
                for item in b.items:
                    m = DEF_RE.match(item.text)
                    if not m or split_id(m.group(1))[0] != want:
                        err(item.line, f"一番上の箇条は `{self.example_id(want)}: 本文` の形で書く")
                        continue
                    ident, text = m.group(1), (m.group(2) or "").strip()
                    typ, child = split_id(ident)
                    if typ in ("R", "Q"):
                        if child:
                            err(item.line, f"{typ} の番号に子の名前は入れない: {ident}")
                    elif self.child and child != self.child:
                        err(item.line, f"子の文書の {typ} は {self.example_id(typ)} の形にする: {ident}")
                    elif not self.child and child:
                        err(item.line, f"{typ} の番号に子の名前を入れるのは子の文書だけ: {ident}")
                    if ident in self.defs:
                        err(item.line, f"番号が重なっている: {ident}（{self.defs[ident].line} 行目）")
                        continue
                    if not text:
                        err(item.line, f"本文が空: {ident}")
                    self.defs[ident] = item
                    self.anchors[id(item)] = ident
                    self.read_id_fields(item, ident, typ, err)

    def read_id_fields(self, item, ident, typ, err):
        fields = read_fields(item, ident, ID_FIELDS[typ], err)
        if typ == "AC" and "要件" in fields:
            self.ac_reqs[ident] = parse_ids(fields["要件"], "要件", "R", err, True)
        elif typ == "S":
            if "受け入れ基準" in fields:
                field = fields["受け入れ基準"]
                self.s_acs[ident] = (field[0].line, parse_ids(field, "受け入れ基準", "AC", err))
            kind = fields.get("種別")
            if kind and kind[1] and kind[1] not in SCENARIO_KINDS:
                err(kind[0].line, f"種別は {'・'.join(SCENARIO_KINDS)} のどれか")
        elif typ == "Q":
            stage = fields.get("止める工程")
            if stage and stage[1]:
                if stage[1] in STAGES:
                    self.q_stage[ident] = (item.line, stage[1])
                else:
                    err(stage[0].line, f"止める工程は {'・'.join(STAGES)} のどれか")

    def collect_refs(self):
        for line, tokens, item, blk in self.inlines():
            if blk is self.meta_block:
                continue
            own = self.anchors.get(id(item)) if item is not None else None
            for text in iter_text(tokens):
                for m in ID_RE.finditer(text):
                    if m.group(0) == own:
                        own = None
                        continue
                    self.refs.append((line, m.group(0)))

    def read_split(self, err):
        self.split = {}
        body = self.body(SPLIT_SECTION) or []
        lists = [b for b in body if b.kind == "list"]
        if not lists:
            paras = [b for b in body if b.kind == "para"]
            text = "".join(t for _, t, _ in paras[0].lines) if paras else ""
            if body and not UNSPLIT_RE.match(text):
                err((paras or body)[0].line, "分割しないときは「分割しない。理由: …」と書く")
            return
        for b in lists:
            for item in b.items:
                m = KV_RE.match(item.text)
                name = m.group(1) if m else ""
                if not m or not CHILD_RE.match(name) or name in RESERVED_CHILD_NAMES:
                    err(
                        item.line,
                        "子は `- 子の名前: 説明` の形で書く。子の名前は英小文字で始まる英小文字・数字の 1〜2 語（2 語はハイフンでつなぐ）",
                    )
                    continue
                if name in self.split:
                    err(item.line, f"子の名前が重なっている: {name}")
                    continue
                if not (m.group(2) or "").strip():
                    err(item.line, f"説明が空: {name}")
                fields = read_fields(item, name, SPLIT_FIELDS, err)
                reqs = parse_ids(fields["要件"], "要件", "R", err, True) if "要件" in fields else []
                deps = []
                dep = fields.get("依存")
                if dep and dep[1] and dep[1] != "なし":
                    for d in dep[1].split("、"):
                        d = d.strip()
                        if d in self.split:
                            deps.append(d)
                        else:
                            err(dep[0].line, f"依存には、先に並べた子を書く（並び順が実装順）: {d}")
                self.split[name] = {"line": item.line, "reqs": reqs, "deps": deps}

    def read_tables(self, err):
        self.tables = {}
        for b in self.body(TABLE_SECTION) or []:
            if b.kind != "table":
                continue
            raws = [raw for raw, _ in b.header]
            name = code_name(b.header[0][1]) if b.header else None
            if len(raws) != 6 or tuple(raws[1:]) != TABLE_HEADER or not name:
                err(b.line, "テーブル定義の見出し行は | `テーブル名` | 意味 | 型・長さ | 必須 | 制約 | 差分 | にする")
                continue
            if name in self.tables:
                err(b.line, f"テーブルが重なっている: {name}")
                continue
            cols = set()
            for ln, cells in b.rows:
                if len(cells) != 6:
                    continue
                col = code_name(cells[0][1])
                if not col:
                    err(ln, "1 つ目のセルにカラム名をコードで書く")
                    continue
                if col in cols:
                    err(ln, f"カラムが重なっている: {name}.{col}")
                    continue
                cols.add(col)
                if cells[5][0] not in DIFF_KINDS:
                    err(ln, f"差分は {'・'.join(DIFF_KINDS)} のどれか")
            self.tables[name] = cols

    def read_data_use(self, err):
        for b in self.body(DATA_USE_SECTION) or []:
            if b.kind != "list":
                continue
            for item in b.items:
                if not item.children:
                    err(item.line, "処理の下に `- 書く:` か `- 読む:` を書く")
                    continue
                seen = set()
                for c in item.children:
                    m = KV_RE.match(c.text)
                    if not m or m.group(1) not in ("書く", "読む"):
                        err(c.line, "処理の下に書けるのは 書く と 読む")
                        continue
                    if m.group(1) in seen:
                        err(c.line, f"{m.group(1)} が重なっている")
                        continue
                    seen.add(m.group(1))
                    cols = read_columns(m.group(2) or "")
                    if cols is None:
                        err(c.line, "`テーブル.カラム` を「、」で区切って書く")
                        continue
                    for table, col in cols:
                        self.data_use.append((c.line, table, col))

    def check_links(self, err):
        """相対パスのリンク先が実在するかを見る。リンク先の書式は Parser で見る。"""
        for line, tokens, _, _ in self.inlines():
            for tok in iter_tokens(tokens):
                if tok[0] != "link":
                    continue
                dest = tok[2]
                if link_dest_error(dest) or dest.startswith("#") or WEB_RE.match(dest):
                    continue
                target = dest.split("#", 1)[0].split("?", 1)[0]
                if target and not (self.path.parent / unquote(target)).exists():
                    err(line, f"リンク先が無い: {dest}")


class Workspace:
    """読んだ文書と型を 1 回の実行の間だけ持つ。"""

    def __init__(self):
        self.docs = {}
        self.templates = {}

    def template(self, kind):
        if kind not in self.templates:
            self.templates[kind] = Template(kind)
        return self.templates[kind]

    def load(self, path):
        key = str(path)
        if key not in self.docs:
            self.docs[key] = Doc(path, self) if path.is_file() else None
        return self.docs[key]


# ---- 文書をまたぐ照合 ----


def required_upstreams(doc):
    s = doc.spec_rel
    if doc.kind == "design":
        req = [f"{s}/requirements.md"]
        if doc.child:
            req.append(f"{s}/design.md")
    else:
        req = [f"{s}/{doc.child}/design.md" if doc.child else f"{s}/design.md"]
        if doc.child:
            req.append(f"{s}/plan.md")
    return req


def check_upstream(doc, err):
    entry = doc.meta.get("上流")
    if doc.kind == "requirements" or entry is None:
        return
    item = entry[0]
    listed = set()
    for c in item.children:
        m = UPSTREAM_RE.match(c.text)
        if not m:
            continue
        rel, short = m.group(1), m.group(2)
        parts = rel.split("/")
        if rel.startswith("/") or any(p in ("", ".", "..") for p in parts):
            err(c.line, f"上流のパスはリポジトリルートからの相対パスで書く: {rel}")
            continue
        if rel in listed:
            err(c.line, f"上流が重なっている: {rel}")
            continue
        listed.add(rel)
        target = doc.root.joinpath(*parts)
        if not target.is_file():
            err(c.line, f"上流のファイルが無い: {rel}")
            continue
        try:
            current = blob_hash(target.read_bytes())
        except OSError as e:
            err(c.line, f"上流のファイルを読めない: {rel}（{e.strerror or e}）")
            continue
        if not current.startswith(short):
            err(c.line, f"上流の hash が合わない: {rel}（今は {current[:12]}）。下流に影響を反映してから書き換える")
        if target.name in DOC_FILES:
            up = doc.ws.load(target)
            if up is not None and up.root is not None and up.state != "approved":
                err(c.line, f"上流が approved でない: {rel}")
    for rel in required_upstreams(doc):
        if rel not in listed:
            err(item.line, f"上流に {rel} が無い")


def listed_in_parent(doc, err):
    top = doc.spec_doc("design")
    if top is None:
        err(1, f"親の設計書 {doc.spec_rel}/design.md が無い")
        return None
    if not top.split or doc.child not in top.split:
        err(1, f"親の設計書の「サブ機能分割」に {doc.child} が無い")
        return None
    return top


def check_coverage(doc, err):
    if doc.kind == "design" and doc.child is None:
        at = doc.heading_line(SPLIT_SECTION)
        for p in sorted(doc.spec_dir.iterdir()):
            if (
                p.is_dir()
                and p.name != "mocks"
                and not p.name.startswith(".")
                and ((p / "design.md").is_file() or (p / "plan.md").is_file())
                and p.name not in (doc.split or {})
            ):
                err(at, f"「サブ機能分割」に無い子のディレクトリがある: {p.name}/")
        req = doc.spec_doc("requirements")
        if req is None:
            err(1, f"{doc.spec_rel}/requirements.md が無い")
            return
        covered = {r for reqs in doc.ac_reqs.values() for r in reqs}
        assigned = {r for c in (doc.split or {}).values() for r in c["reqs"]}
        at = doc.heading_line(("受け入れ基準",))
        for r in req.defs:
            if split_id(r)[0] == "R" and r not in covered and r not in assigned:
                err(at, f"{r} を受ける AC が無い")
    elif doc.kind == "design":
        top = listed_in_parent(doc, err)
        if top is None:
            return
        covered = {r for reqs in doc.ac_reqs.values() for r in reqs}
        at = doc.heading_line(("受け入れ基準",))
        for r in top.split[doc.child]["reqs"]:
            if r not in covered:
                err(at, f"{r} を受ける AC が無い（親の「サブ機能分割」でこの子に割り当てている）")
    elif doc.kind == "plan":
        if doc.child and listed_in_parent(doc, err) is None:
            return
        design = doc.spec_doc("design", doc.child)
        if design is None:
            err(1, "同じディレクトリに design.md が無い")
            return
        covered = set()
        for line, acs in doc.s_acs.values():
            for ac in acs:
                covered.add(ac)
                if ac not in design.defs and doc.resolve(ac) is not None:
                    err(line, f"受け入れ基準には同じディレクトリの設計書の AC を書く: {ac}")
        at = doc.heading_line(("シナリオ",))
        for ac in design.defs:
            if split_id(ac)[0] == "AC" and ac not in covered:
                err(at, f"{ac} を受ける S が無い")


def check_data_use(doc, err):
    top = doc.spec_doc("design") if doc.child else doc
    if top is None or top.tables is None:
        return
    for line, table, col in doc.data_use:
        if col not in top.tables.get(table, ()):
            err(line, f"テーブル定義に無いカラム: {table}.{col}")


def check_gate(doc, gate, require_approved, err):
    for q, (line, stage) in doc.q_stage.items():
        if gate and STAGES.index(stage) <= STAGES.index(gate):
            err(line, f"止める工程が「{stage}」の要確認が残っている: {q}")
        elif doc.state == "approved" and stage == "承認":
            err(line, f"approved の文書に、止める工程が「承認」の要確認が残っている: {q}")
    if require_approved and doc.state != "approved":
        entry = doc.meta.get("状態")
        err(entry[0].line if entry else 1, "状態が approved でない")


def missing_downstream(doc):
    """まだ無い下流の文書を (行, パス, それが無いと止める工程) の列で返す。"""
    s = doc.spec_rel
    out = []
    if doc.kind == "requirements":
        if doc.spec_doc("design") is None:
            out.append((1, f"{s}/design.md", "リリース"))
    elif doc.kind == "design":
        if doc.child is None:
            for name, c in (doc.split or {}).items():
                for kind in ("design", "plan"):
                    if doc.spec_doc(kind, name) is None:
                        out.append((c["line"], f"{s}/{name}/{kind}.md", "リリース"))
        if doc.spec_doc("plan", doc.child) is None:
            here = f"{s}/{doc.child}" if doc.child else s
            out.append((1, f"{here}/plan.md", "実装"))
    return out


def check_doc(doc, gate=None, require_approved=False):
    """文書 1 本の誤りを (行, メッセージ) の列で返す。書式の誤りがあれば書式だけを返す。"""
    if doc.syntax_errors:
        return list(doc.syntax_errors)
    errors = list(doc.local_errors)
    if doc.root is None:
        return errors

    def err(line, msg):
        errors.append((line, msg))

    for line, ident in doc.refs:
        if doc.resolve(ident) is None:
            err(line, f"定義の無い番号: {ident}")
    check_coverage(doc, err)
    check_upstream(doc, err)
    if doc.kind == "design":
        check_data_use(doc, err)
    check_gate(doc, gate, require_approved, err)
    for line, rel, stage in missing_downstream(doc):
        if gate and STAGES.index(stage) <= STAGES.index(gate):
            err(line, f"下流の文書が無い: {rel}")
    return errors


# ---- HTML ----


def esc(text):
    return html.escape(text, quote=True)


class Renderer:
    def __init__(self, doc):
        self.doc = doc

    def link_href(self, dest):
        """行内リンクの href。書式の誤りがあるリンク先は None。specs/ の下の型の文書への .md は .html に書き換える。"""
        if link_dest_error(dest) is not None:
            return None
        if dest.startswith("#") or WEB_RE.match(dest):
            return dest
        path, sep, frag = dest.partition("#")
        if path.rsplit("/", 1)[-1] in DOC_FILES:
            target = Path(os.path.normpath(str(self.doc.path.parent / unquote(path))))
            other = self.doc.ws.load(target)
            if other is not None and other.root is not None:
                path = path[:-3] + ".html"
        return path + sep + frag

    def href_to(self, path):
        return os.path.relpath(str(path), str(self.doc.path.parent)).replace(os.sep, "/")

    def render(self):
        doc = self.doc
        title = plain(doc.title_block.inline) if doc.title_block else doc.path.name
        out = [
            "<!DOCTYPE html>",
            '<html lang="ja">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title>",
            "<style>",
            CSS,
            "</style>",
            "</head>",
            "<body>",
            "<main>",
        ]
        for b in doc.blocks:
            if b is doc.meta_block:
                out.extend(self.meta())
            elif b.kind == "heading":
                out.append(f"<h{b.level}>{self.inline(b.inline)}</h{b.level}>")
            elif b.kind == "para":
                out.append("<p>" + "\n".join(self.inline(inl) for _, _, inl in b.lines) + "</p>")
            elif b.kind == "list":
                out.extend(self.bullets(b.items))
            elif b.kind == "table":
                out.extend(self.table(b))
            elif b.kind == "code":
                code = esc("\n".join(b.code))
                if b.lang == "mermaid":
                    out.append(f'<pre class="mermaid">{code}</pre>')
                else:
                    out.append(f'<pre><code class="language-{esc(b.lang)}">{code}</code></pre>')
        out.append("</main>")
        if any(b.kind == "code" and b.lang == "mermaid" for b in doc.blocks):
            out.append(f'<script src="{MERMAID_URL}" integrity="{MERMAID_INTEGRITY}" crossorigin="anonymous"></script>')
            out.append("<script>if (window.mermaid) { mermaid.initialize({ startOnLoad: true }); }</script>")
        out.append("</body>")
        out.append("</html>")
        return "\n".join(out) + "\n"

    def meta(self):
        out = ['<dl class="meta">']
        for item in self.doc.meta_block.items:
            m = KV_RE.match(item.text)
            if not m:
                out.append(f"<dd>{self.inline(item.inline, False)}</dd>")
                continue
            key, value = m.group(1), (m.group(2) or "").strip()
            out.append(f"<dt>{esc(key)}</dt>")
            if key == "親" and value:
                out.append(f"<dd>{self.doc_link(value, None)}</dd>")
            elif key == "上流":
                out.append("<dd>")
                out.append("<ul>")
                for c in item.children:
                    um = UPSTREAM_RE.match(c.text)
                    out.append(f"<li>{self.doc_link(um.group(1), c.text) if um else esc(c.text)}</li>")
                out.append("</ul>")
                out.append("</dd>")
            else:
                out.append(f"<dd>{self.inline(parse_inline(value, []), False)}</dd>")
        out.append("</dl>")
        return out

    def doc_link(self, rel, code):
        """上流や親へのリンク。表示名は相手の文書の見出しから取る。"""
        if rel.startswith("/") or "\\" in rel or any(p in ("", ".", "..") for p in rel.split("/")):
            return esc(code or rel)
        target = self.doc.root.joinpath(*rel.split("/"))
        href = self.href_to(target)
        if SCHEME_RE.match(href) or href[:1] <= " ":
            href = "./" + href
        label = rel
        if target.name in DOC_FILES:
            href = href[:-3] + ".html"
            other = self.doc.ws.load(target)
            if other is not None and other.title_block is not None:
                label = plain(other.title_block.inline)
        link = f'<a href="{esc(href)}">{esc(label)}</a>'
        return f"{link} <code>{esc(code)}</code>" if code else link

    def bullets(self, items):
        out = ["<ul>"]
        for it in items:
            ident = self.doc.anchors.get(id(it))
            attr = f' id="{ident}"' if ident else ""
            body = self.inline(it.inline)
            if it.children:
                out.append(f"<li{attr}>{body}")
                out.extend(self.bullets(it.children))
                out.append("</li>")
            else:
                out.append(f"<li{attr}>{body}</li>")
        out.append("</ul>")
        return out

    def table(self, b):
        out = ["<table>", "<thead>"]
        out.append("<tr>" + "".join(f"<th>{self.inline(inl)}</th>" for _, inl in b.header) + "</tr>")
        out.append("</thead>")
        out.append("<tbody>")
        for _, cells in b.rows:
            out.append("<tr>" + "".join(f"<td>{self.inline(inl)}</td>" for _, inl in cells) + "</tr>")
        out.append("</tbody>")
        out.append("</table>")
        return out

    def inline(self, tokens, link_ids=True):
        parts = []
        for tok in tokens:
            if tok[0] == "text":
                parts.append(self.text(tok[1]) if link_ids else esc(tok[1]))
            elif tok[0] == "code":
                parts.append(f"<code>{esc(tok[1])}</code>")
            elif tok[0] == "bold":
                parts.append(f"<strong>{self.inline(tok[1], link_ids)}</strong>")
            else:
                href = self.link_href(tok[2])
                label = self.inline(tok[1], False)
                parts.append(f'<a href="{esc(href)}">{label}</a>' if href is not None else label)
        return "".join(parts)

    def text(self, s):
        """定義のある番号を、定義へのリンクにする。"""
        out = []
        pos = 0
        for m in ID_RE.finditer(s):
            ident = m.group(0)
            target = self.doc.resolve(ident)
            if target is None:
                continue
            if target is self.doc:
                href = f"#{ident}"
            else:
                href = f"{self.href_to(target.path.with_suffix('.html'))}#{ident}"
            out.append(esc(s[pos:m.start()]))
            out.append(f'<a href="{esc(href)}">{esc(ident)}</a>')
            pos = m.end()
        out.append(esc(s[pos:]))
        return "".join(out)


# ---- コマンド ----


def expand(args):
    """引数を型の文書のパスへ広げる。ディレクトリは mocks を除いて下をたどる。"""
    files = []
    errors = []
    for arg in args:
        path = Path(os.path.abspath(arg))
        if path.is_dir():
            found = sorted(
                (
                    p
                    for name in DOC_FILES
                    for p in path.rglob(name)
                    if p.is_file() and "mocks" not in p.relative_to(path).parts
                ),
                key=lambda p: p.as_posix(),
            )
            if not found:
                errors.append((path, 1, "型の文書（requirements.md・design.md・plan.md）が無い"))
            files.extend(found)
        elif path.is_file():
            if path.name in DOC_FILES:
                files.append(path)
            else:
                errors.append((path, 1, "型の文書（requirements.md・design.md・plan.md）ではない"))
        else:
            errors.append((path, 1, "ファイルもディレクトリも無い"))
    unique = []
    for p in files:
        if p not in unique:
            unique.append(p)
    return unique, errors


def run_check(args, gate=None, require_approved=False, unchecked=None):
    """unchecked には、この工程では止めないが、無いので照合していない下流の文書を集める。"""
    ws = Workspace()
    files, errors = expand(args)
    for path in files:
        doc = ws.load(path)
        errors.extend((path, line, msg) for line, msg in check_doc(doc, gate, require_approved))
        if unchecked is None or doc.root is None or doc.syntax_errors:
            continue
        for _, rel, stage in missing_downstream(doc):
            stops = gate and STAGES.index(stage) <= STAGES.index(gate)
            if not stops and rel not in unchecked:
                unchecked.append(rel)
    return files, errors


def run_html(args, notes=None):
    """notes には、終了コードに関わらない知らせ（警告・消した HTML）を集める。"""
    notes = [] if notes is None else notes
    ws = Workspace()
    files, errors = expand(args)
    written = []
    for path in files:
        doc = ws.load(path)
        out = path.with_suffix(".html")
        problems = doc.syntax_errors or (doc.local_errors if doc.root is None else [])
        if problems:
            errors.extend((path, line, msg) for line, msg in problems)
            if doc.root is not None and out.is_file():
                try:
                    out.unlink()
                except OSError as e:
                    errors.append((path, 1, f"古い {out.name} を消せない: {e.strerror or e}"))
                else:
                    notes.append((path, 1, f"古い {out.name} を消した"))
            continue
        doc.check_links(lambda line, msg: notes.append((path, line, f"警告: {msg}")))
        try:
            out.write_bytes(Renderer(doc).render().encode("utf-8"))
        except OSError as e:
            errors.append((path, 1, f"{out.name} を書けない: {e.strerror or e}"))
            continue
        written.append(out)
    return written, errors


def run_hash(arg):
    """上流に書く パス@hash の行と終了コードを返す。"""
    path = Path(os.path.abspath(arg))
    if not path.is_file():
        return 1, f"{arg}:1: ファイルが無い"
    for anc in path.parents:
        if anc.name == "specs":
            try:
                data = path.read_bytes()
            except OSError as e:
                return 1, f"{arg}:1: 読めない: {e.strerror or e}"
            return 0, f"{path.relative_to(anc.parent).as_posix()}@{blob_hash(data)[:12]}"
    return 1, f"{arg}:1: specs/ の下のファイルを指定する"


def display(path):
    rel = os.path.relpath(str(path))
    return str(path) if rel.startswith("..") else rel


def format_errors(errors):
    order = {}
    for path, _, _ in errors:
        order.setdefault(path, len(order))
    lines = []
    for path, line, msg in sorted(errors, key=lambda e: (order[e[0]], e[1])):
        text = f"{display(path)}:{line}: {msg}"
        if text not in lines:
            lines.append(text)
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="specdoc.py", description="要件定義書・基本設計書・実装プランを型と照合し、HTML に変換する"
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True
    p = sub.add_parser("check", help="型と照合する")
    p.add_argument("--gate", choices=STAGES, help="この工程かそれより前の工程で止める要確認が残っていればエラーにする")
    p.add_argument("--approved", action="store_true", help="状態が approved でなければエラーにする")
    p.add_argument("paths", nargs="+", metavar="PATH")
    p = sub.add_parser("html", help="Markdown の隣に HTML を書き出す")
    p.add_argument("paths", nargs="+", metavar="PATH")
    p = sub.add_parser("hash", help="上流に書く パス@hash を出す")
    p.add_argument("path", metavar="PATH")
    args = parser.parse_args(argv)

    if args.command == "check":
        unchecked = []
        files, errors = run_check(args.paths, args.gate, args.approved, unchecked)
        for line in format_errors(errors):
            print(line)
        if errors:
            return 1
        note = f"（下流が無く照合していない: {'、'.join(unchecked)}）" if unchecked else ""
        print(f"ok: {len(files)} 件{note}")
        return 0
    if args.command == "html":
        notes = []
        written, errors = run_html(args.paths, notes)
        for line in format_errors(errors) + format_errors(notes):
            print(line)
        for out in written:
            print(display(out))
        return 1 if errors else 0
    code, line = run_hash(args.path)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
