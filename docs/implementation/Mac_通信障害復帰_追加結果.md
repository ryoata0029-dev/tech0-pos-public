# Mac Chrome：通信障害・復帰の追加結果

追記（2026-10-04）：本人のChrome全体終了許可後、別の隔離環境で[完全終了・再起動7条件](Mac_完全終了復帰_結果.md)を実施した。以下は2026-10-03時点の記録として保持する。

2026-10-03。本人の「進めてください」に基づき、[追加作業票](Mac_通信障害復帰_追加作業票.md)のカメラ以外を実施した。**状態別再読込と購入／nextの成功応答喪失を検証し、表示不具合1件を修正・再検証した。Chrome完全終了・再起動は未実施。Mac全体・M3〜M6全体の受入完了ではない。**

対象はF20〜25、業務手順4〜6、[受入：保存失敗・複合状態復帰](../requirements/受入条件_現行.md#r-topic-32)、TC-16〜21・24の実施した条件。詳細は[テストケース](../tests/テストケース.md)、設計[3.4〜3.5](../design/画面と業務処理.md#sec-3-4)・[7.2〜7.5](../design/保存処理.md#sec-7-2)。実DBのCOMMIT ACK喪失は別の[M4結果](M4_実DB障害競合検証.md)を参照する。

## 環境と方法

新規専用 `tech0-pos-mac-recovery-mysql`／同名`-data` volume、MySQL8.4.11、架空データ、localhost TLS＋Cloudflare一時HTTPS。前回環境とDBは停止保持し、旧カート・認証情報を移植／延長／初期化していない。OS証明書信頼設定は変更していない。UIからログイン・開始・Cookie確認・初回カート作成を実施。

MacBookAir10,1・macOS27.0（26A428）・Chrome154.0.8037.58、同じ通常プロフィールRyota。[実装hash・実機版・最終照合](evidence/mac-recovery/runtime-final.json)、[DB環境](evidence/mac-recovery/mysql-environment.json)。Git HEADは前回と同じだが未コミットの修正を含む。

専用バックエンドの実受付COMMIT直後で会員照会503／購入保存前の待機を実施した。購入待機はDBロック外、600秒以内に正規resolveを先行させてから元要求を解放。DB状態の直接書換えはない。購入／nextの成功応答は実アプリの本文読取後に切断し、200/APPLIEDと別接続DBを照合した。

## 実施結果

| 開始状態・条件 | 再読込／明示照合の結果 | 主な証跡 |
|---|---|---|
| 編集中：3商品・会員・537円 | 同じカート・内容・金額を保持。未送信商品／会員入力と選択行は消去 | [入力前後画面](evidence/mac-recovery/ui-editing-reload.txt)・[DB](evidence/mac-recovery/db-editing-reload.json) |
| 会員確認待ち：受付保存後503 | PENDINGを保持し参考額を明示。商品変更／購入は停止。非会員を明示すると570円、その後会員再照会で537円 | [復帰画面](evidence/mac-recovery/ui-member-pending-reload.png)・[DB](evidence/mac-recovery/db-member-pending-reload.json) |
| SAVING：受付済み、売上TX前で待機 | 再読込で正規照合・未保存確定。旧要求をREJECTEDにし、遅着しても売上0件 | [保存前DB](evidence/mac-recovery/db-saving-before.json)・[照合画面](evidence/mac-recovery/ui-saving-resolved.png)・[遅着後DB](evidence/mac-recovery/db-delayed-request-rejected.json) |
| UNSAVED：未保存確定済み | 再読込後も内容と選択待ちを維持。自動再購入なし | [安定画面](evidence/mac-recovery/ui-unsaved-reload-settled.png)・[DB](evidence/mac-recovery/db-unsaved-reload.json) |
| 結果不明：売上保存後の成功応答だけ切断 | 編集／次取引停止。再読込で537円の保存済み結果へ、売上1件維持。修正前の誤表示は下記欠陥として扱う | [切断位置](evidence/mac-recovery/response-loss-saved-loss-reload.json)・[保存DB](evidence/mac-recovery/db-saved-loss-before.json)・[復帰画面](evidence/mac-recovery/ui-saved-loss-reload.png) |
| SAVED：結果表示未終了 | 再読込で固定した537円結果と同じ購入を保持 | [画面](evidence/mac-recovery/ui-saved-reload.png)・[DB](evidence/mac-recovery/db-saved-reload.json) |
| next移行済み：実移行後の成功応答切断 | 再読込で既に作られた次カートへ復帰。0円・会員未指定・商品なし・担当者維持。再読込しても追加カートなし | [切断位置](evidence/mac-recovery/response-loss-next-loss-reload.json)・[画面](evidence/mac-recovery/ui-next-reload.png)・[DB](evidence/mac-recovery/db-next-reload.json) |

今回のカートは`ecb49a55-3746-4475-96d2-1a0cf62e0bc0`→next→`ec0ce4b7-8b15-420c-a28f-494a30e4041c`。再検証を含む最終DBは2カート・2売上（537円／113円）・4売上明細・3税行・NEXT1件。購入停止を使った2要求はいずれも`PURCHASE_ATTEMPT_CLOSED`。再試行・再読込で購入件数は増えない。[最終DB](evidence/mac-recovery/db-final.json)。

## 発見・修正した不具合

UNSAVEDから明示再購入し、実際には保存済みになった後の応答を切ると、操作は禁止される一方で古い「未保存を確認しました」が残り、JSON解析エラーがそのまま表示された。[修正前UI](evidence/mac-recovery/ui-saved-loss-before.txt)。独立レビューでもP2と判定。保存データの破損／重複は発生していない。

`frontend/app/register-cart.tsx`で未保存の確定表示・選択肢をready・非送信中・認証有効のときだけ表示し、購入送信中／結果不明の日本語案内を追加。`frontend/lib/pos.ts`で通信／解析失敗を日本語へ正規化し、正規ApiErrorの分類・理由は維持した。カート状態・元要求・購入補助記録・保存アルゴリズムは保持する。

修正済みビルドで、次カートの113円購入を受付停止→正規resolve→UNSAVED→明示再試行→成功応答切断と再現。送信中と結果不明時に古い未保存表示／選択肢は出ず、編集は停止。同じ要求の再確認で購入完了113円へ戻り、再読込しても売上は合計2件のまま。[送信中](evidence/mac-recovery/ui-regression-retry-sending.txt)・[結果不明](evidence/mac-recovery/ui-regression-unknown.png)・[同要求で復帰](evidence/mac-recovery/ui-regression-saved-retry.png)・[再読込](evidence/mac-recovery/ui-regression-saved-reload.png)。

## 検査・残り・終了

`make check`：lint・型・Python71件＋Node42件＝113件すべて合格、OpenAPI22操作有効。[ログ](evidence/mac-recovery/check.log)。`make build`：backend wheel／Next.js build合格。[ログ](evidence/mac-recovery/build.log)。`node --check tools/mac_flow_https.mjs`合格。独立レビューの期限切れ案内上書き指摘も修正し、再レビューで追加の要修正欠陥なし。[レビュー記録](evidence/mac-recovery/independent-review.md)。

Chrome全体終了は試験外タブへの影響があるため、作業票の直前確認に従い本人の作業保存・終了可否への回答を待っている。全7状態の完全終了／再起動は未実施。検証タブの消失と開き直しを完全終了の代用にしない。カメラ・iPhone、通知欠落、補助記録破損、状態別再認証等はこの結果で合格に拡張しない。本人の主要フロー受入も別工程。

試験終了後は今回のトンネル・Next.js・FastAPI・MySQLだけを停止し、volumeと証跡を保持する。停止確認は[終了記録](evidence/mac-recovery/shutdown-final.json)。戻しは表示修正と専用検証profile／ハーネスの追加差分に限定し、保存済みデータや既存作業を削除しない。commit・push・Azure／本番反映は行っていない。
