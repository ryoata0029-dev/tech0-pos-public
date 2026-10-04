# iPhone・カメラ 継続試験結果

2026-10-04。[継続作業票](iPhone_カメラ_継続試験作業票.md)に沿ってP1a/b・P2a/b・P3a/b・P4a/b・P5b/cの**10小条件を本人報告と実DB差分で限定確認し、独立監査も整合。P5a許可拒否は未実施。** 最終版12／11898円・4明細・売上0。専用環境は日本時間17:17に停止しDB／証跡を保持した。全TC・M5全体・M7受入は未完了。[旧iPhone限定結果](iPhone_カメラ試験_結果.md)と[Mac選択解除結果](商品選択解除_修正検証.md)は別版・別条件の証拠として保持する。

開始追記：本人原文「表示できた」。[今回の開始DB](evidence/parallel-next/db-iphone-screen-ready.json)はUTC07:39:42.993619、REGISTER READY、担当STAFF_A、cart `47605231-5c96-439c-9533-349de5f43c0f`／EDITING／version2、会員UNSPECIFIED、明細0・合計0円・売上0。初回contextはUTC07:38:52に確認済み、SYNC1件APPLIED。これは本人の画面表示報告とサーバー状態の照合であり、端末版・client build直接観測・撮影・P1以降の成功ではない。後段の準備時点のUNSTARTED／未実施記録は履歴として保持する。

## 今回の環境・版

| 項目 | 記録 |
|---|---|
| 指定対象 | profile `parallel-next`、container `tech0-pos-parallel-next-mysql`、volume `tech0-pos-parallel-next-mysql-data` |
| 私有領域・証跡 | `.parallel-next-local` ／ `docs/implementation/evidence/parallel-next`。秘密値はGit除外の私有領域に限り、公開証跡／ログへ出さない。撮影映像・音声を保存／送信しない |
| 成立・runtime／build／source hash | [環境](evidence/parallel-next/mysql-environment.json)・[runtime](evidence/parallel-next/runtime-start.json)を読取確認。build `5_wgTZOtPLE3as7vfiFAN`、記録のHome／RegisterCart／Camera／posの4ファイルhashは本票担当の現在source読取hashと一致 |
| iPhone・OS・Chrome | iPhone 15／iOS27.0.1／Chrome155.0.8059.24。[本人再確認](evidence/parallel-next/iphone-device-owner-report.json)の「さっきと同じやで」と前の申告を対応づける。端末設定画面・client buildの直接観測ではない |
| URL・通常読み込み／client build観測 | 今回originは `https://ebook-psp-provincial-recorded.trycloudflare.com`。本人が商品登録画面の表示を報告、client build直接観測は未取得 |
| 担当者・context／cart・開始版・会員 | 準備時の[before-phone DB](evidence/parallel-next/db-before-phone.json)はUNSTARTED。本人表示報告後の[開始DB](evidence/parallel-next/db-iphone-screen-ready.json)はREADY／STAFF_A／EDITING／version2／UNSPECIFIED、明細0・売上0。contextとcart IDは開始追記と原本を参照 |
| コード対応・価格／税・開始数量 | 同before-phoneに6商品。対応は下表。各比較で保持価格・税・会員・金額を照合済み。最終数量0001=99／EAN13=1／EAN8=4／0002=1 |
| 開始／終了・停止／volume保持 | 初回表示と開始DBから条件別に検証。[最終DB](evidence/parallel-next/db-iphone-final.json)保存後、[17:17:51 JSTの停止](evidence/parallel-next/shutdown-iphone-final.json)を確認。3307／8443／8444閉・container exited・volume保持 |

[MySQL初期証跡](evidence/parallel-next/mysql-snapshot.json)はMySQL8.4.11、TLS必須・暗号化接続、PRODUCT6、AUTH_SESSION／BROWSER_CONTEXT／CART／CART_OPERATION／売上3表0を記録する。DB対象はdigest固定arm64・127.0.0.1:3307。表件数とgrant列挙は実権限の全否定試験やアプリの受入を証明しない。

