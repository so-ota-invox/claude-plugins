---
name: approve
description: sdd の文書 1 本を承認する。上流と要確認を照合し、通れば状態を approved にして承認者を書き、その文書だけを commit する。ユーザーが承認をはっきり示したときだけ使う。
argument-hint: <文書のパス>
disable-model-invocation: true
---

# approve

ユーザーが承認をはっきり示したときだけ動く。自分の判断でこの skill を使わない。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

## 手順

1. 文書は 1 本だけ受け取る。2 本以上を渡されたら、1 本ずつ呼ぶよう伝えて止まる
2. 文書の工程は、ファイル名で決まる（requirements.md は `requirements`、design.md は `design`、plan.md は `plan`）
3. 状態がもう `approved` なら、そう伝えて止まる。その文書に commit していない変更があれば、前の approve が commit の前に止まったおそれがあることと、`draft` に戻して承認者を消してから approve し直すことも伝える
4. 照合する。エラーが出たら、状態を変えずにエラーを示して止まる
   - `python3 <plugin>/scripts/specdoc.py check --gate <工程> <文書>`。上流の各行が決まった文書を指していることも、ここで確かめる
   - 上流があれば `python3 <plugin>/scripts/specdoc.py check --gate <工程> --approved <上流の文書>...`。上流の文書は、管理情報の「上流」の各行の `@` より前のパス
   - 実装プランなら、要件定義書 `specs/<id>-<slug>/requirements.md` にも `python3 <plugin>/scripts/specdoc.py check --gate plan <要件定義書>` を当てる。工程 `plan` の要確認は要件定義書にも書けるため
5. `git config user.name` で名前を得る。空なら止まる
6. 状態を `approved` にし、その次の行に `- 承認者: <名前>` を書く
7. `python3 <plugin>/scripts/specdoc.py check <文書>` を通し、`python3 <plugin>/scripts/specdoc.py html <文書>` で HTML を出す
8. 文書だけを commit する（`git add -- <文書>` の後に `git commit -m "承認: <文書>" -- <文書>`）。リポジトリにコミットメッセージの決まりがあれば、それに合わせる。push はしない

7・8 で失敗したら、6 で書いた状態と承認者を元に戻し、8 で index に足していれば `git restore --staged -- <文書>` で外し、HTML を出していれば出し直してから、エラーを示して止まる。
