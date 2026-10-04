# 会員照会の送信中・結果不明表示の修正

後続追記（2026-10-04）：[Mac Chrome・専用MySQLの修正後再検証](Mac_会員表示_実機再検証結果.md)で、初回指定／AからBへの変更の受付後503と正常復帰を確認。P2は今回のMac条件で解消。iPhone・TC-03全体・本人受入は残る。以下はコード修正時点の記録。

2026-10-04。本人の「修正進めて」に基づき、[完全終了試験で発見したP2](Mac_完全終了復帰_結果.md)を修正した。**コード修正・自動回帰13条件・独立レビュー・buildは完了。実DB／Chromeの503再現は今回再実施していない。** TC-03全体・両端末の受入合格を意味しない。

対象は会員指定・変更の業務手順、[受入：会員指定・変更](../requirements/受入条件_現行.md#r-topic-23)・[操作制限](../requirements/受入条件_現行.md#r-topic-24)、[設計3.2](../design/画面と業務処理.md#sec-3-2)・[4.2](../design/画面と業務処理.md#sec-4-2)、[TC-03](../tests/テストケース.md#tc-03)。要件・設計・API・DDLの変更なし。

## 修正内容

会員変更を送信しても、成功応答を受け取るまで画面のカートは変更前の応答を保持する。そのため受付後の503では、DBがPENDINGでも旧会員・旧額を確定情報として表示していた。原因と実機の修正前証跡は[前回DOM](evidence/mac-restart/ui-member-before.txt)・[DB](evidence/mac-restart/db-member-before.json)に残す。

`frontend/app/register-cart.tsx`に会員指定の未確認表示フラグを追加した。

- 会員の手入力・読取・非会員への変更を送信した時点で、会員表示を「確認待ち（指定結果は未確認）」にし、旧金額・値引きを「変更前の参考額」と明示する。
- 503・通信断・認証失効・期限切れ・照合失敗では未確認表示を保つ。401・期限切れ等の具体的な理由は上書きしない。自動再送や金額の再計算は追加しない。
- 正しいカート・操作IDのAPPLIED、EDITING／PENDINGの正しいPREPARED、安全な確定エラー後のGET、または正規復帰照合を確認してからフラグを解除する。DBがPENDINGなら元の確認待ち・参考額表示を継続する。
- 別タブ通知・購入補助記録・対象不一致・不正PREPAREDで確認できない間は停止を維持する。同じ要求の再試行では元の操作ID・版を保持する。

金額・会員状態の正はAPI／DBのまま。フラグは画面表示だけに使用し、編集／購入の許可を広げない。既存の購入復帰、M5の確定商品エラー後の撮影維持・停止条件は変更していない。

変更ファイルは本体、`frontend/tests/register-member.test.mjs`、既存`frontend/tests/support/register-harness.mjs`（表示テキスト・入力・照合結果の観測を追加）、本記録と進捗への追記。新しい依存なし。

## 検査結果

| 検査 | 結果と証拠 |
|---|---|
| 修正前の欠陥再現 | 初期9条件を追加し、旧会員・旧額の参考注記欠落で8条件失敗。[before.log](evidence/member-display-fix/before.log)。その後4条件を補強し、最終13条件とした |
| 会員回帰13条件 | 送信中→503→明示PENDING照合、通信断、401、期限切れ、不存在後PENDING、会員成功、非会員成功、照合失敗、同要求再試行、正しいPREPARED、別カート、不正PREPARED、通知競合が合格 |
| `make check` | lint・型、Python71件＋Node55件＝126件合格、OpenAPI22操作有効。既存のカメラ／購入回帰も合格。[check.log](evidence/member-display-fix/check.log) |
| `make build` | backend配布物・Next.js本番build合格。[build.log](evidence/member-display-fix/build.log) |
| 独立レビュー | 追加修正が必要な確実な欠陥なし。未確認表示の解除、通知・対象・PREPARED、認証・期限案内、既存M5／購入停止条件を確認。[レビュー記録](evidence/member-display-fix/independent-review.md) |

実TSXのイベントハンドラとJSX表示・操作可否を、既存の決定的hook／API差替えハーネスで検査した。React DOM・実API・MySQL・Chrome実機・カメラ映像の再検証証拠ではない。実機の修正前503再現と、修正後の自動回帰を区別する。既存NodeのMODULE_TYPELESS_PACKAGE_JSON警告は残るが失敗なし。

## 次の確認と戻し方

Mac Chromeの実DBで、旧会員から別会員への変更を受付後503にし、送信中／不明時の未確認・参考額表示、商品変更／購入の停止、正規照合後PENDINGから再照会／非会員選択へ進めることを確認する。最初の会員指定とiPhoneでの表示確認も残る。TC-03全体を合格へ拡張しない。

今回、前回終了済みの専用DB・トンネルは再起動せず、Azure・証明書信頼設定・カメラ撮影・外部送信は変更していない。commit・push・公開・デプロイは行っていない。

戻す場合は今回の表示フラグ・会員対象照合と回帰／文書の差分だけをレビューして戻す。過去の購入表示・M5修正、保存済みDB・volume・証跡を保持する。