| 商品ID | 今回DBコード | 単価（円） | tax_rate_id |
|---|---|---|---|
| 1 | `0001` | 103 | 2 |
| 2 | `0002` | 107 | 1 |
| 3 | `0003` | 107 | 1 |
| 4 | `0001234567895` | 103 | 2 |
| 5 | `00123457` | 103 | 2 |
| 6 | `Ab_01` | 103 | 2 |

DBコードの一致はバーコード画像の物理的な読取成功ではない。今回試験用の形式・提示媒体は開始前に本人と主担当が固定する。初期DBにカートがないため、P1以降は本人の通常ログイン／開始／前提登録後に条件別baselineを取得する。

今回は[既検査版runtime](evidence/mac-parallel/runtime-pattern-fix.json)のbuildを主担当が使用している。全197件（Python78＋Node119）成功、[検査ログ](evidence/mac-parallel/check-pattern-fix-retry.log)・[buildログ](evidence/mac-parallel/build-pattern-fix.log)が存在し、今回runtimeとHome／RegisterCartのhashも一致する。初回runtimeの前検査ログ参照は実ファイル不在だったため、主担当が履歴を保持し[参照訂正の追補](evidence/parallel-next/runtime-check-reference-correction.json)を作成した。追補は正しい3証跡とアプリ／build不変を記録し、本票担当も存在を確認した。これらは稼働版を特定する根拠であり、iPhone側でそのclientを読んだ直接証跡・今回実機合格ではない。旧iPhone2版 `1Br0vNrgQ6qQbXu1qPCjx`／`lHLimVliyl-yfc2bz9kbr`、旧Mac TC01〜03版 `_6zNKKv-evmUKeL_8XYLh` と区別する。

## 条件別結果

### P1の準備操作と解除前状態（採取時点の履歴）

本人原文「数量変更おしてもうた。とりあえず数量１に戻して、８を入力し、数量変更をおしてない状態にした」。最初の数量変更と1への復元は準備操作として記録し、選択解除の前後比較へ混ぜない。途中数量8と最後の入力欄だけ8は本人申告であり、未送信入力をDBから観測したとは扱わない。

[新しい解除前DB](evidence/parallel-next/db-iphone-p1-before-deselect.json)はUTC07:42:07.618869、同じcart／context、EDITING／version5、0001の1明細・登録済み数量1・単価103円・値引き0・税10円・合計113円、会員UNSPECIFIED、売上0。開始版2からADD_LINE1件とSET_QUANTITY2件がAPPLIED（版3→4→5）。DELETE_LINE／購入なし。ここをP1a比較のbaselineとし、選択解除後の採取・本人報告はまだ未取得。P1bの再選択はP1a照合後に別条件で案内する。

### 実機開始前UTC07:30の待機状態（履歴）

[最終DB](evidence/parallel-next/db-ready-final.json)は2026-10-04 UTC07:30:33（日本時間16:30:33）、[phone稼働記録](evidence/parallel-next/environments-phone-ready-final.json)はUTC07:30:36時点。本票担当が初期DB・前回稼働記録・今回最終記録を独立にファイル読取比較し、[比較JSON](evidence/parallel-next/comparison-phone-ready-final-readonly.json)へ12確認項目と限界を保存した。初期DBとのregister／contexts／carts／lines／operations／purchases／purchase_lines／purchase_taxes／productsの9射影集合は完全一致。REGISTER 1はUNSTARTED、active_context/current_cartはnull、カート・売上・操作0、商品6件を保持する。これは選択された列の比較であり、認証/session情報や専用API schemaの全データを含む比較ではない。

