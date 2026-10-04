# Mac非カメラ：旧検索応答・非会員一巡・会員待ちの並行再検証

2026-10-04。本人の最新依頼は、非カメラのMac残試験を並行して進め、iPhone・カメラを後回しにすること。本票は担当Cの準備であり、**作成時点では新環境や試験を実行していない**。rootが専用環境・通常Chrome・CUA・DB観測を担当する。担当Cは本票の編集と、その後の証跡の独立読取レビューだけを行う。

正本は[TC-01〜03](../tests/テストケース.md)、[実施条件](../tests/実施条件.md)、[受入条件](../requirements/受入条件_現行.md)、[画面・業務設計](../design/画面と業務処理.md)、[通信・復帰設計](../design/通信とデータ.md)、[保存設計](../design/保存処理.md)。既存の[検索修正再検証](Mac_TC02_修正再検証.md)、[選択解除結果](商品選択解除_修正検証.md)、[TC03修正後結果](Mac_TC03_不存在復帰_修正再検証結果.md)を参照するが、過去の限定確認を今回の合格へ移さない。

## 1. 固定対象・実行前確認

新規隔離profile `mac-parallel`、container `tech0-pos-mac-parallel-mysql`、volume `tech0-pos-mac-parallel-mysql-data`、`.mac-parallel-local/`、`evidence/mac-parallel/` を使う。rootがsetup／profile許可を追加し、専用resource・product/member gate・検証画面の対象一致を読取確認してから開始する。既存の停止環境・Cookie・資格情報・復帰期限・gate tagを再利用／延長／初期化しない。架空の3商品・会員・担当者、既存のlocalhost TLS・一時HTTPS・最小権限を使い、Azureや実カメラは対象外。

準備時の[170件成功・build](evidence/mac-batch/runtime-selection-fix.json)は `JgJjC7D_Z2jjtELoFKU-V` の過去記録。今回起動する実ソースhash・build ID・検査結果をrootが記録し、過去の170件で別版の検査を代用しない。並行担当のTC20／28等がアプリを変更した場合はrootが版を確定し、本票の依存条件を見直す。試験中のbuild上書き、同じ3307／8443／8444や通常Chromeへの他担当の操作は行わない。GUI／server／DB／tunnelはrootが排他で操作する。

通常UIからSTAFF_Aログイン→初回start→Cookie受取確認→新C0を作る。cart／context1、EDITING・会員未指定・空・0円・売上0、認証／復帰期限有効、購入補助記録なし、通知競合・別タブ・gateなしを開始証跡にする。初期価格0001=103円税10%、0002／0003=107円税8%、架空候補10%を確認する。初回sync等による版増加は実値を記録し、版1を固定期待値にしない。

## 2. TC-02：早いDOM復帰と応答分類を分ける

前回mac-batchでは旧200／実404／注入503／A→B→Aのサーバー返却、入力変更、後のDOM、DB不変を確認したが、生network分類を取得できず、DOMは開始12〜14秒後、old200は開始時刻も未記録だった。disabled「選択解除」のclick待機を使った追加試行はCUA selector deadlineで不成立。この記録は保持する。

### 既存コードから得られる証拠

- [商品検索](../../frontend/app/register-cart.tsx)はbusy／searchingの終了時に検索ボタンを再有効化する。商品コードだけは待ち中に編集できる。旧応答を無視する条件は入力世代・コード・通知・対象cart・状態・enabledであり、A→B→Aも別世代として扱う。
- [api](../../frontend/lib/pos.ts)はfetchとJSON解析を待つが、受信status／bodyを記録しない。成功応答以外はApiError、通信／JSON失敗は一般Errorにする。旧コードのcatchは表示しないため、候補やエラーが出ないだけでは実旧応答と通信失敗を区別できない。
- [画面計測](../../frontend/lib/measurements.ts)は検索結果を採用した成功時だけ呼ばれる。旧応答を無視したケースの完了時刻やHTTP分類は得られない。測定配列が空でも失敗とはしない。
- [relay診断](../../frontend/lib/diagnostics.ts)は固定APIテンプレート・request_id・HTTP分類・elapsed_msを記録し、[relay](../../frontend/lib/relay.ts)は10秒timeoutとレスポンス本体のbufferを使う。これはサーバー側の分類であり、Chrome受信の直接証拠ではない。商品GETのoperation_idはnullでコードもログに出ないため、同時GETを避け、時刻窓とrequest_idで照合する。

