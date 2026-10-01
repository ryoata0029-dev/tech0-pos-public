# M2：隔離DB・HTTPSの実行手順

2026-09-28。新規MySQL・HTTPS中継の構築とプログラムからの検証を実行済み。現在の実結果は[M2実DB検証記録](M2_実DB検証記録.md)を参照。以下は初期適用の手順で、既存の検証DBへ再適用しない。対象は[計画M2](../../プロジェクト計画.md)と[設定別紙3〜4節](../../設計設定・DB運用.md)。既存環境の起動・再利用は含めない。

## 対象と実行条件

- 新規コンテナ：`tech0-pos-m2-mysql`、新規volume：`tech0-pos-m2-mysql-data`、DB：`pos_validation`。
- MySQL 8.4系。公式イメージのパッチ版・digestを取得して作業記録へ固定してから起動。実際に取得・起動した版とdigestは実DB検証記録に保持。
- DB公開先は`127.0.0.1:3307`のみ。`require_secure_transport=ON`。専用CAとlocalhost／127.0.0.1をSANに持つサーバー証明書を用意する。アプリはCA・ホスト名検証を必須とし、TLSを無効にしない。
- 秘密値と証明書は新規のGit除外領域`.m2-local/`だけへ置く。既存`.env`・旧検証フォルダを読み込まない。ファイル権限600、ディレクトリ700。平文パスワードをCLI引数・履歴・作業記録へ書かない。
- HTTPS確認はまずMacのChromeの専用ホストで行う。ローカルAPIもHTTPSで中継する。本人の後続指示により端末の信頼設定は変更しない。現在はHTTP検証クライアントだけにCAを指定する。LAN公開・iPhone信頼設定・実機利用は接続先と利用枠を確認してから行う。
- Azure・課金・IAM・カメラ・公開・commit／pushはこの作業対象に含めない。

`開発環境.md`の「M2の検証環境案と開始条件」は環境作成・端末信頼設定を対象確認後に実行する規定。今回のM2コーディング依頼ではコードとローカル検査を進めた。次の環境操作はこの対象を示して確認する。Docker状態の読取は追加権限を得て実施し、エンジン停止を確認した。

## 準備・適用