phoneのcontainer IDは初期記録と一致してrunning、3307／8443／8444は開いているとの主担当読取記録。Next／FastAPI・tunnelのPIDとoriginは直前記録と一致し、build `5_wgTZOtPLE3as7vfiFAN` とbuild-manifest hashも不変。本票担当は保存値とbuildファイルを比較し、GUI・DB・ps／Docker／socketの再実行はしていない。公開URLの現在の到達性、iPhoneの読み込み・client build・撮影可能性はこれだけでは確認しない。

Mac専用環境の[別の停止記録](evidence/parallel-mac-next/shutdown-final.json)はUTC07:29:46に3317／8453／8454閉鎖、container exited、専用volume保持を報告する。phone-onlyの[読取helper](../../tools/parallel_environment_verify.py)はphoneの固定container ID／port、PID command marker、backend専用TLS key、tunnel専用CA／URL、buildを検査し、Macを検査・停止しない。Mac停止の根拠はこの別証跡であり、phone記録から補完しない。追加の重大な対象混同・状態更新は読取レビューで見つからなかった。

phoneの稼働記録は主担当による `secrets.json` 内の既知文字列と私有directoryのGit候補除外、frontend／backend／tunnelログへの既知文字列不在を報告する。本票担当は秘密値を読み取らず、その検査を再実行していない。Macの同検査結果も別停止記録にある。既知文字列照合を、全形式・全ファイルの秘密情報不存在の保証へ広げない。

本人から今回のiPhone操作回答・OS／Chrome版は未取得。P1〜P5は全て未実施のまま。本票はこの読取時点の状態で凍結する。同じ現在の試験を待機しており、過去試験環境の再利用・期限延長・将来の別試験許可を意味しない。本人操作が可能になった時点で主担当が対象・期限・版・接続成立を確認し、必要な条件別前DBから進める。**試験終了後に主担当が今回phoneのtunnel／Next／FastAPI／MySQLを停止して3307／8443／8444閉鎖・専用volume保持を記録する。今回phoneの停止はまだ実施済みではない。**

### 実機操作後の条件別確定結果

