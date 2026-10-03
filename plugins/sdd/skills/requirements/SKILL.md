---
name: requirements
description: 要件定義書（specs/<slug>/requirements.md）を sdd の型で起草する。チケット・依頼文・よそで書かれた文書などを材料に調べて書き、refine と逆質問まで行う。書きかけの要件定義書を渡せば、残った要確認から逆質問を続ける。
argument-hint: <チケット・依頼文・資料のパス、または書きかけの要件定義書のパス>
---

# requirements

要件定義書を起草する。`<plugin>` は sdd plugin のディレクトリの絶対パス `${CLAUDE_PLUGIN_ROOT}`（置き換わっていなければ、この SKILL.md の 2 つ上）。

## 使うもの

- 型: `<plugin>/formats/common.md` と `<plugin>/formats/requirements.md`
- 手順: `<plugin>/procedures/draft.md`
- 調査の agent: `impact-analyst`
- 前の工程は無い。呼び出しで渡されたもの（チケット、依頼文、よそで書かれた文書）を材料に書く

## 入口

- 渡されたものが `<plugin>/procedures/draft.md` の「再開」に当たれば、入口の残りを飛ばして、下の「起草」のとおり `<plugin>/procedures/draft.md` に従う
- 渡されたものを読む。チケットは使える手段（MCP など）で読み、読めなければ本文を貼ってもらう
- 渡されたものが 2 件以上の対象に広がると分かったら、全部を対象にするか一部でよいかを聞き、1 件ずつ起草する
- 置き場は `specs/<slug>/requirements.md`。`<slug>` は common.md の「置き場」に従って決める。`specs/<slug>/` がもうあれば、別の `<slug>` を聞く

## 起草

`<plugin>/procedures/draft.md` に従う。

## 報告

- 文書と HTML のパス
- refine の報告（逆質問の後に refine をもう 1 度行ったときは、その報告も）
- 残った要確認の件数
- 知らせる相手（`<plugin>/procedures/draft.md` の「下流の著者への知らせ」）
- レビューに出すときのコマンド: `/sdd:submit <文書>`（Codex では `$sdd:submit <文書>`）