本番アプリやブラウザへのfetch差替え・イベント注入・状態書換え・新しい制御方法を追加しない。既存CUAの提供機能で通常Chromeの該当Network応答status／body／時刻が取得できるなら、検索前にその観測を準備する。取得不能なら「gate＋relay＋早期DOMの間接照合」と「生HTTP受信分類未確認」を分け、全条件の完全合格へ広げない。

### 正規Chrome DevTools Networkの確認案

rootが既存のCUA Chrome handleを保持し、通常ChromeのDevToolsを正規UI操作で開く案。Network API／CDP／注入／別のブラウザ制御は使用しない。**rootによるUI可否確認前の案であり、受信証拠を取得できると確定していない。**

1. 通常ログイン・start・Cookie確認を完了してからDevToolsを開く。Networkへ移り、今回の表示記録をクリアし、productsでフィルタする。認証・Cookie・Headers・Request payloadのpaneは開かず、画像／AX採取も商品GETの行とResponse欄へ限定する。強制キャッシュ無効やnetwork throttling等を新たに設定しない。
2. gateなしの通常商品検索1回で、Name・Status・Timeの行とResponse欄の架空公開商品JSONを正規UIで読めるか確認する。rootが成功／取得不能を記録し、取得不能なら短いDOM復帰の検証だけを行って生受信分類を保留する。観測準備の試行は本番の旧応答ケースと分ける。
3. 各ケース前に商品GETの観測行を区別できる状態にする。短時間の検索→入力変更→DOM待機の間はDevTools操作を挟まない。早いt2とDOMを採取した後、当該旧コードのNetwork行を開き、Name／Status／TimeとResponseの公開JSONを画像・AXで保存する。新コードの検索はこの行の証拠保存後に行い、旧／新の同名行や前試行の行を取り違えない。
4. 旧200は商品code0001のJSON、旧404はPRODUCT_NOT_FOUNDのJSON、旧503はSERVICE_UNAVAILABLEのJSONを確認する。Networkの実statusとResponse分類、旧入力コード、開始順、gate／relay時刻を対応付ける。503は約3秒の実照会後ゲート解放とrelay elapsed<10秒も確認し、10秒timeoutの同じSERVICE_UNAVAILABLEへ代用しない。
5. Network行のTimeは要求の所要時間であり、画面復帰時刻を示さない。Responseを後で読み取れた事実と、同一CUA呼出しで測ったt2は別証拠にする。Network行なし、失敗・cancelled、bodyなし、旧要求を識別不能なら、そのケースの生受信分類は未確認。gate-responseだけで補完した扱いにしない。

### 短い同一CUA呼出しの順序

rootは提供済みのCUA API仕様に従って、以下のlocator条件を実際の通常UIへ対応付ける。未確認のlocator APIを推測して実行しない。