| 条件 | 本人原文・実際の操作 | DB証跡・比較 | 判定・限界 |
|---|---|---|---|
| P1a 削除なし選択解除 | 案内後の本人原文「想定通りです。１が残りました」。選択商品欄・数量入力欄の消失と商品数量1保持への肯定報告 | [解除前](evidence/parallel-next/db-iphone-p1-before-deselect.json)→[解除後](evidence/parallel-next/db-iphone-p1-after-deselect.json)、[9射影比較](evidence/parallel-next/comparison-iphone-p1-deselect.json)すべて一致、版5・1明細・数量1・113円・売上0、操作4件不変 | 当該条件を限定確認。入力欄のみ8は本人申告。ブラウザ要求の直接捕捉なし、DB不変を全HTTP未送信の証拠としない。実カメラ保持は未試験 |
| P1b 再選択で登録済み数量 | 同じ商品を再選択して数量欄1かとの質問に本人原文「１になってる」 | [解除後](evidence/parallel-next/db-iphone-p1-after-deselect.json)→[再選択後](evidence/parallel-next/db-iphone-p1-after-reselect.json)、[9射影比較](evidence/parallel-next/comparison-iphone-p1-reselect.json)すべて一致、版5・数量1・113円・売上0 | 当該条件を限定確認。未送信8から1への入力欄変化は本人報告、DB射影に入力欄は含まれない。全HTTP未送信・実カメラ保持の証明ではない |
| P2a 数量99の上限理由・保持 | 本人原文「エラーが表示され、数量９９のまま、カメラもひらいてます」 | [カメラ前](evidence/parallel-next/db-iphone-p2-before-camera.json)→[上限後](evidence/parallel-next/db-iphone-p2-after-limit.json)、[比較](evidence/parallel-next/comparison-iphone-p2-limit.json)。保護8射影不変、既存操作不変、0001のADD_LINE1件だけREJECTED／QUANTITY_LIMIT、要求版6・適用版null。数量99・版6・11216円・売上0 | 当該条件を限定確認。エラー表示とカメラ開は本人報告。HTTP422のChrome受信・MediaStreamトラックは直接未観測。別コード継続はP2bで別検証 |
| P2b 削除／再開始なし別EAN-13追加 | 初報「１個追加されその数量でとまりました」。再開始／削除なし・最後に閉じたかへの追加確認に「手順通り実施しました」 | [上限後](evidence/parallel-next/db-iphone-p2-after-limit.json)→[次コード後](evidence/parallel-next/db-iphone-p2-after-next-code.json)、[比較](evidence/parallel-next/comparison-iphone-p2-next-code.json)。新ADD_LINEはEAN-13の1件だけAPPLIED、版6→7、元0001行完全同一・数量99、新商品1個。小計10300・税1030・11330円・売上0。[終了後確認](evidence/parallel-next/comparison-iphone-p2-closed-p3-before.json)の9射影も不変 | 当該手順条件を限定確認。再開始なし・カメラ表示／終了は本人報告。新DELETE／SET／購入なしはDB比較。HTTP受信・実トラック・提示秒数は直接未観測 |
| P3a 同コード約5秒継続 | EAN-8を枠から外さず約5秒提示して閉じる案内に本人原文「１個登録で数量１でとまった」 | [提示前](evidence/parallel-next/db-iphone-p2-closed-p3-before.json)→[提示後](evidence/parallel-next/db-iphone-p3a-after-hold.json)、[比較](evidence/parallel-next/comparison-iphone-p3a-hold.json)。EAN-8のADD_LINE1件だけAPPLIED、版7→8・新商品1個、元2行と元操作不変。小計10403・税1040・11443円・売上0 | 当該報告とDB差分を限定確認。約5秒は依頼目安で実測なし、ぼけ／decoderイベント時系列・HTTP受信・トラック直接観測なし。終了操作の明示個別報告はなく、次条件は閉じた状態から新規開始する |
| P3b 同じ撮影回の意図再提示 | 初回提示で数量2→枠外にしてカメラ開待機の案内に「おｋ」。そのまま開始押し直さず1回再提示し約5秒継続→閉じる案内に「３になり、止まってる。OK」 | [初回比較](evidence/parallel-next/comparison-iphone-p3b-first-scan.json)で版8→9／数量1→2／適用1件。[再提示前](evidence/parallel-next/db-iphone-p3b-before-represent.json)→[再提示後](evidence/parallel-next/db-iphone-p3b-after-represent.json)の[比較](evidence/parallel-next/comparison-iphone-p3b-represent.json)は版9→10／数量2→3／適用1件、同じ行の条件・他2行・元操作保持。小計10609・税1060・11669円・売上0 | 当該案内条件と本人報告・分離したDB差分を限定確認。初回受付と再提示を別で数える。物理枠外／再開始なしの順序は案内への報告に基づき、表示・track・提示秒数・500ms採否を直接観測したとはしない |
| P4a 背景復帰で自動再開なし | バーコードを映さず開始・待機に「開始した」。ホームへ移動し約5秒後同じChromeへ戻り再読み込み・開始をしない案内後、カメラ閉・自動再開なしかへの本人「閉じてる」 | [背景前DB](evidence/parallel-next/db-iphone-p4-before-background.json)→[背景後DB](evidence/parallel-next/db-iphone-p4-after-background.json)、[比較](evidence/parallel-next/comparison-iphone-p4-background.json)で9射影不変、版10・11669円・数量99／1／3・売上0、操作増分0 | 当該表示報告とDB不変を限定確認。ホーム／復帰・表示閉は本人報告、約5秒は実測なし、MediaStreamTrack／visibilityイベント時系列・HTTPは直接未観測 |
| P4b 手動再開して追加 | 商品カメラを本人が再開始しEAN-8を1回提示して閉じる案内に本人原文「手動再開でき、数量４」 | [背景後](evidence/parallel-next/db-iphone-p4-after-background.json)→[手動再開後](evidence/parallel-next/db-iphone-p4-after-manual-restart.json)、[比較](evidence/parallel-next/comparison-iphone-p4-manual-restart.json)。EAN-8のADD_LINE1件だけAPPLIED、版10→11・数量3→4・同じ行条件／他2行／元操作保持、小計10712・税1071・11783円・売上0 | 当該手動再開と追加を限定確認。カメラ映像／トラック／HTTPは直接未観測。閉じる操作は案内済み、終了トラック状態の証明にはしない |
| P5a 許可拒否の案内 | 初報「でなかった」、開始ボタンとの混同確認を経て本人「それなら、カメラの使用は許可されています。とでてました。」 | [開始後DB](evidence/parallel-next/db-iphone-p5-no-dialog-before.json)・[前提比較](evidence/parallel-next/baseline-iphone-p5-no-dialog.json)でP4b後から9射影不変、版11・11783円・売上0 | 許可済み表示の本人報告。拒否操作は行っておらずP5a未実施。表示の出所・選択肢付きダイアログは直接未観測、初報だけでその不在を確定しない。設定変更なし |
| P5b 非検出から手入力へ | バーコードを映さず約5秒待ちカメラ内文言の報告後に閉じる案内へ本人「コードをカメラに提示してください」 | [開始後](evidence/parallel-next/db-iphone-p5-no-dialog-before.json)→[非検出後](evidence/parallel-next/db-iphone-p5-after-nondetection.json)、[比較](evidence/parallel-next/comparison-iphone-p5-nondetection.json)で9射影不変、版11・11783円・売上0・操作増分0 | 非検出案内の本人報告とDB不変を限定確認。許可拒否・未登録商品エラーとは別条件。約5秒・decoder／track／HTTPは直接未観測。閉じる操作は次の手入力案内でも指定する |
| P5c 手入力追加 | 非検出後に閉じて手入力へ→0002検索→追加1回の案内に本人「演習食品107円Aであってるかな？それは登録された」 | [非検出後](evidence/parallel-next/db-iphone-p5-after-nondetection.json)→[手入力後](evidence/parallel-next/db-iphone-p5-after-manual-entry.json)、[比較](evidence/parallel-next/comparison-iphone-p5-manual-entry.json)。0002／商品2／単価107円／税8％／数量1、新ADD_LINE1件APPLIED・版11→12。元3行と元操作保持、小計10819・税8＋1071・11898円・売上0 | 非検出から手入力への当該条件を限定確認。許可拒否後の試験ではない。商品名は本人報告とfixtureコードを照合。HTTP／実トラックは直接未観測 |

