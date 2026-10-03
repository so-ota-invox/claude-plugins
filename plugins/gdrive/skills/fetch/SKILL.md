---
name: fetch
description: Google Drive のファイル（ドキュメント・スプレッドシート・スライド・PDF など）の URL やファイル名を渡され、その中身を読むときに使う。テキストだけでなく PDF と Office 形式でも書き出し、図・グラフ・画像の中の文字・スピーカーノートまで漏れなく取る。
argument-hint: <URL かファイル名>
---

# fetch

Google Drive の MCP のツールで、ファイルの中身を漏れなく取る。テキストを取るツールは画像を返さないので、テキストだけで済ませない。書き出したファイルは、リポジトリの外の一時ディレクトリに置き、commit しない。

## 1. ファイルを特定する

- URL の `/d/<ID>/` から ID を取り出す。URL に付いている `tab=` や `slide=` は無視してよい（取得されるのはファイル全体）
- 手がかりが名前だけなら `search_files` で探す。0 件なら、探した語を示して止まる。複数件なら、候補を示してユーザーに選んでもらう
- `get_file_metadata` で mimeType を確かめる
  - フォルダ（`application/vnd.google-apps.folder`）なら、中身を読まずに、フォルダであることを報告して止まる
  - 手順 4 と 5 のどちらにも当たらない形式（図形描画・フォームなど）は、手順 2 と 3 だけ行う【未検証】

## 2. テキストを取る

- `read_file_content` を呼ぶ。コメントも要るなら `includeComments: true` を付ける
- ドキュメントは、全タブが `# タブ名` の見出し付きで返る
- 画像は空行になるだけで、取れない。画像だけでできたスライドでは、区切り線 `-----` しか返らない
- テキストが空でも、中身が無いとは判断しない。手順 3 と 4 に進む

## 3. 見た目を取る（PDF）

- `download_file_content` を `exportMimeType: application/pdf` で呼ぶ
- 返り値を手順 6 のとおり `.pdf` に保存し、Read の `pages` で 20 ページずつ、最後のページまで読む
- 図形、グラフ、画像の中の文字、レイアウトは、ここで確かめる

## 4. 埋め込み画像を原寸で取る（Office 形式）

- `download_file_content` の `exportMimeType` に次を指定する
  - スプレッドシート: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`（保存先は `.xlsx`）
  - ドキュメント: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`（保存先は `.docx`）
  - スライド: `application/vnd.openxmlformats-officedocument.presentationml.presentation`（保存先は `.pptx`）
- `File too large for export.` が出たら、PDF（手順 3）だけで済ませ、そのことを報告する
- 返り値を手順 6 のとおり保存する。zip として壊れていないかと、画像・図形とグラフ・スピーカーノートのフォルダの中身が出る。中の XML は、`python3 -m zipfile -e <保存したファイル> <展開先>` で同じ一時ディレクトリに展開して読む（パスの `..` と先頭の `/` を取り除いて展開し、シンボリックリンクを作らない）
- 画像があるかどうかは、画像のフォルダ（`xl/media/`・`word/media/`・`ppt/media/`）の有無だけで決める
- 画像の置き場所は、本文の XML の `r:embed="rIdN"` を `_rels/*.rels` の `Target` と突き合わせて確定する。ファイル名の番号は本文の順ではない
- スプレッドシートの図形とグラフは `xl/drawings/*.xml` にある。中身が空の `<xdr:wsDr/>` なら、図形もグラフも無い
- スライドのスピーカーノートは `ppt/notesSlides/` から取る

## 5. ネイティブ形式でないファイル【未検証】

- アップロードされた PDF・画像・Office ファイルは、`exportMimeType` を付けずに `download_file_content` を呼ぶ。PDF と画像は `read_file_content` でも読める（ツールの説明に対応形式として書かれている）

## 6. 書き出しの返り値を保存する

- 大きいファイルは、返り値が tool-results のファイルに保存され、そのパスが返る。そのパスを `<入力>` にする
- 小さいファイルは、base64 が会話にそのまま返る。base64 だけを一時ディレクトリのファイルに書き、そのファイルを `<入力>` にする。手で書き写した base64 は崩れやすい。次のコマンドがエラーを出したら、書き出しをもう一度呼んでファイルで受け取る
- 次のコマンドで、デコードして `<出力>` に保存する。拡張子で中身の形を確かめるので、`<出力>` の拡張子は手順 3 と 4 のとおりにする

  ```
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/drivefile.py decode <入力> <出力>
  ```

- 終了コードが 0 でなければ、`<出力>` を使わずに、書き出しからやり直す。やり直しても 0 でなければ、その形式は「取得に失敗した」として手順 7 で報告する

## 7. 漏れが無いか確かめる

- 読んだファイルの名前と ID を書く
- テキスト・PDF・画像・ノートのそれぞれについて、取れた / 存在しない / 取得に失敗した、のどれかを報告する
- PDF は、何ページ中何ページ読んだかを書く

## 未検証

- 手順 1: 手順 4 と 5 のどちらにも当たらない形式の扱い
- 手順 5: アップロードされた PDF・画像・Office ファイルの取得
- スピーカーノートが `read_file_content` の返り値に含まれるかどうか
- 書き出しの返り値の base64 が、標準の形式（`+` と `/` を使い、`=` で埋める）かどうか