1. gateなしで「商品コード」と名前完全一致の「検索」を特定する。新コードも空にしない。ケース前DBとDOMを採取し、表示メッセージを記録する。解除helperの準備やexec承認待ちは検索前に済ませる。
2. [商品ゲート](../../tools/mac_tc02_backend.py)の対象をrootの新profileへ限定し、未使用tagをarmする。[既存release-after](../../tools/mac_batch.py)と同じ、実gate到達・分類一致を確認してから約3秒待って私有releaseを作る方式を使う。新profile用wrapperはroot所有であり、旧mac-batch wrapperを実行しない。gate到達前の先行releaseや公開制御APIを使わない。
3. 同一CUA呼出し内で検索開始時刻t0を保存→通常「検索」をclick→同じ検索ボタンのdisabled状態を短時間確認→商品コード入力有効・その他の編集無効を短いDOMで採取→通常fillで新コードを入力しt1を保存する。A→B→Aは同じ呼出しで戻す時刻も保存する。
4. 同じ検索ボタンの **`:disabled` 条件を付けたlocatorがhiddenになる** 状態待機を直ちに開始する。disabledボタンへのclickを待機手段にしない。待機後は名前完全一致の検索ボタンが存在して有効、コードが期待値、追加候補なし、他の編集制約が元状態へ戻ったことを確認し、即時の時刻t2とDOMを保存する。「disabledがhidden」はボタン自体の消失・認証画面への移動でも成立するため、存在・再有効・同cartの事後確認を必須にする。
5. 短い待機timeoutはt0から8秒以内の観測を目標に設定し、t2−t0を実測する。8秒は観測に余裕を取る手順上の目標であり、性能TC-32の2秒合格とは別。CUA waitの開始時点からのtimeout値だけでt0から10秒以内と判断しない。長い画像保存・DB採取・別tool呼出し・追加exec承認待ちはt2の後に行う。
6. gate／helper／gate-response、relay診断と、取得できた場合のブラウザNetwork分類を照合する。t1<release、返却・relay完了とt2の順序、t2−t0<10秒、同一の旧GETを対象にしたことを確認する。ブラウザが先に通信失敗していた場合、gate到達後のサーバー返却だけで旧応答到達を合格にしない。

| ケース | kind・旧コード | 入力順 | サーバーの正しい分類と画面期待 |
|---|---|---|---|
| 旧200 | product-late／0001 | 0001→0002 | 実200の商品0001を返す。新0002を保持し旧候補・追加ボタンなし |
| 旧404 | product-late-missing／PRODUCT_MISSING | PRODUCT_MISSING→0002 | 実404 PRODUCT_NOT_FOUNDを返す。不存在の旧案内で新入力を上書きしない |
| 旧503 | product-late-unavailable／0001 | 0001→0002 | 実200照会後に503 SERVICE_UNAVAILABLEを注入。旧不能案内で新入力を上書きしない。実DB障害とは称さない |
| A→B→A | product-late／0001 | 0001→0002→0001 | 実200でも旧入力世代の候補を出さない |

各ケースの読取GET区間でcart／line／version／operation／purchaseが基準点から不変であることを別接続DBで確認する。t2後に通常検索0002で新商品が表示できることを確認する。最後に通常追加で数量1・税込115円を登録し、正しい新code・新line・保持条件をDB照合して通常削除で空C0へ戻す。各ケースで新検索を実施したかと、追加まで実施したかは別々に記録する。履歴と版増加は保持し、巻戻さない。

合格範囲は「待ち中の入力／他操作制限」「早期DOM復帰」「旧HTTP分類到達」「旧結果不採用」「新検索／追加」「DB不変」を個別判定する。生受信未観測ならその条件を保留。短いDOM待機失敗は観測方式の不成立とアプリ停止を切り分け、gate／relay／後のDOMを保持する。旧結果表示や不正更新が実際に起きた場合は不合格として依存する続行を止める。過去の自動20回帰を実機の受信証拠へ代用しない。

## 3. TC-01：非会員を通常UIで完走

検索試験後に空C0・会員未指定・売上0・gate／処理待ち／補助記録なしを確認する。開始時のログイン／初回作成と、検索試験中の一時行・版増加を同一カートの履歴として報告する。