本人原文と独立DB前後・要求記録が揃った範囲で更新する。DB差分だけで全API未送信・実トラック停止・映像表示・ブラウザ応答到達を断定しない。Mac同時更新・SYNC・期限・通知は記録し、対象差分と分けられない条件は判定保留とする。本人操作の映像・音声・画像・録画は保存／送信しない。

P1aは別担当が[独立比較](evidence/parallel-next/comparison-iphone-p1-deselect-independent.json)を作成し、9射影一致、同cart／context／line、版5・数量1・113円・新操作0、準備SET_QUANTITY2件がbaseline以前であることを原本から確認した。P1bも[独立比較](evidence/parallel-next/comparison-iphone-p1-reselect-independent.json)で同じ9射影一致と新操作0を確認した。本人UI報告とDB不変の整合を限定確認し、両条件で重大な不整合の指摘なし。未送信入力の破棄はDBから直接観測していない。

P2の採用コードは現在登録済みのCode128 `0001` に固定する（作業票の許容候補）。次コードはEAN-13 `0001234567895`、現在は行なし。通常UIで0001を99に確定し選択解除した後、カメラ開始前の別baselineを取得する。非会員・単価103円・税10％の99個は小計10197円、税1019円、税込11216円が期待値で、準備完了後に実DBと照合する。

