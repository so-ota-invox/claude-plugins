---
name: requirements
description: 要件定義書（specs/<id>-<slug>/requirements.md）を sdd の型で起草する。チケットや依頼文から書くか、よそで書かれた要件定義書を取り込み、refine と逆質問まで行う。
argument-hint: <チケット・依頼文・元の文書のパス>
---

# requirements

要件定義書を起草する。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

## 使うもの

- 型: `<plugin>/formats/common.md` と `<plugin>/formats/requirements.md`
- 手順: `<plugin>/procedures/draft.md`
- 調査の agent: `impact-analyst`
- 前の工程は無い。呼び出しで渡されたもの（チケット、依頼文、よそで書かれた要件定義書）から書く

## 入口

- 渡されたものを読む。チケットは使える手段（MCP など）で読み、読めなければ本文を貼ってもらう
- 渡されたものが 2 件以上の対象に広がると分かったら、全部を対象にするか一部でよいかを聞き、1 件ずつ起草する
- 置き場は `specs/<id>-<slug>/requirements.md`。`<id>` と `<slug>` は common.md の「置き場」に従って決める

## 起草

`<plugin>/procedures/draft.md` に従う。

## 報告

- 文書と HTML のパス
- refine の終わり方（逆質問の後に refine をもう 1 度行ったときは、その終わり方も）
- refine で直さなかった指摘と、要確認にした指摘
- 残った要確認の件数
- 承認するときのコマンド: `/sdd:approve <文書>`（Codex では `$sdd:approve <文書>`）
