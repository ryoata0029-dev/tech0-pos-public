# Mac Chrome：業務・復帰の実機確認結果

2026-10-01〜02。本人の「MAC側先に進めて」と専用DB＋一時HTTPSの許可に基づき、カメラ以外を実施した。**実施した通常操作・再読込・タブ通知は期待どおり。Mac全体の受入は未完了。** 一時HTTPSが後に失効し、応答遮断試験は成立していない。Chrome完全終了は本人回答待ちのため実施していない。

対象要件・業務・設計と実行境界は[作業票](Mac_業務復帰確認作業票.md)、条件の正本は[テストケース](../tests/テストケース.md)と[受入条件](../requirements/受入条件_現行.md)。今回の合格をTC全条件・iPhone・Azureへ拡張しない。

2026-10-03の追加実施は[通信障害・復帰の追加結果](Mac_通信障害復帰_追加結果.md)。下記は前回実施の記録として保持する。

## 実行条件

MacBookAir10,1、macOS 27.0（26A428）、Chrome 154.0.8037.58。同じ通常プロフィール、実デスクトップ画面を操作した。担当者STAFF_A、会員MEMBER_0、実在情報を含まない3商品。[実装版・build ID・ソースhash](evidence/mac-flow/runtime.json)を保存。Git HEADは`89ba602731323863843f2f51f44a634698d20f30`で、M5修正等を含む未コミット作業ツリーを対象とした。

`tech0-pos-mac-flow-mysql`／同名`-data` volume／`pos_validation`／MySQL8.4.11の新規専用DB。TLS必須・表単位権限・loopback3307。既存M2/M3/M4を再利用・初期化していない。[DB環境](evidence/mac-flow/mysql-environment.json)・[構築時スナップショット](evidence/mac-flow/mysql-snapshot.json)。一時Cloudflare HTTPSは今回の画面とAPI中継だけに使用し、端末の証明書信頼設定は変更していない。

## 実施結果

| 対象 | 実施条件と結果 | 証跡 |
|---|---|---|
| TC-01 会員の通常フロー | UIからログイン・開始・Cookie確認・初回カート作成。会員指定、商品3行、数量変更、537円購入、結果再読込、結果を閉じて次カートへ進み次の商品登録まで成立 | [会員結果画面](evidence/mac-flow/ui-member-saved.png)・[会員保存DB](evidence/mac-flow/db-member-saved-reload.json)・[最終DB](evidence/mac-flow/db-final.json) |
| TC-01 非会員 | 別の次カートで非会員を明示。3行570円購入まで成立。結果を閉じる試行は一時HTTPS失効によりDB未到達。非会員の全一巡は未完了 | [非会員結果画面](evidence/mac-flow/ui-nonmember-saved.png)・[保存DB](evidence/mac-flow/db-nonmember-saved.json) |
| TC-02 検索・数量・削除 | 手入力検索/追加/行選択、数量1→99→3、0/100/1.5で更新ボタン無効。99個の手入力追加は上限エラー・内容保持、後続編集成功。107円Bを削除→再追加 | [0](evidence/mac-flow/ui-quantity-zero-rejected.txt)・[100](evidence/mac-flow/ui-quantity-100-rejected.txt)・[小数](evidence/mac-flow/ui-quantity-fraction-rejected.txt)・[99](evidence/mac-flow/ui-quantity-99.txt)・[上限](evidence/mac-flow/ui-quantity-limit.txt)・[削除](evidence/mac-flow/ui-deleted-line.txt) |
| TC-03 会員指定 | 商品追加前のMEMBER_0成功と次カートでの非会員明示だけ成立。会員変更/不存在/照会不能/PENDING制限/遅着は未実施 | [会員編集中](evidence/mac-flow/ui-member-editing.txt)・[会員照会後DB](evidence/mac-flow/db-initial.json)・[非会員DB](evidence/mac-flow/db-nonmember-before-master.json) |
| TC-06 計算 | 103円×3・会員10%引き（1個10円）・税10%と107円商品各1件・税8%。会員税抜493/税17+27/税込537、非会員税抜523/税17+30/税込570。画面と保存明細・税2行が一致 | [照合・終了検査](evidence/mac-flow/verified-shutdown.json)・[最終DB](evidence/mac-flow/db-final.json) |
| TC-10 空カート | 初回と次カートの購入ボタン無効を確認。直接APIと商品あり0円は今回未実施 | [初回画面](evidence/mac-flow/ui-initial.txt)・[次の空画面](evidence/mac-flow/ui-next-empty.txt) |
| TC-18 複数タブ | 同一プロフィールの別タブで警告。別タブ数量変更で元タブは最新表示を取得しつつ編集/購入停止。「状態を再確認」で操作再開。実同時競合・通知欠落は今回未実施 | [通知時停止](evidence/mac-flow/ui-multiple-tabs-first-notified.txt)・[再確認後](evidence/mac-flow/ui-multiple-tabs-first-reconciled.txt)。実DBの制御競合は別の[M4結果](M4_実DB障害競合検証.md) |
| TC-21 追加時条件保持 | 専用DBの商品1マスタを103円/税10%→500円/税8%へ履歴と一括変更。検索は500円、既存行は103円/税10%。再読込・購入保存後も保持 | [新マスタと旧カート](evidence/mac-flow/ui-master-new-cart-old.png)・[再読込](evidence/mac-flow/ui-nonmember-master-reload.txt)・[変更前DB](evidence/mac-flow/db-nonmember-before-master.json)・[最終DB](evidence/mac-flow/db-final.json) |
| TC-24 next応答断 | 検証用ハーネスは準備したが、一時HTTPS失効で要求が到達せず遮断未実行。旧SAVED・2購入・2カート・通常NEXT1件を保持。合格にしない | [失敗画面](evidence/mac-flow/ui-next-attempt-tunnel-failed.txt)・[試行時DB](evidence/mac-flow/db-next-response-lost.json)・[終了検査](evidence/mac-flow/verified-shutdown.json) |

