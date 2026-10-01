# M3：新規隔離DB・HTTPS検証の実行範囲

2026-10-01。準備のみ。DB作成・起動は未実施。[M3記録](M3_実装記録.md)のコード検査後、本人の対象確認を得て実行する。AGENTS.mdの「過去の許可・環境の利用期限を延長しない」と、計画6節のDB対象確認に従い、M2環境は再利用しない。

- 新規コンテナ `tech0-pos-m3-mysql`、volume `tech0-pos-m3-mysql-data`、DB `pos_validation`。既存のM2資源は変更しない。同名資源が既にあれば停止して確認する。
- 既存の固定済みMySQL 8.4イメージを使用。loopback `127.0.0.1:3307`、TLS必須。新規秘密値・localhost用TLSをGit除外 `.m3-local/` へ作成（700／600）。端末の証明書信頼設定は変更しない。
- DDL16表、専用3アカウントの最小権限、架空担当者・会員・商品・税・値引きと初期価格履歴を投入。保守停止の照合後にこの新規レジだけ解除。
- ローカルHTTPS `127.0.0.1:8443/8444` で Next.js→FastAPI→MySQLを確認。検証クライアントだけに専用CAを指定。LAN・トンネル・公開・カメラ・Azure・課金・commit／pushは対象外。
- 会員／非会員、数量・削除、値引き・混在税、空拒否・商品あり0円、一括保存・同要求再送、次取引再送を検査。架空マスタ・価格履歴の更新はこの新規DB内でTXに限定し、保存済み・保持条件の不変を照合する。
- 終了時は今回のアプリプロセスと新規コンテナのみ停止。非待受・コンテナ停止を確認し、volumeと証跡を保持。DROP・削除・M2起動は行わない。障害はROLLBACK・別接続照合とし、自動TX再送しない。

共通準備器へ `M2_LOCAL_PROFILE=m3` を指定し、既存M2用とは別の名前・保存先を固定する。以下は実行許可後のみ：

```sh
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m2_local_prepare.py
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m2_local_mysql.py
# ready → bootstrap → schema → grants → seed → release の順に、各成功を確認して実行
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m2_local_db.py ready
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m2_local_servers.py start
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m3_verify_https.py --run
M2_LOCAL_PROFILE=m3 backend/.venv/bin/python tools/m2_local_servers.py stop
# 新規コンテナのみ停止しvolumeを保持
# docker stop tech0-pos-m3-mysql
```

実ブラウザ・両端末の本人確認、実通信断／COMMIT喪失・競合の全条件、Azure受入はこのプログラム検証とは別判定。
