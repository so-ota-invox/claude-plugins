"""specdoc.py の照合・変換・hash を確かめる。"""

import contextlib
import errno
import io
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import specdoc

SPEC = "specs/12-invoice"
REQ = f"{SPEC}/requirements.md"
DESIGN = f"{SPEC}/design.md"
PLAN = f"{SPEC}/plan.md"

REQ_BODIES = {
    "機能概要": "請求書をまとめて発行する。\n\n- R-001: 選んだ請求書をまとめて発行できる\n- R-002: 発行済みの請求書は選べない",
    "非機能要件": "- R-003: 1,000 件を 60 秒以内に発行する",
}
TABLES = """| `invoices` | 意味 | 型・長さ | 必須 | 制約 | 差分 |
| --- | --- | --- | --- | --- | --- |
| `status` | 状態 | varchar(20) | 必須 | draft・issued | 既存 |
| `issued_at` | 発行日時 | datetime | 任意 | JST | 追加 |

| `customers` | 意味 | 型・長さ | 必須 | 制約 | 差分 |
| --- | --- | --- | --- | --- | --- |
| `name` | 顧客名 | varchar(100) | 必須 | なし | 既存 |"""
DESIGN_BODIES = {
    "サブ機能分割": "分割しない。理由: まとまりが 1 つしかない",
    "画面設計": "- 一覧画面: [モック](mocks/list.html)",
    "読み書きするデータ": "- 一括発行\n  - 書く: `invoices.status`、`invoices.issued_at`\n  - 読む: `customers.name`",
    "ER 図": "```mermaid\nerDiagram\n  customers ||--o{ invoices : has\n```",
    "テーブル定義": TABLES,
    "受け入れ基準": (
        "- AC-001: 選んだ請求書が 60 秒以内にすべて発行済みになる\n  - 要件: R-001、R-003\n"
        "- AC-002: 発行済みの請求書には選択欄が出ない\n  - 要件: R-002"
    ),
}
PLAN_BODIES = {
    "シナリオ": (
        "- S-001: まとめて発行する\n  - 受け入れ基準: AC-001\n  - 種別: 正常\n  - 層: 結合\n"
        "  - 前提: 未発行の請求書が 2 件ある\n  - 操作: 2 件を選んで発行する\n  - 期待: 2 件が発行済みになる\n"
        "- S-002: 発行済みは選べない\n  - 受け入れ基準: AC-002\n  - 種別: 異常\n  - 層: 単体\n"
        "  - 前提: 発行済みの請求書がある\n  - 操作: 一覧を開く\n  - 期待: 選択欄が出ない"
    ),
}
SPLIT = (
    "- billing: 請求書の発行\n  - 要件: R-001、R-003\n  - 依存: なし\n"
    "- listing: 一覧の表示\n  - 要件: R-002\n  - 依存: billing"
)


def meta(state="approved", parent=None, upstream=None):
    lines = ["- 著者: 山田", f"- 状態: {state}"]
    if state == "approved":
        lines.append("- 承認者: 佐藤")
    lines.append("- 凡例: " + specdoc.LEGEND)
    if parent:
        lines.append(f"- 親: {parent}")
    if upstream is not None:
        lines.append("- 上流:")
        lines.extend(f"  - {u}" for u in upstream)
    return lines