1. 非会員として続ける→0001検索・追加→選択して数量3へ変更→0002／0003各1個追加。3行・数量3/1/1、税抜523円、税8%17円＋税10%30円、税込570円・非会員・STAFF_Aを画面とDBで照合する。未送信の数量編集と確定済み数量を混同しない。
2. 購入確定を1回送信し、送信中の編集・選択解除・再購入無効を短いDOMで採取。DB SAVED・購入1・明細3・税2・金額・担当者・日時の一致後に購入完了と判定する。応答不明を未保存とせず元要求を保持し、自動再送しない。
3. 通常「閉じて次の取引へ」でC0 CLOSED→新C1へ。NEXT1、REGISTER current_cart=C1、会員／特典・入力／検索候補・行選択／数量欄・商品リストのクリア、合計0、ログイン維持を確認する。作成時版と初期sync後の版を区別する。
4. C1で0001検索・追加、数量1・税込113円、売上は1件のままを確認して一巡完了とする。next到達だけを非会員完走と称さない。

証跡は初回、570円編集、送信中、保存完了、次空カート、次商品登録のDOM・必要画像・別接続DB。UIとDBの取得時刻を別々に保存する。保存・nextが不明なら正規照合が済むまでTC03へ進まない。

## 4. TC-03：実施可能な修正後別タブ条件

TC01後のC1で正常UIから3行・数量3/1/1を作る。すでに追加した0001の数量を3へ変更し0002／0003を追加する。C0の購入1を基準として保持し、この節で売上を増やさない。同画面、同じ通常Chrome・同一オリジンの通常POS別タブ、専用検証画面を区別して証跡を採る。

最初の実行候補は商品ありの非会員→不存在と会員MEMBER_0→不存在、非会員／旧会員からの受付COMMIT後503。不存在では同画面の会員入力／再照会／非会員は追加GET操作なしで有効、商品・購入・選択解除は無効。503では同画面を停止し、旧IDは未確認・旧額は参考、正規の明示照合後に会員選択のみ復帰する。別タブは正規の状態取得で同じcartとPENDINGを確認し、商品操作を拒否する。警告や通知だけでPENDING到達を証明しない。

[専用検証画面](../../tools/mac_tc03_panel.html)の最短操作は「4操作を直接要求」→「確認完了」→label「API検証結果」の全文採取。内部resumeが毎回のcart_id／version／存在する先頭line_idを取得し、POST追加／PATCH数量4／DELETE／POST購入に各新UUIDを付ける。正常形式の4件が409 STATE_CONFLICT、completed=true、before／after同cart・PENDING・版・行・参考額不変であることをrootが確認し、DBも前後照合する。IDを以前の試行からハードコード流用しない。予想外の成功や拒否理由で即停止し、後続要求で状態を整えない。

次に「会員GETを直接照会」→完了→結果採取。画面のcompleted=trueだけでは200をassertしていないので、rootが会員GET200・PENDING非解除・版／額不変を確認する。前後resume・cart GETや会員GET成功だけで会員待ちを解除しない。直接要求画面には通常POSの通知発信や制限UIがなく、API拒否の証拠を別タブの操作制限証拠へ代用しない。

実lookup保留中の別タブと4拒否、新選択後の旧照会遅着は[既存の詳細計画B2/B3](Mac_残試験_並行作業票.md)を参照する。長い拒否採取と10秒以内の旧会員応答到達を同じgateで兼用しない。今回新profileの会員gate・短時間解除が成立した条件だけ追加し、成立しなければ旧照会・照会中条件を未実施として残す。カメラ条件は今回後回しである。

## 5. 中断・証跡・終了

実装hash／build不一致、対象resource／cart／ID不一致、未解決保存・期限超過、予想外の売上／カート／行変更、gate不成立、古い版や不正入力による拒否を停止理由とする。未確認の必須条件と失敗した観測手順も記録し、最終集計から消さない。各ケースは日時・前提・TC／下位条件・実結果・合否・限界と証拠を対応付ける。

rootが最終DB、秘密値非混入、今回トンネル・Next・FastAPI・MySQL停止、3307／8443／8444閉鎖、container exited、専用volume／証跡保持を記録する。既存停止環境や重要ファイルを削除しない。commit／push／Azure／本番反映／iPhone操作／映像保存・送信／M7受入は含めない。戻す場合は本票と今回の限定tool差分だけを対象とし、アプリ修正・過去証跡・DB／volumeを保持する。
