# TC02-P2-01：検索中入力の修正・再検証記録

2026-10-04。本人の残作業①②③並行指示に基づく。[不具合](Mac_TC02_検索中入力不具合.md)を修正した。**コード・自動回帰・ローカル検査・build・独立読取レビューは成功。後続のMac専用実DB・通常Chrome試験で検索待ち中の入力変更とDB不変を確認したが、旧HTTP応答のstatus／bodyのブラウザ到達と10秒以内の画面復帰は未確認。旧応答条件を含む実機再検証全体／TC-02全体を合格にはしない。**

対象は[TC-02](../tests/テストケース.md#tc-02)、[商品受入](../requirements/受入条件_現行.md#r-topic-25)、[設計3.1](../design/画面と業務処理.md#sec-3-1)。要件・設計・API・DDL・依存を変更しない。

`frontend/app/register-cart.tsx` は読取専用の商品検索待ちだけをsearchingで識別し、商品コードinputだけを許可する。更新・購入・会員変更・カメラ開始・再検索はbusy／inflightで停止を維持。入力世代を比較してA→B→Aも旧成功・旧エラーを採用しない。現在の対象・状態・通知世代・enabledを確認し、旧応答で停止案内を上書きしない。401・復帰期限・保守・権限停止はコード変更後でも停止する。

`frontend/tests/register-search.test.mjs` に実TSXイベント処理を使う20回帰を追加。修正前初稿19件の18失敗を保存し、修正後は20件成功。停止境界の厳密化と更新／会員／購入の試験追加で初稿と最終の件数が異なる。[修正前](evidence/mac-tc02-fix/unit-before.log)、[修正後](evidence/mac-tc02-fix/unit-after.log)。

検索修正時の`make check`はPython71＋Node94＝165件、lint・型・OpenAPI22操作を含め成功。`make build`成功、build ID `1Br0vNrgQ6qQbXu1qPCjx`。[当時の検査・版・hash](evidence/mac-tc02-fix/local-verification.json)、[当時のbuildログ](evidence/mac-tc02-fix/make-build.log)。別担当の独立した読取レビューで、検索入力の過剰解除、旧応答、401／期限／通知、TC03・M5停止条件への拡張を確認し、確実な新規欠陥なし。実ブラウザー／撮影の証拠とは区別する。

後続の本人依頼による[商品選択解除の追加・検証](商品選択解除_修正検証.md)を含む実機版は、Python71＋Node99＝170件・build成功、build ID `JgJjC7D_Z2jjtELoFKU-V`。[今回の版・source hash](evidence/mac-batch/runtime-selection-fix.json)で固定した。165件版の記録を170件版へ書き換えず、各版の検査と今回の限定実機観測を区別する。

再検証は[並行進行票](並行試験_進行票.md)の新規mac-batch環境で行った。iPhone最小成立用の環境を先に停止し、同じport／buildの競合を防いだ。固定対象は `tech0-pos-mac-batch-mysql`／専用volume `tech0-pos-mac-batch-mysql-data`／`.mac-batch-local/`／`evidence/mac-batch/`。旧記録の「未修正」は発見時点の状態として保持する。

### 今回の前提と限定観測

[残試験票A0](Mac_残試験_並行作業票.md)は空C0を前提にしたが、本人が追加依頼した選択解除のfixtureを保持するため、今回の検索試験は同じ初回カートのv4・商品0001／0002各1個・会員未指定・税抜210円・税18円・税込228円・売上0を基準にした。基準点は[選択解除後DB](evidence/mac-batch/db-after-deselect-ui.json)。検索は読取専用で、この前提変更による商品削除・DB初期化・版の巻戻しは行わない。空カート前提の全一巡やTC03別タブ試験へ成功を広げない。

通常UIで旧コードを検索し、応答待ち中に別コードを入力した。私有ゲートは実照会のTX終了後に到達し、約5秒保留後にサーバー応答を返した。入力変更が解放より先、商品コード入力は有効、再検索・商品／会員編集・購入・選択解除は無効であることを確認した。[4試行の集計と個別証跡](evidence/mac-batch/comparison-tc02-old-replies.json)に以下を記録した。

| 試行 | 実照会／サーバー返却 | 通常UIの操作と、後のDOM観測 |
|---|---|---|
| old200 | 実商品0001の200を保留して200を返却 | 0001→0002へ変更。後の観測で0002保持・旧商品候補なし・編集再有効。検索開始／後のDOM観測時刻はorder票に記録なし |
| old404 | 実PRODUCT_NOT_FOUND 404を保留して同じ404を返却 | PRODUCT_MISSING→0002へ変更。後の観測で0002保持・旧不存在案内による上書きなし・編集再有効 |
| old503 | 実商品0001の200照会後、解放時に503 SERVICE_UNAVAILABLEを注入 | 0001→0002へ変更。後の観測で0002保持・旧不能案内による上書きなし・編集再有効。実DB停止の試験ではない |
| aba200 | 実商品0001の200を保留して200を返却 | 0001→0002→0001へ戻す。後の観測でも旧商品候補なし・編集再有効 |

4試行の前後DBはregister／contexts／carts／lines／operations／purchases／purchase_lines／purchase_taxes／productsの9集合が完全一致し、v4・2行・228円・売上0を保持した。検索待ち中の入力変更と、他操作・選択解除の禁止、後の観測時点で旧結果を表示していないこと、DB不変は確認済みの個別条件とする。

### 証跡の限界と未確認

ブラウザの生network status／bodyは取得できていない。gate-responseはサーバー返却分類であり、Chrome受信の証明ではない。検索開始時刻があるold404／old503／aba200のサーバー返却は約5.21／5.94／5.74秒だったが、後のDOM観測は開始約13.89／13.09／12.65秒後である。これは観測時刻であり、アプリがその秒数を要した欠陥とも、10秒以内に復帰した成功とも断定しない。old200の要求開始から返却までの時間は保存済みorder票から算出できない。**旧応答status／bodyのChrome到達と10秒以内の画面復帰は全4条件とも未確認。今回結果は限定観測である。**

[集計・追加試行の記録](evidence/mac-batch/verification-attempts.json)には、厳密集計のold404「UI経過10秒未満」assert失敗を残した。追加bounded503は実ゲート約3秒で解放したが、無効な選択解除ボタンへのCUA clickがselector deadlineとなり、解除操作は到達していない。追加試行は不成立とし、後のDOMで正常編集へ戻った事実だけを記録する。[通常選択解除の成功](商品選択解除_修正検証.md)や、アプリ故障へ読み替えない。

新コードの検索・追加を旧応答到達後に行うA0の手順、通知／更新中の停止、TC03修正後の別タブ・旧会員照会、非会員全一巡は今回未実施のまま。170件の自動検査でこれらの実機条件を代用しない。今回Mac実カメラは開かず、iPhoneの選択解除・実映像継続も未実施。

### 終了・保持

今回のトンネル・アプリ・専用MySQLは停止した。[最終DB](evidence/mac-batch/db-final-selection-fix.json)は同じv4・2行・228円・売上0。[終了確認](evidence/mac-batch/shutdown-final-selection-fix.json)で3307／8443／8444閉鎖・container exited・専用volume保持・生成秘密値のGit候補とログ非混入を記録し、[今回のruntime](evidence/mac-batch/runtime-selection-fix.json)も停止・証跡保持へ更新した。旧環境の起動・期限延長・初期化で再試験したものではない。

戻す場合は本修正と新規検索回帰だけを対象とし、以前のカメラ／会員／保存表示修正、DB、volume、証跡を保持する。commit／push／Azure／本番反映は未実施。