1. Dockerの稼働と空き容量を確認。上記コンテナ・volume名、ポート3307が未使用であることを確認する。同名資源が存在したら流用・削除せず停止する。
2. 固定したMySQLイメージを取得し、上記のネットワーク／TLS／保存先で新規起動する。管理用資格情報は新規生成し、Docker secrets等のファイル経由で渡す。初期認証を無効にしない。
3. 認証済み管理接続で`pos_validation`を空で作成する。通常アプリ`pos_app`、マスタ保守`pos_master`、DDL用`pos_schema`をそれぞれ新規作成し、全アカウントを`REQUIRE SSL`にする。パスワードの平文は成果物へ入れない。アカウント・DB作成自体は別の環境管理操作。
4. 先にDDL用アカウントへ対象DBのSELECT／CREATE／ALTER／INDEX／REFERENCESだけを付与する。表作成後に[最小権限SQL](../../backend/sql/m2_grants.sql)を対象・ユーザーと照合して適用し、全3アカウントのSHOW GRANTSを照合する。`%`はloopbackだけに公開した専用コンテナ内の接続用で、Azureへ転用しない。通常アプリは全16表SELECT、許可表だけ更新、CART_LINE以外DELETEなし、マスタ更新・売上UPDATE／DELETE・DDLなし。
5. 環境変数へDDL用接続を設定し、下記`schema`を実行。DDL17文（16 CREATE＋循環参照のALTER）を順次実行し、成功した文番号を記録する。既存表が1つでもあれば実行を拒否。途中失敗・応答不明では再実行せずSHOW CREATE TABLE／information_schemaで照合する。
6. [設計確認SQL](../../設計確認.sql)で版・DB・UTC・厳格モード・16表・FK／CHECK・照合順を確認する。TLS状態もSHOW SESSION STATUSのSsl_cipher等で確認する。
7. `seed`は初期投入担当として認証した環境管理接続で1回だけ行う。全16表の空確認と投入後件数照合にSELECT権限が必要なため、通常の`pos_master`単独では実行しない。管理接続をアプリへ設定しない。担当者2名の演習用パスワードはgetpassで入力し、採用Argon2idでハッシュ化してTX内に渡す。
8. REGISTER=1／UNSTARTED／maintenance_hold=TRUE→担当者2・会員2・税率2→商品2＋初期価格履歴2→値引き1を1TXで投入、全表件数を読取照合後COMMIT。残りの9表は0件。実在データ・UPSERT・初期化処理なし。[架空データ](../../backend/fixtures/m2.json)の会員6属性・UTF-8容量・年齢の整数範囲は投入前に検証する。
9. [初回追加権限解除SQL](../../backend/sql/m2_revoke_initial.sql)でREGISTER／STAFFの初回投入権限を`pos_master`から外す。通常アプリでSELECT・許可DML／禁止DDL・マスタUPDATE・売上UPDATE／DELETEを別々に実証する。禁止操作は隔離DBでROLLBACK前提の検証として記録する。
10. アプリ設定を`pos_app`に切り替える。保守停止のまま認証200／401／503と読取を検査。新規開始・confirm・カート生成は拒否されることを確認する。
11. 対象がこの検証DBであることを再確認し、本人の実行許可範囲内でREGISTER=1のmaintenance_holdだけをFALSEにする。変更前TRUE・更新1件・変更後FALSEを照合してCOMMITする。UNSTARTEDの書戻しやデータ削除は行わない。
12. HTTPSブラウザ→Next.js→FastAPI→MySQLでログイン→start→status→confirm→初回carts→再読込を確認。同時開始・同時失敗5回・8時間境界・Cookie消失・応答断・旧セッション・別担当者・24時間境界はTC-22・25〜29に従い条件別記録。初回以外の保存／復帰状態はM3／M4で拡張する。

リポジトリ直下で実行する。既存ファイルを自動sourceしない。下記の更新コマンドは環境作成・対象確認後のみ。

```sh
# 接続・変更なし。現在実施済みの準備検査。
backend/.venv/bin/python tools/m2_database.py validate

# 個別の実行環境を設定後、DDL担当で空スキーマへ適用。
backend/.venv/bin/python tools/m2_database.py schema --target pos_validation

# 初期投入担当の管理接続で1回だけ。演習用パスワードは非表示入力。
backend/.venv/bin/python tools/m2_database.py seed --target pos_validation
```

設定は[backend設定例](../../backend/.env.example)の各変数。`POS_DB_HOST`はlocalhostまたは127.0.0.1、port=3307、DB=pos_validationだけを書込対象として許可する。フロントの許可Originと中継秘密値も設定する。専用スクリプトは初期適用専用で、マスタ更新・手動復旧・汎用修復の機能を持たない。

## 停止・戻し

- 起動した新規アプリプロセスと新規コンテナだけを停止し、volumeを残す。既存Docker資源へ操作しない。
- 未確定DMLはROLLBACK。COMMIT応答不明は未保存と断定せず、認証済み別接続で対象・件数・内容を照合する。自動再送しない。
- DDLは暗黙COMMITなのでロールバックを約束しない。成功位置を保持し、表のDROP・DB削除・volume削除・全体再適用を行わない。
- 端末信頼設定の解除、新規証明書・volumeの削除は、対象と影響を確認してから別途行う。

## 初期準備時の未確認（現在の結果は実DB検証記録を参照）

MySQLのイメージdigest、起動、DDL受理、FK／CHECK発動、権限拒否、SQLリポジトリの実行、TLS接続、DBロック競合、実ブラウザのCookie保持・JS読取不可、Mac／iPhoneの端末条件は未検証。オフライン試験・モックはこれらの代替ではない。
