---
name: requirements
description: 要件定義書（specs/<slug>/requirements.md）を sdd の型で起草する。チケットや依頼文から書くか、よそで書かれた要件定義書を取り込み、refine と逆質問まで行う。書きかけの要件定義書を渡せば、残った要確認から逆質問を続ける。
argument-hint: <チケット・依頼文・元の文書のパス、または書きかけの要件定義書のパス>
---

# requirements

要件定義書を起草する。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

## 使うもの

- 型: `<plugin>/formats/common.md` と `<plugin>/formats/requirements.md`
- 手順: `<plugin>/procedures/draft.md`
- 調査の agent: `impact-analyst`
- 前の工程は無い。呼び出しで渡されたもの（チケット、依頼文、よそで書かれた要件定義書）から書く

## 入口

- 渡されたものが `<plugin>/procedures/draft.md` の「再開」に当たれば、入口の残りを飛ばして起草へ進む
- 渡されたものを読む。チケットは使える手段（MCP など）で読み、読めなければ本文を貼ってもらう
- 渡されたものが 2 件以上の対象に広がると分かったら、全部を対象にするか一部でよいかを聞き、1 件ずつ起草する
- 置き場は `specs/<slug>/requirements.md`。`<slug>` は common.md の「置き場」に従って決める。`specs/<slug>/` がもうあれば、別の `<slug>` を聞く

## 起草

`<plugin>/procedures/draft.md` に従う。

## 報告

- 文書と HTML のパス
- refine の報告（逆質問の後に refine をもう 1 度行ったときは、その報告も）
- 残った要確認の件数
- レビューに出すときのコマンド: `/sdd:submit <文書>`（Codex では `$sdd:submit <文書>`）
