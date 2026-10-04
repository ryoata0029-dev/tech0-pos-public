# Mac継続残試験：実会員照会保留・旧応答と通常UI復帰

2026-10-04。本人は残試験の同時並行と、後続のiPhone・カメラ試験を許可した。担当CはMacの準備・本票編集・保存証跡の独立読取に加え、主担当から委譲された固定profile／ポート分離のtools変更を担当する。アプリ・DB・server・build・GUIと実環境操作は主担当だけが扱う。**本票の作成は実行・合格の記録ではない。**

根拠は[TC-03](../tests/テストケース.md#tc-03)、[TC-18〜29](../tests/テストケース.md#tc-18)、[会員と待ちの受入](../requirements/受入条件_現行.md#r-topic-23)、[設計4.2](../design/画面と業務処理.md#sec-4-2)、[復帰設計5.1.3](../design/通信とデータ.md#sec-5-1-3)、[次取引7.5](../design/保存処理.md#sec-7-5)、[再認証8.1.1](../design/認証と運用.md#sec-8-1-1)。[直前の限定実証](非カメラ_並行検証_進行結果.md)・[TC03結果](Mac_TC03_非カメラ_並行再検証結果.md)・[19自動回帰](復帰_残試験_自動検証.md)の未確認を、今回の結果へ自動的に読み替えない。

## 1. 固定対象と開始条件

主担当の確定構成は新規profile `parallel-mac-next`、container `tech0-pos-parallel-mac-next-mysql`、volume `tech0-pos-parallel-mac-next-mysql-data`、私有 `.parallel-mac-next-local/`、証跡 `evidence/parallel-mac-next/`。Mac専用MySQLはloopback **3317**、Next HTTPSは **8453**、FastAPI HTTPSは **8454**。phoneの `parallel-next` は3307／8443／8444で稼働を維持でき、Macの起動・停止から変更しない。phoneのDB・Cookie・カートを引き継がず、Mac専用publicOriginで正規login→初回start→Cookie受取確認→初回カートを作る。API担当のphone側別schema `pos_api_validation` とも混同しない。

REGISTERはactive_context・current_cart・active_sessionを1組だけ持ち、[StartupService](../../backend/app/services/startup.py)が元担当者と対応Cookieを照合する。別端末の同じSTAFF_Aというだけでは復帰できない。Cookieの読取・コピー・移植、開始記録のリセット、別担当者による代用を行わない。Macの `pos_validation` は専用container内に新規作成し、独立STAFF password・relay secret・TLS・origin・Cookieを用意する。phoneの同名schemaとは別DBである。

固定[wrapper](../../tools/parallel_mac_next.py)・[profile／port mapping](../../tools/m2_local_profile.py)・backend起動対象・HTTPS・snapshot先を登録し、対象一致を独立レビューしてから主担当が実行する。既存mac-parallel wrapperは別対象を強制するため実行しない。新wrapperは環境変数による対象差替えを受けず `parallel-mac-next` を強制する。fresh prepareは既存私有directoryを拒否、MySQL作成は同名container／volumeと3317の占有を拒否する。`finish-setup` は証跡directoryがなく、専用secrets・mysql-root・CA・server.crt・server.keyが揃ったprepare中断後だけ許可し、MySQLのfresh guardは省略しない。

Nextの起動引数に専用profile／8453を含め、backendは専用TLS keyパスでプロセスを識別する。停止は専用process記録のprofile／port／markerと実command、tunnelは専用CAパス・profile／port、containerは証跡の実IDを照合する。起動時mysql-environment、process記録、tunnel記録、Mac DB snapshotと終了時記録で対象／portを確認する。phone側のPID・container ID・ポート継続は主担当が前後観測し、ソース検査だけで非干渉実証としない。

今回実機に出すbuild ID・ソースhash・全検査を固定し、phone稼働中にbuildを上書きしない。前回の197件／`5_wgTZOtPLE3as7vfiFAN` は過去の検査記録であり、今回の異なる版の代用にしない。新カートID・context ID・開始版・元売上件数を観測する。IDや版を旧証跡からコピーしない。

fixtureの架空会員 `MEMBER_1` と `MEMBER_0` の存在を確認する。以下は旧照会A=`MEMBER_1`、新会員B=`MEMBER_0` と定義する。両方の金額が同じでもmember_idで判別する。商品0001=103円税10%、0002／0003各107円税8%、数量3／1／1なら、非会員は523＋47=570円、確認済み会員は493＋44=537円。phone用の追加コードや数量99をMac期待値へ流用しない。Macのfixtureが異なる場合は実投入値に合わせて独立期待値を先に確定する。

## 2. 保留位置とAPIの期待値

[mac_recovery_backend.py](../../tools/mac_recovery_backend.py)の `member-late` は次の実処理を通す。

1. prepare_memberの更新TXを実COMMIT。PENDING・旧会員操作PREPARED・受付版をDB確定し、`gate-<tag>.json` を作る。
2. 実readonly会員lookupを完了しTX／接続を閉じる。`lookup-held-<tag>.json` を作り、finish_memberの更新TXを始める前に私有releaseファイルを待つ。`found=true`・`after_real_lookup=true`・`outside_update_transaction=true` と同じoperation_idを照合する。
3. 新選択が先に確定した後にrelease。旧finish_memberは旧操作のREJECTEDを読み、カート／明細へ旧照会結果を反映しない。`lookup-released` と `lookup-finished` を作る。

これは**実照会完了後・反映前の保留**であり、会員DBの照会中ロックや実サービス不能ではない。gateだけではlookup完了を証明できない。最大待機は600秒で、その経過だけで正常解放としない。タグは一度だけ使い、予期しない要求がgateを消費していないか、対象cart_id／operation_id／版で照合する。

[prepare_member／finish_member](../../backend/app/services/business.py)はPENDING中の新会員指定・非会員選択を許可する。新選択の新しいID／現在版で旧PREPAREDを `REJECTED / MEMBER_LOOKUP_SUPERSEDED` にし、新会員Bは受付と適用の2増分、非会員は1増分で確定する。旧遅着finishの前後では版も内容も不変。通常再照合のSYNCが後で版を進める場合、その増分を旧finishに帰属させない。

重要なHTTP分類：[API response](../../backend/app/api/business.py)は旧 `REJECTED / MEMBER_LOOKUP_SUPERSEDED` を **409 Error** に変換する。`lookup-finished` はサービス内部のOperationResultであり、Chromeが200 Operationを受けた証拠ではない。新選択は200／APPLIED、旧HTTPの期待は409／MEMBER_LOOKUP_SUPERSEDEDである。

## 3. 最優先の2条件

| 条件 | 開始と新選択 | 独立期待値 |
|---|---|---|
| L1：旧A→新B | NON_MEMBERからA=MEMBER_1を実照会保留。新操作でB=MEMBER_0を確認成功させてから旧Aを解放 | CONFIRMED／MEMBER_0／537円、pending_member_id・active_member_operation_id=null。旧AはREJECTED／MEMBER_LOOKUP_SUPERSEDED、新BはAPPLIED。旧完了前後の9DB集合不変・売上増分0 |
| L2：旧A→非会員 | 正常確認済みMEMBER_0／537円からA=MEMBER_1を実照会保留。新操作で非会員を明示選択してから旧Aを解放 | NON_MEMBER／570円、member_id・pending_member_id・active_member_operation_id=null、値引き0。旧AはREJECTED／MEMBER_LOOKUP_SUPERSEDED、非会員操作はAPPLIED。旧完了前後の9DB集合不変・売上増分0 |

両条件の全段階で同じcart・行ID・数量3／1／1・単価・税・値引き候補・条件固定時刻を保持する。新選択が変更する値引き・小計・税・合計と、保持する購入前条件を分ける。旧会員Aの適用、旧版への巻戻し、意図しない購入・別カート作成は不合格。

### 確実に実施できるサーバー遅着の順序

```sh
backend/.venv/bin/python tools/parallel_mac_next.py snapshot --tag mac-l1-before
backend/.venv/bin/python tools/parallel_mac_next.py arm --kind member-late --tag mac-l1-late
```

主担当が通常POSの会員欄へMEMBER_1→「照会・再照会」。実lookup-heldとPENDING／PREPAREDを確認し、送信中DOMと別接続DBを採取する。元の送信中画面はbusyのため会員3操作も無効でよい。別の通常POSタブで同じcartのPENDINGを正規取得すると、再入力／再照会／非会員は有効、商品／数量／削除／選択解除／購入は無効となる。readonly会員GET成功だけではPENDINGを解消しない。

今回の最初の実施では、主担当の指定に従い、通常POSで商品3種の数量3／1／1を作ってから旧MEMBER_1を保留し、別タブの同一origin検証panel `/__tc03` を使う。L1は「MEMBER_0を新しく指定」、L2は「非会員を新しく選択」を通常ボタンで要求する。新選択のAPPLIEDとDB期待値を確認した後、旧完了前DBを採取して解放する。panelは現在カート／版を正規resumeで取得し新操作IDを生成するため、IDのハードコードやCookie移植をしない。これは検証panelからの正規API新選択であり、別POSの通常会員入力を実施済みとは書かない。別POSからの新選択は上記の追加方式として区別する。

```sh
backend/.venv/bin/python tools/parallel_mac_next.py snapshot --tag mac-l1-new-before-release
backend/.venv/bin/python tools/parallel_mac_next.py release --tag mac-l1-late
backend/.venv/bin/python tools/parallel_mac_next.py snapshot --tag mac-l1-after-old-finish
```

最後のsnapshotは実際のlookup-finished保存を確認してから行う。L2は全tagのl1をl2へ変えた新規タグで別実施する。exec承認仲介に約24秒かかった過去があるため、この順序は中継10秒を超える可能性が高い。**その場合の合格範囲は旧サーバー処理の不反映であり、旧HTTPのChrome到達は未確認。** 中継タイムアウト後でも旧実処理が残ることを記録し、新選択・明示GET・再読込による復帰と混同しない。

別POSから新選択した場合はBroadcastChannelで元POSを停止させる。[RegisterCart](../../frontend/app/register-cart.tsx)の通知処理による「別タブの操作を検知」「状態を再確認」は正常な停止であり、自動ready復帰を期待しない。検証panelは更新通知を送らないため、この通知を期待しない。旧応答後も新会員を旧Aで上書きせず、元POSの通常「状態を再確認」後に新B／537円または非会員／570円を表示することを照合する。再確認でmember lookupを自動起動した証拠があれば分けて調べる。

### 10秒内の旧HTTP到達を追加する場合

長いDB／画像／exec採取を挟まず、別POSの新選択確定→旧releaseを短い通常UI呼出し内で行える主担当の方式が成立したときだけ追加する。現在の[product release-after](../../tools/mac_product_release.py)は商品gate専用で、member-lateには使えない。主担当が新しい局所helperを用意するなら、実lookup-held・同cart／旧操作ID・新選択確定を確認し、未使用tagの私有releaseだけを作る方式を別レビューする。固定秒数後の先行解放だけでは「新選択後に旧完了」を保証しない。

原要求開始・lookup-held・新選択確定・release・旧finish・UI停止／新状態取得のUTC順を残す。旧要求開始から中継返却まで10秒未満か確認し、正規Chrome DevTools Networkの当該member PUT **409とResponseのMEMBER_LOOKUP_SUPERSEDED** を保存する。auth完了後に観測し、Headers／Cookie／Payloadは保存しない。複数PUTの行は時刻・順序・statusで区別する。本文に操作IDがないため、同名行を識別できなければ直接到達未確認とする。gate完了・画面停止だけから生HTTP到達へ補完しない。

[既存panel](../../tools/mac_tc03_panel.html)の「MEMBER_0を新しく指定」「非会員を新しく選択」は、同じ正規APIを通常のCookie自動送信で呼び、新ID／現在版をresumeから得るfixtureである。必要ならrootが別タブの**検証画面**として使うが、通常POSで新選択した証拠とは区別する。panelはpos-cart-updatesを送らないため、旧HTTPの実拒否表示を通知から区別しやすい。今回新profileの `/__tc03` GET許可はHTTPS harnessへ登録済みで、固定対象レビュー後にだけ使用する。公開障害制御APIは追加しない。CUAから直接APIを呼んだりアプリstate／localStorageを書き換えたりしない。

## 4. 通常UIで追加できるChrome復帰と限界

| 残条件 | 今回の通常UIで可能な確認 | 残る条件／必要な別方式 |
|---|---|---|
| TC21 EDITING／会員PENDING | 未送信コード・会員欄・数量と選択行を持つ状態→正規reload。内容・会員待ち・同cart・保持価格を復帰、未送信入力／選択をクリア。PENDINGでは商品／購入停止・会員選択だけ復帰 | これだけで完全終了・全7状態を合格にしない。今回の並行稼働中はChrome全体終了を実施せず、別の占有可能な時間枠で確認する |
| TC16／20／21 保存結果不明 | 既存purchase応答切断をarm→通常購入1回。unknown表示・編集禁止→正規reload／状態再確認。実保存済みなら固定結果、未保存を推測して再購入しない | 元ID・補助記録はアプリが通常購入で作る。偽storage故障／壊れた複数記録は製造しない。purchase切断だけでは未保存UNKNOWN・SAVING照合503の全条件にならない |
| TC17／21 SAVING→UNSAVED | purchase-holdで実受付を保留した状態をDBで確認→通常状態再確認でresolveを確定→旧release→旧処理拒否。UNSAVED選択肢・同cart保持を確認 | purchase-holdは実保存TX前であり、COMMIT成否不明や売上TX途中故障とは異なる。resolveと旧finishの順序を証明する。売上が先に保存されたらSAVEDとして判定を変える |
| TC24 next応答断 | 正常保存後にnext切断→通常「閉じて次の取引へ」→正規照合。同旧CLOSED・新current空cart・売上1維持、別空cartを作らない | 現HTTPS wrapperは切断した応答を後で届けない。さらに先の取引へ進んでから古いNEXT応答を受ける条件には別の局所応答保留fixtureが必要。19自動回帰で代用しない |
| TC28 再認証 | 実8時間固定期限到達後、通常操作で401→元担当者form→誤認証／別担当者／正しい再認証を通常UIで観測する方法はある | 既存controlに認証期限操作はない。今回の短時間枠では6状態ごとの実失効を保証できない。ログイン画面のpattern検査や再読込成功を、失効・再認証と数えない |
| TC20 storage障害／複数破損記録 | 通常購入が作る元記録と未知結果からの正規照合を観測する | storage注入・JS state変更不可。Chrome設定でJS自体を止めた試験は、実ハンドラのstorage故障とは異なる。破損・容量・複数未解決を通常UIだけで任意製造できるとは断定しない |
| TC18／19／29 同時・通知欠落・Cookie逆順 | 通常別POSの存在警告・正規更新通知・停止と再確認は観測できる | 2クリックを順番に行っただけで同時競合を称さない。通知遮断やCookie逆順到着をGUIで任意に作れるとは断定しない。既存実DB／自動検査と区別 |

本票の実行優先はL1→L2→両結果のDB／UI照合。追加Chrome復帰はrootが時間・既存証跡の同一条件共有・未解決操作の有無を確認して選ぶ。全表を今回実施予定／合格としない。新schemaを使うAPI担当の7境界検査と、Mac実画面の観測を別々に記録する。

## 5. 必要証跡・停止・終了

各L条件はbefore・lookup-held/PENDING・new-selection-before-release・after-old-finish・reconciledのDB、元POS送信中／通知停止／再確認後と別POS PENDING／新選択のDOM、gate／lookup-held／lookup-released／lookup-finished、実行tag・版・元／新操作IDを採取する。9集合の旧完了前後完全一致と、全段階の保持条件・売上増分0を照合する。再確認後SYNCの増分は別区間へ分ける。生HTTP到達はNetworkが揃った条件だけ確認にする。

fixture・profile・port・build不一致、Cookie対応不能、実lookup-held不成立、新選択前の旧完了、旧member適用、版巻戻し、予期しない売上／新cart、600秒期限・トンネル失効を停止理由として保存する。観測失敗をアプリ不合格と自動同一視せず、成立しなかった必須条件は未確認で残す。control待機を放置しない。phone並行中は共有buildとChrome全体を停止・変更しない。

rootが全保留処理の終了・最終DB・Mac専用tunnel／Next／FastAPI／MySQL停止、3317／8453／8454閉鎖・container exited・volume／証跡保持・秘密値非混入を記録する。phoneの3307／8443／8444と専用containerはMac停止対象に含めず、phone実行票に従う。phoneのDB、API別schema、過去環境は削除しない。本票担当はcamera／iPhone／DB／GUI／buildを操作しない。全TC・Azure・本番・M7本人受入・commit／pushの完了を意味しない。