P2準備の本人原文「99にして解除した」。[開始前DB](evidence/parallel-next/db-iphone-p2-before-camera.json)（UTC07:47:54.305268）と[baseline照合](evidence/parallel-next/baseline-iphone-p2-camera.json)で、同cart／context・EDITING／版6、0001数量99、小計10197・税1019・税込11216円・売上0を確認した。P1b後からは通常SET_QUANTITY1件APPLIED（版5→6）だけ追加、選択解除は本人報告。次EAN-13（商品4）は行なし／事前数量0。ここをP2aの前状態とし、カメラ開始・0001提示・上限理由表示の本人結果はこれから取得する。

P2aは別担当の[独立比較](evidence/parallel-next/comparison-iphone-p2-limit-independent.json)でも保護8射影不変・元操作5件不変・拒否1件だけ追加を確認し、重大不整合なし。P2bの税は同じ10％区分の合算小計10300から1030円となり、前状態の1019円から11円増える。追加103円の単体税10円をそのまま足す計算は用いない。

P2bも別担当の[DB独立比較](evidence/parallel-next/comparison-iphone-p2-next-code-independent.json)で元操作6件と0001行の不変、新EAN-13適用1件、合計11330円を確認し重大不整合なし。この独立記録と初報比較JSONは追加の手順確認前のpending記録として保持する。後続の本人「手順通り実施しました」と[終了後DB](evidence/parallel-next/db-iphone-p2-closed-p3-before.json)／[追補比較](evidence/parallel-next/comparison-iphone-p2-closed-p3-before.json)が確認待ちを補う。終了後の9射影は不変。次EAN-8 `00123457`（商品5）は行なし／数量0であり、ここをP3aの新baselineとする。

上記P2b手順追補も別担当が[独立比較](evidence/parallel-next/comparison-iphone-p2-closed-p3-before-independent.json)で9射影不変・次EAN-8事前数量0を確認した。P3a後はEAN-8数量1／版8をP3b前状態とする。P3bはカメラを閉じた状態から新規1回開始し、最初の提示で数量2を確認して枠外へ出し、カメラを開いたまま中間DBを採取する。その後だけ同じ撮影回の再提示を案内し、初回受付と再提示分を別差分で検証する。

P3aの[別担当独立比較](evidence/parallel-next/comparison-iphone-p3a-hold-independent.json)も初回適用1件・既存2行／元操作保持・11443円を照合し重大不整合なし。P3b初回の本人原文「おｋ」と再提示前DBで数量2／版9を固定した。ここから開始を押し直さず同じEAN-8を1回再提示し、約5秒継続後に閉じる手順を案内する。期待は同じ行の数量2→3・版9→10と適用1件増分であり、カメラ再開始直後の初回1件を再提示分へ数えない。

P3b初回は別担当の[独立比較](evidence/parallel-next/comparison-iphone-p3b-first-scan-independent.json)でも適用1件・数量2・11556円を確認した。再提示後の本人「３になり、止まってる。OK」と再提示比較は数量3／版10・追加1件だけに整合。次P4はバーコードを映さず新規開始し、映像が開いた状態の前DBを採取してからホーム画面移行／同じChromeページ復帰を案内する。操作不明・読取増分があればP4の非読取条件を判定せず切り分ける。

P4準備の本人原文「開始した」。背景前DBはP3b後の9射影すべて不変で、数量99／1／3・版10・11669円・売上0を保持。ここからiPhoneホームへ移動し約5秒後同じChromeページへ戻り、再読み込み・手動カメラ開始をせず表示状態を確認するよう案内する。ホーム移行・復帰・カメラ閉鎖は本人の次回答を取得して別に記録する。

後続の本人「閉じてる」と背景後DBの9射影不変でP4aを限定確認した。背景後DBをP4b前状態（EAN-8数量3／版10）とし、本人が手動で商品カメラ開始→EAN-8を1回提示→閉じて手入力へを案内する。期待は数量3→4、版10→11、新ADD_LINE1件だけ・他2行保持・売上0である。

