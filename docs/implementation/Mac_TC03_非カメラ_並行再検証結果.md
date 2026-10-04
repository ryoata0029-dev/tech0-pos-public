# Mac TC03 非カメラ・並行再検証結果

2026-10-04。新規隔離mac-parallel環境の実Chrome・HTTPS API・実MySQL証跡を独立読取で照合した限定結果。不存在・操作制限・確認成功・明示的な非会員復帰と、受付COMMIT後503の2条件を確認した。**TC03全体・M3〜M6全体・M7の受入合格ではない。** カメラ・iPhoneは本人指示により後回しで、今回操作していない。

## 根拠と対象

- [TC-03](../tests/テストケース.md#tc-03)、[会員指定・変更の受入](../requirements/受入条件_現行.md#r-topic-23)、[会員確認中の操作制限](../requirements/受入条件_現行.md#r-topic-24)。
- [設計4.2 会員処理](../design/画面と業務処理.md#sec-4-2)、[API・DB詳細](../tests/API・DB詳細.md)。不存在・確認不能はPENDINGを保持し、商品編集・購入を禁止。会員GET成功だけでは解除せず、確認成功／明示的な非会員選択で解除する。
- [runtime](evidence/mac-parallel/runtime.json)記録のbuild `_6zNKKv-evmUKeL_8XYLh`、全体検査196件（Python78＋Node118）・build成功。register-cart.tsx SHA256 `ad1055a84c4f2541001c163ba4e2df1e9024c5d28a33c9b8d2d50ea5650f03a6`。この記録は試験開始時のbuild・検査証跡であり、後続修正の検査とは区別する。

対象は架空商品0001／0002／0003、数量3／1／1、STAFF_A、手入力会員MEMBER_0／MEMBER_MISSING。対象cartは `6501b600-ccf3-4e80-ad5f-3dcb949ab9cc`。この環境には直前TC01で保存した別cartの売上1件が既に存在するため、「売上1件保持」と「今回の新規売上0件」を区別する。

## 現在照合できた結果

| 条件 | 実画面・API | DBと判定 |
|---|---|---|
| 非会員から不存在を指定 | [同画面](evidence/mac-parallel/ui-tc03-missing-ready.txt)で不存在理由と「変更前の参考額・会員確認待ち」を表示。再入力・再照会・非会員選択が可能、商品入力・行選択・数量変更・選択解除・削除・購入は無効。 | [開始](evidence/mac-parallel/db-tc03-before.json)のNON_MEMBER v7／570円から、[PENDING](evidence/mac-parallel/db-tc03-pending-before.json) v8／pending_member_id=MEMBER_MISSING。明細と570円を保持、SET_MEMBERはREJECTED／MEMBER_NOT_FOUND。限定成功。 |
| 通常POS別タブの待ち状態 | [別タブ画面](evidence/mac-parallel/ui-tc03-other-pending.txt)に複数タブ警告・会員確認待ち・参考額。商品入力・行選択・購入は無効。非会員選択は可能。会員欄は未入力のため再照会ボタンは無効。 | 同cartの待ち状態を表示したことを確認。通知競合・警告無視・待ち中の全競合を試したものではない。限定成功。 |
| 待ち中の直接API 4操作 | [4拒否](evidence/mac-parallel/tc03-four-rejections.json)：追加POST、数量PATCH、削除DELETE、購入POSTはそれぞれ有効な新操作ID・現在版8で送信し、全件409／STATE_CONFLICT。 | [待ち後](evidence/mac-parallel/db-tc03-pending-after.json)と待ち前の9集合を照合し全て不変。版不一致や不正入力だけによる拒否ではない。新規売上0件。限定成功。 |
| 会員GET成功だけでは解除しない | [GET証跡](evidence/mac-parallel/tc03-member-get.json)：members/MEMBER_0は200／confirmed=true。before／afterのcart応答が同一、MEMBER_MISSING待ち・参考額trueを保持。 | 4拒否とGET後のDB9集合も不変。会員GETは状態変更APIの代わりにならない。限定成功。 |
| 再入力して実会員を確認 | [確認画面](evidence/mac-parallel/ui-tc03-confirmed.txt)でMEMBER_0と再計算した537円を表示。 | [確認DB](evidence/mac-parallel/db-tc03-confirmed.json)：v10 CONFIRMED／MEMBER_0、待ち候補・活動中会員操作を解除。SET_MEMBER APPLIED（受付版9／適用版10）。数量3／1／1を保持し、0001は10円／個引き、小計493円・税44円・税込537円。限定成功。 |
| 確認済み会員から不存在へ変更 | [画面](evidence/mac-parallel/ui-tc03-confirmed-missing.txt)で旧会員を確認済みとして表示せず、待ち・参考額537円・編集／購入無効を表示。 | [DB](evidence/mac-parallel/db-tc03-confirmed-missing.json)：v11 PENDING／MEMBER_MISSING、元の3明細・537円を保持、SET_MEMBER REJECTED／MEMBER_NOT_FOUND。DBのmember_id=MEMBER_0は旧参考条件の保持であり、CONFIRMEDへの自動復帰ではない。限定成功。 |
| 不存在後の明示的な非会員復帰 | [復帰画面](evidence/mac-parallel/ui-tc03-missing-nonmember-recovered.txt)：参考額の注意を消し、商品編集・選択解除・購入が有効。変更先の入力文字列は残るが適用会員は未指定の非会員。 | [復帰DB](evidence/mac-parallel/db-tc03-missing-recovered.json)：v12 NON_MEMBER、member_id・pending_member_id・active_member_operation_idはnull。3明細の数量・単価・税を保持し、値引き0へ再計算、523円＋税47円＝570円、SET_MEMBER APPLIED。旧売上1件は不変、新規売上0件。限定成功。 |

9集合はREGISTER、CONTEXT、CART、CART_LINE、CART_OPERATION、PURCHASE、PURCHASE_LINE、PURCHASE_TAX、PRODUCT。比較はstage・観測時刻のメタデータだけを除外し、各集合の内容を省略せず照合した。[独立読取比較](evidence/mac-parallel/comparison-tc03-core-independent.json)に9集合不変、旧売上保持、全段階の行ID・数量・単価・税・条件固定時刻の保持、復帰後明細と元非会員明細の一致、参照JSONのSHA256を記録した。

## 受付COMMIT後503の追加結果

受付COMMIT後に503を返す注入条件は、実会員マスタの照会不能・実ネットワーク切断とは区別する。`member-unavailable` は会員待ち受付の実DB確定後に固定3秒待って503を返す局所注入で、照会を実行する前の応答不能を模擬する。

| 条件 | 証跡 | 判定 |
|---|---|---|
| 非会員570円から受付後503 | [独立比較](evidence/mac-parallel/comparison-tc03-503-nonmember-independent.json)、[unknown画面](evidence/mac-parallel/ui-tc03-503-nonmember-unknown.txt)、[resumed画面](evidence/mac-parallel/ui-tc03-503-nonmember-resumed.txt)、[recovered画面](evidence/mac-parallel/ui-tc03-503-nonmember-recovered.txt)。 | v12 NON_MEMBER／570円→v13 PENDING／570円・元操作PREPARED。503後は会員指定結果未確認として全変更を止め、状態再確認を提示。再確認後のDB9集合はunknown時と同一で、待ち・参考額を保持して会員再選択を許可、商品編集・選択解除・購入は停止。明示的な再照会で別操作を受付しv15 CONFIRMED／MEMBER_0／537円、旧操作をREJECTED／MEMBER_LOOKUP_SUPERSEDEDへ。旧売上1件・元商品条件は不変。限定成功。 |
| 確認済み会員537円から受付後503 | [独立比較](evidence/mac-parallel/comparison-tc03-503-confirmed-independent.json)、[unknown画面](evidence/mac-parallel/ui-tc03-503-confirmed-unknown.txt)、[resumed画面](evidence/mac-parallel/ui-tc03-503-confirmed-resumed.txt)、[recovered画面](evidence/mac-parallel/ui-tc03-503-confirmed-recovered.txt)。 | v15 CONFIRMED／MEMBER_0／537円→v16 PENDING／537円・元操作PREPARED。503後は指定結果未確認として全変更を止め、状態再確認を提示。再確認後のDB9集合はunknown時と同一で、参考額・会員待ちと商品編集／選択解除／購入停止を維持。明示的な非会員選択でv17 NON_MEMBER／570円、旧会員ID・待ち候補・活動中会員操作をnull、値引き0へ。旧操作はREJECTED／MEMBER_LOOKUP_SUPERSEDED、新非会員操作はAPPLIED。旧売上1件・元商品条件は不変。限定成功。 |

両条件はそれぞれbefore／unknown／resumed／recoveredの4DB stage、busy／unknown／resumed／recoveredの4DOM、受付gate・503応答gateを照合した。比較JSONには元操作の受付版／PREPARED保持と後続明示操作への置換、元明細の行ID・数量・単価・税・条件固定時刻の保持、unknown→resumedの9集合不変、旧売上保持、参照ファイルSHA256を記録した。DB不変だけでは全HTTP照会回数や照会処理の呼出不在を直接証明しない。

この503試験はChromeの応答status／Response本文を独立保存していない。503を返すgate記録と実Chromeの停止／再確認画面、実DB結果を組み合わせた確認であり、TC02の独立Network status＋本文の受信証拠と同じ強さではない。また確認済み条件で指定した候補は同じMEMBER_0で、登録済みAから別の登録済みBへの変更ではない。

## 未確認と証拠の限界

- 会員照会そのものを保留した中での操作制限、新選択後の旧照会遅着・旧特典の上書き防止は今回未実施。上記503注入ではこの条件を代用しない。
- 商品追加前の初回指定、全会員分岐・会員Aから登録済みBへの変更、会員Code128、Mac実カメラ・iPhone実機、実ネットワーク切断・サービス停止は今回未実施。
- 別タブは保存画面の操作可否の観測。直接API4件とは別の証拠であり、GUI無効ボタンをクリックして4拒否を確認したものではない。
- 待ち中の選択解除は同画面の選択中商品で無効を観測。通常編集時の選択解除・カメラ映像継続の合格へ拡張しない。
- 全体受入・本人受入・Azureは未実施。本票担当は保存済み証跡の読取比較と本票編集のみで、GUI・DB・アプリ・カメラ・buildを起動／変更していない。

戻す場合は本結果票と、本票のために新規作成した読取比較証跡だけが対象。DB・売上・保存volumeの削除は不要。
