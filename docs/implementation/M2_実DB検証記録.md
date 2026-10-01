# M2：実MySQL・HTTPS検証記録

2026-09-28の実DB検証記録。実MySQLとHTTPS中継でM2の初回経路を確認した。以下の未確認記述は当時の範囲。2026-10-01に両Chrome実機・空カート保持・手動復旧と旧値拒否・M2限定独立レビューを追加確認し、M2の実装・限定検証を完了した。本人の段階承認は未記録。[最新のM2結果・終了状態・後続の未確認範囲](M2_実装記録.md)を参照。業務範囲・API契約・DDLの変更なし。

## 実行許可と証明書の扱い

本人の「OK.Docker起動して検証に進んでよい」に基づき、新規隔離環境を作成した。続いて証明書登録のポップアップについて確認があり、本人から「信頼設定を変更せず進める」と指定された。

macOSログインキーチェーンへの信頼設定コマンドはOS承認がキャンセルされ、`SecTrustSettingsSetTrustSettings: The authorization was canceled by the user.`で失敗。初回のsandbox内照会では非検出だったが、終了時の権限付き照会で公開CA証明書だけが残っていることが判明した。今回生成したCAとのDER完全一致とSHA-256を確認し、該当証明書だけを削除。権限付きで再照会して未登録を確認した。ユーザーの信頼設定に今回のCAは存在せず、Chromeの証明書警告を無視する設定も行っていない。**終了時にはCA登録を残していない。** この経緯は本人へ作業中に訂正・説明した。

以降は検証プログラムのSSLContextとNodeの`NODE_EXTRA_CA_CERTS`に今回のCAだけを指定し、証明書・ホスト名検証を維持した。これはChrome／iPhoneの実機Cookie検証を代替しない。新規秘密情報とCA／鍵はGit除外の`.m2-local/`にのみ置き、認証／復帰Cookie値は検証プロセス内だけで扱った。

## 実環境

| 項目 | 実測・実行内容 |
|---|---|
| Docker | Desktopエンジン29.7.2。旧`pos-validation-mysql`と`pos-validation_mysql-data`は停止状態のまま保持 |
| 新規MySQL | 8.4.11／arm64。コンテナ`tech0-pos-m2-mysql`、volume`tech0-pos-m2-mysql-data` |
| イメージ固定 | 公式`mysql:8.4`を取得しdigest `sha256:0744ee5ef89ce6ccfa13de3e579fe6b9e27f93dd70da9c06d2c908b1b193fb8d`で起動。[環境証跡](evidence/m2/mysql-environment.json) |
| ネットワーク | DB=`127.0.0.1:3307`、フロント=`https://localhost:8443`、API=`https://127.0.0.1:8444`。LAN公開なし |
| TLS | 専用CA／localhost・127.0.0.1 SAN、30日証明書。MySQL require_secure_transport=ON、接続暗号TLS_AES_256_GCM_SHA384。証明書・ホスト名検証有効 |
| DB作成・DDL | `pos_validation`を新規作成。DDL担当で16 CREATE＋1 ALTERを順次適用、全17文の成功を確認。対象DDLファイルは変更なし |
| 初期投入 | 管理接続で担当者2・会員2・税率2・商品2・初期価格履歴2・値引き1・REGISTER1を1TXで投入。全表件数照合後COMMIT |
| 権限 | アプリ・マスタ・DDLで別アカウント。アプリは表単位。初回REGISTER／STAFF追加権限は投入後に解除。[最終DB照合](evidence/m2/mysql-snapshot.json) |
| 保守停止 | TRUEで認証／読取と変更拒否を先に検査した後、対象レジ1だけ解除。初回開始前の状態を照合し、変更1件で確定 |

手順の具体化として、まずDDL用のDB単位権限だけを与えて表を作成し、その後に全表のGRANTを適用した。表単位GRANTを表作成前に一括実行する順序にはしない。通常アプリへ管理接続を渡していない。

## 条件別の結果

以下の件数は検査グループ数。TC群全体の完了数ではない。