P3b再提示は[独立比較](evidence/parallel-next/comparison-iphone-p3b-represent-independent.json)で初回と異なる操作IDの追加1件・数量2→3・11669円を確認。P4aも[独立比較](evidence/parallel-next/comparison-iphone-p4-background-independent.json)で準備前後と背景復帰前後の両9射影一致を確認し、両条件で重大不整合なし。P4bの本人「手動再開でき、数量４」とDB追加1件を記録し、11783円／版11を次P5の前状態とする。

P5aは通常開始時に今回サイトの許可ダイアログが出る場合だけ本人が拒否する。出なければP5a未実施を記録し、設定変更で拒否を強制作成せずP5bの非検出から手入力へ進む。次の開始もバーコードを映さない。拒否／非検出の結果を別条件で記録する。

P4bは[別担当独立比較](evidence/parallel-next/comparison-iphone-p4-manual-restart-independent.json)でも数量3→4の適用1件・11783円・元行／元操作保持を確認し重大不整合なし。P5aの本人「でなかった」と通常開始後DBの不変を記録。ここをP5b非検出前baselineとし、同じ撮影でバーコードを映さず約5秒待ち、カメラ内文言の報告後に閉じて手入力へ移る案内を行う。時間は依頼目安で、計時合格へ扱わない。

P5a解釈訂正：本人原文「許可確認って、カメラ開始ボタンのこと？それなら出るし、押した」。アプリ内のカメラ開始ボタンと、Chrome／iOSの別の権限確認画面を区別する説明が不足していたため、初報のダイアログ不在は再確認待ちに戻す。初回比較JSONの `permission_denial_result=not_executed_no_dialog` はその時点の解釈として保持し、現時点の確定判定に使わない。開始ボタンを押したこと自体は拒否操作ではない。権限確認画面が別に出たかを次回答で確認し、拒否／非検出の条件を混同しない。

後続の本人原文「コードをカメラに提示してください」はP5bの案内表示報告として採用する。P5aの別ダイアログ不在の明示確認ではなく、拒否操作が行われた証拠もないためP5aは未実施／ダイアログ有無の解釈未確定を維持する。非検出後DBは9射影不変で、通常手入力用0002は行なし／数量0。次は閉じて手入力へ→0002検索→追加1回を案内する。期待は新0002数量1・版11→12・元3行保持・売上0で、数量入力ではなく通常商品追加を検証する。

許可状態の追加報告：本人原文「それなら、カメラの使用は許可されています。とでてました。」。許可済みの表示報告として記録し、拒否操作の試験は未実施を維持する。UI出所・実権限設定は直接未観測で、許可済み表示を拒否案内の成功へ読み替えない。P5cは拒否後ではなくP5b非検出後の手入力として検証する。

## 自動回帰と未確認範囲

以下のAPI・SQL・26件回帰の段落は、実機開始前の独立担当の読取記録である。「本人操作未実施」「版未取得」はその時点の状態であり、現在の実機結果・端末再確認は冒頭と条件別確定結果を参照する。

主担当はiPhone用 `pos_validation` と別schema `pos_api_validation` で追加API・DB検証を実行した。[実行結果](evidence/parallel-next/api-db-run.json)の8条件群はカメラ試験ではない。[phone前後比較](evidence/parallel-next/comparison-phone-after-api.json)に加え、本票担当も[前DB](evidence/parallel-next/db-before-phone.json)と[API検証後DB](evidence/parallel-next/db-after-api-db-run.json)のregister／contexts／carts／lines／operations／purchases／purchase_lines／purchase_taxes／productsをJSON直接比較し、9集合が完全一致、iPhone用レジはUNSTARTED・カート／売上0のままと確認した。今回の本人操作・実撮影はなお未実施。この前後不変は当該観測間の業務データに限り、共有コンテナの性能影響や全将来操作の非干渉を保証しない。

