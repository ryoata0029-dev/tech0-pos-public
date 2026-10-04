# TC-03：Mac Chrome追加検証結果

後続追記（2026-10-04）：この試験で発見したTC03-P2-01は[修正・Mac再検証](Mac_TC03_不存在復帰_修正再検証結果.md)で手入力4条件の解消を確認。以下は修正前試験の記録を保持している。TC-03全体の受入は未完了。

2026-10-04。**予定したMac手入力の追加試験を実施。直接API20要求の拒否、別タブの編集・購入停止、GETだけでは会員待ちを解除しないこと、旧照会による新選択の上書き防止は確認した。一方、会員不存在後の再入力・非会員選択に新規P2を1件確認し、TC-03は不合格／未完了。** 今回アプリは未修正。両端末・Code128・本人受入へ合格を拡張しない。

本人の「OK。進めよう」に基づく[作業票](Mac_TC03_追加作業票.md)。対象は会員指定・変更、商品編集・購入可否の業務手順、[受入：会員指定・変更](../requirements/受入条件_現行.md#r-topic-23)・[操作制限](../requirements/受入条件_現行.md#r-topic-24)、[設計3.2](../design/画面と業務処理.md#sec-3-2)・[4.2](../design/画面と業務処理.md#sec-4-2)、[TC-03](../tests/テストケース.md#tc-03)。

## 環境・準備

新規の固定専用`tech0-pos-mac-tc03-mysql`、volume `tech0-pos-mac-tc03-mysql-data`。MySQL 8.4.11 arm64、digest固定、localhost:3307、TLS必須、架空データのみ。[環境](evidence/mac-tc03/mysql-environment.json)・[初期DB/TLS・権限](evidence/mac-tc03/mysql-snapshot.json)。MacBook Air（MacBookAir10,1・Apple M1・16GB）、macOS 27.0、Chrome 154.0.8037.97通常モード。[端末](evidence/mac-tc03/device.json)・[実装版／照合](evidence/mac-tc03/verification.json)。

UIの通常ログイン→利用開始→Cookie受取確認→初回空カートを通した。古い環境・Cookie・期限を流用・初期化・延長しない。アプリソースhashとbuild ID `JZgq0YlIZQIBqIDG2IS3O`は[前回修正時](evidence/member-display-fix/verification.json)と一致する。

Next.js／FastAPIはlocalhost HTTPS、一時Cloudflare HTTPSを中継。承認済みの試験専用資格情報／Cookieがその経路を通る。証明書検証を維持し、端末信頼設定は変更しない。`/__tc03`のprofile限定検証画面は同じChromeの通常Cookie自動送信で正規APIを使い、Cookieの読取・移植や保護の迂回はしない。公開障害制御APIはない。

1カートで会員指定・再入力の一連試験を行い、各下位条件の前提を通常の明示非会員化／確認成功で整えた。最初の空カート条件を除き「初回」は旧指定会員がない非会員からの指定を意味する。履歴0・版1の独立ケースとは区別する。商品登録前は0円・0明細、登録後は103円×3、107円×1、107円×1の3商品・3明細、非会員570円・会員537円を使用した。

## 条件別結果

| 条件 | 判定・観測 | 主な証跡 |
|---|---|---|
| 商品追加前の正常会員指定・A→B成功 | 確認。MEMBER_0からMEMBER_1へ変更、0円・0明細を保持 | [会員A画面](evidence/mac-tc03/ui-empty-member-a.txt)・[会員B画面](evidence/mac-tc03/ui-empty-member-b.txt)・[B確定DB](evidence/mac-tc03/db-empty-member-b.json) |
| 商品追加前の不存在・変更不存在 | **不合格：TC03-P2-01**。不存在案内と参考額は正しいが会員操作が無効。明示的な状態再確認後なら再入力／非会員化が可能 | [不具合記録・4条件](Mac_TC03_会員不存在後の復帰不具合.md) |
| 商品追加前の照会不能・非会員化／再照会 | 確認。非会員からの指定と旧MEMBER_1→MEMBER_0変更を受付COMMIT後503にした。0円保持、旧IDを確定表示せず、明示照合後に再照会または非会員化で復帰 | [非会員から503](evidence/mac-tc03/ui-empty-initial-unavailable.txt)・[DB](evidence/mac-tc03/db-empty-initial-unavailable.json)、[変更503](evidence/mac-tc03/ui-empty-change-unavailable.txt)・[DB](evidence/mac-tc03/db-empty-change-unavailable.json)、[再照会成功](evidence/mac-tc03/ui-empty-relookup.txt)・[非会員復帰](evidence/mac-tc03/ui-empty-final-nonmember.txt) |
| 商品ありの正常指定・変更・非会員化 | 確認。A／Bとも537円、非会員化でID・特典解除して570円。参考注記解除、通常の編集／購入可に戻る。購入は実行しない | [A](evidence/mac-tc03/ui-lines-member-a.txt)・[B](evidence/mac-tc03/ui-lines-member-b.txt)・[非会員](evidence/mac-tc03/ui-lines-notfound-nonmember.txt) |
| 商品ありの不存在・変更不存在 | **同じP2を再現**。元3明細・570円／537円を参考表示し商品編集／購入を停止するが、再入力／非会員も無効 | [不具合記録](Mac_TC03_会員不存在後の復帰不具合.md) |
| 商品ありの照会不能・変更不能 | 確認。実受付COMMIT後3秒503、PENDING保持。明示照合後の再照会／非会員選択で復帰。旧額の参考注記は今回も正常 | [非会員から503](evidence/mac-tc03/ui-lines-initial-unavailable.txt)・[DB](evidence/mac-tc03/db-lines-initial-unavailable-before-api.json)、[A→B503](evidence/mac-tc03/ui-lines-change-unavailable.txt)・[DB](evidence/mac-tc03/db-lines-change-unavailable-before-api.json)、[再照会](evidence/mac-tc03/ui-lines-unavailable-relookup.txt)・[非会員化](evidence/mac-tc03/ui-lines-unavailable-nonmember.txt) |
| 商品ありPENDINGの直接API4操作 | 確認。不存在2条件・照会不能2条件・照会処理継続中1条件、計5条件×4操作＝20要求を409 STATE_CONFLICTで拒否。最新の版・正しい明細ID・新操作IDで試し、無効入力や古い版による拒否とは区別 | [不存在](evidence/mac-tc03/api-initial-notfound-blocked.json)・[変更不存在](evidence/mac-tc03/api-change-notfound-blocked.json)・[不能](evidence/mac-tc03/api-initial-unavailable-blocked.json)・[変更不能](evidence/mac-tc03/api-change-unavailable-blocked.json)・[処理中](evidence/mac-tc03/api-held-blocked.json) |
| 別タブで同じPENDINGの操作制限 | 確認。上の5条件を通常POSで照合し、商品入力・行選択・購入は無効。選択行がない別タブでは、数量／削除へ進むための行選択が無効 | [不存在](evidence/mac-tc03/ui-other-initial-notfound.txt)・[変更不存在](evidence/mac-tc03/ui-other-change-notfound.txt)・[不能](evidence/mac-tc03/ui-other-initial-unavailable.txt)・[変更不能](evidence/mac-tc03/ui-other-change-unavailable.txt)・[処理中](evidence/mac-tc03/ui-other-held.txt) |
| 会員GET成功・カートGETだけで待ちを解除しない | 確認。不存在・不能・処理継続中の3条件で会員GET200 MEMBER_0を取得しても同じPENDING・版・参考額。会員確定や購入を起動しない | [不存在](evidence/mac-tc03/api-initial-notfound-member-get.json)・[不能](evidence/mac-tc03/api-initial-unavailable-member-get.json)・[処理中](evidence/mac-tc03/api-held-member-get.json) |

503は状態未確認として一旦停止し、正規の明示照合を経てPENDINGから選択する。404不存在は確定した業務結果と同一カートの自動GETが成功しているのに、会員操作の停止が残る点をP2と判定した。両者を同じ復帰不具合として扱わない。

## 古い照会を新選択の後に完了させる

受付COMMIT後にPENDINGを確定し、実会員lookupで`found=true`を得た後・反映前に旧要求を停止した。読取トランザクションと接続は終了し、更新ロックを持たない。新選択確定後、私有releaseファイルで旧処理を再開した。状態名をDBへ直接注入していない。

| 条件 | 観測と限界 | 証跡 |
|---|---|---|
| 旧MEMBER_1要求→別の通常POSタブからMEMBER_0 | 新会員537円・v33を先に確定。旧処理は約57.583秒後に完了しREJECTED/MEMBER_LOOKUP_SUPERSEDED。再開前後のDBは同一。10秒中継タイムアウト後なので、**遅着サーバー処理不反映**の証拠。旧応答のブラウザ到達とは扱わない | [受付](evidence/mac-tc03/gate-initial-held.json)・[実照会後停止](evidence/mac-tc03/lookup-held-initial-held.json)・[新会員状態のAPI読取](evidence/mac-tc03/api-initial-new-member.json)・[再開前DB](evidence/mac-tc03/db-initial-new-member-before-release.json)・[旧完了](evidence/mac-tc03/lookup-finished-initial-held.json)・[再開後DB](evidence/mac-tc03/db-initial-new-member-after-release.json)・[画面照合](evidence/mac-tc03/ui-initial-new-member-reconciled.txt) |
| A→B要求→検証API別タブで非会員を明示選択 | 新NON_MEMBER・570円・v36を先に確定。旧処理は約0.752秒でREJECTED。旧処理完了直後のDOMで実API拒否文言を確認し、旧会員Bを適用せず停止。旧537円を未確認の参考額として保持し、明示照合で新しい570円へ | [受付](evidence/mac-tc03/gate-change-held.json)・[新選択API](evidence/mac-tc03/api-change-new-nonmember.json)・[旧完了](evidence/mac-tc03/lookup-finished-change-held.json)・[旧応答後画面](evidence/mac-tc03/ui-change-old-response.txt)・[DB](evidence/mac-tc03/db-change-new-nonmember-after-release.json)・[明示照合画面](evidence/mac-tc03/ui-change-new-nonmember-reconciled.txt) |
| 非会員からB要求→検証API別タブでAを新指定 | 新MEMBER_0・537円・v40を先に確定。旧処理は約0.960秒でREJECTED。旧処理完了直後のDOMで実API拒否文言を確認し、旧Bを適用しない。明示照合後はA・537円（通常SYNCによりv41） | [受付](evidence/mac-tc03/gate-initial-fast.json)・[新会員API](evidence/mac-tc03/api-initial-fast-new-member.json)・[旧完了](evidence/mac-tc03/lookup-finished-initial-fast.json)・[旧応答後画面](evidence/mac-tc03/ui-initial-fast-old-response.txt)・[明示照合画面](evidence/mac-tc03/ui-initial-fast-new-member-reconciled.txt)・[DB](evidence/mac-tc03/db-fast-new-member-after-reconcile.json) |

高速2条件は新選択のAPI応答とGETを観測してから私有releaseを書き、旧完了を待った。秒数は受付から旧処理完了までであり、ブラウザ受信時間ではない。旧HTTP応答本体・ブラウザ受信時刻は直接記録しておらず、実API拒否文言のDOMとサーバー処理記録を照合した。初回長時間条件の新会員API記録は状態の読取であり、選択要求の証跡ではない。新指定の確定はDBのSET_MEMBER APPLIED（v32→33）と通常POSの画面で確認した。通常のAPIを操作する検証画面を使い、障害解除操作は公開していない。旧応答は実業務の置換済み拒否であり、偽のAPPLIED応答を作った試験ではない。応答を受けただけで新選択確定と推測せず、明示照合まで停止する安全動作も維持した。

## 証跡照合・終了・次の修正

21個の別接続DB観測で同じ1カート・担当者STAFF_A、商品追加後の3明細・数量3/1/1・追加時単価／税率／固定日時を保持。5組の拒否試験前後でカート・明細・操作・売上等は同一。全観測で売上・売上明細・売上税0件、PURCHASE/NEXT操作なし。最終はNON_MEMBER・v42・570円。[最終DB](evidence/mac-tc03/db-final.json)。オフラインの証跡整合性検査は成功だが、会員不存在4条件の不合格をそのまま残す。[検証コード](../../tools/mac_tc03_verify.py)・[照合結果](evidence/mac-tc03/verification.json)。

独立した読取レビューで試験位置・API保護・実証範囲を確認し、新規P2を確定した。[レビュー](evidence/mac-tc03/independent-review.md)。今回の差分は専用profile／wrapper、API検証画面、profile限定照会停止・証跡、検証器と記録。アプリの修正・新依存はない。対象PythonのRuff lint／format、HTTPS中継と検証画面のJavaScript構文、文書リンク・差分を検査。[検査記録](evidence/mac-tc03/checks.json)。アプリhash/build一致のため`make check`／`make build`は今回再実行しない。以前の126件合格は、新しく発見した不存在後復帰の合格を証明しない。

今回のトンネル・両アプリ・専用DBは停止済み。3307/8443/8444閉鎖、container exited、volume保持、Git候補・私有ログに今回生成した秘密値なしを確認。[終了](evidence/mac-tc03/shutdown-final.json)。旧環境、DB／volume／証跡を削除していない。カメラ撮影・iPhone・Chrome全体終了・Azure・commit／push・本番公開／デプロイは実施していない。

次は[TC03-P2-01](Mac_TC03_会員不存在後の復帰不具合.md)の最小修正・回帰・実機再検証を優先する。TC-03全体の判定には、この修正に加え、両端末の対応条件・Code128／カメラ経路・本人確認が必要。今回の試験を両端末の受入合格へ読み替えない。
