# API・DBの試験詳細

[テスト本文](../../テスト仕様書.md) · [実施条件](実施条件.md) · [ケース一覧](テストケース.md) · [API・DB詳細](API・DB詳細.md) · [文書マップ](../文書マップ.md)

2026-09-27更新。テスト仕様書v0.10の詳細の正本。本人が受け入れた独立レビュー指摘を反映。全ケース未実施。本文2章の詳細は「実施条件」、3章の詳細は「ケース一覧」と「API・DB詳細」を参照する。

本書は[TC-11〜15](テストケース.md#tc-11)の詳細。共通データ・初期状態・判定方法は[実施条件](実施条件.md)、未確認範囲は[本文4章](../../テスト仕様書.md#sec-4)を正とする。

## TC-11の操作別入力・期待応答

根拠は[API契約](../../API契約.openapi.json)と[受付・再送契約](../../docs/design/通信とデータ.md#sec-5-1-2)。以下の01〜22はTC-11内の条件番号であり、独立した管理台帳を増やさない。各行を独立した前提で実施し、前行の成功を暗黙の前提にしない。

入力の略記：`C`＝準備で取得した対象cart_id、`L`＝そのカートのline_id、`V`＝送信直前に取得したversion文字列、`O`＝その試験操作用の新規UUIDv4、`PW_A`＝実行準備で生成したSTAFF_Aのパスワード。これらは置換記号であり文字どおり送信しない。`I` は `{"operation_id":O,"version":V}`、`I＋項目` は同じJSONオブジェクトに項目を追加する意味。同一再送は置換後の値を一切更新しない。JSONはContent-Typeをapplication/jsonとし、本文なしは `{}` で代用しない。

認証は `__Host-pos_session`、復帰は `__Host-pos_resume` を使用。login／reauthは有効な認証Cookieを前提にしない。auth/status・register/start・register/statusは認証Cookie、その他は認証と復帰Cookieを使用する。開始済みのreauthでは復帰Cookieで元担当者を照合する。全更新操作に許可Originと `X-POS-Request: 1` を付ける。GETに更新専用ヘッダーを一律要求しない。

| 条件・操作 | 前提・送信入力 | 期待する応答・DB差分／個別異常 |
|---|---|---|
| 01 `POST /api/login` | 通常開始可。`{"staff_id":"STAFF_A","password":PW_A}` | 200 Auth：authenticated=true、staff_id=STAFF_A、expires_atを返し保護Cookie発行。認証のみ更新、カート・売上は作らない。誤PW／不存在ID／試行制限中は共通401。継続カートありでは初期化しない（TC-26〜28）。 |
| 02 `POST /api/reauth` | Aの継続取引・認証失効。01と同じ本文 | 200 Auth、新認証有効・旧認証失効。カート・会員・保存状態・復帰起算は不変。Bの正しい資格情報は元取引を再開させず403。誤PWは401（TC-28・29）。 |
| 03 `GET /api/auth/status` | 本文なし。有効／失効・なし／DB照合不能 | 有効は200 Auth、失効・なしは401、照合不能は503。Cookie発行・削除、カート・購入・期限更新なし。 |
| 04 `GET /api/products/{code}` | code=P103、本文なし | 200 Product：code=P103、nameは投入値、unit_price="103"。カートに条件を固定しない。NO_PRODUCTは404、通信障害を不存在としない。 |
| 05 `GET /api/members/{id}` | id=MEM_A、本文なし | 200 Member：member_id=MEM_A、confirmed=true。氏名等は返さず、カートの会員状態・特典は変更しない。NO_MEMBERは404。 |
| 06 `POST /api/register/start` | REGISTER=UNSTARTED、本文なし | 200 Register、COOKIE_PENDING。復帰Cookie発行・対応1件、カート・売上なし。開始済みで再送は409、再発行なし。 |
| 07 `GET /api/register/status` | 本文なし。UNSTARTEDでCookieなし／COOKIE_PENDING・READYで正しいCookie | 200 Registerで各start_stateとCookie照合結果を返す。DB変更なし。開始済みでCookieなし・不一致は403、対象情報なし。DB不通をUNSTARTEDとしない。 |
| 08 `POST /api/register/confirm` | COOKIE_PENDING、開始担当者・正しいCookie、本文なし | 200 Register：READY・MATCH、通常の利用可否に従う。カートなし。READYへの同じ確認は200、対応・Cookie・カートを増やさない。 |
| 09 `POST /api/carts` | READY・継続カート未作成、本文なし | 200 CartResult：新C、version="1"、EDITING、UNSPECIFIED、member_id=null、空lines、subtotal/total="0"、NOT_REQUESTED、purchase=null。再要求は既存対象を返し重複作成なし。 |
| 10 `GET /api/resume` | 本文なし。継続Cあり／READYだがカートなし | ありは200 CartResultで継続Cの現在状態。なしは404・CART_NOT_CREATED。照会だけでカートや売上を作らない。状態別確認はTC-21。 |
| 11 `GET /api/carts/{id}` | id=C、本文なし | 200 CartResultでCの現在値。操作フィールドなし。GET前後で版・業務時刻・購入件数不変。未認証・他担当者は共通異常条件を適用。 |
| 12 `POST /api/carts/{id}/sync` | id=C、EDITING・会員待ちなし・売上なし、本文I | 200 OperationResult：APPLIED、版+1。内容・条件・業務起算・Cookie期限不変。同一再送でさらに増版しない。SAVING等は409。 |
| 13 `POST /api/carts/{id}/lines` | id=C、空・非会員、I＋`"code":"P103"` | 200 OperationResult：APPLIED、版+1。数量1、unit_price/net_unit_price/line_subtotal="103"、値引き0、税10円、total="113"。新O・最新版で同商品追加すると1行数量2、subtotal="206"・税20円・total="226"。NO_PRODUCTは404、99個超は422。 |
| 14 `PATCH /api/carts/{id}/lines/{line_id}` | id=C、line_id=L、非会員P103あり、I＋`"quantity":3` | 200 OperationResult：数量を3へ置換、版+1、subtotal="309"・税30円・total="339"。差分3個加算ではない。0／100／1.5／文字列"3"／trueは422、元行保持。 |
| 15 `DELETE /api/carts/{id}/lines/{line_id}` | id=C、line_id=L、クエリ `operation_id=O&version=V`、本文なし | 200 OperationResult：対象行と保持条件を削除、版+1、再計算。1行だけなら空・合計0。同一再送は削除成功の操作結果を返し重複反映なし。クエリ欠落は422。 |
| 16 `PUT /api/carts/{id}/member` | id=C、P103×3・10％引き候補、I＋`"member_id":"MEM_A"`。別実施でnull | 成功200 OperationResult：CONFIRMED・MEM_A・小計279／税込306。null指定はNON_MEMBER・member_id=null・小計309／税込339、候補保持。未完了202ではPREPARED・PENDING、member_id=null、pending_member_id=MEM_A、amounts_are_reference=true。不存在404／照合不能は待ちと制限を維持（TC-03）。 |
| 17 `POST /api/purchases` | 2章の保存基準データ、I＋`"cart_id":C` | 成功200 OperationResult：APPLIED・SAVED、purchaseに税抜"493"・税込"537"、明細3・税2。受付のみなら202・PREPARED・UNKNOWN・purchase=null。保存済み同要求再送は同一購入日時・金額で売上1件。空カートは409 Error・STATE_CONFLICT、会員待ちも状態制限で拒否（TC-10・16・17）。 |
| 18 `GET /api/carts/{id}/purchase` | id=C、本文なし。EDITING／SAVING／UNSAVED／SAVED／CLOSEDを別実施 | 200 CartResult：順にNOT_REQUESTED／UNKNOWN／UNSAVED／SAVED／SAVED。最後の2状態だけ固定purchase、他はnull。NOT_REQUESTEDを未到着購入の不存在としない。 |
| 19 `POST /api/carts/{id}/resolve-purchase` | id=C、SAVING・PREPARED・売上なし、購入とは別のOで本文I | 確定できたら200 OperationResult：確認操作APPLIED、UNSAVED・版+1、旧購入操作REJECTED。売上先着ならSAVED。新しい確認は既にUNSAVEDでも版+1。同じ確認の再送だけ増版なし。EDITING＋PENDINGは専用分岐で旧購入を無効化し、200・APPLIED・PURCHASE_FENCED_MEMBER_PENDING・適用版を返す。cartはEDITING/PENDING、purchase_status=NOT_REQUESTED・purchase=null（詳細は下記の競合条件）。DB照合不能は既存OpenAPIの503 Error（code・message必須）。照合結果がないときcurrentを生成せず、画面は結果不明の停止を維持（TC-17）。 |
| 20 `POST /api/carts/{id}/reopen` | id=C、UNSAVED・売上なし、本文I | 200 OperationResult：APPLIED、EDITING・版+1、内容・会員・保持条件不変、NOT_REQUESTED・purchase=null。SAVING／SAVEDは409、勝手に編集可能へ戻さない。 |
| 21 `POST /api/carts/{id}/next` | id=C、SAVED・結果未終了、本文I | 200 NextResult：operation_id/applied_versionは旧C、cart/new_cart_idは同じ新C。初回は新Cの版"1"・空・未指定・NOT_REQUESTED。旧CはCLOSED。同一再送は同じ次Cの現在値、別Oによる再移行は409（TC-24）。 |
| 22 `GET /api/carts/{id}/operations/{operation_id}` | id=C、operation_id=対象O、本文なし。APPLIED／PREPARED／REJECTED／未記録を別実施 | 200 OperationResult：記録状態、未記録はNOT_FOUND・applied_version=null。new_cart_idは必須、NEXT反映済みだけ記録済みID、その他null。cartは旧Cの現在値。再取得で操作を実行せず、未記録を未保存としない。 |

応答型名はOpenAPIのschemas名を示す。共通で全必須項目・明示null・未知項目禁止・金額の十進文字列・UTC日時・Cache-Control: no-storeを検証する。動的なUUID・日時は固定文字列比較をせず、準備で取得した値・サーバー時刻・対応関係を照合する。税率の"0.1"と"0.10"等は契約上の形式を満たす正確な十進値として比較する。401／403にError.currentや保護対象情報を含めない。

## 共通の異常入力・適用範囲

各条件は他の入力・認証・状態を正常にして単独実施する。同じ条件の重複実行は[証跡共有ルール](実施条件.md#shared-evidence)でまとめられる。下表と各操作の個別異常を合わせてTC-11の実行条件とする。OpenAPIに共通掲載された全HTTPコードを、発生条件のない操作へ機械的に割り当てない。

| 条件 | 適用・具体的な変更 | 期待結果 |
|---|---|---|
| 必須・NULL・未知項目 | JSON要求の必須項目を1つずつ削除／null化、`"unexpected":1`を追加。member_id=nullのみ正常。本文必須操作では本文なし・不正JSONも実施 | 422 Error。更新・購入なし。正当なnull指定は16の正常ケースで確認 |
| 型・識別子 | Vを数値1／"0"／"01"／上限+1文字列へ、O・パスUUIDを"bad"／大文字／v4以外へ。コード境界はTC-08 | 422。既存カート・売上不変。空のパスセグメントは別ルートになり得るため、項目の422検証は値を渡せる入口で行う |
| 不正な申告値 | lines／数量／会員／購入の要求にunit_price、tax_rate、total、staff_idを1つずつ追加 | 422、クライアント申告値で価格・税・担当者を変更しない |
| 認証・復帰Cookie | 認証必須の各操作で認証なし／期限切れ。復帰Cookie必須操作では認証を有効にして復帰なし／不一致 | 未認証401、復帰対応不正403。login／reauthに「認証Cookieなしなら401」を適用しない。register/statusの初回例外は07どおり |
| 更新ヘッダー | 全POST／PUT／PATCH／DELETEでOrigin欠落／null／不一致、X-POS-Request欠落／値0を別実施 | 403、副作用なし。GETにこの検査を適用しない |
| 同一性・古い版 | 操作IDを使う更新で同一要求再送、同Oで値・版変更、新Oで旧版。未保存確定後の再購入は新O・最新版 | 完了済みの同一再送は重複反映なし。購入PREPAREDの明示再送は再検査後に保存を完了できる（TC-16）。GETや再認証では完了させない。異内容は409 OPERATION_MISMATCH、通常の古い版は409 VERSION_CONFLICT。保存済み購入の例外・NEXTは詳細設計どおり（TC-12・17・24） |
| 対象権限・保守 | Cを別担当者の対象へ変更。maintenance_hold=trueで更新／権限付き読取を実施 | 他担当者は403で内容非公開。保守中の業務更新は409、認証と権限付き読取だけ許可。認証・送信元等の検査を迂回しない |
| DB照合不能 | 各操作が最初にDB確認する前に利用不能を発生させる。TX中断はTC-16等へ分離 | 503・結果確認不能。成功・未保存・不存在に読み替えない。予期しない障害の500も秘密値・SQL例外を応答へ反射しない |

既存契約の再確認結果と承認済み補足：

| 確認点 | 既存の根拠と試験での扱い |
|---|---|
| resolve-purchaseのDB照合不能 | OpenAPIの当該操作は503 Errorを定義済み。Errorはcode・message必須、currentは権限とDB照合結果を確認できた場合だけ。トップレベルのpurchase_statusを503本文に追加しない。設計7.2・7.4のUNKNOWNは結果分類・画面停止の意味として確認する。HTTP／本文の組合せを新たに定義する必要はない |
| 既に定義された機械判定code | 版競合VERSION_CONFLICT、異内容同IDのOPERATION_MISMATCH、状態競合STATE_CONFLICT、旧購入操作終了のPURCHASE_ATTEMPT_CLOSED、未作成カートのCART_NOT_CREATEDを該当分岐で照合する。Error.codeに列挙制約はないため、それ以外を一律に契約違反とはしない |
| 空カート購入のHTTP／code | 2026-09-27本人承認により409 Error・STATE_CONFLICTへ確定。[設計7.2](../../docs/design/保存処理.md#sec-7-2)・[5.3](../../docs/design/通信とデータ.md#sec-5-3)・OpenAPI v0.36に明記。TC-10・TC-11条件17で固定比較。拒否・保存なしという要件は不変 |

DB障害等の個別code文字列は、現行契約が要求する文字列型・表示／状態の振る舞いを確認する。クライアントが特定のcodeで分岐する実装にする場合だけ、その対応を実装前に明示する。エラー名を網羅した新しい台帳の作成を、本書全体の試験開始条件にはしない。

<a id="tc12-snapshot"></a>

## TC-12 照会中の一貫性

根拠：[設計5.1.2](../design/通信とデータ.md#sec-5-1-2)。商品あり・編集中の `GET /api/carts/{id}` を代表に、アプリの読取専用REPEATABLE READトランザクションで最初のSELECTを完了後、後続SELECTの前で停止する。別接続から正規の数量変更を確定し、版・明細・合計が変わったことを確認してGETを再開する。

応答全体が更新前の版・状態・明細・合計に一致し、更新前後を混ぜないことを確認する。次の新しいGETでは更新後の一式を返す。アプリ内の読取順と別接続のCOMMIT到達を証跡に残し、確認用SQLだけをREPEATABLE READにすることで代用しない。共通の読取処理を使わない他の複数SELECT経路があれば、その経路でも同じ条件を確認する。

<a id="tc16-fault"></a>

## TC-16 COMMIT応答喪失

根拠：[設計7.2](../design/保存処理.md#sec-7-2)・[DB接続運用](../../設計設定・DB運用.md)。ケース一覧①〜④のブラウザ応答喪失・処理中断とは別に、以下を実施する。試験側でMySQLの確定を確認し、MySQL→FastAPIのCOMMIT応答だけを失わせる。アプリへ確定結果を注入しない。

| 遮断位置 | 到達確認・期待結果 |
|---|---|
| 受付TXのCOMMIT後、FastAPIが成功を確認する前 | DBはSAVING・PREPARED、売上0件。売上TX開始前で停止し、受付や売上TXを自動再実行しない。照合後も受付済みとして編集不可。売上処理は同じ購入要求の明示再送でのみ再検査して進める |
| 売上TXのCOMMIT後、FastAPIが成功を確認する前 | DBはSAVED・APPLIED、売上1・明細3・税2件。新規接続の照合で同一の保存済み結果へ収束し、同じ要求の明示再送でも売上と購入日時・金額は増減しない |

両条件で成否不明の接続を破棄し、別の新規接続で照合することと、TXの自動再実行がないことを接続・処理順の証跡で確認する。照合も利用不能にした間はUNKNOWN・編集／次取引不可を維持し、未保存と推測しない。照合復旧後は上表の結果へ収束する。GET・再読込・再認証は照合だけで、売上保存を開始しない。

<a id="tc31-relay"></a>

## TC-31 中継の保護

根拠：[設計9.1](../design/認証と運用.md#sec-9-1)。許可された検証環境で、正常な認証・送信元・要求による中継成功を対照にし、各条件を1つずつ変える。要求の到達・拒否・副作用を確認し、設計にないHTTPコードは新設しない。

| 条件 | 期待結果・観測 |
|---|---|
| 許可リスト外のAPI／許可されないメソッド | Next.jsが拒否し、FastAPIへ転送されず、業務状態不変 |
| 外部入力から転送先URL／Hostの変更を試みる | 固定の上流・Hostを変更できず、指定した別宛先へ送信されない。観測先も許可済み検証範囲とする |
| ブラウザから中継秘密値と同名のヘッダーへ偽値を送る | 入力ヘッダーを除去しサーバーの正規値を付与、FastAPIが検証する。正常対照と同じ業務結果。ヘッダー処理の証跡は値を秘匿し、秘密値をブラウザ・応答・ログへ出さない |
| FastAPIへ直接要求し中継秘密値を欠落／不一致にする | 正常な利用者認証があっても拒否、業務状態不変。送信元IP制限と秘密値検証を別に確認し、後者は許可済み送信元から実施してIP拒否で隠さない |

正規の中継秘密値だけで利用者認証・権限を代替できないことはTC-11／25の同一条件の証跡と対応付ける。到達点を観測できない条件は合格にせず実施不能として記録する。

## TC-13〜15のDB入力と確認方法

根拠：[物理制約・SQL外の検査](../../docs/design/通信とデータ.md#sec-6-2-1)・[DDL](../../設計スキーマ.sql)。正常な基準行を準備し、下表の差分だけを与える。DB制約の確認は隔離した検証DBで、各不正DMLを独立したトランザクション内で実施し、受理・拒否のどちらでも最後にROLLBACKする。実際の保存処理の検証ではアプリのCOMMITと別接続からの照合を使い、全体を外側のROLLBACKで囲って原子性・競合の試験を代用しない。

| 条件・対象 | 正常値から変える入力 | 拒否する場所・確認結果 |
|---|---|---|
| 01 必須・形式 | STAFF／MEMBERのIDを空・33文字・空白へ。MEMBERの各必須属性をNULL、文字列を空へ | DBのNOT NULL・CHECK等で拒否し行不変。年齢の小数0.5、4294967296、TEXTの容量超過は投入前検証で拒否。年齢0／4294967295は型境界として受理。型の自動変換に任せない |
| 02 一意性 | PRODUCT.code=P103を重複登録。CART_LINEに既存のcart_id＋product_id／line_no、CART_OPERATIONに既存のcart_id＋operation_id、PURCHASEに既存cart_idを投入 | UNIQUE／PKで拒否。既存行は1件のまま。別コード001Ab／001abは別商品として登録可。初回REGISTERは1件、register_id=2を拒否 |
| 03 外部キー | 対象をSELECTして不存在を確認した親IDを、商品税率／商品条件／カート所属／購入明細の親参照へ指定。参照中の親削除も試す | FKで拒否、子・履歴を連鎖削除しない。不存在IDは固定番号を推測しない |
| 04 金額・率・数量 | 単価-1／1000000000000、税率-0.0001／1.0001、数量0／100。別条件で円額0.5、率0.00001を投入前検証へ渡す | DBの範囲・型制約と投入前検証で拒否。小数円・率の桁超過をDBが丸めて受理できても合格にしない。0円・税率0・数量1／99は他の計算列を整合させて受理 |
| 05 値引き種別・期間 | RATEなのにamountあり／rateなし、AMOUNTなのにrateあり／amountなし、未知kind、valid_from=valid_to／開始が終了より後 | CHECKで拒否。正常RATEはrateのみ、正常AMOUNTはamountのみ非NULL。期間中かどうかは別途TC-09で確認 |
| 06 明細・税の計算 | P103×3・10％引きでnet_unit_priceを92（正93）、line_subtotalを280（正279）、discount_per_unitを104（単価超過）へ。税10％・課税小計279で税額28（正27） | CART_LINE／PURCHASE_LINE／PURCHASE_TAXのCHECKで個別拒否。各変異の前後で行が増減せず基準値が残る |
| 07 状態とNULL | CONFIRMEDでmember_id=null、NON_MEMBERでmember_idあり、PENDINGでpending_member_id／active_member_operation_id欠落、SAVINGで購入操作／受付版欠落、CLOSEDで終了日時なし。PREPAREDに完了日時、APPLIEDに完了日時なし | CART・CART_OPERATIONのCHECKで拒否。これらを単にAPIのエラー表示だけで合格にしない |
| 08 JSON・所属 | 候補を配列でなくオブジェクトへ。配列内のkind不正・必須キー欠落・余分キー・率／額両方あり。実在する別context／cartの操作IDをactive操作へ指定 | 配列型はDB、要素構造・所属関係はアプリ／投入前検証で拒否。DBのFKだけでは保証しない部分を区別。JSON列が保存できたことを妥当性の証明にしない |
| 09 取引全体 | 売上に明細なし、明細小計と売上合計の不一致、税率行の不足／余剰、別担当者との所属不一致を保存処理へ与える | 保存TX内の検査で拒否、対象売上・明細・税を部分確定しない。診断SQLの検出試験ではDB制約を満たす不整合だけを隔離TX内に作り、同接続で検出後ROLLBACK。制約を無効化しない |
| 10 価格履歴 | 初回old_price=NULL・new_price=103、変更103→110、同値110→110、後続の旧値を109にする | 初回と正しい変更は商品・履歴を一括確定。同値履歴はCHECKで拒否。旧値の連続性は更新手順で検査し不一致なら停止。103円で保存済みの購入を110円へ書き換えない |

以下は検証時に使う**読取SQLのテンプレート（未実行）**。`:cart_id`／`:product_id`は実行記録の対象IDをバインドする記法で、MySQLへそのまま貼り付けるSQLではない。実行クライアントのパラメーター方式へ合わせる。複数のSELECTは同じ接続の読取専用・REPEATABLE READトランザクションで取得し、動作中の異なる時点を混ぜない。書込試験後は新しい読取トランザクションを開始する。

**保存・部分保存・再送（TC-14・16〜18）**：保存前、受付後、売上TXの終了後、再送後で同じ対象を照合する。

```sql
SELECT c.cart_id, c.state, c.version, c.member_state,
       (SELECT COUNT(*) FROM PURCHASE p WHERE p.cart_id=c.cart_id) AS purchases,
       (SELECT COUNT(*) FROM PURCHASE_LINE l WHERE l.cart_id=c.cart_id) AS lines,
       (SELECT COUNT(*) FROM PURCHASE_TAX t WHERE t.cart_id=c.cart_id) AS taxes
FROM CART c WHERE c.cart_id=:cart_id;
SELECT purchased_at, subtotal, total
FROM PURCHASE WHERE cart_id=:cart_id;
SELECT code_snapshot, quantity, unit_price_snapshot, discount_per_unit,
       net_unit_price, line_subtotal
FROM PURCHASE_LINE WHERE cart_id=:cart_id ORDER BY line_no;
SELECT tax_rate_snapshot, taxable_subtotal, tax_amount
FROM PURCHASE_TAX WHERE cart_id=:cart_id ORDER BY tax_rate_snapshot;
SELECT operation_id, kind, status, request_version, applied_version, result_code
FROM CART_OPERATION WHERE cart_id=:cart_id ORDER BY created_at, operation_id;
```

最初のSELECTは必ず1行。0行は対象誤りとして停止。基準データの保存前／受付後は件数0・0・0、成功後は1・3・2、再送後も同じ。明細はP103が数量3・単価103・値引き10・値引き後93・小計279、P107_A／Bが各数量1・単価107・値引き0・小計107。税8％は小計214・税17、税10％は小計279・税27、購入は小計493・税込537。未保存確定前の売上0件は編集許可を意味しない。状態・操作結果はTC-16・17と併せて判定する。

**復帰・次取引（TC-19〜24・33）**：旧cart_idを指定し、継続先と元対象を区別する。照合値・Cookie値は出力しない。

```sql
SELECT c.cart_id, c.state, c.version, c.active_purchase_operation_id,
       c.purchase_prepared_version, c.result_closed_at,
       r.current_cart_id, r.start_state, r.maintenance_hold,
       b.last_business_at, b.manual_released_at, b.invalidated_at
FROM CART c JOIN REGISTER r ON r.register_id=c.register_id
JOIN BROWSER_CONTEXT b ON b.context_id=c.context_id
WHERE c.cart_id=:cart_id;
SELECT o.operation_id, o.status, o.next_cart_id,
       n.state AS next_state, n.version AS next_version
FROM CART_OPERATION o LEFT JOIN CART n ON n.cart_id=o.next_cart_id
WHERE o.cart_id=:cart_id AND o.kind='NEXT';
```

TC-24の初回成功では旧C=CLOSED、反映済みNEXTが1件、next_cart_idとREGISTER.current_cart_idが一致、新C=EDITING・版1。さらに取引が進んだ後はREGISTERが変わってよいが、旧操作のnext_cart_idは不変。TC-19のsync・処理済み再送・照会では業務起算不変、TC-33の手動許可はmanual_released_atだけを起算用に追加し、元の購入結果を保持する。

**単価履歴（TC-14）**：P103のproduct_idを準備時に取得する。

```sql
SELECT product_id, code, unit_price FROM PRODUCT WHERE product_id=:product_id;
SELECT old_price, new_price, changed_at
FROM PRICE_HISTORY WHERE product_id=:product_id ORDER BY changed_at, history_id;
```

新規準備からの正常変更後は商品110、履歴がNULL→103と103→110の2件。同値更新・失敗・同じ更新結果の照合だけでは増えない。既存の[確認SQL](../../設計確認.sql)による参照・状態・集計の診断と組み合わせる。DB実機での構文受理、パラメーター接続、診断SQLの不正検出は実行時に別途確認する。


<a id="review-races"></a>
### TC-17・TC-20・TC-18：保存と会員確認の競合条件

既存ケース内で以下を別条件として実施し、確定順・要求版・操作ID・応答・DB状態・購入補助記録を記録する。通常データ・故障注入の実行許可は既存条件に従う。

| 条件 | 手順 | 期待結果 |
|---|---|---|
| TC-17 未保存後の再試行遅延 | UNSAVED vで購入P(v)を送りAPI到着前に保留。別操作R(v)のresolveを確定後、Pを到着させる | Rでv+1・UNSAVED。Pは409 VERSION_CONFLICTで売上なし。R同一再送は増版なし。逆順で購入保存が先ならSAVED。R応答喪失後も同一再送／操作GETで確定結果を取得 |
| TC-20/18 会員待ちとの重複 | タブAが購入P(v)の補助記録を作って送信を遅延。タブBの会員変更でEDITING/PENDING v+1を確定。会員操作PREPARED／不存在REJECTEDを別実施。再読込し新しいR(v+1)を実行、旧購入・旧会員結果を遅着 | Rでv+2、EDITING/PENDING、商品・旧参考値を保持。旧会員PREPAREDだけREJECTED/MEMBER_LOOKUP_SUPERSEDEDに終了、既REJECTEDの理由・完了時刻は不変。active_member_operation_id保持、旧会員結果を拒否。Pは旧版拒否で売上なし。RはAPPLIED・PURCHASE_FENCED_MEMBER_PENDING・applied_version=v+2、NOT_REQUESTED/null。last_business_at・Cookie期限は不変 |
| TC-20 確認応答断・古い応答・複数記録 | 上記Rの応答を失わせ同一R再送／操作GET。異なるカート、同カートの要求版がR適用版未満／同値／超過の補助記録を用意。現在カートが後にSAVING／SAVEDへ進んだ結果も取得 | 同一cart・確認操作対応・APPLIED・専用code・非null適用版が揃う場合だけ、同cartで要求版が適用版未満の記録を除去。現在versionで代用せず、同値／超過・別cartは保持。一般NOT_REQUESTED・NOT_FOUND・照合不能では除去しない。現在状態を優先し古い応答で編集再開しない |
| TC-20/18 会員操作への復帰 | 対象購入補助記録の解消後に再取得し、再照会／非会員選択を別実施 | PENDING中の商品編集・購入は不可。新会員操作で旧操作を置換、成功／非会員化後だけ通常操作へ。会員も購入も自動実行しない |
| TC-12/17/20 競合・停止境界 | resolve期待版不一致、版上限、DB照合不能、先着SAVING／SAVED、認証・Cookie・期限不正を既存条件で確認 | 版不一致は409再取得、上限は既存拒否で更新なし、照合不能は503で停止。SAVINGは通常resolve、SAVEDは既存結果。認証等の制限を迂回せず、確定応答のない補助記録は保持 |
