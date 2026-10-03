---
name: submit
description: sdd の文書 1 本をレビューに出す。上流と要確認を照合し、通れば状態を draft から review にして、その文書だけを commit する。ユーザーがレビューに出すとはっきり示したときだけ使う。
argument-hint: <文書のパス>
disable-model-invocation: true
---

# submit

ユーザーがレビューに出すとはっきり示したときだけ動く。自分の判断でこの skill を使わない。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

著者が、自分の目で見てレビューに出せるところまで仕上がったと示す。`<plugin>/procedures/state.md` に従う。この skill で決まるもの:

- 前の状態: `draft`
- 前の照合: `python3 <plugin>/scripts/specdoc.py check --gate <工程> <文書>`
- 書くこと: 状態を `review` にする
- 後の照合: `python3 <plugin>/scripts/specdoc.py check <文書>`
- commit メッセージ: `提出: <文書>`。代理なら `提出（代理）: <文書>`
