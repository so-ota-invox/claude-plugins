# claude-plugins

Claude Code の plugin marketplace。

## 導入

```
/plugin marketplace add so-ota-invox/claude-plugins
```

## 収録している plugin

- `sdd`: 要件定義書・基本設計書・実装プランを決まった型で書き、番号の対応と見出しの構造を機械で照合する。型は `plugins/sdd/formats/`、照合と HTML への変換は `plugins/sdd/scripts/specdoc.py`（Python 3.9 以上、標準ライブラリだけで動く。macOS と Linux（WSL を含む）で動かす。Windows では動作を保証しない）
  - skill: `/sdd:requirements`（要件定義書の起草）、`/sdd:review`（文書の review）、`/sdd:refine`（review と反映のくり返し）、`/sdd:approve`（承認）
  - 使うリポジトリの `.gitignore` と `.gitattributes` に、`plugins/sdd/formats/common.md` に挙げた行を足す。0.2.0 で `.gitignore` の `specs/**/*.review.md` が増えた

```
/plugin install sdd@so-ota-plugins
```

## ライセンス

MIT
