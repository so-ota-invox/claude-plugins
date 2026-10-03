---
name: approve
description: sdd の文書 1 本を承認する。上流と要確認を照合し、通れば状態を review から approved にして承認者を書き、その文書だけを commit する。ユーザーが承認をはっきり示したときだけ使う。
argument-hint: <文書のパス>
disable-model-invocation: true
---

# approve

ユーザーが承認をはっきり示したときだけ動く。自分の判断でこの skill を使わない。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

上流の文書の著者が、レビュー中の文書を承認する。要件定義書は、著者を含めて誰でも承認できる。`<plugin>/procedures/state.md` に従う。この skill で決まるもの:

- 前の状態: `review`
- 前の照合: `python3 <plugin>/scripts/specdoc.py check --gate <工程> <文書>`
- 書くこと: 状態を `approved` にし、その次の行に `- 承認者: <名前>` を書く。代理なら `- 承認者: <名前>（代理）`
- 後の照合: `python3 <plugin>/scripts/specdoc.py check <文書>`
- commit メッセージ: `承認: <文書>`。代理の印は承認者の行に残すので、代理でも同じ
