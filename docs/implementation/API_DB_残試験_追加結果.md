# API・DBの残試験：追加自動検証と実DB確認条件

2026-10-04。本人の「可能な範囲で同時並行でサブエージェント使って進めて。カメラとiPhone周りは後回し」に基づくTC-06〜17の追加検証。**既存Python71件成功を確認後、API経路の重要な不足を7テスト追加し、全Python78件成功。新たな確実な実装不具合は検出していない。実DB・サーバー・GUIは本担当が起動／操作していない。以下の実DB追加条件は未実行。** カメラ・iPhone・Azure・M7受入の合格を示すものではない。

## 根拠と既存検証との差分

正本は[TC-06〜17](../tests/テストケース.md#tc-06)、[API・DB詳細](../tests/API・DB詳細.md)、[金額計算例](../requirements/受入条件_現行.md#sec-5-2)・[境界](../requirements/受入条件_現行.md#sec-5-4)・[保存／価格履歴](../requirements/受入条件_現行.md#r-topic-29)・[保存失敗](../requirements/受入条件_現行.md#r-topic-32)、[設計4.1](../design/画面と業務処理.md#sec-4-1)・[4.3](../design/画面と業務処理.md#sec-4-3)・[保存7.2](../design/保存処理.md#sec-7-2)、[DDL](../../設計スキーマ.sql)・[確認SQL](../../設計確認.sql)。要件・設計・API契約を変更していない。

既存の純計算は同額候補・値引き上限・全保存金額の超過・期間境界を検査済み。ASGIテストは主な業務一巡、条件固定、空／0円購入、受付後障害、resolve/reopen等を検査済み。[M3実DBの8項目](M3-M6_テスト結果.md)と[M4実DB障害・競合14条件群](M4_実DB障害競合検証.md)にも既存の根拠がある。今回これらを同じ条件の新合格として数え直さず、API応答・保存値・拒否後の状態・編集再開後の内容に不足していた条件を補った。

追加ファイルは[新規テスト](../../backend/tests/test_coverage_remaining.py)だけ。既存の`BusinessApiTests`の準備・HTTP・契約検査ヘルパーを再利用し、既存テストクラスを継承して71件を重複収集する方式は使わない。実FastAPI／サービス／シリアライズを使い、リポジトリとTXはメモリ差替え。成功応答はOpenAPIのOperationResult等、エラーはErrorとして照合する。コピーによる模擬ロールバックはMySQLの制約・ロック・COMMIT・SQLの正しさを証明しない。

## 今回追加した7テストの結果

| TC・新しい確認範囲 | 独立した期待値と結果 | 限界 |
|---|---|---|
| TC-06：同額候補のAPI→保存値 | 103円・税10％、条件ID10の定額10円とID2の割合10％を両順で入力。保存値はID2／RATE／候補10／実値引き10、小計93・税9・税込102。両順成功 | メモリから渡す候補列の順序を逆転。実SQLの取得順・制約検査ではない |
| TC-06／10：上限適用前の候補選択と0円保存詳細 | 103円にID2=120円、ID10=130円。大きい候補ID10を選択、候補130・実103・値引き後0。0円明細1・税10％行1・税0を保持し、同購入再送も売上1。成功 | 純計算の成功だけでなく応答と模擬保存詳細を検査。実DBの0円税行は別確認 |
| TC-07／09／14：期間終了・マスタ変更後の後付会員と保存固定 | 非会員で103円／税10％／10％候補を固定後、候補期間終了とマスタ500円／税8％／50％へ変更。同商品追加・数量3・後付会員でも279／306円、元候補・固定日時・明細IDを保持。保存後のマスタ名／価格変更・GET・同購入再送でも担当者／会員／元商品名／条件／購入日時／金額不変。成功 | 時計・候補検索はテスト用メモリ。実MySQLの期間比較・同時マスタ更新は未実施 |
| TC-08／12：最大金額行の数量超過と確定拒否 | 税率0・単価999999999999円を1個追加。数量2は422 AMOUNT_INVALID、元カート・版・明細・業務起算保持、Cookie更新なし。マスタを1円へ変えて同操作再送しても元拒否、1個の最大金額は保存成功。成功 | 行小計超過のAPI経路。税率別／全取引集計・行値引き額超過の実DB拒否を全面証明しない |
| TC-12：精度と購入の増分余裕 | 版9007199254740991／992／993を十進文字列でGET・sync成功。M=18446744073709551615のM−2で購入成功し版／適用版M、同要求再送は同結果。Mでnextは409 VERSION_LIMIT、全模擬DB不変。成功 | BIGINT値のAPI精度。実MySQLへの格納・各操作のM−1／M分岐は別条件 |
| TC-13／14：保存済み不整合の停止 | 売上明細なし・税率行不足・余剰・合計不一致・担当者不一致・会員不一致・保存数量不一致の7変異。各変異でcart GET／purchase GET／resumeが503、データを修復・上書きせず保持。成功 | 1テスト内の7変異×3GET。MySQLが拒否する物理制約とアプリ整合性の役割は別。別接続へ未COMMIT変異を見せた試験ではない |
| TC-17：編集再開後の全編集種別と旧要求排除 | 会員の元537円を受付後失敗→resolve UNSAVED→reopenで保持。数量3→2、商品削除→新500円／税0で再追加、非会員指定を実施。元103円行の条件保持、GETで保存を起動せず、最新の新操作だけ小計813／税込841円で保存。元購入は409・REJECTED、売上1。同購入再送不変。成功 | 模擬TXの受付保持・全編集の結合。実DB障害／競合を既存M4根拠に読み替えて追加合格と数えない |

実行：`cd backend`で次を実施。通常の試験診断イベントは画面への大量出力を避けるため、テストプロセス内だけ`logging.disable(logging.CRITICAL)`を指定した。アプリのログ実装は変更していない。

```sh
.venv/bin/python -c 'import logging,sys,unittest; logging.disable(logging.CRITICAL); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("tests", pattern="test_coverage_remaining.py")); sys.exit(not result.wasSuccessful())'
.venv/bin/python -c 'import logging,sys,unittest; logging.disable(logging.CRITICAL); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); sys.exit(not result.wasSuccessful())'
.venv/bin/ruff check tests/test_coverage_remaining.py
.venv/bin/ruff format --check tests/test_coverage_remaining.py
```

追加7件成功（0.242秒）、全78件成功（0.868秒）、Ruff lint／format成功。所要時間はローカルテスト実行時間で、性能受入ではない。Nodeの並行追加分・全体buildは主担当の検査記録へ分け、本票で全アプリ検査成功と表現しない。

## 主担当が実DBで追加する優先条件（本担当は未実行）

実行対象は主担当が選定・独占する今回の隔離検証DBと架空データだけ。旧環境・iPhone環境・Azureを起動して代用しない。新条件の証跡には対象DB／カート／商品・要求版・操作ID・応答・別接続の確定値を保持し、Cookie／秘密値／会員属性を記録しない。すでに同一条件の実証がある場合は[既存証跡の共有条件](../tests/実施条件.md#shared-evidence)に照合し、同条件を重複実行しない。

| 優先 | 対応・操作・独立期待値 | 必要な実DB観測 |
|---|---|---|
| 1 | TC-06／10：架空の専用商品103円・税10％へ、定額10円と割合10％の同額2候補。実際に割り当てた数値IDの小さい方を記録。別商品で120円と130円の2候補を投入し130円を選択、0円保存と同要求再送 | PURCHASE_LINEのdiscount_snapshot内のcondition_id／kind／候補額／実額、明細件数、税行件数。0円でも売上1・明細1・税率行1。先行M3の120円候補1件の0円成功とは別条件 |
| 2 | TC-08：専用商品999999999999円・税0を1個追加、数量2を送信。422 AMOUNT_INVALID、版・行・金額・業務時刻保持、REJECTED記録だけ追加。同操作再送は同拒否。最大1個は保存可能 | CART・CART_LINE・BROWSER_CONTEXTの前後、CART_OPERATIONの要求版／適用版null／結果code、売上0→明示購入後1。単価列に格納できたことだけで集計超過の拒否を合格にしない |
| 3 | TC-13：正常に保存した専用カートへ、DB CHECKを満たす既知不整合を1つずつ与えて診断SQLの検出を確認。例：PURCHASE.totalを1増加、税0の余分税率行を追加 | 各独立TX内・同接続で診断SQLを実行し、対象cart_idを検出後ROLLBACK。正常データでは対象0件。別接続GETは未COMMIT変異を見ないため、ここでアプリ503成功とは扱わない |
| 4 | TC-14：価格履歴の103→110、同値更新、履歴INSERT途中失敗、COMMIT成功ACK未読を別条件にする。主担当の単一TXの価格更新手順で実施 | 商品価格と履歴を新規別TLS接続で同時照合。同値は履歴増分0、失敗は商品103／履歴増分0、確定ACK未読は価格110／履歴103→110が1件。応答断から無条件の価格再更新は禁止。購入済み103円条件と購入日時は不変 |
| 5 | TC-07／09：新規行の条件取得と関連マスタ一括更新を重ね、旧103／税10％／10％引き一式か新500／税8％／50％引き一式だけを固定。期間の開始直前・開始ちょうど・終了直前・終了ちょうども別実施 | 実SQLの単一SELECT・確定順・DB UTC時刻を観測。混在条件は禁止。単なる待機で「ちょうど」を狙わず、試験プロセスの時刻供給を局所固定して実MySQLの期間比較を確認する方式と通常API時刻の証拠を分ける |

上表は新しい実行許可を本票で発行するものではなく、主担当が既存の本人依頼と対象に従って実行する条件整理。DB・サーバー操作は主担当のみが行う。新たな確実な実装欠陥が見つかった場合、実装変更の担当境界を調整してから修正する。

### 読取SQLと具体的な期待値

以下は**未実行のSQLテンプレート**。`:cart_id`・`:product_id`は実行クライアントのパラメーター方式に合わせ、準備時に取得した実対象をバインドする。複数SELECTは同じ新規読取専用・REPEATABLE READ TX内で取得し、終了後に再取得する場合は新しい読取TXを使う。0行の対象や件数だけの成功判定を避ける。

```sql
SELECT c.cart_id,c.state,c.version,c.member_state,c.subtotal,c.total,
       b.last_business_at
FROM CART c JOIN BROWSER_CONTEXT b ON b.context_id=c.context_id
WHERE c.cart_id=:cart_id;
SELECT line_no,quantity,unit_price_snapshot,tax_rate_snapshot,
       discount_candidates,discount_snapshot,discount_per_unit,
       net_unit_price,line_subtotal,conditions_fixed_at
FROM CART_LINE WHERE cart_id=:cart_id ORDER BY line_no;
SELECT operation_id,kind,status,request_version,applied_version,result_code
FROM CART_OPERATION WHERE cart_id=:cart_id ORDER BY created_at,operation_id;
SELECT staff_id,member_id,purchased_at,subtotal,total
FROM PURCHASE WHERE cart_id=:cart_id;
SELECT line_no,code_snapshot,quantity,unit_price_snapshot,tax_rate_snapshot,
       discount_snapshot,discount_per_unit,net_unit_price,line_subtotal
FROM PURCHASE_LINE WHERE cart_id=:cart_id ORDER BY line_no;
SELECT tax_rate_snapshot,taxable_subtotal,tax_amount
FROM PURCHASE_TAX WHERE cart_id=:cart_id ORDER BY tax_rate_snapshot;
```

同額10円の保存期待は小計93／税9／税込102・condition_idは実IDの小さい方。120／130円候補の保存期待はcandidate_amount=130／actual_discount=103・小計0／税0／税込0。最大額の数量超過は数量1・小計／税込999999999999・元版とlast_business_at不変、拒否操作のみREJECTED／applied_version=null。編集再開の追加自動ケースを実DBで繰り返す場合は、新購入だけ813／841円・3明細（103円×2、107円×1、500円×1）で、元購入操作はREJECTED、売上1件。

価格履歴は次で照合する。103→110の正常確定後に履歴は初期NULL→103と変更103→110。同値・失敗・確定結果の照合だけで履歴を増やさない。

```sql
SELECT product_id,code,unit_price FROM PRODUCT WHERE product_id=:product_id;
SELECT old_price,new_price,changed_at
FROM PRICE_HISTORY WHERE product_id=:product_id ORDER BY changed_at,history_id;
```

既知不整合の診断は、正常な専用保存カートの総額に余裕がある場合だけ、1条件1TXで以下のいずれかを実施し、同接続で[現行確認SQL](../../設計確認.sql)を実行後、必ずROLLBACKする。正常状態から開始し、条件を重ねない。

```sql
-- 条件A：売上合計だけが不一致。診断SQLの合計照合で対象を検出する。
START TRANSACTION;
UPDATE PURCHASE SET total=total+1 WHERE cart_id=:cart_id;
-- 設計確認.sqlの「明細件数・税抜小計・税込合計」を同接続で実行。
ROLLBACK;

-- 条件B：元カートに税率0の税行が存在しないことを先に確認。
START TRANSACTION;
INSERT INTO PURCHASE_TAX(cart_id,tax_rate_snapshot,taxable_subtotal,tax_amount)
VALUES(:cart_id,0,0,0);
-- 設計確認.sqlの「税率別集計の不足・余剰」を同接続で実行。
ROLLBACK;
```

これらは物理CHECKを無効化せずに診断SQLの非ゼロ検出を確認する条件。CHECKそのものの数量0／100・税計算等の拒否は[TC-13〜15のDB入力一覧](../tests/API・DB詳細.md)へ分ける。アプリ読取停止の実DB確認を別接続で行うなら、未COMMIT変異では成立しない。専用検証カートでの確定済み変異・復元、または同接続の実リポジトリ／サービス読取という実施方法を明示し、後者をHTTPSのAPI成功と表現しない。

## 残る範囲と戻し方

TC-11の22操作別全入力異常、TC-13の全物理制約／所属・候補JSON、TC-14の価格履歴故障、TC-15の実投入、上記の実DB追加条件は今回の7テストだけでは合格にしない。TC-16の実障害・COMMIT ACK未読とTC-17のロック・確定順には既存M4の限定証拠を参照するが、全中断位置・順序・境界が網羅済みとは扱わない。カメラ・iPhone・実ブラウザ表示・Azure性能／復元・M7受入は別に残る。

変更は新規テストと本票のみ。アプリ実装・frontend・tools・DB・環境・依存は変更していない。commit／pushは行わない。戻す場合は今回の新規テスト・本票の差分だけを対象とし、他担当の変更・DB／volume・既存証跡を削除しない。