続く専用schemaの[条件5 SQL結果](evidence/parallel-next/api-db-conditions.json)は、実Repositoryの明示時刻による候補0／1／1／0と、別writerの未確定変更を保持した旧一式／COMMIT後の新一式を記録する。このSQL検証もiPhone試験ではない。本票担当は[phone SQL後比較](evidence/parallel-next/comparison-phone-after-sql.json)の元ファイルである前DBと[SQL後DB](evidence/parallel-next/db-after-sql-conditions.json)を直接比較し、同じ9集合が完全一致、UNSTARTED・カート／売上0を確認した。iPhone側のOS／Chrome版、client build観測、実撮影・映像終了は未取得のまま。

本票担当が今回実行した対象回帰は `frontend` の `node --test tests/register-camera.test.mjs tests/camera-feedback.test.mjs tests/scan-gate.test.mjs`、26件成功・失敗0。MODULE_TYPELESS_PACKAGE_JSON警告あり。新コード修正なし。実TSXハンドラ・模擬callback／mediaとScanGateの検証で、実撮影・実DOM・実Chrome・端末トラックの代替ではない。主担当の全検査／buildと実機判定は別記録。

P5bは[独立比較](evidence/parallel-next/comparison-iphone-p5-nondetection-independent.json)で9射影不変を確認。P5cも[独立比較](evidence/parallel-next/comparison-iphone-p5-manual-entry-independent.json)で0002追加1件・数量1・11898円・元3行保持に整合した。[全条件の独立監査](evidence/parallel-next/comparison-iphone-conditions-independent-audit.json)は10小条件の11差分（P3b初回／再提示を別比較）を生JSONから再比較し、既存独立証跡の36原本hash一致も確認。試験差分の新操作は拒否1件＋適用6件で別ID、準備の数量変更を試験結果へ混ぜない。P2bの手順追補とP5aの解釈訂正も維持し、重大不整合・過剰合格の指摘なし。独立担当はライブDB／GUI／環境を操作していない。

TC-03〜05全体、許可拒否（P5a）、会員変更／PENDING異常系、未登録拒否反復、一瞬の欠落・全照明、待機中／未知／GET失敗／401／競合、許可後着、全終了経路・回転／キーボード／長名称、Mac実カメラ、M5全体・M7受入は未確認。背景復帰時の表示終了をMediaStreamTrack終了の直接証拠へ拡張しない。旧限定成功や自動回帰を全面合格にしない。

## 最終状態と終了

[最終DB](evidence/parallel-next/db-iphone-final.json)はP5c後と9射影不変。STAFF_A・同cart／context・EDITING／版12・会員UNSPECIFIED、0001数量99・EAN-13数量1・EAN-8数量4・0002数量1の4明細。小計10819円、8％税8円・10％税1071円、税込11898円、操作12件・売上0件。購入は行っていない。

[停止原本](evidence/parallel-next/shutdown-iphone-final.json)は2026-10-04 UTC08:17:51.866989（日本時間17:17:51）、profile `parallel-next`／固定container、3307／8443／8444閉鎖、container exited、専用volume保持、既知秘密値がGit候補／専用ログにないことを記録する。[独立終了比較](evidence/parallel-next/comparison-iphone-shutdown-independent.json)は最終9射影不変と初期対象名／volume・保存停止記録の一致を確認。停止原本に最終container IDは含まれないため、別担当が最終IDをlive Dockerで再照合したとはしない。

一時HTTPSは終了した。私有の試験ログイン手渡しファイルにも終了・再利用しない旨を追記し、値を公開文書へ出さない。Mac専用環境も既に別停止記録で終了済み。両volume・DB・証跡を保持し、Azure／本番／commit／pushは実施していない。アプリ・依存・buildを今回の実機操作で変更していない。

独立担当は指定の新作業票・本結果票を編集し、証跡を読取比較した。起動停止・DB採取・本人への実機案内・完了追記は主担当が実施した。今回の実機試験でbuild・Azure・commit／pushは実施していない。文書を戻す場合は対象票の差分だけを扱い、volume・DB・原本証跡を保持する。