def build_doc(kind, meta_lines, bodies=None, child=False):
    """型の見出しをすべて並べた文書を作る。本文を渡さない見出しは「なし」にする。"""
    bodies = bodies or {}
    tpl = specdoc.Template(kind)
    lines = [f"# {tpl.title}: 請求書の一括発行", ""] + list(meta_lines) + [""]
    heads = tpl.expected(child)
    for n, (level, text) in enumerate(heads):
        lines += ["#" * level + " " + text, ""]
        has_sub = n + 1 < len(heads) and heads[n + 1][0] > level
        body = bodies.get(text)
        if body is None and not has_sub:
            body = "なし"
        if body is not None:
            lines += [body, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def with_body(bodies, **changes):
    out = dict(bodies)
    out.update(changes)
    return out


def question(stage):
    return f"- Q-001: 締め日は何日か\n  - 確認先: 経理\n  - 期限: 2026-10-15\n  - 解決する工程: {stage}"


def lock(test, path):
    """path の権限をすべて外す。外しても読める環境（root、WSL の /mnt/c など）では、確かめようがないのでテストを飛ばす。"""
    mode = path.stat().st_mode
    path.chmod(0)
    test.addCleanup(path.chmod, mode)
    try:
        if path.is_dir():
            os.listdir(path)
        else:
            path.read_bytes()
    except PermissionError:
        return
    test.skipTest(f"権限を外しても {path.name} を読める環境")


class Repo:
    """一時ディレクトリをリポジトリルートに見立てる。"""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.test = test
        self.root = Path(tmp.name)

    def path(self, rel):
        return self.root / rel

    def write(self, rel, text):
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        return p

    def read(self, rel):
        return self.path(rel).read_bytes().decode("utf-8")

    def replace(self, rel, old, new):
        text = self.read(rel)
        if old not in text:
            self.test.fail(f"{old!r} が {rel} に無い")
        self.write(rel, text.replace(old, new, 1))

    def ref(self, rel):
        return f"{rel}@{specdoc.blob_hash(self.path(rel).read_bytes())[:specdoc.HASH_LEN]}"

    def docs(self):
        """specs/ の下の型の文書のパスを、名前の順に返す。specdoc.py はディレクトリを受け付けないので、渡すファイルをここで並べる。"""
        return sorted(p.relative_to(self.root).as_posix() for p in self.path("specs").rglob("*.md") if p.name in specdoc.DOC_FILES)

    def check(self, *rels, gate=None, approved=False):
        paths = [str(self.path(r)) for r in rels or self.docs()]
        _, errors = specdoc.run_check(paths, gate, approved)
        return [(p.relative_to(self.root).as_posix(), line, msg) for p, line, msg in errors]

    def messages(self, *rels, **kwargs):
        return [msg for _, _, msg in self.check(*rels, **kwargs)]

    def case_error(self, rel):
        """実際の名前と大文字・小文字だけが違うパスのエラー。区別しないファイルシステムでは、そのパスでも開ける。"""
        return "パスの大文字・小文字が実際の名前と違う" if self.path(rel).is_file() else "ファイルが無い"

    def write_requirements(self, bodies=REQ_BODIES, state="approved"):
        self.write(REQ, build_doc("requirements", meta(state), bodies))

    def write_design(self, bodies=DESIGN_BODIES, state="approved"):
        self.write(f"{SPEC}/mocks/list.html", "<!DOCTYPE html>\n")
        self.write(DESIGN, build_doc("design", meta(state, upstream=[self.ref(REQ)]), bodies))

    def write_plan(self, bodies=PLAN_BODIES, state="draft"):
        self.write(PLAN, build_doc("plan", meta(state, upstream=[self.ref(DESIGN)]), bodies))

    def write_valid(self):
        self.write_requirements()
        self.write_design()
        self.write_plan()


class TemplateTest(unittest.TestCase):
    def test_formats_follow_the_markdown_subset(self):
        for name in ("common", "requirements", "design", "plan"):
            with self.subTest(name=name):
                text = (specdoc.FORMATS_DIR / f"{name}.md").read_bytes().decode("utf-8")
                self.assertEqual(specdoc.Parser(text).errors, [])

    def test_common_holds_the_legend_line(self):
        text = (specdoc.FORMATS_DIR / "common.md").read_bytes().decode("utf-8")
        self.assertIn("- 凡例: " + specdoc.LEGEND + "\n", text)

    def test_heading_texts_are_unique_and_parent_only_names_exist(self):
        for kind in ("requirements", "design", "plan"):
            with self.subTest(kind=kind):
                tpl = specdoc.Template(kind)
                texts = [text for _, text in tpl.headings]
                self.assertEqual(len(texts), len(set(texts)))
                self.assertLessEqual(tpl.parent_only, set(texts))
        self.assertEqual(
            specdoc.Template("design").parent_only, {"サブ機能分割", "データ設計", "インターフェース設計", "主要な用語"}
        )

    def test_child_design_drops_parent_only_headings_and_their_children(self):
        texts = [text for _, text in specdoc.Template("design").expected(True)]
        for dropped in ("サブ機能分割", "データ設計", "テーブル定義", "公開 API", "主要な用語"):
            self.assertNotIn(dropped, texts)
        self.assertIn("影響範囲", texts)
        self.assertIn("受け入れ基準", texts)

    def test_research_scope_closes_design_and_plan(self):
        for kind in ("design", "plan"):
            with self.subTest(kind=kind):
                self.assertEqual(specdoc.Template(kind).headings[-1], (2, "調査範囲"))
        self.assertNotIn("調査範囲", [text for _, text in specdoc.Template("requirements").headings])


class HelperTest(unittest.TestCase):
    def test_blob_hash_matches_git(self):
        self.assertEqual(specdoc.blob_hash(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(specdoc.blob_hash(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_blob_hash_ignores_crlf_checkout(self):
        self.assertEqual(specdoc.blob_hash(b"a\r\nb\r\n"), specdoc.blob_hash(b"a\nb\n"))

    def test_repo_relative_path_form(self):
        # html が上流と親をリンクにするときの判定
        for rel in ("/specs/x.md", "specs//x.md", "specs/./x.md", "specs/../x.md", "specs\\x.md", "specs/x/", ""):
            with self.subTest(rel=rel):
                self.assertTrue(specdoc.bad_repo_path(rel))
        self.assertFalse(specdoc.bad_repo_path(REQ))

    def test_mermaid_integrity_is_sha384(self):
        self.assertRegex(specdoc.MERMAID_INTEGRITY, r"^sha384-[A-Za-z0-9+/]{64}$")

    def test_parser_reports_the_same_error_once(self):
        parser = specdoc.Parser("")
        before = list(parser.errors)
        for line, msg in [(3, "x"), (1, "y"), (3, "x")] + before:
            parser.error(line, msg)
        self.assertEqual(parser.errors, before + [(3, "x"), (1, "y")])

    def test_format_errors_orders_by_file_then_line_without_duplicates(self):
        a, b = Path("a.md"), Path("b.md")
        errors = [(b, 2, "x"), (a, 1, "y"), (b, 1, "z"), (b, 2, "x")]
        self.assertEqual(specdoc.format_errors(errors), ["b.md:1: z", "b.md:2: x", "a.md:1: y"])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write_valid()

    def write_question(self, rel, stage, state="draft"):
        """rel の要確認に、解決する工程が stage の Q-001 を置く。"""
        q = question(stage)
        if rel == REQ:
            self.repo.write_requirements(with_body(REQ_BODIES, 要確認=q), state)
        elif rel == DESIGN:
            self.repo.write_design(with_body(DESIGN_BODIES, 要確認=q), state)
        else:
            self.repo.write_plan(with_body(PLAN_BODIES, 要確認=q), state)

    def set_ac_reqs(self, value):
        acs = DESIGN_BODIES["受け入れ基準"].replace("  - 要件: R-001、R-003", f"  - 要件: {value}")
        self.repo.write_design(with_body(DESIGN_BODIES, 受け入れ基準=acs))

    def test_valid_set_passes(self):
        self.assertEqual(self.repo.check(), [])

    def test_syntax_errors(self):
        cases = [
            ("* x", "箇条書きは - で書く"),
            ("1. x", "番号付きの箇条書きは使えない（- で書く）"),
            ("> x", "引用は使えない"),
            ("---", "区切り線は使えない"),
            ("x\n===", "見出しは # で書く"),
            ("#### x", "見出しは ### まで"),
            ("a *b* c", "コードの外で * を使わない（太字は ** で囲む。記号として書くならコードで囲む）"),
            ("snake_case は可、_x は不可", "コードの外で語の端に _ を置かない（コードで囲む）"),
            ("~~x~~", "打ち消し線は使えない"),
            ("a\\b", "バックスラッシュは使えない（コードで囲む）"),
            ("&amp;", "文字参照は使えない。文字をそのまま書く"),
            ("a<br>b", "HTML は使えない（< を記号として書くならコードで囲む）"),
            ("![図](a.png)", "画像は使えない"),
            ("[文字](a b)", "リンクは `[文字](先)` の形で書く。先に空白と括弧を入れない"),
            ("`x", "` の対応が取れていない"),
            ("```\nx\n```", "コードブロックに言語名を書く"),
            ("```text\nx", "コードブロックが閉じていない"),
            ("| a |\n| :-: |", "表の 2 行目は、見出し行と同じ数の `| --- |` の区切りにする"),
            ("| a |\n| --- |\n| b | c |", "表の列の数が見出し行と違う（セルの中に | を書かない）"),
            ("- a\n    - b", "箇条の入れ子は 2 段まで。字下げは空白 2 つにする"),
            ("-", "空の箇条"),
            ("- # x", "箇条の先頭に書式の記号を置かない"),
            ("段落\n- a", "前の行との間に空行を入れる"),
            (" x", "行頭に空白を置かない"),
            ("a\tb", "タブを使わない"),
            ("# x", "# の見出しは 1 行目に 1 つだけ"),
            ("### x #", "見出しの末尾に # を書かない"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=body))
                self.assertIn(expected, self.repo.messages(REQ))

    def test_syntax_errors_hide_other_errors(self):
        text = build_doc("requirements", meta(), with_body(REQ_BODIES, 明示的除外事項="* x"))
        self.repo.write(REQ, text.replace("## リリース日\n\nなし\n\n", ""))
        self.assertEqual(self.repo.messages(REQ), ["箇条書きは - で書く"])

    def test_line_endings_and_bom(self):
        text = self.repo.read(REQ)
        self.repo.write(REQ, text.replace("\n", "\r\n"))
        self.assertEqual(self.repo.messages(REQ), ["改行は LF にする"])
        self.repo.write(REQ, "\ufeff" + text)
        self.assertEqual(self.repo.messages(REQ), ["BOM を付けない"])

    def test_lone_cr_is_reported_on_its_own_line(self):
        cr = "改行は LF にする（CR だけで改行しない）"
        self.repo.replace(REQ, "## 仮定\n\nなし", "## 仮定\n\nなし\rなし")
        lines = self.repo.read(REQ).split("\n")
        at = lines.index("なし\rなし") + 1
        self.assertEqual(self.repo.check(REQ), [(REQ, at, cr)])
        # CR より後ろの行の番号も、grep -n や git など LF で数える行と合う
        self.repo.replace(REQ, "## 要確認\n\nなし", "## 要確認\n\n* x")
        lines = self.repo.read(REQ).split("\n")
        self.assertEqual(
            sorted(self.repo.check(REQ)),
            sorted([(REQ, at, cr), (REQ, lines.index("* x") + 1, "箇条書きは - で書く")]),
        )

    def test_lone_cr_at_the_end_and_with_crlf(self):
        cr = "改行は LF にする（CR だけで改行しない）"
        text = self.repo.read(REQ)
        # LF の無い CR で終わるときは、最後の行の 1 件だけ
        body = text.rstrip("\n")
        self.repo.write(REQ, body + "\r")
        self.assertEqual(self.repo.check(REQ), [(REQ, len(body.split("\n")), cr)])
        # CRLF と CR だけの改行が混ざるときは、両方を出す
        mixed = text.replace("## 仮定\n\nなし", "## 仮定\n\nなし\rなし")
        at = mixed.split("\n").index("なし\rなし") + 1
        self.repo.write(REQ, mixed.replace("\n", "\r\n"))
        self.assertEqual(sorted(self.repo.check(REQ)), sorted([(REQ, 1, "改行は LF にする"), (REQ, at, cr)]))

    def test_title_needs_subject(self):
        self.repo.replace(REQ, "# 要件定義書: 請求書の一括発行", "# 要件定義書")
        self.assertEqual(self.repo.check(REQ), [(REQ, 1, "1 行目は `# 要件定義書: 件名` の形で書く")])

    def test_missing_and_extra_headings(self):
        self.repo.replace(REQ, "## リリース日\n\nなし\n\n", "")
        self.repo.replace(REQ, "## 仮定\n", "## 補足\n\nなし\n\n## 仮定\n")
        messages = self.repo.messages(REQ)
        self.assertIn("見出しが無い: ## リリース日", messages)
        self.assertIn("型に無い見出し: ## 補足", messages)

    def test_empty_section_must_say_none(self):
        self.repo.replace(REQ, "## リリース日\n\nなし\n\n", "## リリース日\n\n")
        self.assertEqual(self.repo.messages(REQ), ["本文が空: ## リリース日。書く内容が無ければ「なし」と書く"])

    def test_nothing_between_meta_and_first_section(self):
        self.repo.replace(REQ, "\n## 背景・目的", "\n補足\n\n## 背景・目的")
        self.assertEqual(self.repo.messages(REQ), ["管理情報と最初の ## の間には何も書かない"])

    def test_meta_rules(self):
        cases = [
            ("- 著者: 山田\n- 状態: approved", "- 状態: approved\n- 著者: 山田", "管理情報の順序が違う（著者・状態・承認者・凡例・親・上流・元の文書 の順）"),
            ("- 承認者: 佐藤\n", "", "approved のときは承認者を書く"),
            ("- 状態: approved", "- 状態: wip", "状態は draft・approved のどれか"),
            ("（例: AC-billing-001）", "", "凡例の文言が違う。common.md の文言をそのまま書く"),
            ("- 承認者: 佐藤\n", "- 承認者: 佐藤\n- 担当: 鈴木\n", "管理情報に使えない項目: 担当（使えるのは 著者・状態・承認者・凡例・親・上流・元の文書）"),
            ("- 著者: 山田\n", "", "管理情報の項目が無い: 著者"),
            ("- 凡例:", "- 親: specs/12-invoice/requirements.md\n- 凡例:", "親は子の文書だけに書く"),
        ]
        original = self.repo.read(REQ)
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.repo.write(REQ, original)
                self.repo.replace(REQ, old, new)
                self.assertIn(expected, self.repo.messages(REQ))

    def test_draft_must_not_name_an_approver(self):
        self.repo.replace(REQ, "- 状態: approved", "- 状態: draft")
        self.assertEqual(self.repo.messages(REQ), ["承認者は approved のときだけ書く"])

    def test_wrong_or_missing_state_does_not_add_an_approver_error(self):
        # 状態の誤りが 1 つなら、承認者のエラーを重ねず 1 件にする
        cases = [
            ("- 状態: approved", "- 状態: aproved", "状態は draft・approved のどれか"),
            ("- 状態: approved\n", "", "管理情報の項目が無い: 状態"),
        ]
        original = self.repo.read(REQ)
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                self.repo.write(REQ, original)
                self.repo.replace(REQ, old, new)
                self.assertEqual(self.repo.messages(REQ), [expected])

    def test_requirements_have_no_upstream(self):
        self.repo.write(REQ, build_doc("requirements", meta(upstream=["specs/x.md@0123456"]), REQ_BODIES))
        self.assertIn("要件定義書には上流を書かない", self.repo.messages(REQ))

    def test_design_needs_upstream(self):
        self.repo.write(DESIGN, build_doc("design", meta(), DESIGN_BODIES))
        self.assertEqual(self.repo.check(DESIGN), [(DESIGN, 3, "管理情報の項目が無い: 上流")])

    def test_meta_must_follow_title(self):
        self.repo.write(REQ, build_doc("requirements", [], REQ_BODIES))
        self.assertEqual(self.repo.check(REQ), [(REQ, 4, "見出しの直後に管理情報（`- 著者: …`）を書く")])

    def test_duplicate_id(self):
        bodies = with_body(REQ_BODIES, 非機能要件="- R-003: 1,000 件を 60 秒以内に発行する\n- R-002: 重ねた番号")
        self.repo.write_requirements(bodies)
        first = self.repo.read(REQ).split("\n").index("- R-002: 発行済みの請求書は選べない") + 1
        self.assertEqual(self.repo.messages(REQ), [f"番号が重なっている: R-002（{first} 行目）"])

    def test_definition_form_in_definition_section(self):
        bodies = with_body(DESIGN_BODIES, 受け入れ基準="- 請求書を発行できる")
        self.repo.write_design(bodies)
        self.assertIn("一番上の箇条は `AC-001: 本文` の形で書く", self.repo.messages(DESIGN))

    def test_id_bullet_outside_definition_section_is_a_reference(self):
        self.repo.write_design(with_body(DESIGN_BODIES, 設計判断="- R-003: 60 秒を守るため非同期で発行する"))
        self.assertEqual(self.repo.check(DESIGN), [])
        self.repo.write_design(with_body(DESIGN_BODIES, 設計判断="- R-009 に合わせて同期で発行する"))
        self.assertEqual(self.repo.messages(DESIGN), ["定義の無い番号: R-009"])

    def test_ids_in_code_are_not_references(self):
        self.repo.write_design(with_body(DESIGN_BODIES, 設計判断="`R-009` は番号ではない"))
        self.assertEqual(self.repo.check(DESIGN), [])

    def test_references_do_not_reach_downstream(self):
        expected = ["下流か別の子の文書の番号は参照しない: AC-001", "下流か別の子の文書の番号は参照しない: S-001"]
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="AC-001 と S-001 は扱わない"))
        self.assertEqual(self.repo.messages(REQ), expected)
        self.repo.path(DESIGN).unlink()
        self.repo.path(PLAN).unlink()
        self.assertEqual(self.repo.messages(REQ), expected)
        self.repo.write_design(with_body(DESIGN_BODIES, 設計判断="S-001 で確かめる"))
        self.assertEqual(self.repo.messages(DESIGN), ["下流か別の子の文書の番号は参照しない: S-001"])

    def test_questions_are_not_referenced_from_downstream(self):
        # Q は文書ごとに 001 から数えるので、上流の文書にだけある Q-001 は参照できない
        self.write_question(REQ, "design", "approved")
        self.repo.write_design(with_body(DESIGN_BODIES, 設計判断="- Q-001 の回答で締め日を決める"))
        self.assertEqual(self.repo.messages(DESIGN), ["定義の無い番号: Q-001"])

    def test_spec_dir_name(self):
        expected = "specs/ の下のディレクトリ名は <id>-<slug> にする（英数字をハイフンでつなぎ、最後の語は英小文字・数字）"
        bad = (
            "specs/invoice/requirements.md",
            "specs/12 invoice/requirements.md",
            "specs/12_invoice/requirements.md",
            "specs/12-Invoice/requirements.md",
        )
        text = self.repo.read(REQ)
        for rel in bad:
            with self.subTest(rel=rel):
                self.repo.write(rel, text)
                self.assertEqual(self.repo.messages(rel), [expected])
        # チケット番号の <id> は大文字を含んでよい
        rel = "specs/PROJ-12-invoice/requirements.md"
        self.repo.write(rel, text)
        self.assertEqual(self.repo.messages(rel), [])

    def test_requirement_without_ac(self):
        acs = "- AC-001: 選んだ請求書が 60 秒以内にすべて発行済みになる\n  - 要件: R-001、R-003"
        self.repo.write_design(with_body(DESIGN_BODIES, 受け入れ基準=acs))
        self.assertEqual(self.repo.messages(DESIGN), ["受ける AC の無い R: R-002"])

    def test_ac_may_receive_no_requirement(self):
        acs = DESIGN_BODIES["受け入れ基準"] + "\n- AC-003: 既存の単票発行は変わらない\n  - 要件: なし"
        self.repo.write_design(with_body(DESIGN_BODIES, 受け入れ基準=acs))
        self.assertEqual(self.repo.check(DESIGN), [])

    def test_ac_without_scenario(self):
        scenarios = PLAN_BODIES["シナリオ"].split("\n- S-002")[0]
        self.repo.write_plan(with_body(PLAN_BODIES, シナリオ=scenarios))
        self.assertEqual(self.repo.messages(PLAN), ["受ける S の無い AC: AC-002"])

    def test_plan_without_design(self):
        self.repo.path(DESIGN).unlink()
        self.assertIn(f"設計書が無い: {DESIGN}", self.repo.messages(PLAN))

    def test_scenario_fields(self):
        scenarios = (
            PLAN_BODIES["シナリオ"]
            .replace("  - 期待: 2 件が発行済みになる\n", "  - 備考: 手で確かめる\n")
            .replace("種別: 異常", "種別: 普通")
        )
        self.repo.write_plan(with_body(PLAN_BODIES, シナリオ=scenarios))
        messages = self.repo.messages(PLAN)
        self.assertIn("S-001 の下に書けるのは 受け入れ基準・種別・層・前提・操作・期待", messages)
        self.assertIn("S-001 の下の項目が無い: 期待", messages)
        self.assertIn("種別は 正常・異常・境界 のどれか", messages)

    def test_scenario_field_repeated_or_empty(self):
        cases = [
            ("  - 期待: 2 件が発行済みになる\n  - 期待: 一覧に出ない\n", "S-001 の下の項目が重なっている: 期待"),
            ("  - 期待:\n", "S-001 の下の項目が空: 期待"),
        ]
        for new, expected in cases:
            with self.subTest(expected=expected):
                scenarios = PLAN_BODIES["シナリオ"].replace("  - 期待: 2 件が発行済みになる\n", new)
                self.repo.write_plan(with_body(PLAN_BODIES, シナリオ=scenarios))
                self.assertEqual(self.repo.messages(PLAN), [expected])

    def test_question_fields(self):
        q = "- Q-001: 取り消せる期限はあるか\n  - 推奨: 発行から 30 日\n  - 確認先: 経理\n  - 解決する工程: 実装"
        self.repo.write_requirements(with_body(REQ_BODIES, 要確認=q))
        messages = self.repo.messages(REQ)
        self.assertIn("Q-001 の下の項目が無い: 期限", messages)
        self.assertIn("解決する工程は requirements・design・plan・release のどれか", messages)

    def test_question_stage_must_not_precede_the_document(self):
        cases = [
            (DESIGN, "requirements", "design.md の解決する工程は design・plan・release のどれか"),
            (PLAN, "requirements", "plan.md の解決する工程は plan・release のどれか"),
            (PLAN, "design", "plan.md の解決する工程は plan・release のどれか"),
        ]
        for rel, stage, expected in cases:
            with self.subTest(rel=rel, stage=stage):
                self.repo.write_valid()
                self.write_question(rel, stage)
                self.assertEqual(self.repo.messages(rel), [expected])

    def test_upstream_hash_mismatch(self):
        self.repo.replace(REQ, "## 仮定\n\nなし", "## 仮定\n\n- 税込で計算する")
        current = specdoc.blob_hash(self.repo.path(REQ).read_bytes())[:specdoc.HASH_LEN]
        self.assertEqual(
            self.repo.messages(DESIGN),
            [f"上流の hash が合わない: {REQ}（今は {current}）。下流に影響を反映してから書き換える"],
        )

    def test_upstream_must_be_approved(self):
        self.repo.write_requirements(state="draft")
        self.repo.write_design()
        self.assertEqual(self.repo.messages(DESIGN), [f"上流が approved でない: {REQ}"])

    def test_required_upstream(self):
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[]), DESIGN_BODIES))
        messages = self.repo.messages(DESIGN)
        self.assertIn("上流が空", messages)
        self.assertIn(f"上流に書いていない文書: {REQ}", messages)

    def test_upstream_paths(self):
        # 上流に書けるのは同じ機能の決まった型の文書だけ。在るファイルで hash が合っていても、ほかのパスは誤りにする
        guide = f"{SPEC}/資料/ガイド.md"
        other = "specs/13-other/requirements.md"
        self.repo.write(guide, "x\n")
        self.repo.write(other, self.repo.read(REQ))
        wrong = [f"{SPEC}/Requirements.md", f"../{REQ}", f"{SPEC}/{'a' * 300}.md"]
        ups = [self.repo.ref(REQ), self.repo.ref(guide), self.repo.ref(other)] + [f"{rel}@0123456789ab" for rel in wrong]
        self.repo.write(DESIGN, build_doc("design", meta(upstream=ups + [self.repo.ref(REQ)]), DESIGN_BODIES))
        self.assertEqual(
            self.repo.messages(DESIGN),
            [f"上流に書けるのは {REQ} だけ: {rel}" for rel in [guide, other] + wrong] + [f"上流が重なっている: {REQ}"],
        )

    def test_missing_upstream_file(self):
        self.repo.path(REQ).unlink()
        messages = self.repo.messages(DESIGN)
        self.assertIn(f"上流のファイルが無い: {REQ}", messages)
        self.assertIn(f"要件定義書が無い: {REQ}", messages)

    def test_upstream_name_case_must_match(self):
        # 大文字・小文字を区別しない macOS でも、Linux と同じく名前の違う上流は無いとみなす
        text = self.repo.read(REQ)
        self.repo.path(REQ).unlink()
        self.repo.write(f"{SPEC}/Requirements.md", text)
        messages = self.repo.messages(DESIGN)
        self.assertIn(f"上流のファイルが無い: {REQ}", messages)
        self.assertIn(f"要件定義書が無い: {REQ}", messages)

    def test_upstream_hash_ignores_crlf_checkout(self):
        # Windows の git が CRLF で取り出しても、上流の hash は合う
        self.repo.write(REQ, self.repo.read(REQ).replace("\n", "\r\n"))
        self.assertEqual(self.repo.check(DESIGN), [])

    def test_link_must_be_nfc(self):
        self.repo.write(f"{SPEC}/mocks/ガイド.html", "<!DOCTYPE html>\n")
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計="- [ガイド](mocks/ガイド.html)"))
        self.assertEqual(self.repo.check(DESIGN), [])
        nfd = unicodedata.normalize("NFD", "mocks/ガイド.html")
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計=f"- [ガイド]({nfd})"))
        self.assertEqual(self.repo.messages(DESIGN), [f"リンク先の文字を NFC にする: {nfd}"])

    def test_names_must_match_case(self):
        # 大文字・小文字を区別しない macOS でも、区別する Linux と同じく見つからない
        for dest in ("mocks/List.html", "Mocks/list.html"):
            with self.subTest(dest=dest):
                self.repo.write_design(with_body(DESIGN_BODIES, 画面設計=f"- 一覧画面: [モック]({dest})"))
                self.assertEqual(self.repo.messages(DESIGN), [f"リンク先が無い: {dest}"])

    def test_document_path_case_must_match(self):
        self.repo.write("specs/PROJ-12-invoice/requirements.md", self.repo.read(REQ))
        typed = "specs/proj-12-invoice/requirements.md"
        self.assertEqual(self.repo.messages(typed), [self.repo.case_error(typed)])

    def test_document_name_case_must_match(self):
        # ファイルの名前だけが違うときも、トレースバックにせず 1 行のエラーにする
        self.repo.write("specs/13-other/Design.md", self.repo.read(DESIGN))
        typed = "specs/13-other/design.md"
        self.assertEqual(self.repo.messages(typed), [self.repo.case_error(typed)])

    def test_path_that_cannot_be_examined(self):
        # 置き場を 1 段ずつ照らせないときは、トレースバックにせず 1 行のエラーにする。
        # 実際には、途中のディレクトリに実行の権限だけがあり、中のファイルは開けるが一覧を読めないときに起こる。
        # root は権限に関わらず一覧を読めるので、権限を外す代わりに例外を差し替え、root で実行しても確かめる
        with mock.patch.object(specdoc, "exact_kind", side_effect=PermissionError(errno.EACCES, "Permission denied")):
            self.assertEqual(self.repo.messages(REQ), ["パスを調べられない: Permission denied"])

    def test_os_error_without_errno(self):
        # errno の無い OSError は strerror が None なので、例外の文字列を出す
        with mock.patch.object(specdoc, "exact_kind", side_effect=OSError("boom")):
            self.assertEqual(self.repo.messages(REQ), ["パスを調べられない: boom"])
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("boom")):
            self.assertEqual(self.repo.messages(REQ), ["読めない: boom"])

    def test_too_long_names_are_missing(self):
        # Python 3.12 までの Path.exists は ENAMETOOLONG で例外を送る
        name = "a" * 300 + ".md"
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [x]({name})、[y]({name}/x.md)"))
        self.assertEqual(self.repo.messages(REQ), [f"リンク先が無い: {name}", f"リンク先が無い: {name}/x.md"])

    def test_gate(self):
        # ゲートは、解決する工程がそのゲートかそれより前の要確認で止まる
        cases = [
            (REQ, "requirements", ("requirements", "design", "plan", "release")),
            (DESIGN, "design", ("design", "plan", "release")),
            (PLAN, "plan", ("plan", "release")),
            (PLAN, "release", ("release",)),
        ]
        for rel, stage, stopping in cases:
            self.repo.write_valid()
            self.write_question(rel, stage)
            self.assertEqual(self.repo.check(rel), [])
            for gate in specdoc.STAGES:
                with self.subTest(stage=stage, gate=gate):
                    expected = [f"解決する工程が {stage} の要確認が残っている: Q-001"] if gate in stopping else []
                    self.assertEqual(self.repo.messages(rel, gate=gate), expected)

    def test_approved_doc_keeps_only_questions_for_later_stages(self):
        for rel, stage in ((REQ, "requirements"), (DESIGN, "design"), (PLAN, "plan")):
            with self.subTest(rel=rel, stage=stage):
                self.repo.write_valid()
                self.write_question(rel, stage, "approved")
                self.assertEqual(
                    self.repo.messages(rel), [f"approved の文書に、解決する工程が {stage} の要確認が残っている: Q-001"]
                )
        for rel, stage in ((REQ, "design"), (DESIGN, "plan"), (PLAN, "release")):
            with self.subTest(rel=rel, stage=stage):
                self.repo.write_valid()
                self.write_question(rel, stage, "approved")
                self.assertEqual(self.repo.check(rel), [])

    def test_approved_flag(self):
        self.assertEqual(self.repo.messages(PLAN, approved=True), ["状態が approved でない"])
        self.assertEqual(self.repo.check(DESIGN, approved=True), [])

    def test_table_definition(self):
        cases = [
            (TABLES.replace("型・長さ", "型", 1), "テーブル定義の見出し行は | `テーブル名` | 意味 | 型・長さ | 必須 | 制約 | 差分 | にする"),
            (TABLES.replace("| 追加 |", "| 新規 |"), "差分は 既存・追加・変更・削除 のどれか"),
            (TABLES.replace("| `status` |", "| status |"), "1 つ目のセルにカラム名をコードで書く"),
        ]
        for tables, expected in cases:
            with self.subTest(expected=expected):
                self.repo.write_design(with_body(DESIGN_BODIES, テーブル定義=tables))
                self.assertIn(expected, self.repo.messages(DESIGN))

    def test_data_use(self):
        cases = [
            ("- 一括発行\n  - 書く: `invoices.total`", "テーブル定義に無いカラム: invoices.total"),
            ("- 一括発行\n  - 書く: invoices.status", "`テーブル.カラム` を「、」で区切って書く"),
            ("- 一括発行\n  - 消す: `invoices.status`", "処理の下に書けるのは 書く・読む"),
            ("- 一括発行", "処理の下に 書く・読む の箇条を 1 つ以上書く"),
            (DESIGN_BODIES["読み書きするデータ"] + "\n  - 読む: `customers.name`", "処理の下の項目が重なっている: 読む"),
        ]
        for body, expected in cases:
            with self.subTest(expected=expected):
                self.repo.write_design(with_body(DESIGN_BODIES, 読み書きするデータ=body))
                self.assertEqual(self.repo.messages(DESIGN), [expected])

    def test_link_target_must_exist(self):
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計="- 詳細画面: [モック](mocks/detail.html)"))
        self.assertEqual(self.repo.messages(DESIGN), ["リンク先が無い: mocks/detail.html"])

    def test_link_scheme(self):
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計="- [外](https://example.com) と [悪](javascript:x)"))
        self.assertEqual(self.repo.messages(DESIGN), ["リンク先は相対パスか http・https・mailto にする: javascript:x"])

    def test_unsplit_statement(self):
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割="なし"))
        self.assertEqual(self.repo.messages(DESIGN), ["分割しないときは「分割しない。理由: …」と書く"])

    def test_location(self):
        self.repo.write("docs/design.md", self.repo.read(DESIGN))
        self.assertEqual(self.repo.messages("docs/design.md"), ["specs/<id>-<slug>/ の下に置く"])
        self.repo.write(f"{SPEC}/billing/requirements.md", self.repo.read(REQ))
        self.assertEqual(
            self.repo.messages(f"{SPEC}/billing/requirements.md"),
            ["要件定義書は分けない。specs/<id>-<slug>/requirements.md に置く"],
        )

    def test_directory_is_not_accepted(self):
        # どのファイルを渡すかは呼び出す側が決める。ディレクトリの下のどれを見るかの規則を持たない
        for run in (specdoc.run_check, specdoc.run_html):
            with self.subTest(run=run.__name__):
                files, errors = run([str(self.repo.path(SPEC))])[:2]
                self.assertEqual(files, [])
                self.assertEqual([msg for _, _, msg in errors], ["ファイルを指定する"])

    def test_document_name_must_match_exactly(self):
        # 大文字・小文字を区別しない macOS でも、Design.md を型の文書として扱わない
        rel = "specs/13-other/Design.md"
        self.repo.write(rel, self.repo.read(DESIGN))
        self.assertEqual(self.repo.messages(rel), [f"型の文書（{specdoc.DOC_LIST}）ではない"])

    def test_ids_must_be_separated_by_comma(self):
        for value in ("R-001 R-003", "R-001、、R-003", "、R-001、R-003", "R-001、R-003、", "R-001、 R-003", "R-001,R-003"):
            with self.subTest(value=value):
                self.set_ac_reqs(value)
                self.assertIn("要件 は `R-001、R-002` のように番号を「、」で区切って書く", self.repo.messages(DESIGN))
        self.set_ac_reqs("R-001、R-002、R-003")
        self.assertEqual(self.repo.check(DESIGN), [])

    def test_ids_must_not_repeat(self):
        self.set_ac_reqs("R-001、R-001、R-003")
        self.assertEqual(self.repo.messages(DESIGN), ["要件 に同じ番号を重ねて書かない"])

    def test_unsplit_statement_needs_reason(self):
        for body in ("分割しない", "分割しない。理由:", "分割しないで進める", "```text\nx\n```", "| a |\n| --- |\n| b |"):
            with self.subTest(body=body):
                self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=body))
                self.assertEqual(self.repo.messages(DESIGN), ["分割しないときは「分割しない。理由: …」と書く"])
        for body in ("分割しない。理由: x", "分割しない。\n理由: まとまりが 1 つしかない"):
            with self.subTest(body=body):
                self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=body))
                self.assertEqual(self.repo.check(DESIGN), [])

    def test_upstream_hash_is_12_digits(self):
        full = specdoc.blob_hash(self.repo.path(REQ).read_bytes())
        for n in (7, 11, 13, 40):
            with self.subTest(n=n):
                self.repo.write(DESIGN, build_doc("design", meta(upstream=[f"{REQ}@{full[:n]}"]), DESIGN_BODIES))
                self.assertIn("上流は `パス@hash` の形で書く（specdoc.py hash の出力）", self.repo.messages(DESIGN))
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[f"{REQ}@{full[:12]}"]), DESIGN_BODIES))
        self.assertEqual(self.repo.check(DESIGN), [])

    def test_not_utf8(self):
        self.repo.write(REQ, self.repo.path(REQ).read_bytes().replace("発行".encode("utf-8"), b"\xff\xfe", 1))
        self.assertEqual(self.repo.messages(REQ), ["UTF-8 で書く"])

    def test_link_destination_form(self):
        cases = [
            ("HTTPS://example.com", "リンク先は相対パスか http・https・mailto にする: HTTPS://example.com"),
            ("//evil.example.com/x", "リンク先は相対パスで書く: //evil.example.com/x"),
            ("/etc/passwd", "リンク先は相対パスで書く: /etc/passwd"),
            ("\x01javascript:alert%281%29", "リンク先に制御文字を入れない"),
            ("a\x7fb.md", "リンク先に制御文字を入れない"),
            # check は %2F を区切りとして照らすが、ブラウザは区切りと読まない
            ("mocks%2Flist.html", "リンク先のパスに %2F・%5C を入れない（区切りは / にする）: mocks%2Flist.html"),
            ("mocks%5clist.html", "リンク先のパスに %2F・%5C を入れない（区切りは / にする）: mocks%5clist.html"),
        ]
        for dest, expected in cases:
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [x]({dest})"))
                self.assertEqual(self.repo.messages(REQ), [expected])
        # ? と # より後はパスではない。URL と、# で始まる文書の中へのリンク先も %2F を照らさない
        for dest in ("mocks/list.html?q=a%2Fb", "mocks/list.html#a%2Fb", "mocks/list.html?q=1#x", "https://example.com/a%2Fb", "#a%2Fb"):
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [x]({dest})"))
                self.assertEqual(self.repo.check(REQ), [])

    def test_link_destination_without_backslash(self):
        # ブラウザは http・https・file の URL でバックスラッシュを / と読むので、\\host は //host と同じになる
        for dest in ("\\\\evil.example.com/x", "\\/evil.example.com/x", "a\\b.md", "https://example.com\\x"):
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [x]({dest})"))
                self.assertEqual(self.repo.messages(REQ), ["リンク先にバックスラッシュを入れない（区切りは / にする）"])

    def test_gate_does_not_look_downstream(self):
        # どの文書が揃えば先へ進めるかは呼ぶ側が決める
        self.repo.path(PLAN).unlink()
        for gate in specdoc.STAGES:
            with self.subTest(gate=gate):
                self.assertEqual(self.repo.check(gate=gate), [])

    def test_unreadable_file(self):
        lock(self, self.repo.path(REQ))
        messages = self.repo.messages(REQ)
        self.assertEqual(len(messages), 1, messages)
        self.assertTrue(messages[0].startswith("読めない: "), messages)
        messages = self.repo.messages(DESIGN)
        self.assertTrue(any(m.startswith(f"上流のファイル {REQ} を読めない: ") for m in messages), messages)

    def test_unreadable_directory(self):
        # Python 3.12 までの Path.exists は EACCES で例外を送る。トレースバックにせず 1 行のエラーにする
        lock(self, self.repo.path(f"{SPEC}/mocks"))
        messages = self.repo.messages(DESIGN)
        self.assertEqual(len(messages), 1, messages)
        self.assertTrue(messages[0].startswith("リンク先 mocks/list.html を調べられない: "), messages)


class SplitTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write_requirements()
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=SPLIT, 受け入れ基準="なし"))
        self.write_child("billing", "- AC-billing-001: 選んだ請求書をまとめて発行できる\n  - 要件: R-001、R-003")
        self.write_child("listing", "- AC-listing-001: 発行済みの請求書には選択欄が出ない\n  - 要件: R-002")

    def child_path(self, name):
        return f"{SPEC}/{name}/design.md"

    def write_child(self, name, acs, data=None, parent=DESIGN, upstream=None):
        if upstream is None:
            upstream = [self.repo.ref(REQ), self.repo.ref(DESIGN)]
        bodies = {"受け入れ基準": acs}
        if data:
            bodies["読み書きするデータ"] = data
        self.repo.write(self.child_path(name), build_doc("design", meta(parent=parent, upstream=upstream), bodies, True))

    def test_split_set_passes(self):
        self.assertEqual(self.repo.check(), [])

    def test_child_plan(self):
        acs = "- AC-001: 既存の単票発行は変わらない\n  - 要件: なし"
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=SPLIT, 受け入れ基準=acs))
        self.write_child("billing", "- AC-billing-001: 選んだ請求書をまとめて発行できる\n  - 要件: R-001、R-003")
        self.repo.write(PLAN, build_doc("plan", meta(upstream=[self.repo.ref(DESIGN)]), {}))
        s = (
            "- S-billing-001: まとめて発行する\n  - 受け入れ基準: AC-billing-001\n  - 種別: 正常\n  - 層: 結合\n"
            "  - 前提: 未発行が 2 件\n  - 操作: 発行する\n  - 期待: 発行済みになる"
        )
        up = [self.repo.ref(self.child_path("billing")), self.repo.ref(PLAN)]
        path = f"{SPEC}/billing/plan.md"
        self.repo.write(path, build_doc("plan", meta("draft", parent=PLAN, upstream=up), {"シナリオ": s}, True))
        self.assertEqual(self.repo.check(path), [])
        cases = [
            ("AC-listing-001", "下流か別の子の文書の番号は参照しない: AC-listing-001"),
            ("AC-001", "受け入れ基準には同じディレクトリの設計書の AC を書く: AC-001"),
        ]
        for ac, expected in cases:
            with self.subTest(ac=ac):
                self.repo.write(path, build_doc("plan", meta("draft", parent=PLAN, upstream=up), {"シナリオ": s.replace("AC-billing-001", ac)}, True))
                messages = self.repo.messages(path)
                self.assertIn(expected, messages)
                self.assertIn("受ける S の無い AC: AC-billing-001", messages)
        self.repo.path(self.child_path("billing")).unlink()
        self.assertIn(f"設計書が無い: {self.child_path('billing')}", self.repo.messages(path))

    def test_parent_plan_must_not_receive_child_ac(self):
        s = PLAN_BODIES["シナリオ"].split("\n- S-002")[0].replace("AC-001", "AC-billing-001")
        self.repo.write_plan(with_body(PLAN_BODIES, シナリオ=s))
        self.assertEqual(self.repo.messages(PLAN), ["下流か別の子の文書の番号は参照しない: AC-billing-001"])

    def test_split_names_and_descriptions(self):
        bad_name = "子は `- 子の名前: 説明` の形で書く。子の名前はどの語も英小文字で始まる英小文字・数字の 1〜2 語（2 語はハイフンでつなぐ）"
        cases = [
            (SPLIT + "\n- billing: 請求書の再発行\n  - 要件: なし\n  - 依存: なし", "子の名前が重なっている: billing"),
            (SPLIT.replace("- listing:", "- mocks:"), bad_name),
            (SPLIT.replace("- listing:", "- specs:"), bad_name),
            # 2 語目が数字で始まると、AC-phase-100 が子 phase の AC-100 とも読めてしまう
            (SPLIT.replace("- listing:", "- phase-2:"), bad_name),
            (SPLIT.replace("- listing: 一覧の表示", "- listing:"), "説明が空: listing"),
        ]
        for split, expected in cases:
            with self.subTest(expected=expected, split=split):
                self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
                self.assertIn(expected, self.repo.messages(DESIGN))

    def test_r_assigned_to_two_children(self):
        # 子をまたぐ R は子に割り当てず、親の AC で受ける。後の子の「要件」の行に出す
        item = "  - 要件: R-002、R-003"
        split = SPLIT.replace("  - 要件: R-002", item)
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
        line = self.repo.read(DESIGN).split("\n").index(item) + 1
        msg = "2 つ以上の子に割り当てた R: R-003（billing と listing。子をまたぐ R は割り当てず、この文書の AC で受ける）"
        self.assertEqual(self.repo.check(DESIGN), [(DESIGN, line, msg)])
        # 1 つの子の中の重なりは、子をまたぐ割り当てとは別のエラーにする
        split = SPLIT.replace("R-001、R-003", "R-001、R-001、R-003")
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
        self.assertEqual(self.repo.messages(DESIGN), ["要件 に同じ番号を重ねて書かない"])

    def test_child_name_may_end_with_digits(self):
        split = SPLIT.replace("- listing:", "- phase2:")
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
        self.assertEqual(self.repo.messages(DESIGN), [])

    def test_child_directory_name(self):
        bad_dir = "子のディレクトリ名は、どの語も英小文字で始まる英小文字・数字の 1〜2 語（2 語はハイフンでつなぐ）にする"
        for name in ("phase-2", "mocks"):
            with self.subTest(name=name):
                self.write_child(name, f"- AC-{name}-001: 発行できる\n  - 要件: R-001")
                self.assertEqual(self.repo.messages(self.child_path(name)), [bad_dir])

    def test_unlisted_child_directory(self):
        self.write_child("refund", "- AC-refund-001: 取り消せる\n  - 要件: R-001")
        # 親は子のディレクトリを見ない。子の check が親の「サブ機能分割」と照合する
        self.assertEqual(self.repo.check(DESIGN), [])
        self.assertEqual(self.repo.messages(self.child_path("refund")), ["親の設計書の「サブ機能分割」に無い子: refund"])

    def test_child_of_unsplit_parent(self):
        # 親が「分割しない。理由: …」のときは、どの子も「サブ機能分割」に無い
        self.repo.write_design(DESIGN_BODIES)
        self.write_child("billing", "- AC-billing-001: 選んだ請求書をまとめて発行できる\n  - 要件: R-001、R-003")
        self.assertEqual(self.repo.messages(self.child_path("billing")), ["親の設計書の「サブ機能分割」に無い子: billing"])

    def test_dependency_must_come_first(self):
        split = SPLIT.replace("依存: billing", "依存: refund")
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
        self.assertEqual(self.repo.messages(DESIGN), ["依存には、先に並べた子を書く（並び順が実装順）: refund"])

    def test_requirement_not_assigned_nor_covered(self):
        split = SPLIT.replace("要件: R-001、R-003", "要件: R-001")
        self.repo.write_design(with_body(DESIGN_BODIES, サブ機能分割=split, 受け入れ基準="なし"))
        self.assertEqual(self.repo.messages(DESIGN), ["受ける AC の無い R: R-003"])

    def test_child_must_cover_assigned_requirements(self):
        self.write_child("billing", "- AC-billing-001: 選んだ請求書をまとめて発行できる\n  - 要件: R-001")
        self.assertEqual(
            self.repo.messages(self.child_path("billing")),
            ["受ける AC の無い R: R-003（親の「サブ機能分割」でこの子に割り当てている）"],
        )

    def test_child_ids_carry_the_child_name(self):
        self.write_child("billing", "- AC-001: 選んだ請求書をまとめて発行できる\n  - 要件: R-001、R-003")
        self.assertIn("子の文書の AC は `AC-billing-001` の形にする: AC-001", self.repo.messages(self.child_path("billing")))

    def test_parent_only_heading_in_child(self):
        path = self.child_path("billing")
        self.repo.replace(path, "## 非機能設計\n", "## データ設計\n\nなし\n\n## 非機能設計\n")
        self.assertEqual(self.repo.messages(path), ["子の文書には書かない見出し: ## データ設計"])

    def test_child_meta(self):
        self.write_child("billing", "- AC-billing-001: 発行できる\n  - 要件: R-001、R-003", parent=None)
        self.assertIn(f"子の文書には親を書く: {DESIGN}", self.repo.messages(self.child_path("billing")))
        self.write_child("billing", "- AC-billing-001: 発行できる\n  - 要件: R-001、R-003", upstream=[self.repo.ref(REQ)])
        self.assertEqual(self.repo.messages(self.child_path("billing")), [f"上流に書いていない文書: {DESIGN}"])
        # 別の子の設計書は上流に書けない
        sibling = self.child_path("listing")
        up = [self.repo.ref(REQ), self.repo.ref(DESIGN), self.repo.ref(sibling)]
        self.write_child("billing", "- AC-billing-001: 発行できる\n  - 要件: R-001、R-003", upstream=up)
        self.assertEqual(self.repo.messages(self.child_path("billing")), [f"上流に書けるのは {REQ}・{DESIGN} だけ: {sibling}"])

    def test_unreadable_parent(self):
        # 親の設計書を読めないときは、読めないと知らせる。「サブ機能分割」に無いとは言わない
        lock(self, self.repo.path(DESIGN))
        messages = self.repo.messages(self.child_path("billing"))
        self.assertTrue(any(m.startswith(f"親の設計書 {DESIGN} を読めない: ") for m in messages), messages)
        self.assertFalse(any("サブ機能分割" in m for m in messages), messages)

    def test_missing_parent(self):
        self.repo.path(DESIGN).unlink()
        messages = self.repo.messages(self.child_path("billing"))
        self.assertIn(f"親の設計書が無い: {DESIGN}", messages)
        self.assertFalse(any("サブ機能分割" in m for m in messages), messages)

    def test_child_data_use_refers_to_parent_tables(self):
        acs = "- AC-billing-001: 発行できる\n  - 要件: R-001、R-003"
        self.write_child("billing", acs, data="- 発行\n  - 書く: `invoices.status`")
        self.assertEqual(self.repo.check(self.child_path("billing")), [])
        self.write_child("billing", acs, data="- 発行\n  - 書く: `invoices.total`")
        self.assertEqual(self.repo.messages(self.child_path("billing")), ["テーブル定義に無いカラム: invoices.total"])

    def test_child_html_links_to_parent_documents(self):
        written, errors, _ = specdoc.run_html([str(self.repo.path(self.child_path("billing")))])
        self.assertEqual(errors, [])
        out = written[0].read_bytes().decode("utf-8")
        self.assertIn('<a href="../requirements.html#R-001">R-001</a>', out)
        self.assertIn('<dt>親</dt>\n<dd><a href="../design.html">基本設計: 請求書の一括発行</a></dd>', out)

    def test_gate_does_not_look_for_children(self):
        self.repo.path(self.child_path("billing")).unlink()
        for gate in specdoc.STAGES:
            with self.subTest(gate=gate):
                self.assertEqual(self.repo.check(DESIGN, gate=gate), [])


class HtmlTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write_valid()

    def render(self, rel):
        written, errors, _ = specdoc.run_html([str(self.repo.path(rel))])
        self.assertEqual(errors, [])
        return written[0].read_bytes().decode("utf-8")

    def render_directly(self, rel):
        """run_html が書き出さない書式の誤りのある文書でも、Renderer が作る HTML を返す。"""
        return specdoc.Renderer(specdoc.Workspace().load(self.repo.path(rel))).render()

    def meta_of(self, rel):
        return self.render(rel).split('<dl class="meta">', 1)[1].split("</dl>", 1)[0]

    def test_output_is_deterministic(self):
        first = self.render(DESIGN)
        self.assertEqual(self.render(DESIGN), first)
        self.assertTrue(self.repo.path(f"{SPEC}/design.html").is_file())

    def test_anchors_and_links(self):
        out = self.render(DESIGN)
        self.assertIn('<li id="AC-001">', out)
        self.assertIn('<a href="requirements.html#R-001">R-001</a>', out)
        self.assertIn('<a href="mocks/list.html">モック</a>', out)
        up = self.repo.ref(REQ)
        self.assertIn(f'<li><a href="requirements.html">要件定義書: 請求書の一括発行</a> <code>{up}</code></li>', out)

    def test_legend_is_not_linked(self):
        out = self.render(REQ)
        self.assertIn("（例: AC-billing-001）", out)
        self.assertNotIn("AC-billing-001</a>", out)

    def test_mermaid_script_only_when_needed(self):
        design = self.render(DESIGN)
        self.assertIn('<pre class="mermaid">erDiagram\n  customers ||--o{ invoices : has</pre>', design)
        # SRI は crossorigin が無いとブラウザが照合できず、読み込みを止める
        script = f'<script src="{specdoc.MERMAID_URL}" integrity="{specdoc.MERMAID_INTEGRITY}" crossorigin="anonymous"></script>'
        self.assertIn(script, design)
        # CDN を読めないときは初期化せず、コードのまま表示する
        self.assertIn("<script>if (window.mermaid) { mermaid.initialize({ startOnLoad: true }); }</script>", design)
        self.assertNotIn("<script", self.render(REQ))

    def test_md_links_become_html_and_text_is_escaped(self):
        body = "A & B を比べる。[設計](design.md#AC-001) と [表](data.md) と [問](design.md?v=1)"
        self.repo.write(f"{SPEC}/data.md", "x\n")
        self.repo.write_requirements(with_body(REQ_BODIES, **{"背景・目的": body}))
        out = self.render(REQ)
        self.assertIn("A &amp; B", out)
        self.assertIn('<a href="design.html#AC-001">設計</a>', out)
        self.assertIn('<a href="data.md">表</a>', out)
        # check と同じく ? より前をパスとして扱う
        self.assertIn('<a href="design.html?v=1">問</a>', out)

    def test_no_output_on_syntax_error(self):
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="* x"))
        written, errors, _ = specdoc.run_html([str(self.repo.path(REQ))])
        self.assertEqual(written, [])
        self.assertEqual([msg for _, _, msg in errors], ["箇条書きは - で書く"])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_no_output_on_link_form_error(self):
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="- 例: [x](javascript:alert%281%29)"))
        written, errors, _ = specdoc.run_html([str(self.repo.path(REQ))])
        self.assertEqual(written, [])
        self.assertEqual([msg for _, _, msg in errors], ["リンク先は相対パスか http・https・mailto にする: javascript:alert%281%29"])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_no_output_on_not_utf8(self):
        self.repo.write(REQ, self.repo.path(REQ).read_bytes().replace("発行".encode("utf-8"), b"\xff\xfe", 1))
        written, errors, _ = specdoc.run_html([str(self.repo.path(REQ))])
        self.assertEqual(written, [])
        self.assertEqual([msg for _, _, msg in errors], ["UTF-8 で書く"])

    def test_no_output_outside_specs(self):
        self.repo.write("docs/design.md", self.repo.read(DESIGN))
        written, errors, _ = specdoc.run_html([str(self.repo.path("docs/design.md"))])
        self.assertEqual(written, [])
        self.assertEqual([msg for _, _, msg in errors], ["specs/<id>-<slug>/ の下に置く"])

    def test_no_output_on_document_name_case(self):
        # 名前の大文字・小文字だけが違う文書は書き出さず、ほかの文書は書き出し続ける
        self.repo.write("specs/13-other/Design.md", self.repo.read(DESIGN))
        rel = "specs/13-other/design.md"
        typed = self.repo.path(rel)
        written, errors, notes = specdoc.run_html([str(self.repo.path(REQ)), str(typed)])
        self.assertEqual(written, [self.repo.path(f"{SPEC}/requirements.html")])
        self.assertEqual(errors, [(typed, 1, self.repo.case_error(rel))])
        self.assertEqual(notes, [])
        self.assertFalse(self.repo.path("specs/13-other/Design.html").exists())

    def test_renderer_links_only_allowed_destinations(self):
        denied = ("javascript:alert%281%29", "JAVASCRIPT:x", "data:text/html,x", "vbscript:x", "//evil.example.com/x", "/etc/passwd", "HTTPS://example.com")
        for dest in denied:
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [危ない]({dest})"))
                out = self.render_directly(REQ)
                self.assertIn("<li>例: 危ない</li>", out)
                self.assertNotIn(f'href="{specdoc.esc(dest)}"', out)
        for dest in ("https://example.com", "http://example.com", "mailto:a@example.com", "#R-001"):
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [可]({dest})"))
                out = self.render_directly(REQ)
                self.assertIn(f'<a href="{specdoc.esc(dest)}">可</a>', out)

    def test_renderer_does_not_link_backslash_destinations(self):
        for dest in ("\\\\evil.example.com/x", "\\/evil.example.com/x"):
            with self.subTest(dest=dest):
                self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項=f"- 例: [危ない]({dest})"))
                out = self.render_directly(REQ)
                self.assertIn("<li>例: 危ない</li>", out)
                self.assertNotIn("evil.example.com", out)

    def test_output_despite_other_check_errors(self):
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="- R-099 を参照"))
        self.assertEqual(self.repo.messages(REQ), ["定義の無い番号: R-099"])
        self.assertIn("<li>R-099 を参照</li>", self.render(REQ))

    def test_missing_link_target_is_a_warning(self):
        item = "- 詳細画面: [モック](mocks/detail.html)"
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計=item))
        line = self.repo.read(DESIGN).split("\n").index(item) + 1
        written, errors, notes = specdoc.run_html([str(self.repo.path(DESIGN))])
        self.assertEqual((written, errors), ([self.repo.path(f"{SPEC}/design.html")], []))
        self.assertEqual(notes, [(self.repo.path(DESIGN), line, "警告: リンク先が無い: mocks/detail.html")])
        self.assertEqual(self.repo.messages(DESIGN), ["リンク先が無い: mocks/detail.html"])

    def test_meta_path_outside_the_repository_is_not_linked(self):
        bad = "../outside/design.md@0123456789ab"
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[self.repo.ref(REQ), bad]), DESIGN_BODIES))
        out = self.meta_of(DESIGN)
        self.assertIn(f"<li>{bad}</li>", out)
        self.assertNotIn("outside/design.html", out)

    def test_meta_path_that_looks_like_a_scheme(self):
        # check は上流に書けないパスとして誤りにするが、html はリンクにしても javascript: にしない
        rel = f"{SPEC}/javascript:alert(1)"
        self.repo.write(rel, "x\n")
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[self.repo.ref(REQ), self.repo.ref(rel)]), DESIGN_BODIES))
        self.assertIn(f"上流に書けるのは {REQ} だけ: {rel}", self.repo.messages(DESIGN))
        out = self.meta_of(DESIGN)
        self.assertIn('<a href="./javascript:alert(1)">', out)
        self.assertNotIn('href="javascript:', out)

    def test_meta_path_to_a_misplaced_document_keeps_md(self):
        rel = "docs/design.md"
        self.repo.write(rel, self.repo.read(DESIGN))
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[self.repo.ref(REQ), self.repo.ref(rel)]), DESIGN_BODIES))
        out = self.meta_of(DESIGN)
        self.assertIn('<a href="../../docs/design.md">', out)
        self.assertNotIn("docs/design.html", out)

    def test_meta_path_with_backslash_is_not_linked(self):
        # 書式の誤りなので html は書き出さないが、Renderer の側でもリンクにしない
        for bad in (f"{SPEC}/\\\\evil.example.com/x@0123456789ab", f"{SPEC}/..\\..\\outside/design.md@0123456789ab"):
            with self.subTest(bad=bad):
                self.repo.write(DESIGN, build_doc("design", meta(upstream=[self.repo.ref(REQ), bad]), DESIGN_BODIES))
                out = self.render_directly(DESIGN)
                self.assertIn(f"<li>{specdoc.esc(bad)}</li>", out)

    def test_only_typed_documents_become_html(self):
        self.repo.write("docs/design.md", "x\n")
        self.repo.write(f"{SPEC}/mocks/design.md", "x\n")
        self.repo.write("specs/13-other/design.md", "x\n")
        body = "[外](../../docs/design.md)、[モック](mocks/design.md)、[別](../13-other/design.md)"
        self.repo.write_requirements(with_body(REQ_BODIES, **{"背景・目的": body}))
        out = self.render(REQ)
        self.assertIn('<a href="../../docs/design.md">外</a>', out)
        self.assertIn('<a href="mocks/design.md">モック</a>', out)
        self.assertIn('<a href="../13-other/design.html">別</a>', out)

    def test_stale_html_is_removed(self):
        self.render(REQ)
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="* x"))
        written, errors, notes = specdoc.run_html([str(self.repo.path(REQ))])
        self.assertEqual((written, [msg for _, _, msg in errors]), ([], ["箇条書きは - で書く"]))
        self.assertEqual(notes, [(self.repo.path(REQ), 1, "古い requirements.html を消した")])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_stale_html_of_unreadable_document_is_removed(self):
        self.render(REQ)
        lock(self, self.repo.path(REQ))
        written, errors, notes = specdoc.run_html([str(self.repo.path(REQ))])
        self.assertEqual(written, [])
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0][2].startswith("読めない: "), errors)
        self.assertEqual(notes, [(self.repo.path(REQ), 1, "古い requirements.html を消した")])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_html_outside_specs_is_never_removed(self):
        self.repo.write("docs/design.md", "x\n")
        self.repo.write("docs/design.html", "<p>人が書いた</p>\n")
        self.repo.write(f"{SPEC}/mocks/design.md", "壊れた文書\n")
        self.repo.write(f"{SPEC}/mocks/design.html", "<p>モック</p>\n")
        for rel in ("docs/design.md", f"{SPEC}/mocks/design.md"):
            with self.subTest(rel=rel):
                notes = specdoc.run_html([str(self.repo.path(rel))])[2]
                self.assertEqual(notes, [])
                self.assertTrue(self.repo.path("docs/design.html").is_file())
                self.assertTrue(self.repo.path(f"{SPEC}/mocks/design.html").is_file())

    def test_write_error_is_reported_and_others_continue(self):
        self.repo.path(f"{SPEC}/plan.html").mkdir()
        written, errors, _ = specdoc.run_html([str(self.repo.path(r)) for r in self.repo.docs()])
        self.assertEqual([p.name for p in written], ["design.html", "requirements.html"])
        self.assertEqual([(p.name, line) for p, line, _ in errors], [("plan.md", 1)])
        self.assertTrue(errors[0][2].startswith("plan.html を書けない: "), errors)

    def test_half_written_html_is_removed(self):
        self.render(REQ)
        path = self.repo.path(REQ)

        def write_half(out, data):
            with open(out, "wb") as f:
                f.write(data[: len(data) // 2])
            raise OSError(errno.ENOSPC, "No space left on device")

        with mock.patch.object(specdoc, "write_output", write_half):
            written, errors, notes = specdoc.run_html([str(path)])
        self.assertEqual((written, errors), ([], [(path, 1, "requirements.html を書けない: No space left on device")]))
        self.assertEqual(notes, [(path, 1, "古い requirements.html を消した")])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_interrupted_html_is_removed(self):
        # Ctrl-C で止めたときも書きかけを残さず、KeyboardInterrupt はそのまま送る
        self.render(REQ)
        path = self.repo.path(REQ)

        def write_half(out, data):
            with open(out, "wb") as f:
                f.write(data[: len(data) // 2])
            raise KeyboardInterrupt

        with mock.patch.object(specdoc, "write_output", write_half):
            with self.assertRaises(KeyboardInterrupt):
                specdoc.run_html([str(path)])
        self.assertFalse(self.repo.path(f"{SPEC}/requirements.html").exists())

    def test_symlinked_html_is_not_followed(self):
        # 出力先のシンボリックリンクをたどってリンク先を上書きせず、書けなかったときと同じくリンクを消す
        victim = self.repo.path("victim.txt")
        victim.write_bytes(b"keep\n")
        out = self.repo.path(f"{SPEC}/requirements.html")
        os.symlink(victim, out)
        path = self.repo.path(REQ)
        written, errors, notes = specdoc.run_html([str(path)])
        reason = os.strerror(errno.ELOOP)
        self.assertEqual((written, errors), ([], [(path, 1, f"requirements.html を書けない: {reason}")]))
        self.assertEqual(notes, [(path, 1, "古い requirements.html を消した")])
        self.assertEqual(victim.read_bytes(), b"keep\n")
        self.assertFalse(os.path.lexists(out))
        # リンクを消したので、次は書き出せる
        self.assertEqual(specdoc.run_html([str(path)])[:2], ([out], []))
        self.assertFalse(out.is_symlink())

    def test_dangling_symlinked_html_is_not_followed(self):
        # リンク先が無いときも、リンク先を作らない
        victim = self.repo.path("victim.txt")
        out = self.repo.path(f"{SPEC}/requirements.html")
        os.symlink(victim, out)
        path = self.repo.path(REQ)
        written, errors, notes = specdoc.run_html([str(path)])
        reason = os.strerror(errno.ELOOP)
        self.assertEqual((written, errors), ([], [(path, 1, f"requirements.html を書けない: {reason}")]))
        self.assertEqual(notes, [])
        self.assertFalse(os.path.lexists(victim))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.write_valid()
        cwd = os.getcwd()
        os.chdir(str(self.repo.root))
        self.addCleanup(os.chdir, cwd)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = specdoc.main(list(argv))
        return code, out.getvalue()

    def run_script(self, *argv):
        """スクリプトとして実行する。標準出力・標準エラーの文字コードは ASCII にしておく。"""
        env = dict(os.environ, PYTHONIOENCODING="ascii")
        return subprocess.run(
            [sys.executable, specdoc.__file__] + list(argv), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def test_check_ok(self):
        self.assertEqual(self.run_main("check", REQ, DESIGN, PLAN), (0, "ok: 3 件\n"))

    def test_check_error(self):
        self.repo.replace(REQ, "## リリース日\n\nなし\n\n", "## リリース日\n\n")
        line = self.repo.read(REQ).split("\n").index("## リリース日") + 1
        code, out = self.run_main("check", REQ)
        self.assertEqual(code, 1)
        self.assertEqual(out, f"{REQ}:{line}: 本文が空: ## リリース日。書く内容が無ければ「なし」と書く\n")

    def test_check_missing_path(self):
        code, out = self.run_main("check", "nothing")
        self.assertEqual(code, 1)
        self.assertEqual(out, "nothing:1: ファイルが無い\n")

    def test_hash(self):
        code, out = self.run_main("hash", REQ)
        self.assertEqual(code, 0)
        self.assertEqual(out, self.repo.ref(REQ) + "\n")

    def test_html(self):
        code, out = self.run_main("html", REQ, DESIGN, PLAN)
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[:3], [f"{SPEC}/requirements.html", f"{SPEC}/design.html", f"{SPEC}/plan.html"])

    def test_check_gate_takes_english_stage_names(self):
        self.repo.path(PLAN).unlink()
        self.assertEqual(self.run_main("check", "--gate", "release", REQ, DESIGN), (0, "ok: 2 件\n"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_main("check", "--gate", "実装", REQ)
        self.assertEqual(cm.exception.code, 2)

    def test_hash_takes_one_file(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_main("hash", REQ, DESIGN)
        self.assertEqual(cm.exception.code, 2)

    def test_check_gate_and_approved_together(self):
        self.repo.write_plan(with_body(PLAN_BODIES, 要確認=question("release")))
        code, out = self.run_main("check", "--gate", "release", "--approved", PLAN)
        self.assertEqual(code, 1)
        self.assertEqual(
            sorted(line.split(": ", 1)[1] for line in out.splitlines()),
            ["状態が approved でない", "解決する工程が release の要確認が残っている: Q-001"],
        )

    def test_hash_errors(self):
        # hash は上流に書ける文書（置き場の合った型の文書）だけを受け付ける
        self.repo.write("README.md", "x\n")
        self.repo.write("docs/design.md", self.repo.read(DESIGN))
        not_typed = f"型の文書（{specdoc.DOC_LIST}）ではない"
        cases = [
            ("nothing.md", "ファイルが無い"),
            (f"{SPEC}/{'a' * 300}.md", "ファイルが無い"),
            ("a" * 300 + ".md", "ファイルが無い"),
            (SPEC, "ファイルを指定する"),
            ("README.md", not_typed),
            (f"{SPEC}/mocks/list.html", not_typed),
            ("docs/design.md", "specs/<id>-<slug>/ の下に置く"),
        ]
        # 大文字・小文字を区別しないファイルシステムでも、名前の違いを誤りにする
        self.repo.write("specs/PROJ-12-invoice/requirements.md", self.repo.read(REQ))
        typed = "specs/proj-12-invoice/requirements.md"
        cases.append((typed, self.repo.case_error(typed)))
        # ファイルの名前だけが違うときも同じ
        self.repo.write("specs/13-other/Design.md", self.repo.read(DESIGN))
        named = "specs/13-other/design.md"
        cases.append((named, self.repo.case_error(named)))
        for arg, expected in cases:
            with self.subTest(arg=arg):
                self.assertEqual(self.run_main("hash", arg), (1, f"{arg}:1: {expected}\n"))

    def test_hash_of_unreadable_file(self):
        lock(self, self.repo.path(REQ))
        code, out = self.run_main("hash", REQ)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith(f"{REQ}:1: 読めない: "), out)

    def test_hash_output_is_the_upstream_line(self):
        # どこから、どんな形のパスで呼んでも、出力をそのまま上流に書けば check が通る
        self.assertEqual(self.run_main("hash", str(self.repo.path(REQ))), (0, self.repo.ref(REQ) + "\n"))
        os.chdir(str(self.repo.path(SPEC)))
        code, line = self.run_main("hash", "requirements.md")
        self.assertEqual(code, 0)
        self.repo.write(DESIGN, build_doc("design", meta(upstream=[line.strip()]), DESIGN_BODIES))
        code, line = self.run_main("hash", "design.md")
        self.assertEqual(code, 0)
        self.repo.write(PLAN, build_doc("plan", meta("draft", upstream=[line.strip()]), PLAN_BODIES))
        self.assertEqual(self.run_main("check", "requirements.md", "design.md", "plan.md"), (0, "ok: 3 件\n"))

    def test_check_too_long_path(self):
        arg = "a" * 300 + ".md"
        self.assertEqual(self.run_main("check", arg), (1, f"{arg}:1: ファイルが無い\n"))

    def test_path_on_another_drive_is_shown_as_given(self):
        # Windows の relpath はドライブが違うと ValueError を送る
        path = str(self.repo.path("nothing"))
        with mock.patch.object(specdoc.os.path, "relpath", side_effect=ValueError("path is on mount 'C:', start on mount 'D:'")):
            self.assertEqual(self.run_main("check", path), (1, f"{path}:1: ファイルが無い\n"))

    def test_stdout_is_utf8_whatever_the_locale(self):
        # 標準出力の文字コードを ASCII にしても、スクリプトとして実行すれば UTF-8 で出す
        result = self.run_script("check", "nothing")
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("nothing:1: ファイルが無い\n", result.stdout.decode("utf-8"))

    def test_stderr_is_utf8_whatever_the_locale(self):
        # 引数の誤り（argparse）が出る標準エラーも同じ
        result = self.run_script("check", "--gate", "実装", "nothing")
        self.assertEqual(result.returncode, 2, result)
        self.assertIn("'実装'", result.stderr.decode("utf-8"))

    def test_html_writes_nothing_to_stderr(self):
        # 警告と「古い HTML を消した」も stdout に出す。stderr は引数の誤りだけ
        self.run_main("html", REQ)
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="- 例: [x](javascript:x)"))
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計="- 詳細画面: [モック](mocks/detail.html)"))
        result = self.run_script("html", REQ, DESIGN)
        self.assertEqual(result.returncode, 1, result)
        out = result.stdout.decode("utf-8")
        self.assertIn("古い requirements.html を消した", out)
        self.assertIn("警告: リンク先が無い: mocks/detail.html", out)
        self.assertEqual(result.stderr, b"")

    def test_main_leaves_the_caller_streams_alone(self):
        # モジュールから main を呼ぶ側の標準出力の設定は変えない
        out = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="backslashreplace")
        with mock.patch.object(sys, "stdout", out):
            self.assertEqual(specdoc.main(["check", "nothing"]), 1)
        self.assertEqual(out.encoding, "ascii")

    def test_html_error_and_notes(self):
        self.run_main("html", REQ)
        self.repo.write_requirements(with_body(REQ_BODIES, 明示的除外事項="- 例: [x](javascript:alert%281%29)"))
        line = self.repo.read(REQ).split("\n").index("- 例: [x](javascript:alert%281%29)") + 1
        self.assertEqual(
            self.run_main("html", REQ),
            (
                1,
                f"{REQ}:{line}: リンク先は相対パスか http・https・mailto にする: javascript:alert%281%29\n"
                f"{REQ}:1: 古い requirements.html を消した\n",
            ),
        )

    def test_html_warning_keeps_exit_code(self):
        item = "- 詳細画面: [モック](mocks/detail.html)"
        self.repo.write_design(with_body(DESIGN_BODIES, 画面設計=item))
        line = self.repo.read(DESIGN).split("\n").index(item) + 1
        self.assertEqual(
            self.run_main("html", DESIGN),
            (0, f"{DESIGN}:{line}: 警告: リンク先が無い: mocks/detail.html\n{SPEC}/design.html\n"),
        )

    def test_html_write_error_does_not_stop_the_others(self):
        self.repo.path(f"{SPEC}/plan.html").mkdir()
        code, out = self.run_main("html", *self.repo.docs())
        lines = out.split("\n")
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith(f"{PLAN}:1: plan.html を書けない: "), out)
        self.assertEqual(lines[1:], [f"{SPEC}/design.html", f"{SPEC}/requirements.html", ""])


if __name__ == "__main__":
    unittest.main()