`db-initial.json`は会員照会後v4の記録で、会員未指定の`ui-initial.txt`と同時点ではない。`ui-next-empty.txt`は移行後の同期中を捉えた記録。後続の非会員編集/保存と通常NEXTの継続先一致で次カートの成立を確認した。非会員を明示しても画面文言は「未指定の非会員」だが、DBはNON_MEMBER・member_id NULL・値引き0である。

## 状態別の復帰（TC-21）

| 状態 | 再読込 | Chrome完全終了・再起動 |
|---|---|---|
| 編集中 | 会員537円・同じカート/担当者/会員/3行を保持。未送信の会員/商品入力と選択行は解除。非会員570円もマスタ変更後に保持 | 未実施 |
| 会員確認待ち | 未実施 | 未実施 |
| 保存中 | 未実施 | 未実施 |
| 結果不明 | 未実施。一時HTTPS失効後の通信エラー画面は取得したが、復帰試験として扱わない | 未実施 |
| 未保存確定 | 未実施 | 未実施 |
| 保存済み結果未終了 | 会員537円の固定結果へ復帰。DB購入は1件のまま | 未実施 |
| 次取引移行済み | 移行先の新カートへ商品追加後の再読込で、同じ新カートに復帰。next直後の空カートだけの再読込は未実施 | 未実施 |

TC-02の未登録検索/検索遅着/成功同商品加算、TC-03の異常系、TC-06の定額・最大候補・同額候補・0円等の全計算表、TC-18の通知欠落、TC-20の購入補助記録異常、TC-28の状態別再認証、カメラは今回未実施。M4のAPI/DB試験を今回のブラウザ実証へ置き換えない。本人による主要フロー受入も別判定。

## 中断理由・検査・終了

最後の正常購入は2026-10-01 12:03:28 UTC。10/02にトンネルログが`Unauthorized: Tunnel not found`を記録し、画面のnext要求は`Failed to fetch`となった。最後の正常業務から24時間超が経過しているため、新URLで認証するだけで通常復帰試験を継続できるとは判断しない。再開前に復帰期限・Origin・担当者・対象を確認する。今回、期限延長・Cookie移植・手動復旧・空カート追加による回避は行っていない。

`db-next-response-lost.json`という名前は試行目的を表すだけで、応答遮断成功を証明しない。検証用`mac_flow_https.mjs`の遮断経路は未実行であり、その成立性は未確認。UI/DB記録の[独立レビュー](evidence/mac-flow/independent-review.md)では実施範囲内の確実な追加アプリ不具合は指摘されなかった。

検証器の初回lint失敗を修正し、最終[make check](evidence/mac-flow/check.log)はlint・format・型・Python71件・Node38件・OpenAPI22操作が成功。追加JS2ファイルはNode構文検査成功。アプリコードは今回変更せず、M5時の成功buildを利用した。新規本番依存・commit/push・Azure反映は行っていない。

専用トンネル・HTTPS両アプリ・MySQLを停止、3307/8443/8444非待受、volume保持、生成秘密値のGit候補/ログ非混入を確認。[終了証跡](evidence/mac-flow/verified-shutdown.json)。売上2件・明細6件・税4件、最終カートSAVEDを保持した。証跡のsnapshotは整合した読取TXで取得し、Cookie/hash/パスワードを含めていない。

今回の追加は`mac-flow`専用profile、fixture/読取照合、トンネル起動停止、未実行の応答遮断ハーネスと証跡。戻す場合はこれら検証器の差分だけを対象とし、既存M3/M4/M5修正・DBvolume・記録を削除しない。
