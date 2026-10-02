# agent の起動

skill と手順が agent を起動するときに従う。`<plugin>` は sdd plugin のディレクトリ（このファイルの 1 つ上）の絶対パス。

- Claude Code では `sdd:<名前>` の agent を起動する
- ほかの環境では、subagent に `<plugin>/agents/<名前>.md` を読ませ、その役割で動かす。subagent を使えなければ、その役割を自分で順に行い、そうしたことを報告に書く
- agent には、`<plugin>/agents/<名前>.md` の「受け取るもの」だけを渡す。起草の経緯は渡さない
- agent が `<plugin>/agents/<名前>.md` に書いた返すものを返さなければ、その名前と返したものを示して止まる
