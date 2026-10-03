"""drivefile.py のデコードと zip の確かめを確かめる。"""

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

    def test_errors(self):
        cases = {
            "JSON として読めない": '{"content": ',
            "JSON に文字列の content が無い": '{"id": "abc"}',
            "base64 が空": " \n",
            "base64 として読めない": "not base64!",
        }
        for want, text in cases.items():
            with self.subTest(want):
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

    def test_lists_the_folders_of_a_sheet(self):
        names = ["xl/workbook.xml", "xl/media/image1.png", "xl/drawings/drawing1.xml", "xl/drawings/_rels/drawing1.xml.rels"]
        self.write_tool_result(make_zip(names), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        code, lines = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(
            lines[1:],
            ["zip は壊れていない", "xl/media/: 1 件", "  xl/media/image1.png", "xl/drawings/: 1 件", "  xl/drawings/drawing1.xml"],
        )

    def test_says_none_for_missing_folders(self):
        self.write_tool_result(make_zip(["ppt/presentation.xml"]))
        code, lines = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(lines[1:], ["zip は壊れていない", "ppt/media/: なし", "ppt/notesSlides/: なし"])

    def test_lists_nothing_for_a_zip_that_is_not_office(self):
        self.write_tool_result(make_zip(["readme.txt"]))
        code, lines = self.decode()
        self.assertEqual(code, 0)
        self.assertEqual(lines[1:], ["zip は壊れていない"])

    def test_broken_zip(self):
        data = make_zip(["word/document.xml"], b"A" * 100)
        self.write_tool_result(data.replace(b"A" * 100, b"B" * 100))
        code, lines = self.decode()
        self.assertEqual(code, 1)
        self.assertEqual(lines, [f"保存した: {self.out}（{len(data)} バイト）", f"{self.out}: zip の中の word/document.xml が壊れている"])

    def test_takes_a_command_an_input_and_an_output(self):
        for argv in ([], ["decode", str(self.src)], ["decode", str(self.src), str(self.out), "extra"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    drivefile.main(argv)
                self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
