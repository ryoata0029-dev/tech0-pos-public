# 10月05日 API・DB検証の計画と結果

2026-10-05。本人の提案継続・最大限の同時並行依頼に基づく担当Aの追加検証。**別の新規固定schemaで519小項目成功。今回選択したTC-11は467件中467成功・未実行0へ減少した。** 正常入口は22操作で、正当null等の追加成功条件も467件に含む。TC-08は25件、TC-12は18件、TC-13は9件。初回実行は検証器のnested oneOf参照で350条件成功後に停止（選択TC-11は346成功・121未実行）した履歴として保持する。初回350件と今回519件を合算せず、全TC・M7の合格にも読み替えない。実行・環境作成・停止は主担当だけが行う。

根拠は[現行受入](../requirements/受入条件_現行.md#sec-5-4)、[TC-08・11〜13](../tests/テストケース.md#tc-11)、[操作別詳細01〜22](../tests/API・DB詳細.md)、[通信とデータ](../design/通信とデータ.md#sec-5-1-2)、[OpenAPI22操作](../../API契約.openapi.json)、[現行DDL](../../設計スキーマ.sql)。本票の小項目IDは既存TC内の実行記録であり、受入条件の追加ではない。

## 既存証拠から今回の限定条件へ

| 対象 | 既存証拠 | 今回選択した不足条件 | 現在の状態 |
|---|---|---|---|
| TC-11 01〜22 | [前回API・DB8条件群](API_DB_追加実DB検証結果.md)、M3の業務一巡、M4の停止／競合。特定操作・状態の成功を記録している | 22操作をそれぞれ正常状態で呼び、JSON必須・null・型・未知項目、本文なし、DELETEクエリ、パス形式、Cookie・更新ヘッダーの拒否を単一変更で確認 | 新schema選択467件：成功467、未実行0。正常22操作と正当nullの追加条件は467件の内数。初回の346／121は履歴として保持 |
| TC-08 | 前回最大単価1個の保存と数量2拒否、自動数量境界 | 別々に有効な行の合計超過、税抜は有効でも税込のみ超過、32文字／大小文字の商品分離、無断trim等の拒否。実DB保持と新REJECTED1件を区別 | 選択25条件：成功25、未実行0（補助の追加／削除／数量戻しを含む） |
| TC-12 | M4再送／競合／照会snapshot、前回MAX拒否再送 | JSONキー順だけ変えた同一再送、同IDの値／版変更、新ID旧版、2^53近傍3値とunsigned BIGINT上限近傍3値の十進文字列精度／増分不足 | 新schema選択18条件：成功18、未実行0。6版の読取、4増分、上限2拒否、次カート追加、再送等5件 |
| TC-13 | 16表DDL適用、前回診断SQL陽性対照／rollback、app権限6拒否 | 固定schemaで重複コード、FKなし親、必須null／空、REGISTER=2、数量0、候補JSON型、金額／状態CHECKを各独立TXで拒否しrollback・別TLS前後一致 | 選択9条件：成功9、未実行0。各制約拒否後rollback・別物理TLS射影不変 |

TC-08の税率別小計超過は取引小計超過も同時に成立し得る。今回の2行合計条件を、内部の税率別分岐だけを独立に検証した合格とは呼ばない。TC-12の応答後着／照会中COMMITは既存証拠を参照し、今回の非並行試験で再実証したとは扱わない。

## TC-11の有限実行台帳

[専用script](../../tools/oct05_api_verify.py)の `planned_tc11()` が接続なしで次の467 IDを生成する。JSONには全 `planned_tc11_ids`、成功したID、`remaining_tc11_ids`、選択条件の成功数を残す。IDは `TC11-<operationId>-<変更条件>`。例えば `TC11-addLine-missing-code`、`TC11-getCart-auth-expired-sql`。正常・正当null・保存202／200を別に記録する。実行が途中で止まれば成功済みIDだけを数え、以降は未実行として残す。

| 詳細条件 | operationId | 選択件数 | 正常状態・限定 |
|---|---|---:|---|
| 01 | login | 17 | UNSTARTED・専用A認証。password値は記録しない |
| 02 | reauth | 18 | 継続カートあり・専用認証行を局所SQLで期限切れにした状態。同じA正常／正しいB拒否 |
| 03 | authStatus | 7 | 有効認証・照会不変 |
| 04 | product | 12 | READY・P103照会、cart条件を固定しない |
| 05 | member | 12 | MEM_API照会、cart会員を確定しない |
| 06 | registerStart | 12 | UNSTARTED→COOKIE_PENDING |
| 07 | registerStatus | 7 | UNSTARTEDのCookie例外だけ。COOKIE_PENDING／READYの全組合せは本台帳で網羅しない |
| 08 | registerConfirm | 14 | 正しいresume対応・COOKIE_PENDING→READY |
| 09 | createCart | 14 | READYから空v1作成 |
| 10 | resume | 9 | 継続カートの照会だけ |
| 11 | getCart | 12 | EDITING・空cart照会 |
| 12 | syncCart | 31 | EDITINGで版+1、業務起算・Cookie更新なし |
| 13 | addLine | 38 | 新規P103数量1、値引きなし113円 |
| 14 | setQuantity | 41 | 同じP103行の数量3置換 |
| 15 | deleteLine | 26 | UNSAVEDからreopen済みのEDITING、対象行削除・正規クエリ |
| 16 | setMember | 38 | 確認済みMEM_API／306円、正当null指定／339円 |
| 17 | purchase | 39 | 実受付後のSAVING／202と、別の通常保存200。全保存状態の組合せではない |
| 18 | getPurchase | 12 | SAVING／UNKNOWN・照会不変 |
| 19 | resolvePurchase | 31 | SAVING→UNSAVED、旧購入REJECTED |
| 20 | reopen | 31 | UNSAVED→EDITING、明細保持 |
| 21 | next | 31 | SAVED→旧CLOSED・次空v1 |
| 22 | getOperation | 15 | 未記録UUIDのNOT_FOUND・照会不変。全記録状態は今回の正常行で網羅しない |
| 合計 | 22操作 | 467 | 全TC-11受入の母数ではなく今回の選択条件数 |

適用されるJSONで必須各項目の欠落／null／型違い、未知項目、本文欠落／不正JSON、版0／先頭0／上限+1、UUID bad／大文字／v1、不正な単価・税・合計・担当者申告を確認する。member_id=nullは拒否条件に入れない。外部staff／member IDをUUIDとして誤分類しない。本文なし入口は `{}` も本文ありとして拒否。DELETEは欠落／未知／重複クエリと不正版・操作ID、GETは未知クエリ・隠れた本文を確認する。

全更新のOrigin欠落／null／不一致、X-POS-Request欠落／0を403と確認。GET正常では両ヘッダーを付けず、照会だけ成功することを確認する。認証必須20操作の認証なし／不一致／局所SQL期限切れは401。適用操作の復帰なし／不一致は403、401／403は保護currentや内容を返さない。各拒否はCookie更新0、対象14射影の前後不変を確認する。

22操作の503条件は**そのASGIアプリのengineを局所的に未利用可能にする契約検査**である。正常DBは独立TLS observerで接続できたままであり、DBネットワーク断・接続時故障・TX中断・COMMIT ACK未読の実障害は今回未実施。22件の503を実DB障害22件と表現しない。

## 固定環境・実行手順・証跡

- profile `oct05-mac`、container `tech0-pos-oct05-mac-mysql`、volume同名末尾 `-data`、私有 `.oct05-mac-local`、MySQL `127.0.0.1:3327`、通常Mac HTTPS8463／8464。初期 `mysql-environment.json` のcontainer IDと実docker ID、固定name／port／volume、MySQL8.4・TLS証明書／名前・hostname一致、一般／slow log無効を実行時guardで確認する。
- 専用schema `pos_oct05_api`、accounts `pos_oct05_api_app/master/schema`、staff `STAFF_API_A/B`、member `MEM_API`、専用7商品。通常Macは別schema `pos_validation`。REGISTER=1固定のためCookieを別にするだけでは分離できず、schema自体を分ける。
- 初回 `--prepare` はschema／accounts不存在を確認し、現行16表DDL／最小権限／初期権限revoke／架空fixtureを投入する。既存DB・accountsをDROP／resetしない。DDLの部分失敗は件数と例外型／数値コードを保存して停止し、自動再送しない。
- `--run` はfresh UNSTARTED／cart0・商品集合一致を確認し、一度だけ実行する。実FastAPI ASGI middleware・handler・サービス・Repositoryと実MySQLを通すが、Next中継・実HTTPS受信・ブラウザの検査ではない。専用Cookieはプロセス内のみ。
- 503・SAVING／202の局所注入は専用ASGIプロセスだけ。purchaseは実prepare TXのCOMMIT後、finishを実readへ一時置換して保存TXを始めずにPREPAREDを返す。その後resolve／reopenは通常handlerを使用する。実ネットワーク結果不明を作った証拠ではない。
- 新規物理TLS接続・READ ONLY REPEATABLE READの14射影をSHA256で重複排除し、生行集合を `snapshots` へ保存する。AUTH_SESSION／BROWSER_CONTEXT／REGISTERはtoken_hash・active_session_hashを除く明示列射影。STAFFのpassword_hash・秘密値・Cookie・認証tokenは出力しない。全認証秘密列不変の証拠ではない。
- 巨大版は専用の次カートだけSQLで単調に設定し、APIの読取／sync／増分拒否を照合。通常アプリの操作で版を設定したとは表現しない。最終版上限のカートは編集／保存に進めず状態保持する。

主担当の明示実行コマンド。既存 `api-prepare.json`／`api-run.json` は上書き・自動再実行を拒否する。

```sh
python3 tools/oct05_api_verify.py
M2_LOCAL_PROFILE=oct05-mac backend/.venv/bin/python tools/oct05_api_verify.py --prepare
M2_LOCAL_PROFILE=oct05-mac backend/.venv/bin/python tools/oct05_api_verify.py --run
```

結果ファイルは `docs/implementation/evidence/oct05-mac/api-prepare.json`／`api-run.json`。失敗時は最後のstage・成功済み条件・前後生集合と、sanitized例外型／ソース行／数値DBコードを残して停止する。例外文字列やSQLパラメーターは出さない。主担当は通常schemaのbefore／afterとアプリmanifestも別に採取する。担当B／Cの実行前・実行後独立読取へ渡し、担当Aのセルフレビューだけで実合格としない。

初回script SHA256は `f51d68066f1fe712b3220947ea634ce3ee54f6e6bcc3b522afe235dbd6eb39ea`。[初回prepare](evidence/oct05-mac/api-prepare.json)と[初回run](evidence/oct05-mac/api-run.json)のsource hashに一致した。初回実行版は逆差分から復元後、記録済みSHA256との完全一致を確認して[原本](evidence/oct05-mac/oct05_api_verify.py.executed.txt)へ保存した。初回schemaと証跡は保持し、reset／DROP／元出力の上書きはしない。

## 初回停止・検証器修正・新規検証の境界

初回runは `TC11-getOperation-normal` で `_WrappedReferencingError`（schema validate内）となり、status=stopped・350成功条件／選択TC11 346成功・121未実行を保存した。schemaの直下 `$ref` だけを完全URIにしたため、oneOf内部の `#/components/...` が文脈を失った**検証script側の欠陥**。アプリの応答不正と断定しない。getOperation正常や以後のresolve／reopen／delete／next、金額／巨大版／DB拒否は、この初回では成功として数えない。

修正版はschema内のlist／dictを再帰的に走査して全内部 `$ref` を `urn:pos#/...` に固定し、format検査も有効にした。担当Aの接続なし `--replay-original` は既存350応答をそれぞれの操作／HTTP schemaへ再投入し全件成功。元run JSONのSHA256 `3ee8fa274f7ede7a918116600572dff0272442db1ce58b2e9786fbbe91ccbd94` は不変。これは保存した応答本文の再検査であり、初回DB要求を再送した証拠ではない。

実ASGI＋模擬repositoryで取得したNOT_FOUND操作照会応答がnested oneOfを通り、applied_versionの不正な数値型7は拒否される追加回帰も成功した。元のSAVING／PREPAREDは実受付後にfinishをreadへ差し替えた状態で、元Cookieはプロセス終了時に失われている。この取引の復帰／再購入を試みず、主担当が別の新規schema `pos_oct05_api_retry`、accounts同prefix `_app/master/schema`、`api-prepare-retry.json`／`api-run-retry.json` を明示的に選ぶ。固定の `--retry` 以外で任意のschemaや出力先を指定できない。

```sh
backend/.venv/bin/python tools/oct05_api_verify.py --replay-original
M2_LOCAL_PROFILE=oct05-mac backend/.venv/bin/python tools/oct05_api_verify.py --prepare --retry
M2_LOCAL_PROFILE=oct05-mac backend/.venv/bin/python tools/oct05_api_verify.py --run --retry
```

これは検証器修正後の**新規検証実行**であり、元購入の回復・自動再送ではない。元schema不変は主担当の別TLS採取を根拠にし、script内の対象名宣言だけで不変を証明しない。修正版SHA256は `b771e3894f8376c8d79f961294995cf64f4f9fc4502c770f8f7c29930720fbbf`。主担当の実行前レビューで、connect関数の既定DBが定義時の元schemaへ束縛される問題を検出し、sentinelによる実行時解決へ修正した。server-onlyの明示Noneは保持し、実ASGI SettingsのDB／userもretry専用に一致する。接続先修正はretry実行前であり、元DBをretryで変更した事実ではない。独立レビュー後に主担当が実行版を[原本](evidence/oct05-mac/oct05_api_verify.py.retry-executed.txt)へ保存して凍結し、明示prepare／runを実行した。実行証跡・原本・現行scriptのSHA256は同じb771であり、実行後scriptを変更していない。

## 新規固定schemaの実行結果

[retry prepare](evidence/oct05-mac/api-prepare-retry.json)で専用schema・3アカウントと16表の作成が成功。[retry run](evidence/oct05-mac/api-run-retry.json)は `status=limited_cases_passed`／`completed=true`、最後のstageは `TC12-max-sync-refusal`。担当Aの読取再集計は519件のIDがすべて一意、計画TC11の467集合と実行467集合が完全一致、remaining=0を確認した。22操作の正常入口はすべて実行済み。`-normal` というID末尾だけで数えるとmember-null追加を含む23件となるため、22という値は正常operationの種類数である。

| 実行群 | 成功小項目 | 生証跡の読取結果 |
|---|---:|---|
| TC-11 | 467 | JSON／Cookie／Origin／認証・復帰条件と22正常入口。510 HTTP応答全体を各operation・statusの現行schemaへ再投入して成功（他TCのHTTP43件を含む） |
| TC-08 | 25 | 32文字・大小文字3コードを別行として追加、形式拒否10件は14射影不変。単行／合計／税込超過3件はAMOUNT_INVALID、99への追加はQUANTITY_LIMIT。それぞれ既存operation保持・新REJECTED1件のみ、他13集合は不変 |
| TC-12 | 18 | キー順／DELETE同一再送2件は前後不変、同ID値・版違いはOPERATION_MISMATCH、新ID旧版はVERSION_CONFLICT。2^53近傍3値とBIGINT最大近傍3値のAPI版は正確な十進文字列、可能な4値のsyncは+1。最大−1から購入の2増分不足、最大からsyncはVERSION_LIMITで前後不変 |
| TC-13 | 9 | REGISTER2／空会員名／数量0／JSON object候補／不整合金額／不正stateは3819、コード重複1062、存在しない税率親1452、会員名null1048。各拒否後rollback・独立TLS読取14集合不変 |
| 合計 | 519 | 510 HTTP条件＋9直接SQL制約。全受入の母数ではない |

62種類の保存された生射影をJSONのSHA256へ独立再計算し全一致。各ケースのbefore／afterは異なる物理接続IDであり、unchangedラベルの全ケースは同じ射影hashだった。4業務拒否はhash差分が生じるため「全部不変」と呼ばず、CART_OPERATIONの新拒否行1件だけを個別に比較した。

売上は**1件**。PURCHASE／PURCHASE_LINE／PURCHASE_TAXはそれぞれ1行、P103数量1・単価103・税率0.1000、小計103／税10／合計113の独立定数に一致した。PURCHASE operationは実通常保存APPLIED1件（prepared版23→applied24）と、局所PREPAREDからresolveで閉鎖したREJECTED1件（prepared8、PURCHASE_ATTEMPT_CLOSED）。operation2件を売上2件とは数えない。next後の旧cartはCLOSED v25・103／113、次cartはEDITING v18446744073709551615・未購入P103数量1・103／113で保持された。次cartは巨大版検証のために専用SQLで版を単調設定したもので、一般利用フローの最終状態とは扱わない。

担当Bの実行前独立レビューはnested参照／retry固定アカウント／sentinel／オフライン実接続引数とSettings経路に重大指摘なし。[実行後独立比較](evidence/oct05-mac/comparison-api-retry-independent.json)も本票の値・限界と一致し、追加の確実な欠陥・過剰合格はなかった。主担当の[通常Mac before](evidence/oct05-mac/db-before-api.json)／[retry後](evidence/oct05-mac/db-after-api-retry.json)の業務9集合を担当Aも比較し全一致、UNSTARTED／cart0／売上0の保持を確認した。全表・認証秘密列・HTTP到達なしの証明ではない。[元DB・Mac比較](evidence/oct05-mac/comparison-original-and-mac-after-retry.json)の元schema before／after生JSONも担当Aが独立比較し、14射影が完全一致、SHA256はともに `2a96d228ce814951537f8a98022ee6f0ab8b40f5e41ea084fa61e091b5cf20e1`、異なる物理TLS接続でSAVING v8／売上0の保持を確認した。元run JSONのSHA256も3ee8のまま不変。元購入の復帰・resolve・再送は行っていない。除外した秘密列・STAFF／MEMBER・DDL／アカウントの全不変をこの14射影から推定しない。[最終環境確認](evidence/oct05-mac/environment-checks-complete.json)のアプリ32ファイルshaを担当Aも現行ファイルへ再計算して全一致、現行BUILD_ID `5_wgTZOtPLE3as7vfiFAN` との一致を確認した。主担当が固定ID／ports／runtime一致とGit候補・ログへの秘密値非掲載を記録した。buildは既検証版との一致を確認したもので、今回buildを再実行した証拠ではない。その後の本人ログインを経て、主担当が選択Mac6条件（会員2・復帰4）を実Chromeで完了した。条件別の結果・証跡・限界は[会員結果票](10月05日_会員検証計画結果.md)と[復帰結果票](10月05日_復帰検証計画結果.md)を参照し、API519件の件数へ足さない。[最終停止証跡](evidence/oct05-mac/shutdown-gui-final.json)で専用container exited、3327／8463／8464閉鎖、専用volume `tech0-pos-oct05-mac-mysql-data` 保持を確認した。現在はログイン／稼働待機ではなく停止済み。API試験時の通常Mac9集合不変と元API schema保持はその時点の証拠として残し、後続GUI操作後の通常Mac状態へ自動延長しない。

## 現在のローカル検査と残範囲

[追加検査](../../backend/tests/test_api_contract_remaining.py)は、実ASGIハンドラ＋模擬repositoryの3条件（2行集計拒否／再送、税込だけ超過拒否、NOT_FOUNDのnested oneOf／型拒否）と、検証harnessの4条件（offlineのDB・秘密値・docker禁止、拒否時の部分変更検出、失敗を成功証跡へ追加しない、fake connectorへのretry／None実引数と実runのDB／user一致）で**7件成功**。初回は再送のrequest_idも同一とする検査期待だけが失敗し、再送不変の対象をHTTP status・業務本文に直して成功した。アプリの欠陥ではない。模擬TXは実MySQLの保存証拠ではない。

scriptの接続なし既定コマンドは成功し、選択467 IDを生成。backend設定の対象Ruff lint／formatも成功。主担当のmake check自体はXcodeライセンス未同意によるexit69で開始できず、ライセンス同意操作はしていない。その後、直接等価コマンドでbackend／frontendのlint・format・型検査、全Python85件＋Node123件＝208件、OpenAPI22操作を検査し成功。担当Aも[backend結果](evidence/oct05-mac/check-backend-tests.log)／[frontend結果](evidence/oct05-mac/check-frontend-tests.log)／[契約結果](evidence/oct05-mac/check-contract.log)と各lint／format／型ログを読取確認した。environment確認JSONの `full_application_suite_rerun:false` はその環境verifier内ではテストを走らせないという意味であり、別途実行した今回208件を未実行にする値ではない。makeコマンド成功とも読み替えない。文書リンク検査はerrors=[]、最終git diff --checkも同じ環境制限で未完了（それ以前の成功と区別）。実行前独立レビューは重大指摘なし、数量99追加の理由をQUANTITY_LIMIT固定で照合する補強を反映した。DB／Docker／GUI／ネットワーク／buildは本担当が実行していない。新規本番依存・アプリ・共有toolsを変更せず、commit／pushも行わない。

全22操作の全定義応答・試行制限・保守／別担当者の全操作・復帰期限／全Cookie組合せ、保存状態ごとの全GET、実DB初回接続故障、全16表の全制約・SQL外候補JSON意味検査、内部JOIN全競合、通常HTTP時計、両端末、Azure、M7は残る。今回の選択条件に対応する未実行数だけを減らし、その他の未確認を自動解除しない。

戻す対象は今回のscript・追加テスト・本票の差分だけ。専用schema／accounts／売上・volume・証跡の削除は自動で行わず主担当の対象確認へ戻す。
