---
name: refine
description: sdd の文書 1 本を review し、指摘を反映して check を通す。P0 と P1 が無くなるまで、最大 2 往復くり返す。ほかの環境で review した指摘ファイルを渡すと、1 往復目にそれを使う。
argument-hint: <文書のパス> [<指摘ファイル>]
---

# refine

文書 1 本の review と反映をくり返す。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。直すときは `<plugin>/formats/common.md` と文書の種類の型に従う。

## 手順

呼び出しで渡されたのが文書 2 本以上なら、全部を回すか一部でよいかを聞き、1 本ずつ行う。

次の 1 往復を、最大 2 往復くり返す。

1. `python3 <plugin>/scripts/specdoc.py check <文書>` が通るまで直す
2. 指摘を用意する
   - 1 往復目で指摘ファイルを渡されたときは、`finding-verifier` に指摘ファイルを渡し、今の文書で確かめ直させる。起動のしかたは `<plugin>/skills/review/SKILL.md` の「agent の起動」と同じ
   - それ以外は `<plugin>/skills/review/SKILL.md` の手順で review する
3. `<文書名>.review.md` を読む。P0 も P1 も無ければ止める
4. 反映する
   - P0 と P1 を直す
   - 反証の付いた P0 と、直せない P0 は、要確認として文書に積む。解決する工程は、その文書の工程にする
   - P1 と P2 のうち人の判断が要るものは、要確認として文書に積む
   - P1 で直すかの判断が割れたら、直さずに理由を報告に書く
   - P2 は直すかを任意に決める
5. check が通るまで直し、`python3 <plugin>/scripts/specdoc.py html <文書>` で HTML を出す

## 報告

- 回した往復の数
- 直した指摘の件数
- 直さなかった P1 とその理由、要確認にした指摘
- 最後の `<文書名>.review.md` のパス
