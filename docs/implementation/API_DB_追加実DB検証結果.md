# API・DB追加実検証結果

2026-10-04。本人の「続けて同時並行で進めよう。iPhone・カメラもOK」に基づく追加作業。[追加スクリプト](../../tools/parallel_next_db_verify.py)を主担当が明示実行し、**優先1〜4の8条件群が実ASGI＋実MySQLで成功。7件の専用購入は再送でも各1件。優先5も実Repository＋実MySQLで期間4境界と、未COMMIT／COMMIT後の関連マスタ読取が成功。** 本担当と別担当の独立読取でも保存額・拒否保持・価格履歴・接続分離・source hashを照合した。優先5は明示時刻の単一SQL条件に限定し、通常HTTPの時計・新しいcart行は未検証。M7受入・Azure・HTTPS／端末の合格を示さない。

## 根拠と分離方式

[優先条件1〜5](API_DB_残試験_追加結果.md)、[TC06〜17](../tests/テストケース.md#tc-06)、[金額例](../requirements/受入条件_現行.md#sec-5-2)、[境界](../requirements/受入条件_現行.md#sec-5-4)、[保存・価格履歴](../requirements/受入条件_現行.md#r-topic-29)、[保存失敗](../requirements/受入条件_現行.md#r-topic-32)、[設計4.3](../design/画面と業務処理.md#sec-4-3)、[現行DDL](../../設計スキーマ.sql)・[診断SQL](../../設計確認.sql)を参照した。

現行REGISTERはCHECK(register_id=1)、認証・業務処理も1レジを固定している。同じDB内で別staff／Cookieを作るだけではactive_sessionやcurrent_cartを分離できない。主担当と調整し、固定profile `parallel-next` の同じMySQLコンテナに専用schema `pos_api_validation` を新設する。iPhone／通常HTTPSは `pos_validation` を使い、本試験は独立したREGISTER=1・STAFF_API・MEMBER_API・API_*商品・専用Cookieを使う。

- 固定container `tech0-pos-parallel-next-mysql`、専用volume `tech0-pos-parallel-next-mysql-data`、DB公開 `127.0.0.1:3307`、MySQL8.4、TLS必須・証明書／接続先名検証。
- 固定DBアカウント `pos_api_app`／`pos_api_master`／`pos_api_schema`。既存隔離秘密ファイルの対応passwordをプロセス内で再利用し、値をログ・証跡へ出さない。STAFF_APIは架空の専用IDで、既存架空STAFF_A用passwordから独立したArgon2 hashを生成する。
- 実FastAPI middleware・API・サービス・SQLリポジトリをASGIで呼び、専用DBの実MySQLへ接続する。**HTTPサーバー／Next.js中継／実HTTPS受信／実ブラウザの試験ではない。** 8443／8444のphoneサーバーへAPI要求を送らない。
- `--prepare` はfresh schema・専用accountの不存在を確認してから既存DDLとtable単位GRANTを固定置換し、専用架空fixtureを投入する。既存schema/accountのDROP・reset・再構築はしない。DDL途中失敗は部分状態を保持し、主担当の確認へ止める。
- `--run` は専用REGISTER未開始・CART0件・専用商品／候補を確認して一度だけ実行。Cookieはプロセス内だけ。各観測は新規の物理TLS接続・REPEATABLE READ読取TXで取得し、書込接続の見かけの値を確定成功へ読み替えない。
- 独立schemaによる分離と、phoneカートの前後不変照合は別の証拠。phone側の照合は主担当が行い、準備コードの `phone_modified=false` だけで実際の不変を証明しない。

## 実行条件と手順

主担当だけが、新規parallel-next環境の作成・起動・秘密値準備・以下の明示実行を行う。共有helpers・アプリ・本番依存は本担当が変更していない。

```sh
python3 tools/parallel_next_db_verify.py
M2_LOCAL_PROFILE=parallel-next backend/.venv/bin/python tools/parallel_next_db_verify.py --prepare
M2_LOCAL_PROFILE=parallel-next backend/.venv/bin/python tools/parallel_next_db_verify.py --run
```

前提は `.parallel-next-local/secrets.json`（private mode、root／pos_app／pos_master／pos_schema／STAFF_A／relayの既存shape）、`.parallel-next-local/tls/ca.crt`、固定containerが実稼働、一般／slowログ無効、既存の準備／実行証跡がないこと。profile登録・container／volume／TLS等は主担当の環境作業とする。

証跡は[prepare](evidence/parallel-next/api-db-prepare.json)と[run](evidence/parallel-next/api-db-run.json)。主担当が2026-10-04 07:04 UTCに実行した。既存ファイルがあれば上書きしない。実行途中の失敗はエラー型・数値DBコード・ソース行だけを保存して止め、SQLパラメーター・password・Cookie・例外文字列を表示しない。部分DDL・一部保存済みcart・結果不明COMMITを自動再実行せず、主担当が保存状態を照合する。

実行前の[source manifest](evidence/parallel-next/application-source-manifest.json)28パス（backend app全py・DDL・GRANT／REVOKE・診断SQL・OpenAPI）と現在sourceのSHA256一致を読取確認。[script凍結記録](evidence/parallel-next/api-script-before-execution.json)・prepare・run・[保存した第一実行原本](evidence/parallel-next/parallel_next_db_verify.py.executed.txt)のhashは `2e3f29228c7ffda47344b45ec0b1de00c450d2051dad538eb78dfc1d028096a8` で一致した。実行後の書式修正により現在scriptのhashは別値となった。実DB結果は保存した実行原本に対応する。

[phone用DB前後比較](evidence/parallel-next/comparison-phone-after-api.json)は9集合すべて一致、REGISTER=UNSTARTED・cart0・売上0を保持。これはこのDB試験前後の分離を確認した証拠で、phoneの主要操作・カメラ受入の証拠ではない。

## 優先1〜4の検証条件と成功結果

| 対応 | 専用fixture／操作 | 独立した期待値と観測 |
|---|---|---|
| TC06 同額候補 | API_TIE：103円／税10％、小さい数値IDの割合10％、後のIDの定額10円。会員指定→保存→同購入再送。 | 割合条件IDを選択、候補10円／実10円、小計93・税9・税込102。PURCHASE_LINEのdiscount_snapshotと売上・明細・税行各1件を別TLSで確認。実SQLの候補列はID順であり、メモリ試験の両入力順を重複して実証したとは扱わない。 |
| TC06／10 上限前の選択と0円 | API_CAP：103円／税10％、定額120円／130円。会員指定→保存→同購入再送。 | 候補130円の条件を選択、実値引き103円。0円でも売上1・明細1・税10％行1／税0を保存。選択を実額103円で同順位に丸めない。 |
| TC08 最大額超過 | API_MAX：単価999999999999円／税0、数量1→数量2。拒否→同要求再送→数量1を明示購入。 | 422 AMOUNT_INVALID、元cart／版／明細／業務起算不変・Cookie更新0。REJECTED操作1件、適用版null。同再送は同拒否で操作増分0。その後最大1個の売上／明細／税行各1件を保存。全集計種別の金額超過を網羅したものではない。 |
| TC13 診断SQLの陽性対照とrollback | 正常保存したAPI_TIE cartで、売上totalだけ+1、税0の余分税行の2条件を別TXに注入。 | CHECKを無効化せず、同じ接続で現行診断SQLが対象cartを検出。各TXはfinallyでROLLBACK。別の新規TLS読取で元cart／明細／売上／税／操作／業務時刻が不変。未COMMIT変異を別接続のAPIが見た／503になった試験ではない。 |
| TC14 正常価格変更 | API_HISTORY_NORMAL：103円で保存後、SELECT FOR UPDATE→110円更新＋103→110の履歴INSERTを単一TXで確定。 | 初期NULL→103と103→110の履歴2件、商品110円。保存済みの103円／数量1／購入日時／担当者／明細／税は不変。 |
| TC14 同値更新 | API_HISTORY_SAME：103円で保存後、要求価格も103円としたmaster手順で一致を確認し書込を省略。 | 商品103円・履歴は初期1件のまま。これは局所の運用手順の同値省略を確認する条件で、存在しない管理APIの挙動を証明しない。 |
| TC14 履歴INSERT失敗 | API_HISTORY_FAIL：103円で保存後、110円UPDATEの同TX内で履歴changed_at=NULLをINSERTし実DB 1048を発生。 | 例外後にROLLBACKし、新規TLS接続で商品103円・履歴初期1件、保存済み103円条件／購入日時不変。失敗位置は履歴INSERTのNOT NULL違反で、全INSERT途中位置を網羅しない。 |
| TC14 COMMIT ACK未読 | API_HISTORY_ACK：103円で保存後、商品110円＋履歴INSERTのCOMMIT送信後、driverがACKを読む前に別TLS接続で確定を観測。socketを閉じOperationalError 2013にする。 | 書込と別のconnection_idで商品110円・履歴103→110が1件増分と観測してからACK未読故障を成立させる。価格UPDATEを自動再実行しない。最終新規TLS接続でも商品／履歴整合、購入済み103円と購入日時不変。実ネットワーク障害や管理UIの試験とは区別する。 |

価格履歴には現行実装に管理APIがないため、正常・同値・失敗・ACK未読は本スクリプトの局所単一TX手順を検証する。値更新と履歴を別確定する方式、購入済みsnapshotへの上書き、ACK未読から推測した再更新は行わない。専用app userで商品変更／売上訂正削除／cart削除／REGISTER投入／DDLが実DB1142になることも検査し、通常API成功とともに専用table権限を確認する。

上表の8条件群はいずれもrun成功記録と期待値が一致した。同額は条件ID1／RATE、上限前選択は条件ID4／AMOUNT。独立DBの売上・明細・税は93／102・税9、0／0・税0、999999999999／同額・税0を確認。MAX拒否のbefore／rejected／retryではcart・明細・業務時刻・売上不変、REJECTED操作1件だけ追加し再送増分0。履歴4条件の保存前後はcart・明細・売上・売上明細・税・操作・業務時刻の7集合が同一だった。

ACK未読はwriter connection56、確定observer57、最終観測58が独立し、observerと最終商品110円・履歴103→110の確定値が一致。正常は商品110／履歴2件、同値・失敗は商品103／履歴1件。専用appの禁止SQL6条件も全て1142だった。

別担当の実行後独立読取でも上記金額・拒否保持・履歴4群・ACK接続分離・phone9集合・source／script hash一致を確認し、重大な欠陥の指摘はなかった。診断rollbackはrun JSONに陽性検出・未COMMITのbooleanだけを保存し、生のbefore／after行集合は残していない。そのため**読取レビュー済みscriptの同接続陽性対照と別TLS7集合一致assertが通ったことの確認**であり、診断の生比較証跡をJSONから独立再構築できたとは扱わない。

## 優先5の実SQL結果と証拠の限界

現在の[SQLリポジトリ](../../backend/app/repositories/business.py)の `product_conditions(code, now)` は、商品・税率・有効候補を1つのSELECTでJOINし、`valid_from <= now AND now < valid_to` をバインドした時刻で判定する。優先5は主担当が[別専用スクリプト](../../tools/parallel_next_conditions_verify.py)を2026-10-04 07:09 UTCに実行し、[結果JSON](evidence/parallel-next/api-db-conditions.json)は `limited_sql_conditions_passed`／`completed=true`。通常HTTPで全境界／同時更新を実証したとは扱わない。

専用商品API_PERIOD（product_id8／condition_id5）の開始t=2030-01-01 00:00 UTC、終了u=2030-01-02 00:00 UTCに対し、実Repositoryのバインド時刻を以下の4値にして確認した。有効時の候補ID・開始終了も一致した。

| 明示入力UTC | 候補件数の期待／実値 | 候補ID |
|---|---|---|
| 2029-12-31 23:59:59.999999（t−1μs） | 0／0 | null |
| 2030-01-01 00:00:00（t） | 1／1 | 5 |
| 2030-01-01 23:59:59.999999（u−1μs） | 1／1 | 5 |
| 2030-01-02 00:00:00（u） | 0／0 | null |

実行日の時計は2026-10-04のままで、phoneプロセス・DB時計・通常HTTPを変更していない。これは実MySQLのSQL比較を明示入力で確認した証拠であり、通常APIがDB UTC時計の境界ちょうどに到達した証拠ではない。

関連マスタAPI_CONSISTENCY（product_id9／condition_id6）は、master writer connection71が旧103円／税率ID1・10％／10％候補から新500円／税率ID3・8％／50％候補と価格履歴を1TX内で変更した。**変更済み・未COMMITのwriterをeventで保持**している間の実Repository read connection70は旧一式だけ、COMMIT成功後にpoolをdisposeした新しい物理TLS read connection73は新一式だけを返した。いずれもREAD COMMITTED・同じ単一SELECTで候補ID6を維持した。

証跡時刻はwriter ready 07:09:27.695374 → 旧joined read .697638 → coordinator release .705344 → COMMIT ACK .706343 → 新joined read .713584（すべてUTC）の順。別のfresh TLS observer72／74でも確定商品103→500・履歴1→2（103→500増分1件）を確認した。履歴changed_atはINSERT時刻であり、COMMIT時刻の代用にしていない。SQL本文も証跡へ保存し、期間4件と旧／新読取でSHA256 `0d7aca663a7e8dffa957f1f788d4f0bff20caec07fdbf061f3e0d49d2d803cc3` が一致した。単なるsleepや偶然の同時送信から競合成立を推測していない。

[レビュー後の実行前凍結記録](evidence/parallel-next/sql-script-reviewed-before-execution.json)・実行JSON・[保存した第二実行原本](evidence/parallel-next/parallel_next_conditions_verify.py.executed.txt)はSHA256 `165a4fd25bfdfa49e9806b823a33195b6ed64df4755cec98dfbe9378508e0ca2` で一致。旧 `sql-script-before-execution.json` は接続ID補強前のレビュー前参照として保持し、実行版の根拠に使わない。現在scriptは実行後の書式版であり、実行原本とは区別する。

主担当が実DB実行後のbackend設定による最終RuffでE501×6／I001×1とformat差を検出し、[初回失敗記録](evidence/parallel-next/final-check-before-format.json)を保持した。実行原本を変更せず保存してから、コメント・docstring・文字列分割・import順・書式だけを修正した。[書式変更の来歴](evidence/parallel-next/script-format-provenance.json)はSQL文字列を含む正規化AST一致を記録する（位置情報とdocstringを除外し、連続import群の順を正規化）。**書式版ではDBを再実行していない。** 現在hashは第一 `1565941170e27a7389d93c797d48e1494c74ae82ce123ccac4ca581a84d4d871`、第二 `4a14185e1a072f07265eedb263e2bc0d4dc979fe1fb79985606b3ac3f0d768ad`。本担当も保存原本／現在ファイルの各hashを読取照合し、同じ正規化規則の独立AST比較で2本とも一致を確認した。

実行JSONの `original_before`／`original_after` を独立に比較し、元7cartの購入・明細・税・操作・業務状態と、既存7商品の価格／履歴がすべて不変。[phone用DB前後比較](evidence/parallel-next/comparison-phone-after-sql.json)も9集合すべて一致した。別担当の独立読取でも4境界・時刻順・接続ID・旧／新一式・履歴・元データ不変・hashを確認し、追加の重大欠陥はなかった。この前後一致は観測区間の分離証拠であり、phoneの操作成功を示さない。

この方式でもSQL内部の各JOIN読取を途中で停止した証明にはならず、1SELECTのMySQL snapshotとマスタ単一TXの境界に対する確認となる。初期／後続の混在、関連更新を別TXに分割したケース、全競合順序を網羅した合格へ拡張しない。通常HTTP／Cookie／新しいcart行への条件固定は未実施であり、アプリの新規行まで確認するにはAPIの条件取得点と行snapshotを別に照合する必要がある。

主担当の実行コマンドは以下。固定 `pos_api_validation`・第一run成功を前提に、API_PERIOD／API_CONSISTENCYの不存在を確認して専用データだけ追加する。元7cart・既存7商品の価格履歴は前後全面照合する。結果 `api-db-conditions.json` が存在すれば再実行・上書きせず止める。

writerの期限超過・例外・COMMIT結果不明はsanitized分類と途中証拠を残して停止し、COMMITを再送しない。daemon threadがjoin期限後も生存している場合は未確定の停止であり、書込接続の終了・完全cleanupまで成功したとは表現しない。部分状態の確認と後片付けは主担当へ戻す。

```sh
python3 tools/parallel_next_conditions_verify.py
M2_LOCAL_PROFILE=parallel-next backend/.venv/bin/python tools/parallel_next_conditions_verify.py --run
```

## 現在の検査と残範囲

- 接続なし既定コマンド：成功。誤profile `mac-parallel` の `--run` は実行前にValueError分類だけで停止、DB・docker接続へ進まない。
- Python構文確認は成功。初回のrepo root設定による対象Ruffは成功したが、後続のbackend設定による最終検査は上記7件とformat差で失敗した。書式修正後はbackend設定のRuff check／formatと接続なし既定コマンドが成功。DB再実行はしていない。専用スクリプト以外のsource・sharedtools・依存を本担当は変更していない。
- 優先1〜4の実MySQL・実ASGI `--prepare`／`--run`、優先5の明示時刻Repository実SQL `--run`、それぞれのphone用DB前後不変は成功。結果は上記実行条件に限定する。実行後のapp/server停止・volume保持は別の環境記録で確認する。
- HTTPS中継・実Cookieブラウザ・iPhone・カメラ・全受入・Azure・M7はこの追加DB試験の範囲外。

戻す場合は本スクリプトと本票の差分だけが対象。専用schema・accounts・volume・売上・既存証跡の削除は別の本人指示と主担当の確認が必要で、自動削除しない。
