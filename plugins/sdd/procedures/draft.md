# 起草の共通手順

起草の skill がすべて従う手順。工程によって変わる部分は各 skill の SKILL.md に書く。`<plugin>` は sdd plugin のディレクトリ（このファイルの 1 つ上）の絶対パス。agent は `<plugin>/skills/review/SKILL.md` の「agent の起動」のとおりに起動する。

## 起草

著者は、ユーザーが言わなければ `git config user.name` にする。それも空なら、ユーザーに聞く。

1. 渡されたものが、よそで書かれた同じ種類の文書なら、調査と起草の代わりに `importer` で型へ写し、3 へ進む。書き出す先に文書がもうあれば、上書きしてよいかを先に聞き、よくなければ止まる
2. SKILL.md に挙げた調査の agent を起動し、報告を読んで、`<plugin>/formats/common.md` と自分の型に従って文書を書く。調査の報告はファイルに残さない
3. `python3 <plugin>/scripts/specdoc.py check <文書>` が通るまで直す。文書を直しても消えないエラー（上流が approved でない、置き場が違うなど）や、直しても同じエラーが続くときは、エラーを示して止まる。通ったら `python3 <plugin>/scripts/specdoc.py html <文書>` で HTML を出す
4. `<plugin>/skills/refine/SKILL.md` の手順で refine する

## 逆質問

1. 要確認を 1 問ずつ、推奨の答えを付けて聞く。順は 範囲 > セキュリティ・プライバシー > UX > 技術
2. 答えを文書に書き戻し、check → html
3. 要確認が尽きるか、ユーザーが止めたら終える
4. 逆質問で本文が変わっていたら、refine をもう 1 回だけ回す
