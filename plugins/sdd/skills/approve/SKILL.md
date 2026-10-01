---
name: approve
description: sdd の文書 1 本を承認する。上流と要確認を照合し、通れば状態を approved にして承認者を書き、その文書だけを commit する。ユーザーが承認をはっきり示したときだけ使う。
argument-hint: <文書のパス>
disable-model-invocation: true
---

# approve

ユーザーが承認をはっきり示したときだけ動く。自分の判断でこの skill を使わない。`<plugin>` は sdd plugin のディレクトリ（この SKILL.md の 2 つ上）の絶対パス。

## 手順

1. 呼び出しで渡されたのが文書 2 本以上なら、全部を承認するか一部でよいかを聞き、1 本ずつ行う
2. 文書の工程は、ファイル名で決まる（requirements.md は `requirements`、design.md は `design`、plan.md は `plan`）
3. 状態がもう `approved` なら、そう伝えて止まる
4. 照合する。上流の文書は、管理情報の「上流」の各行の `@` より前のパス。エラーが出たら、状態を変えずにエラーを示して止まる
   - `python3 <plugin>/scripts/specdoc.py check --gate <工程> <文書> <上流の文書>...`
   - 上流があれば `python3 <plugin>/scripts/specdoc.py check --approved <上流の文書>...`
5. `git config user.name` で名前を得る。空なら止まる
6. 状態を `approved` にし、その次の行に `- 承認者: <名前>` を書く
7. `python3 <plugin>/scripts/specdoc.py check <文書>` を通し、`python3 <plugin>/scripts/specdoc.py html <文書>` で HTML を出す
8. 文書だけを commit する（`git add -- <文書>` の後に `git commit -m "承認: <文書>" -- <文書>`）。リポジトリにコミットメッセージの決まりがあれば、それに合わせる。push はしない
