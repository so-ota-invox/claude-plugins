"""drivefile.py のデコードと、保存したファイルの検査をテストする。"""

import base64
import contextlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import drivefile


def make_zip(names, data=b"x"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in names:
            z.writestr(name, data)
    return buf.getvalue()


class DecodeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.src = self.dir / "result.txt"
        self.out = self.dir / "file.bin"

    def write_src(self, text):
        self.src.write_text(text, encoding="utf-8")

    def write_tool_result(self, data, mime="application/pdf"):
        content = base64.b64encode(data).decode("ascii")
        self.write_src(json.dumps({"content": content, "id": "abc", "mimeType": mime, "title": "見積"}))

    def run_main(self, *argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = drivefile.main(list(argv))
        return code, stdout.getvalue().splitlines()

    def decode(self):
        return self.run_main("decode", str(self.src), str(self.out))

    def test_decodes_content_of_a_tool_result(self):
        self.write_tool_result(b"%PDF-1.4 body")
        code, lines = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(self.out.read_bytes(), b"%PDF-1.4 body")
        self.assertEqual(lines, [f"保存した: {self.out}（13 バイト）"])

    def test_decodes_plain_base64_with_line_breaks(self):
        b64 = base64.b64encode(b"0123456789" * 10).decode("ascii")
        self.write_src("\n".join(b64[i : i + 40] for i in range(0, len(b64), 40)) + "\n")
        code, _ = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(self.out.read_bytes(), b"0123456789" * 10)

    def test_decodes_a_tool_result_after_blank_lines(self):
        content = base64.b64encode(b"%PDF").decode("ascii")
        self.write_src("\n  " + json.dumps({"content": content}))
        code, _ = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(self.out.read_bytes(), b"%PDF")

    def test_errors(self):
        cases = {
            "JSON として読めない": '{"content": ',
            "JSON に文字列の content が無い": '{"id": "abc"}',
            "base64 が空": " \n",
            "base64 として読めない": "not base64!",
        }
        for want, text in cases.items():
            with self.subTest(want=want):
                self.write_src(text)
                code, lines = self.decode()
                self.assertEqual(code, 1)
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith(f"{self.src}: {want}"), lines[0])
                self.assertFalse(self.out.exists())

    def test_unreadable_input(self):
        code, lines = self.decode()
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith(f"{self.src}: 読めない: "), lines[0])

    def test_unwritable_output(self):
        self.write_tool_result(b"%PDF")
        self.out = self.dir / "missing" / "file.bin"
        code, lines = self.decode()
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith(f"{self.out}: 書けない: "), lines[0])

    def test_intact_zip(self):
        self.write_tool_result(make_zip(["xl/workbook.xml", "xl/media/image1.png"]))
        code, lines = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(lines[1:], ["zip は壊れていない"])

    def test_broken_zip(self):
        data = make_zip(["word/document.xml"], b"A" * 100)
        self.write_tool_result(data.replace(b"A" * 100, b"B" * 100))
        code, lines = self.decode()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [f"保存した: {self.out}（{len(data)} バイト）", f"{self.out}: zip の中の word/document.xml が壊れている"])

    def test_accepts_a_shape_that_matches_the_suffix(self):
        cases = {
            "file.pdf": b"%PDF-1.4 body\n%%EOF\n",
            "file.docx": make_zip(["word/document.xml"]),
            "file.PDF": b"%PDF-1.4 body\n%%EOF",
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                self.out = self.dir / name
                self.write_tool_result(data)
                code, lines = self.decode()
                self.assertEqual(code, 0, lines)
                self.assertEqual(self.out.read_bytes(), data)

    def test_rejects_a_shape_that_does_not_match_the_suffix(self):
        cases = {
            "head.pdf": (b"body\n%%EOF\n", "PDF の先頭に %PDF- が無い"),
            "tail.pdf": (b"%PDF-1.4 body", "PDF の末尾に %%EOF が無い"),
            "early.pdf": (b"%PDF-1.4\n%%EOF\n" + b"x" * 1024, "PDF の末尾に %%EOF が無い"),
            "cut.xlsx": (make_zip(["xl/workbook.xml"])[:-10], "Office 形式なのに zip でない"),
            "text.pptx": (b"not a zip", "Office 形式なのに zip でない"),
        }
        for name, (data, error) in cases.items():
            with self.subTest(name=name):
                self.out = self.dir / name
                self.write_tool_result(data)
                code, lines = self.decode()
                self.assertEqual(code, 1)
                self.assertEqual(lines, [f"保存した: {self.out}（{len(data)} バイト）", f"{self.out}: {error}"])

    def test_takes_a_command_an_input_and_an_output(self):
        for argv in ([], ["decode", str(self.src)], ["decode", str(self.src), str(self.out), "extra"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    drivefile.main(argv)
                self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
