#!/usr/bin/env python3
"""Google Drive MCP の書き出し（base64）をデコードして、ファイルに保存する。

使い方（<plugin> は gdrive plugin のディレクトリの絶対パス）:
  python3 <plugin>/scripts/drivefile.py decode <入力> <出力>

<入力> は、書き出しの返り値が保存された tool-results のファイル（content に base64 が入った JSON）か、
base64 だけを書いたファイル。<出力> の拡張子が .pdf なら PDF の先頭と末尾を、.xlsx・.docx・.pptx なら
zip であることを確かめる。保存したファイルが zip（Office 形式）なら、壊れていないかを確かめ、
画像・図形とグラフ・スピーカーノートのフォルダの中身を出す。
Python 3.9 以上の標準ライブラリだけで、macOS と Linux（WSL を含む）で動く。
"""

import argparse
import base64
import binascii
import json
import os
import sys
import zipfile
import zlib

# Office 形式の本体のフォルダごとに、中身を出すフォルダ。SKILL.md の手順 4 と揃える
FOLDERS = {
    "xl/": ("xl/media/", "xl/drawings/"),
    "word/": ("word/media/",),
    "ppt/": ("ppt/media/", "ppt/notesSlides/"),
}
OFFICE_SUFFIXES = (".xlsx", ".docx", ".pptx")
PDF_TAIL = 1024  # PDF の %%EOF を探す、末尾のバイト数


def read_base64(text):
    """tool-results の JSON なら content を、そうでなければ text 全体を返す。base64 の文字に { は無い。"""
    if not text.lstrip().startswith("{"):
        return text
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"JSON として読めない: {e}") from None
    content = data.get("content")
    if not isinstance(content, str):
        raise ValueError("JSON に文字列の content が無い")
    return content


def decode(text):
    b64 = "".join(read_base64(text).split())
    if not b64:
        raise ValueError("base64 が空")
    try:
        return base64.b64decode(b64, validate=True)
    except binascii.Error as e:
        raise ValueError(f"base64 として読めない: {e}") from None


def check_shape(out, data):
    """<出力> の拡張子に中身の形が合わなければ、その理由を返す（合えば None）。"""
    suffix = os.path.splitext(out)[1].lower()
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            return "PDF の先頭に %PDF- が無い"
        if b"%%EOF" not in data[-PDF_TAIL:]:
            return "PDF の末尾に %%EOF が無い"
    elif suffix in OFFICE_SUFFIXES and not zipfile.is_zipfile(out):
        return "Office 形式なのに zip でない"
    return None


def inspect_zip(path):
    """壊れていればその理由（無ければ None）と、FOLDERS のフォルダごとの中身（_rels/ の下は除く）を返す。"""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            names = [n for n in z.namelist() if not n.endswith("/")]
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError) as e:
        # 暗号化された項目は RuntimeError、未対応の圧縮方式は NotImplementedError になる
        return f"zip として読めない: {e}", []
    if bad is not None:
        return f"zip の中の {bad} が壊れている", []
    listing = []
    for top, folders in FOLDERS.items():
        if any(n.startswith(top) for n in names):
            for folder in folders:
                inside = [n for n in names if n.startswith(folder) and "/_rels/" not in n]
                listing.append((folder, inside))
    return None, listing


def run_decode(src, out):
    """出す行とエラーを返す。"""
    try:
        with open(src, encoding="utf-8") as f:
            data = decode(f.read())
    except OSError as e:
        return [], [f"{src}: 読めない: {e.strerror or e}"]
    except UnicodeDecodeError as e:
        return [], [f"{src}: UTF-8 として読めない: {e}"]
    except ValueError as e:
        return [], [f"{src}: {e}"]
    try:
        with open(out, "wb") as f:
            f.write(data)
    except OSError as e:
        return [], [f"{out}: 書けない: {e.strerror or e}"]
    lines = [f"保存した: {out}（{len(data)} バイト）"]
    error = check_shape(out, data)
    if error:
        return lines, [f"{out}: {error}"]
    if not zipfile.is_zipfile(out):
        return lines, []
    error, listing = inspect_zip(out)
    if error:
        return lines, [f"{out}: {error}"]
    lines.append("zip は壊れていない")
    for folder, names in listing:
        lines.append(f"{folder}: {len(names)} 件" if names else f"{folder}: なし")
        lines.extend(f"  {n}" for n in names)
    return lines, []


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="drivefile.py", description="Google Drive MCP の書き出し（base64）をデコードして、ファイルに保存する"
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True
    p = sub.add_parser("decode", help="base64 をデコードして保存し、zip なら壊れていないかと中身を確かめる")
    p.add_argument("src", metavar="入力")
    p.add_argument("out", metavar="出力")
    args = parser.parse_args(argv)

    lines, errors = run_decode(args.src, args.out)
    for line in lines + errors:
        print(line)
    return 1 if errors else 0


if __name__ == "__main__":
    # 日本語を出すので、標準出力の文字コードが UTF-8 でない環境でも UTF-8 で書く。モジュールから main を呼ぶ側の出力は変えない
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(main())
