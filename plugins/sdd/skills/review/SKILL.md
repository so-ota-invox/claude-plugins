---
name: review
description: sdd の文書（requirements.md・design.md・plan.md）1 本を、独立した 3 体の agent でレビューし、検証した指摘を文書の隣の <文書名>.review.md に書く。文書は直さない。
argument-hint: <文書のパス>
---

# review

文書 1 本をレビューし、指摘を文書の隣の `<文書名>.review.md` に書く。文書は直さない。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

## agent の起動

- Claude Code では `sdd:<名前>` の agent を起動する
- ほかの環境では、subagent に `<plugin>/agents/<名前>.md` を読ませ、その役割で動かす。subagent を使えなければ、その役割を自分で順に行い、そうしたことを報告に書く
- agent には、`<plugin>/agents/<名前>.md` の「受け取るもの」だけを渡す。起草の経緯は渡さない

## 手順

1. 呼び出しで渡されたのが文書 2 本以上なら、全部をレビューするか一部でよいかを聞き、1 本ずつ行う
2. `python3 <plugin>/scripts/specdoc.py check <文書>` を走らせる。エラーがあれば、エラーをそのまま返して止まる
3. `conformance-reviewer`・`fact-checker`・`adversarial-reviewer` を並列に起動する。3 体の報告は読まない。件数と報告のファイルのパスを返さなかった agent があれば、その名前を示して止まる
4. `finding-verifier` を起動し、3 体の報告のファイルのパスを渡す。件数とパスを返さなければ、返したものを示して止まる
5. `finding-verifier` が返した件数と、指摘のファイル `<文書名>.review.md` のパスを返す
