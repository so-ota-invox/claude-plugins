# claude-plugins

Claude Code の plugin marketplace。

## 導入

```
/plugin marketplace add so-ota-invox/claude-plugins
```

## 収録している plugin

- `sdd`: 要件定義書・基本設計書・実装プランを決まった型で書き、番号の対応と見出しの構造を機械で照合する。型は `plugins/sdd/formats/`、照合と HTML への変換は `plugins/sdd/scripts/specdoc.py`（Python 3.9 以上、標準ライブラリだけで動く）

```
/plugin install sdd@so-ota-plugins
```

## ライセンス

MIT
