---
name: review
description: sdd の文書（requirements.md・design.md・plan.md）1 本を、独立した 3 体の agent で review し、検証した指摘を文書の隣の <文書名>.review.md に書く。文書は直さない。指摘のファイルを渡すと、3 体の review を省き、その指摘を今の文書で確かめ直す。
argument-hint: <文書のパス> [<指摘のファイル>]
---

# review

文書 1 本を review し、指摘を文書の隣の `<文書名>.review.md` に書く。文書は直さない。`<plugin>` は sdd plugin のディレクトリの絶対パス `${CLAUDE_PLUGIN_ROOT}`（置き換わっていなければ、この SKILL.md の 2 つ上）。agent は `<plugin>/procedures/agent.md` のとおりに起動する。

「止まる」と書いたところでは、理由をユーザーに示して終える。この skill を呼んだ手順も続けない。

## 手順

1. 文書は 1 本だけ受け取る。2 本以上を渡されたら、1 本ずつ呼ぶよう伝えて止まる
2. `python3 <plugin>/scripts/specdoc.py check <文書>` を走らせる。エラーがあれば、エラーをそのまま返して止まる
3. 指摘のファイルを渡されたら、4 へ進む。渡されなければ、`conformance-reviewer`・`fact-checker`・`adversarial-reviewer` を並列に起動する。3 体の報告は読まない
4. `finding-verifier` を起動し、3 体の報告のファイルのパスか、渡された指摘のファイルのパスを渡す
5. `finding-verifier` が返した件数と、指摘のファイル `<文書名>.review.md` のパスを返す
