# TC-02：Mac手入力の商品検索・同商品加算・検索待ちの追加結果

2026-10-04。[作業票](Mac_TC02_追加作業票.md)の実機試験を実施。**TC-02は不合格／未完了**。検索中の商品コード変更ができない新規P2（[TC02-P2-01](Mac_TC02_検索中入力不具合.md)）を確認し、未修正。通常の検索・再追加・検索成功後のコード変更・不存在と不能の区別は今回の範囲で確認できた。

対象は[TC-02](../tests/テストケース.md#tc-02)、[商品受入F08〜F12](../requirements/受入条件_現行.md#r-topic-25)、[設計3.1](../design/画面と業務処理.md#sec-3-1)・[3.2](../design/画面と業務処理.md#sec-3-2)・[4.1](../design/画面と業務処理.md#sec-4-1)。アプリの要件・設計・コードは今回変更していない。

## 実行環境

新規 `tech0-pos-mac-tc02-mysql`／`tech0-pos-mac-tc02-mysql-data`、MySQL 8.4.11 arm64固定digest、TLS必須、localhost HTTPSと承認済みCloudflare一時HTTPSを使用。架空のSTAFF_A・商品0001〜0003だけを使用し、通常ログイン・利用開始・Cookie確認・初回カート作成から実行した。過去の環境・Cookie・期限・証跡を流用していない。

MacBook Air（MacBookAir10,1／Apple M1／16 GB）、macOS 27.0、通常Chrome 154.0.8037.97。build ID `RUxKQtYgrAwNydMBUxSQa`、TC03-P2-01修正後とソースhashが一致する。[環境・版](evidence/mac-tc02/runtime.json)、[MySQL環境](evidence/mac-tc02/mysql-environment.json)。ブラウザー操作は通常UI経由。

## 結果

| 確認条件 | 結果・証跡 |
|---|---|
| 商品0001の検索→追加→同商品再検索・再追加 | 同一line_idで数量1→2、単価103円・税率10%・条件固定日時を保持。税込113→226円、版3→4。成功後にコード・検索結果・追加ボタンを消去。[1点](evidence/mac-tc02/db-first-added.json)、[2点](evidence/mac-tc02/db-repeat-added.json)、[UI](evidence/mac-tc02/ui-repeat-added.txt) |
| 検索成功後に0001→0002へ入力変更 | 旧検索の名称・単価・追加ボタンが消失。新たに検索すると0002の名称／単価107円を表示。購入行は0001・2点を保持。[変更後](evidence/mac-tc02/ui-code-changed.txt)、[新検索](evidence/mac-tc02/ui-new-code-lookup.txt) |
| 未登録PRODUCT_MISSING | 「商品が登録されていません。」、検索結果／追加ボタンなし、内容保持。HTTP404の直接記録はなく、通常UI・実fixture・実装のPRODUCT_NOT_FOUND経路で照合。[UI](evidence/mac-tc02/ui-missing.txt)、[DB](evidence/mac-tc02/db-after-missing.json) |
| 登録済み0001の実照会後503 | 「状態を確認できません。内容を保持して停止してください。」を表示し、不存在表示にしない。検索結果／追加ボタンなし。応答後は検索・購入等の操作が再有効であり、業務全体を停止したとの判定はしない。通常再検索で結果／追加ボタンが復帰。[503](evidence/mac-tc02/gate-response-lookup-unavailable.json)、[UI](evidence/mac-tc02/ui-unavailable.txt)、[再検索](evidence/mac-tc02/ui-after-unavailable-relookup.txt) |
| 検索中のコード変更 | **不合格**。実GET成功後の応答保留中、商品コード欄がdisabled、isEnabled=false。0002への実変更は行っていない。[入力証跡](evidence/mac-tc02/ui-held-input.json)、[UI](evidence/mac-tc02/ui-lookup-held.txt) |
| 保留した実200の解除 | 実照会到達04:51:45.223922 UTC→200解放45.536806、約0.313秒。入力不可の観測はその間。10秒中継timeoutより前で、変更されていない0001の結果／追加ボタンが復帰。[到達](evidence/mac-tc02/gate-lookup-held.json)、[200](evidence/mac-tc02/gate-response-lookup-held.json)、[解放後](evidence/mac-tc02/ui-lookup-released.txt) |
| コード変更後の旧応答が表示を戻さない | **未確認**。入力変更の前提が成立せず、disabled除去・状態注入で回避していない。上書き発生を確認したとは扱わない。 |
| 検索によるDB変化 | 再追加後と404／503＋再検索／保留解放後の5読取snapshotを照合。register・context・cart・line・operation・商品マスター・売上等が不変。[監査](evidence/mac-tc02/verification.json) |

最終は1カート・1明細、商品0001数量2、税抜206円・消費税20円・税込226円、EDITING／UNSPECIFIED／版4、売上0件。購入は実行していない。

## 検査・レビュー・停止

保存証跡の監査、プロジェクトのRuff設定でtools全37ファイルlint／format、Node構文検査、文書リンク検査を実施。[検査記録](evidence/mac-tc02/checks.json)。保存証跡監査の合格はTC-02合格ではなく、不合格／未確認を含む判定の整合確認である。独立した欠陥探索レビューでDB不変、実200解除の時刻、入力無効、未確認範囲、秘密値の不掲載と停止を確認。[レビュー](evidence/mac-tc02/independent-review.json)。

今回の変更はTC02専用profile・私有制御による検索応答の試験用gate・証跡監査・文書。新規ツールは `tools/mac_tc02.py`、`tools/mac_tc02_backend.py`、`tools/mac_tc02_verify.py`。既存の隔離環境共通ツールと `.gitignore` にmac-tc02を追加した。アプリの変更がないため、前回145件とbuildの全検査は再実行しておらず、今回の結果として数えない。

終了後、一時HTTPS・アプリ・専用MySQLを停止し、3307／8443／8444の閉鎖・container exited・volume保持・秘密値のGit候補／ログ非混入を確認。[停止記録](evidence/mac-tc02/shutdown-final.json)。停止済みで追加の戻し操作は不要。DB・証跡は削除しない。commit／push／公開／本番反映は未実施。

次はTC02-P2-01を最小修正し、検索中のコード変更→旧成功／失敗応答遅着→新コードの検索／追加、および会員待ち・更新送信中・応答不明時の操作禁止が維持されることを再検証する。今回の変更はアプリ未修正。iPhone・カメラ／Code128・TC-02全体・Azure・本人の主要フロー確認／M7受入は残る。
