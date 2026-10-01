# 起草の共通手順

requirements・design・plan の skill がすべて従う手順。工程によって変わる部分は各 skill の SKILL.md に書く。`<plugin>` は sdd plugin のディレクトリ（このファイルの 1 つ上）の絶対パス。

## agent の起動

- Claude Code では `sdd:<名前>` の agent を起動する
- ほかの環境では、subagent に `<plugin>/agents/<名前>.md` を読ませ、その役割で動かす。subagent を使えなければ、その役割を自分で順に行う
- agent には、`<plugin>/agents/<名前>.md` の「受け取るもの」を渡す

## 起草

著者は、ユーザーが言わなければ `git config user.name` にする。

1. 渡されたものが、よそで書かれた同じ種類の文書なら、調査と起草の代わりに `importer` で型へ写し、3 へ進む
2. SKILL.md に挙げた調査の agent を起動し、報告を読んで、`<plugin>/formats/common.md` と自分の型に従って文書を書く。調査の報告はファイルに残さない
3. `python3 <plugin>/scripts/specdoc.py check <文書>` が通るまで直し、`python3 <plugin>/scripts/specdoc.py html <文書>` で HTML を出す
4. `<plugin>/skills/refine/SKILL.md` の手順で refine する

## 逆質問

1. 要確認を 1 問ずつ、推奨の答えを付けて聞く。順は 範囲 > セキュリティ・プライバシー > UX > 技術
2. 答えを文書に書き戻し、check → html
3. 要確認が尽きるか、ユーザーが止めたら終える
4. 逆質問で本文が変わっていたら、refine をもう 1 回だけ回す
