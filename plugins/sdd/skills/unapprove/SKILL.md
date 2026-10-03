---
name: unapprove
description: sdd の文書 1 本の承認を取り消す。状態を approved から draft にして承認者を消し、その文書だけを commit する。上流の要求が変わったときなどに、ユーザーが取り消しをはっきり示したときだけ使う。
argument-hint: <文書のパス>
disable-model-invocation: true
---

# unapprove

ユーザーが承認の取り消しをはっきり示したときだけ動く。自分の判断でこの skill を使わない。`<plugin>` は sdd plugin のディレクトリの絶対パス `${CLAUDE_PLUGIN_ROOT}`（置き換わっていなければ、この SKILL.md の 2 つ上）。

著者か、その文書を承認できる人が、上流の要求が変わったときなどに承認を取り消す。`<plugin>/procedures/state.md` に従う。この skill で決まるもの:

- 前の状態: `approved`
- 前の照合: なし（上流の承認を先に取り消していても、取り消せるようにする）
- 書くこと: 状態を `draft` にし、承認者の行を消す
- 後の照合: なし
- commit メッセージ: `承認取消: <文書>`。代理なら `承認取消（代理）: <文書>`
