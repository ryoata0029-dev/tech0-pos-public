# Mac Chrome：完全終了・再起動の結果

後続追記（2026-10-04）：本人の「修正進めて」で[会員照会未確認表示の修正](Mac_会員照会未確認表示_修正.md)を実施し、コード・自動回帰・独立レビュー・buildを完了。実DB／Chromeの503は未再実施。以下は修正前試験の記録として保持する。

2026-10-04。[作業票](Mac_完全終了復帰_作業票.md)と本人回答「保存済み。Chrome全体を終了・再起動してよい」に基づき、カメラ以外の7状態を実施した。**各状態でChromeアプリの全プロセス消失と同じ通常プロフィールでの復帰を確認し、今回の7復帰条件は合格。自動購入・二重購入・余分なカート作成は発生しなかった。ただし、終了前の会員照会503画面にP2の表示不具合1件を発見し、未修正。** iPhone・カメラ・M3〜M6全体・M7本人受入の合格を意味しない。

対象は業務手順4〜6、F20〜25と復帰条件、[受入：終了後の復帰](../requirements/受入条件_現行.md#r-topic-33)、[TC-21](../tests/テストケース.md#tc-21)、[設計3.5](../design/画面と業務処理.md#sec-3-5)。[前回の再読込結果](Mac_通信障害復帰_追加結果.md)とは別実施である。

## 環境と実行方法

新規専用 `tech0-pos-mac-restart-mysql`／`tech0-pos-mac-restart-mysql-data`、MySQL8.4.11、架空担当者・会員・商品、localhost TLS＋許可済みCloudflare一時HTTPS。UIから通常ログイン・開始・Cookie確認を実施し、Cookie移植・期限延長・DB状態の直接書換えは行っていない。既存DB・Azure・証明書信頼設定は変更していない。[環境記録](evidence/mac-restart/mysql-environment.json)。

macOS27.0（26A428）、同じ通常プロフィールRyota。試験後に確認したインストール済みChromeは154.0.8037.97。[実機版・ビルドID・ソースhash・DB照合](evidence/mac-restart/runtime-final.json)。前回修正済みNext.jsビルドを使用した。Git HEADは`89ba602731323863843f2f51f44a634698d20f30`で未コミット差分を含む。

終了操作はネイティブの「Google Chrome を終了」。各終了前13プロセス→終了後0→再起動後13を記録し、旧プロセスが再利用されないことも照合した。タブの自動復元に依存せず、同じプロフィールで同一HTTPSの画面を開いた。終了直後はアプリ観測がChromeを再起動することがあるため、CLIのプロセス消失確認を先に行った。

最初の編集状態試行はプロセス消失を確認できず、合格数に含めていない。未送信入力を再設定し、`editing-verified`で完全終了を確認した試行だけを採用した。初回試行の証跡は保管し、正しい試行の画面は`ui-editing-ready`と`ui-editing-after`で区別している。

## 7条件の結果

| 終了前 | 完全終了後の結果 | UI／実DB証跡 |
|---|---|---|
| 編集中：3商品、数量3、会員、537円。未送信コード・会員ID・数量9・選択行あり | 同じカート・登録済み数量3・会員・537円を保持。未送信入力・選択行を消去。商品1のマスタを500円・税8％へ変更しても既存行103円・税10％を保持 | [前画面](evidence/mac-restart/ui-editing-ready.png)・[後画面](evidence/mac-restart/ui-editing-after.png)・[DB](evidence/mac-restart/db-editing-after.json) |
| 会員確認待ち：実受付COMMIT後の503 | 同じPENDINGと参考額を保持。商品編集・購入禁止、会員確認／非会員選択は可能。明示非会員で570円、その後会員再照会で537円 | [後画面](evidence/mac-restart/ui-member-after.png)・[DB](evidence/mac-restart/db-member-after.json)・[障害位置](evidence/mac-restart/gate-member-fault.json) |
| SAVING：購入受付COMMIT済み、売上TX前で保留 | 同じカートを正規resolveでUNSAVEDへ確定。自動購入なし、購入0件。元要求を解放しても拒否される | [前DB](evidence/mac-restart/db-saving-before.json)・[後画面](evidence/mac-restart/ui-saving-after.png)・[後DB](evidence/mac-restart/db-saving-after.json)・[解放後DB](evidence/mac-restart/db-unsaved-before.json) |
| UNSAVED：内容保持、選択待ち | 同じ内容・537円と再試行／修正の選択肢を保持。自動再購入なし、購入0件 | [後画面](evidence/mac-restart/ui-unsaved-after.png)・[DB](evidence/mac-restart/db-unsaved-after.json) |
| 結果不明：実売上保存後の200応答を遮断 | 不明時は編集停止、日本語の確認案内。古い未保存表示なし。再起動後は同じ537円の購入完了へ。購入1件を維持 | [不明画面](evidence/mac-restart/ui-unknown-before.png)・[遮断位置](evidence/mac-restart/response-loss-unknown-fault.json)・[後画面](evidence/mac-restart/ui-unknown-after.png)・[DB](evidence/mac-restart/db-unknown-after.json) |
| SAVED：購入結果未終了 | 同じ固定購入結果537円へ。購入1件を維持、新規購入送信なし | [後画面](evidence/mac-restart/ui-saved-after.png)・[DB](evidence/mac-restart/db-saved-after.json) |
| next確定済み：次カート作成後の200応答を遮断 | 作成済みの次カートへ。商品なし・会員未指定・0円・STAFF_Aを保持。2カート・購入1件・NEXT1件のまま | [遮断位置](evidence/mac-restart/response-loss-next-fault.json)・[後画面](evidence/mac-restart/ui-next-after.png)・[前DB](evidence/mac-restart/db-next-before.json)・[後DB](evidence/mac-restart/db-next-after.json) |

各終了のプロセス証跡は`evidence/mac-restart/chrome-before-*.json`と`chrome-stopped-*.json`。終了／再起動の時系列と新旧プロセス比較を[最終照合](evidence/mac-restart/runtime-final.json)にまとめた。会員以降は`native-quit-*.json`、保存中以降は`native-restart-*.json`も記録した。

SAVINGは実受付COMMIT後、DBロック外で保留。再起動後に正規resolveを先行させ、受付から267.42秒で元要求を解放した（ハーネス上限600秒以内）。元操作`76ea9d3b-cdc9-4af7-b83a-96a73b9b1b55`は`REJECTED / PURCHASE_ATTEMPT_CLOSED`で、明示再試行まで売上0件を維持した。[受付位置](evidence/mac-restart/gate-saving-fault.json)・[解放記録](evidence/mac-restart/gate-released-saving-fault.json)。成功応答の喪失は実応答本文取得後の遮断で、200/APPLIEDと別接続DBを照合した。

最終DBは旧カート`9778aaa3-ded4-4af9-b0b4-02899214e6c8`がCLOSED、次カート`78a8d0d7-0225-440c-b203-7d4edd46f4b8`がEDITING。購入1件537円・売上明細3行・税行2行（17円／27円）・NEXT1件。[最終DB](evidence/mac-restart/db-final.json)。

## 変更・検査・残り

**新規P2・未修正：会員照会結果不明時の旧会員／旧金額表示。** MEMBER_0適用中にMEMBER_1へ変更し、実受付COMMIT後に503となると、DBはPENDINGだが終了前UIには「会員：MEMBER_0」と537円が参考表示なしで残る。[不具合画面](evidence/mac-restart/ui-member-before.png)・[DOM](evidence/mac-restart/ui-member-before.txt)・[同時点DB](evidence/mac-restart/db-member-before.json)。[受入：会員指定・変更](../requirements/受入条件_現行.md#r-topic-23)と[設計4.2](../design/画面と業務処理.md#sec-4-2)に反する。商品変更・購入は停止しており、売上の破損／重複はない。応答不明中の会員ボタン停止だけを本指摘の欠陥とはしない。

再起動後は正しいPENDING・参考額と会員選択へ復帰するため、7復帰条件の合格とは分ける。TC-03全体は未完了。次の修正では、照会開始／結果不明時に旧会員を適用中と見せず、旧額を参考扱いにし、正規照合後の待ち状態・確定エラー・期限切れ案内・操作制限を保つ回帰検査が必要。

今回、アプリ機能は変更していない。隔離試験profile `mac-restart`、固定対象ラッパー`tools/mac_restart.py`、既存Mac検証ツールのprofile許可、専用ディレクトリのGit除外、作業票と本結果を追加した。新しい本番依存・要件・設計判断は追加していない。

`make check`のlint・型・Python71件＋Node42件＝113件はすべて合格、OpenAPI22操作有効。[今回ログ](evidence/mac-restart/check.log)。アプリソースとビルドIDは前回検証ビルドと一致しており、今回は再buildしていない。証跡の件数・状態・遅延要求拒否・旧条件保持・プロセス消失を追加照合した。

独立レビューで上記P2を指摘し、7復帰条件のプロセス・DB件数・遮断成立には追加の合否誤りなし。[レビュー記録](evidence/mac-restart/independent-review.md)。文書リンク検査は正本26文書・1307リンクでエラーなし、新規結果／作業票・追記文書のローカル参照も別検査し、`git diff --check`合格。カメラ／映像の消去、iPhone、通知欠落・補助記録破損・状態別再認証等は未確認範囲として残す。本人の主要フロー確認とM7受入は別工程。

今回のトンネル・Next.js・FastAPI・専用MySQLを停止済み。3307／8443／8444は非待受、containerはexited、volumeと証跡を保持。生成秘密値がGit対象候補とログに含まれないことを確認した。[停止記録](evidence/mac-restart/shutdown-final.json)。

戻す場合は今回追加したprofileと検証ツール／文書の差分に限定し、保存済みDB・volume・既存作業は削除しない。commit・push・Azure／本番反映は行っていない。