| 分類 | 確認した条件 | 結果・証跡 |
|---|---|---|
| DB構造・制約・権限・TLS：19グループ | 設計確認SQLの実行、16表／列／FK・CHECKの取得、代表的な一意／FK／必須／空文字／年齢／税率／状態／コードの拒否、アプリのマスタ更新・売上訂正／削除・レジINSERT・カートDELETE・DDL拒否、非TLS・不信CA拒否、READ ONLY拒否、プール隔離水準復帰 | 全て合格。[検査結果](evidence/m2/mysql-checks.json)／[物理スキーマ](evidence/m2/mysql-schema.json) |
| HTTPS保守中：6グループ | 未認証、全M2更新入口のOrigin／専用ヘッダー、バックエンド直結、中継・入力、実ログイン、保守中の開始拒否 | 全て合格。[結果](evidence/m2/https-maintenance.json) |
| HTTPS初回経路：15グループ | 上記共通拒否、同時start、Cookie未確認／消失、confirm応答を捨ててGET照合、同時carts、同一カート、DBハッシュ、別担当者、商品／会員GET、再認証、同時5失敗、認証・照会で復帰期限不延長 | 全て合格。[結果](evidence/m2/https-startup.json) |
| 実TX・境界：7グループ | 認証8時間直前／到達、復帰24時間直前／到達・手動許可起算、失敗窓下端・制限解除時刻、所属／参照不整合拒否、実REGISTERロック待切れ503、別接続更新を挟む2SELECTの同一スナップショット、試験変更ROLLBACK後の保持 | 全て合格。[結果](evidence/m2/mysql-transactions.json) |
| DB停止・再起動 | DB停止中のauth status／loginが503でCookieなし。再起動後にREGISTER・context・カート・認証／制限の件数と参照・照合値が一致。未認証照会は401へ戻る | 合格。[結果](evidence/m2/mysql-restart.json) |

期限境界はDBのUTC取得値を基準に、同じ接続内の試験行と判定時刻を設定して検査した。8時間／24時間の実時間待機ではない。境界用Cookie照合値・セッション・期限・失敗記録・参照不整合は1TX内だけで作り、全体をROLLBACKした。照会一貫性試験のmaintenance_hold一時変更は試験後に元へ戻した。

HTTPS確認は実Next.js→実FastAPI→実MySQLを通したHTTPクライアント試験。応答破棄のケースは取得した応答を採用しないことで照合分岐を確認したもので、OSレベルのパケット切断やCOMMIT応答喪失注入とは区別する。端末JSからのCookie読取不可・host-only送信範囲・ブラウザ再起動保持は未確認。

## 検証中の修正と回帰検査

- アプリ用アカウントの`REQUIRE SSL`により非TLS接続は1045で拒否された。試験は3159だけでなくこの正しい拒否分類を受け入れるよう修正。TLS要件を緩和していない。
- 認証Cookieの残時間計算について、セッションINSERT／COMMITに費やす時間も差し引くよう、計時開始をDB書込前へ移した。回帰単体試験を追加。認証DBの8時間固定は変更なし。
- 環境作成・HTTPS起動・DB照合・結合試験は`tools/m2_local_*.py`、`tools/m2_https.mjs`、`tools/m2_verify_*.py`へ記録した。初期作成とstartup試験は一度限りの前提を持つ。既存データを巻き戻して再実行しない。
- 最終`make check`はPython／フロントlint・型検査、バックエンド48件・中継5件、OpenAPI静的検証を確認。[最終検査ログ](evidence/m2/live-check.log)。本番buildは[最終buildログ](evidence/m2/live-build.log)。

## 終了状態と残り

終了時は今回のHTTPSプロセスとM2コンテナを停止し、3307／8443／8444の非応答を確認する。volume・証跡・秘密情報は保持し、削除していない。Docker Desktop自体は起動状態を維持する。停止結果は[終了確認](evidence/m2/shutdown.json)。

検証用のカートと開始済みcontextは保持した。Cookieはクライアントのプロセスメモリだけで扱い、プロセス終了後はブラウザ操作用に引き継げない。次に起動しても無条件の初期化・新カート作成をしない。再使用する場合は既存の手動復帰手順による対象確認、または別名の新規隔離検証環境を用いる。アプリにCookie再発行用の復旧APIは追加していない。

未確認：Mac／iPhoneのChromeでの実画面・Cookie保持、Q04の手動Cookie修復、TC-13全制約の網羅、未実装M3／M4の保存・状態別復帰、COMMIT応答喪失、Azure配置・性能・ログ／バックアップ運用、独立レビュー、本人主要フロー確認。実DB試験の合格をアプリ全体の受入へ読み替えない。

参照した公式資料：[MySQL公式イメージとファイル経由の秘密値](https://hub.docker.com/_/mysql)、[MySQL TLS設定](https://dev.mysql.com/doc/refman/8.4/en/using-encrypted-connections.html)、[Next.js custom server](https://nextjs.org/docs/app/guides/custom-server)。custom HTTPS serverはローカル検証専用で、Azure配置方式を変更しない。
