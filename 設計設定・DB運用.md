# 設計設定・DB運用

更新：2026-09-27。[設計仕様書](設計仕様書.md)の技術設定とDB作業の詳細。未決・実証状況は[設計残課題](設計残課題.md)、判断経緯は[設計承認履歴](設計承認履歴.md)で管理する。対象：P02・P03、F01〜F07・F18〜F25、N01・N02、T02・T03。受入条件は[要件5.1](docs/requirements/受入条件_現行.md#sec-5-1)・5.3・5.4。

## 1. 実行環境・依存の選び方

| 対象 | 設計上の選択 | 固定方法 |
|---|---|---|
| フロント | Node.js 24 LTS、Next.js 16系 | Reactは採用Next.jsの対応版。導入時に修正適用済みの具体版を確認し、package-lock.jsonに固定 |
| API | Python 3.13系、FastAPI＋Pydantic v2、Uvicorn | PythonはAzure提供版と合わせ、依存は互換性を確認した完全版番号で固定。FastAPIが要求するStarletteの範囲を勝手に上書きしない |
| DBアクセス | SQLAlchemy 2.0系Core＋PyMySQL 1.1系 | ORMのモデル自動同期は使わず、既存DDLを正とする。接続プールを自作しない |
| パスワード | pwdlibのArgon2ハッシャー＋argon2-cffi | 次節の値を明示指定。既定値の将来変更で設定を変えない |
| DB | Azure MySQL Flexible Server 8.4系 | サービス提供パッチを環境記録へ記載。自動更新による版変化も記録 |

上記は採用系列であり、完全な依存ロックではない。導入時に公開脆弱性・ライセンス・Python／Node適合を確認して完全版番号を固定する。Azureの利用可能ランタイムは対象環境で読取確認する。系列が提供されない場合は勝手に切り替えず再選定する。

フロントは`frontend/`、APIは`backend/app/`を配置単位とする。API内は`api`（入力・認証）、`services`（業務計算・状態遷移）、`repositories`（SQL・TX）、`infrastructure`（接続・設定）に分ける。DB接続をUIや計算関数へ渡さない。同期PyMySQLは同期ハンドラー／スレッドで実行し、asyncハンドラーのイベントループを直接塞がない。

根拠（2026-09-27確認）：[Node LTS](https://nodejs.org/en/about/previous-releases)、[Next.jsサポート](https://nextjs.org/support-policy)、[Azure Python配置とランタイム照会](https://learn.microsoft.com/en-us/azure/app-service/quickstart-python?tabs=azure-cli)、[FastAPIの版固定](https://fastapi.tiangolo.com/deployment/versions/)。

### 1.1 導入前の候補版

2026-09-27の公開メタデータ確認に基づく候補。全依存の解決・導入・動作検証後に固定版とする。根拠・照会時刻・配布物ハッシュ・宣言された依存条件・OSV照会結果は[依存候補_確認根拠.json](依存候補_確認根拠.json)に保持する。

| パッケージ | 候補版 | ライセンス表記 | 区分 |
|---|---|---|---|
| [fastapi](https://pypi.org/pypi/fastapi/0.141.1/json) | 0.141.1 | MIT | 直接依存候補 |
| [pydantic](https://pypi.org/pypi/pydantic/2.13.5/json) | 2.13.5 | MIT | 直接依存候補 |
| [uvicorn](https://pypi.org/pypi/uvicorn/0.54.0/json) | 0.54.0 | BSD-3-Clause | 直接依存候補 |
| [SQLAlchemy](https://pypi.org/pypi/SQLAlchemy/2.0.54/json) | 2.0.54 | MIT | 直接依存候補 |
| [PyMySQL](https://pypi.org/pypi/PyMySQL/1.1.3/json) | 1.1.3 | MIT | 直接依存候補 |
| [pwdlib](https://pypi.org/pypi/pwdlib/0.3.1/json) | 0.3.1 | MIT | 直接依存候補 |
| [argon2-cffi](https://pypi.org/pypi/argon2-cffi/25.1.0/json) | 25.1.0 | MIT | 直接依存候補 |
| [starlette](https://pypi.org/pypi/starlette/1.7.0/json) | 1.7.0 | BSD-3-Clause | 主要な間接依存 |
| [next](https://registry.npmjs.org/next/16.3.6) | 16.3.6 | MIT | 直接依存候補 |
| [react](https://registry.npmjs.org/react/19.3.0) | 19.3.0 | MIT | 直接依存候補 |
| [react-dom](https://registry.npmjs.org/react-dom/19.3.0) | 19.3.0 | MIT | 直接依存候補 |
| [@zxing/browser](https://registry.npmjs.org/%40zxing%2Fbrowser/0.2.1) | 0.2.1 | MIT | 直接依存候補 |
| [@zxing/library](https://registry.npmjs.org/%40zxing%2Flibrary/0.23.0) | 0.23.0 | Apache-2.0 | 直接依存候補 |

Python 3.13／Node 24と、表内の相互依存は公開された版条件を満たす。これは実行時互換性の保証ではない。pwdlibは`[argon2]`を指定し、FastAPI／Uvicornの`[standard]`など未使用機能をまとめた追加依存は付けない。PyMySQLの追加認証依存はAzure上のTLS接続方式で必要性を確認する。

13候補の指定版に対する[OSV照会](https://google.github.io/osv.dev/api/#osv-api)では該当報告は返らなかった。全依存の安全性を確認した意味ではなく、pydantic-core、argon2-cffi-bindings、h11等の間接依存、開発用依存、Node／Python／OS本体は全体固定時に確認する。候補版に対応する配布物のライセンス／NOTICEも導入時に確認する。pwdlibはPyPIの本文・分類でMITを確認し、機械可読license欄の欠落を根拠JSONに記録した。

カメラは`@zxing/browser`＋`@zxing/library`を第一候補とする。[libraryの公式README](https://github.com/zxing-js/library)には保守モードとの記載があり、継続保守とMacBook Air／iPhone 15のChromeでの読取・同コード抑止を確認して採否を確定する。版条件を満たすだけで実機適合済みとはしない。

## 2. 認証・接続設定

以下は初期設定値。性能実証で調整する場合も、認証8時間・復帰24時間・正常応答2秒の要件は変更しない。

| 項目 | 値・処理 |
|---|---|
| パスワードハッシュ | Argon2id、memory_cost=65536 KiB、time_cost=3、parallelism=4、salt_len=16 bytes、hash_len=32 bytes。saltは毎回安全な乱数で生成し、パラメータ込みのエンコード済み文字列を保存 |
| 認証・復帰識別子 | それぞれ独立した32 bytesの暗号学的乱数をBase64url（paddingなし）にする。DBにはそのASCII文字列のSHA-256のみ保存。平文はCookie受渡し以外で出力・永続化しない |
| ハッシュ照合失敗 | 不存在担当者でも同設定のダミーハッシュ照合を行い、表示は共通エラー。計算エラー・DB不通をパスワード誤りと扱わない。8時間の更新規則は[設計8章](docs/design/認証と運用.md#sec-8)のまま |
| APIプロセス | Uvicorn worker=1を初期値。複数要求は既存のDBロック・版で制御し、1プロセスを排他の根拠にしない |
| DBプール | pool_size=5、max_overflow=0、pool_timeout=1秒、pool_pre_ping=True、pool_recycle=300秒。プロセスごとに1個。再起動／配置中のプロセス重複と保守接続分をDB上限に加算 |
| DB接続 | TLS証明書・ホスト名検証、autocommit=False、utf8mb4、UTC、READ COMMITTED、厳格SQLモード。通常更新はREAD COMMITTED、複数SELECTの照会は[設計5.1.2](docs/design/通信とデータ.md#sec-5-1-2)どおり読取専用REPEATABLE READをTX開始前に指定。終了後は設定を戻して返却し、TX残留を許さない |
| DB待ち | connect_timeout=3秒、read_timeout=5秒、write_timeout=5秒、SESSION innodb_lock_wait_timeout=1秒。待ち切れ・デッドロックではTX全体をROLLBACKし、失敗接続を破棄。TXの自動再送なし |
| HTTP待ち | Next.js→APIは10秒、ブラウザは15秒で打ち切る初期値。これは障害検出用で正常時2秒の許容時間ではない。切断後もサーバー処理が継続し得るため、既存の同一操作照合へ進む |

通信断・COMMIT応答不明は「未保存」と断定しない。プールの接続確認／交換はTX開始前だけで、開始後に接続を交換して処理を続けない。各待ち時間は処理全体の上限ではなく、SQL往復・ロックの累積は別途測定する。認証の同時要求で64MiBずつ消費するため、B1共有時の負荷確認を行う。試行制限は次節に従う。

根拠：[Argon2パラメータ](https://argon2-cffi.readthedocs.io/en/25.1.0/api.html)、[SQLAlchemyプール・切断時の扱い](https://docs.sqlalchemy.org/en/20/core/pooling.html)、[PyMySQL接続設定](https://pymysql.readthedocs.io/en/latest/modules/connections.html)。

### 2.1 ログイン試行制限

`POST /api/login`と`POST /api/reauth`で共通のAUTH_LOGIN_LIMITを使用する。キーは入力された担当者ID（既存のASCII・大小文字区別）。不存在IDにも同じ記録・共通エラーを適用し、ID存在の有無で制限の有無を変えない。形式不正・Origin拒否は照合前に拒否する。

- 行ロック取得後のDB UTC時刻をnowとし、`now < locked_until`なら照合せず共通の401を返す。既存Cookieを削除せず、期限・失敗数も更新しない。
- 制限期限に到達したら、次の要求時に期限と過去の失敗配列をクリアする。解除ジョブや手動解除APIは不要。
- 制限中でなければ、失敗時刻が`now - 10分 < 時刻 <= now`の記録を残す。パスワード照合失敗時だけ今回の時刻を追加し、5件になった時点で`locked_until = now + 10分`とする。
- 成功要求を失敗数へ加算しない。直近10分の失敗記録は成功だけでは消さず、時間窓で除外する。DB・ハッシュ処理の障害、資格情報が正しいが別担当者の取引で拒否された場合は数えない。
- REGISTER→AUTH_LOGIN_LIMITの順にロックし、初回行作成・期限確認・照合結果記録を直列化する。不存在IDはダミーハッシュで照合する。成功時は既存セッション切替と同じTXで確定。資格情報の照合失敗も失敗回数・期限のTXをCOMMITしてから401を返す。401を例外扱いして失敗記録までROLLBACKしない。記録不能なら503で停止し、制限を迂回してログインさせない。
- 再起動や別タブでもDBの制限を共有する。failure_timesはUTC日時文字列の昇順配列で最大5件とし、日時形式・順序を保存前に検査する。DB行は演習中保持し、過去の時刻を配列から除く処理は制限判定用の更新として行う。

5回目の失敗と制限中の応答も既存の共通401形式・文言を使用し、残回数・入力IDの存在・個別の解除時刻を応答へ含めない。制限によって有効なセッションを失効させたり、カートを初期化したりしない。資格情報の失敗がDB確定後に応答断となった場合は1回として残る。認証POSTを自動再送しない。

## 3. DB権限の割当

各用途に別アカウントを用い、アプリへ保守資格情報を配布しない。DB名・ユーザー・接続元は実環境に置換する。`GRANT ALL`・`GRANT OPTION`は使わない。MySQLの権限付与とAzureのIP許可は両方必要。

| 利用者 | 表と権限 |
|---|---|
| 通常アプリ | 全16表のSELECT。AUTH_LOGIN_LIMITはINSERT・UPDATE。REGISTERはUPDATEのみ。BROWSER_CONTEXT／AUTH_SESSION／CART／CART_LINE／CART_OPERATIONはINSERT・UPDATE、CART_LINEだけDELETE。PURCHASE／PURCHASE_LINE／PURCHASE_TAXはINSERTのみ |
| マスタ保守 | MEMBER／TAX_RATE／PRODUCT／DISCOUNT_CONDITIONのSELECT・INSERT・UPDATE。PRICE_HISTORYはSELECT・INSERT。売上3表はSELECTのみ。STAFFの資格情報変更はこの常用権限に含めない |
| 初期投入担当 | マスタ保守の範囲に加え、初回だけREGISTER／STAFFのSELECT・INSERT。投入完了後に初回用追加権限を外す |
| スキーマ変更担当 | 対象DBのCREATE・ALTER・INDEX・REFERENCESと照合用SELECT。DROPは常用権限にしない。ユーザー／GRANT管理は環境管理者が実施 |
| 例外復帰担当 | [設計9.4](docs/design/認証と運用.md#sec-9-4)の対象を確認するSELECTと必要列のUPDATEを作業時だけ付与。REGISTER(maintenance_hold,active_session_hash)、AUTH_SESSION(revoked_at)、BROWSER_CONTEXT(token_hash,manual_released_at)、CART(version,state,active_member_operation_id,active_purchase_operation_id,purchase_prepared_version)、CART_OPERATION(status,result_code,result_payload,applied_version,completed_at)を上限候補とし、対象分岐で使う列だけ許可 |

例外復帰の列名は現行DDLと照合する。MySQL列権限は行を制限しないため、対象ID・元状態・元版のWHERE条件と更新1件を必須とする。売上のUPDATE／DELETE、レジのUNSTARTED化、元の業務日時の変更は許可しない。

SQL書式例（実アカウント作成前のテンプレート。以下の識別子は置換用）：

```sql
GRANT SELECT ON `TARGET_DB`.`PRODUCT` TO 'APP_USER'@'APP_HOST';
GRANT SELECT, INSERT ON `TARGET_DB`.`PURCHASE` TO 'APP_USER'@'APP_HOST';
GRANT UPDATE (maintenance_hold, active_session_hash)
  ON `TARGET_DB`.`REGISTER` TO 'RECOVERY_USER'@'RECOVERY_HOST';
SHOW GRANTS FOR 'APP_USER'@'APP_HOST';
REVOKE UPDATE (maintenance_hold, active_session_hash)
  ON `TARGET_DB`.`REGISTER` FROM 'RECOVERY_USER'@'RECOVERY_HOST';
```

表ごとに権限表から展開して付与し、`SHOW GRANTS`で照合する。既存利用者に広い権限がある場合、追加GRANTだけで最小権限になったと扱わない。手動復帰終了後は作業時権限を解除する。根拠：[MySQL GRANT](https://dev.mysql.com/doc/refman/8.4/en/grant.html)。

## 4. 初期投入・変更・戻し

1. 対象DB・DDL版・全16表・FK／CHECKを[設計確認.sql](設計確認.sql)で照合。新規空DBであることを確認し、既存データがあれば初期投入を停止する。
2. 演習用の担当者・会員・税率・商品・値引きを準備する。会員は6属性全てを必須とし、欠落・NULL・空文字を投入前に拒否する。年齢は真偽値でない0以上の整数であることとINT UNSIGNEDの範囲を検査し、小数の丸めを許さない。文字列はutf8mb4符号化後にTEXT容量内か検査する。性別の選択肢・独自の長さ制限は追加しない。ハッシュは採用pwdlibの同設定で生成し、平文をSQLやシェル履歴に含めない。
3. 自動COMMITを無効にした1つのTXで、REGISTER=1／UNSTARTED／maintenance_hold=TRUE→STAFF・MEMBER・TAX_RATE→PRODUCTとPRICE_HISTORY→DISCOUNT_CONDITIONを投入する。初期履歴はold_price=NULL、new_price=商品単価。生成IDは同一接続で受け取る。使用中DBへ上書きするUPSERTは使わない。
4. 宣言した投入件数・各ID・金額・期間・FK、全商品の初期履歴1件をSELECTで照合する。例外・件数違いは全体ROLLBACK。会員属性の検査は初期登録と更新に共通適用する。
5. 照合後にCOMMIT。応答不明なら新接続で全投入IDと値を照合し、無条件に再投入しない。確定済みなら初期化を繰り返さない。
6. 初回用権限を外し、利用開始の確認へ進む。保守停止中は通常の初回カート作成を行えないため、停止中に設定・読取を確認し、本人の利用開始判断後にmaintenance_holdを解除してログイン・初回Cookie確認へ進む。失敗時は再び停止する。

商品単価変更は[設計9.6](docs/design/認証と運用.md#sec-9-6)のロック・旧値照合・履歴同時保存に従う。COMMIT前はROLLBACK、COMMIT後は確認した差分を戻す別TXとし、単価を戻した事実も価格履歴へ追加する。確定済みの初期データや売上をDELETEして「未実行」に戻さない。DDL途中失敗は成功した文を記録し、未適用部分だけの修正手順を作る。

## 5. 復旧の作業単位

| 状況 | 照合と変更範囲 | 再開条件 |
|---|---|---|
| 期限切れのみ | レジ・context・担当者・カートを共通ロック順で確認。manual_released_atをDB UTC時刻へ更新。元のlast_business_at・売上日時は維持 | 元の結果／会員待ちを保持し、24時間の判定が通る |
| Cookie消失 | 上記に加え新しい復帰識別子の照合値に置換。旧認証失効、有効セッション参照を解除。同一context・カートを保持 | 正しいオリジンにSecure／HttpOnly等を保持したCookieを設定し、同じ担当者の再認証後に対象一致 |
| SAVINGで結果不明 | 全アプリ停止とDB処理終了を確認。売上・明細・税と受付操作をロック下で照合。売上ありは既存結果、なしは旧保存操作の終了とUNSAVED化。版を進めて旧要求を拒否 | 不整合・版上限・終了しないDB処理があれば停止継続。単独の売上不存在SELECTで再開しない |
| DB全体の復元 | 旧DBを保存し別サーバーへ復元。復元時点以降の売上・操作を旧DB／証跡と照合。旧認証を失効し再照合 | 差分未解消なら切替不可。旧DBを読めず照合不能な場合も同じ |

共通：maintenance_hold=TRUE→全アプリ停止／DB処理終了確認→対象TX→保守停止のまま起動→認証・状態照合→停止解除。Cookie修復はブラウザ管理機能で実施し、HttpOnlyをdocument.cookieで代用しない。秘密値を画面証跡へ写さない。対象ブラウザで安全に設定できない場合は停止を維持する。

例外復帰は、対象と分岐を確定してから列権限・WHERE条件・期待件数・変更前後・戻し方を含む1回分のSQLを用意する。汎用の一括修復SQLや復旧ツールは作らない。COMMIT前はROLLBACK、応答不明なら読取照合、COMMIT後に旧Cookieや失効済み認証を復活させない。手動修復で新しい取引を作らない。

### 5.1 iPhone ChromeのCookie修復候補

通常操作はiPhone 15のChromeのままとし、保守時だけMacBook AirのSafari Web InspectorからiPhone上のChromeの対象タブを検査する。Mac側Safariは保守ツールとして使用し、POSの対応ブラウザをSafariへ拡大しない。専用復旧API・アプリの改修はこの候補に含めない。成立状況は残課題Q04を参照する。

公開資料で確認したこと（2026-09-27）：

- [Google公式手順](https://developer.chrome.com/blog/debugging-chrome-on-ios)：iOS 16.4以降・Chrome 115以降で、Chromeの設定→コンテンツの設定→Web Inspectorを有効化しChromeを再起動。Macとケーブル接続して、Mac Safariの開発メニューからiPhoneのChromeの対象URLを選択できる。記載は2023年公開であり、実際の採用版の設定位置・接続可否は確認する。
- [AppleのCookie編集機能説明](https://developer.apple.com/videos/play/wwdc2020/10646/)と[WebKit CookiePopoverのソース](https://raw.githubusercontent.com/WebKit/WebKit/main/Source/WebInspectorUI/UserInterface/Views/CookiePopover.js)：Cookieの追加・編集とHttpOnly／Secure／SameSite／期限の編集機能がある。上流mainの実装確認であり、採用macOS／iOS版での搭載・動作を証明するものではない。

実証手順（架空の識別値・隔離したHTTPS環境、別途実行許可後）：

1. macOS・Safari・iOS・Chromeの実版とMacBook Airのモデルを記録。iPhoneのChrome通常タブを開き、上記手順でそのタブへ接続する。Mac側Safari自身のCookieを編集していないことを確認する。
2. テスト用Cookieを作成して削除した状態から、StorageのCookie編集で再作成する。名前は`__Host-pos_resume`、Path=/、Secure／HttpOnly有効、SameSite=Lax、期限30日相当とする。別名・保護属性の省略で成功扱いにしない。
3. **host-onlyの扱いを確認する。** 編集UIにDomain欄があるため、ホスト文字列を入力できることだけで「Domain属性なし」と同等だと判断しない。`__Host-`制約を満たす保存状態・送信先を検証する。確認不能なら不合格として停止する。
4. 設定した値がiPhone ChromeのHTTPS要求で送られ、DB照合値と一致すること、ページJavaScriptから読めないこと、再読込・Chrome終了後にも必要属性が残ることを確認。値自体をログ・HAR・スクリーンショットへ残さず、属性と照合の成否を記録する。
5. アプリ構築後は[設計9.4](docs/design/認証と運用.md#sec-9-4)と合わせ、保守停止・旧認証失効・同じ担当者の再認証・元カート一致・旧Cookie拒否まで確認する。初回COOKIE_PENDINGでは停止解除後にconfirmし、新しい取引を勝手に作らない。
6. 作業後はWeb Inspectorを無効化し、不要なテスト値・クリップボードの秘密値を残さない。接続不能・属性不一致・対象不一致では保守停止を維持する。

判断：標準ツールを使う経路は公開資料で確認できた。HttpOnlyをJavaScriptから書き換える方法は採用しない。`__Host-`を含む実機での再設定は未実証なので、手動復旧の成立確認は未完了とする。

この経路が不成立なら、次の比較を本人へ提示してから設計を変更する。

| 代替 | 影響 |
|---|---|
| 本人のDB側許可後、既存認証経路でサーバーからCookieを再発行 | ブラウザ手動編集への依存を減らせるが、本人許可の対象・一回性・期限・担当者照合・応答断の処理を追加設計する必要がある。現行の自動修復禁止との境界を明示して判断する |
| Cookie消失時は停止を維持する運用に限定 | アプリ追加は少ないが、手動再開できる現行要件を満たさないため要件変更が必要 |

Macへの取引移管、初期化、新カート作成、Cookie保護の弱化で代用しない。資料だけで不可能と断定して代替方式を先に実装しない。

## 6. 実行前に揃える確認資料

| 対象 | 実行前に記録するもの | 許可後の成立確認 |
|---|---|---|
| 版・依存 | Node／Python実版、全依存の完全版番号・ライセンス・脆弱性確認日、Azure提供ランタイム、固定ファイル | 同じ固定版でbuild・起動・認証・DB接続。提供版変更時は再確認 |
| 初期データ・権限 | 演習データの件数／ID、全GRANTと解除SQL、対象DB・利用者・接続元 | 会員正常／欠落／空文字／年齢0・負数・小数／型上限、商品初期履歴、アプリでの禁止権限拒否。検証用TXは隔離環境で扱う |
| 認証・接続 | 2節の設定実値、DB最大接続数、B1メモリ、認証とDB通信の測定条件 | ハッシュ照合・同時負荷、接続貸出失敗・切断・COMMIT応答断。自動再送・二重保存なし、正常時性能は[設計9.2](docs/design/認証と運用.md#sec-9-2) |
| 復旧 | 対象レジ／context／cart／操作・元版、停止確認方法、対象ブラウザのCookie設定手順、分岐別SQLと期待件数 | 期限切れ・Cookie消失・結果不明・初回Cookie失敗を分け、元データ保持／旧要求拒否／失敗時停止を確認 |

ここに記した検証は実施予定であり、実行結果ではない。実アカウント・対象ID・秘密値を共通の設計文書へ埋め込まない。具体値を必要としない設計と、環境構築後に作成する1回分の作業票を分ける。

## 7. 診断ログの保存

Next.js・FastAPIの各Linux App Serviceで、標準のApplication loggingをFile System、Retention Periodを7日、Quotaを100MBにする。100MBはアプリごとの初期設定で、実際の提供範囲・プラン共用容量・7日分の発生量を配置時に照合する。追加のLog Analytics・Application Insights・Blob保存・外部通知は構成に含めない。独自のログ削除ジョブも作らない。

| 項目 | 設定・確認 |
|---|---|
| 出力 | サーバー側で1イベント1行のJSONをstdout／stderrへ出力し、App Serviceのコンソールログとして収集。Pythonは標準logging、Next.jsはサーバー側の共通出力関数を使う |
| 記録内容 | [設計9.5](docs/design/認証と運用.md#sec-9-5)の許可項目だけを明示構築。UTC時刻、サーバー生成の要求ID、検証済み操作ID、ルート定義、処理時間、結果コード、DBエラー分類、配置版。生の例外・SQL・パラメータはそのまま出さない |
| リクエストログ | Uvicornの生URL付きアクセスログは無効化し、完了時の共通ログで置換。Next.js中継もルート定義で記録。未一致ルートはUNKNOWN_ROUTEとし生パスを出さない。要求ヘッダー・本文・Cookie・会員ID・IP／User-Agentは記録項目に加えない |
| レベル | 通常はINFO、異常はWARN／ERROR。DEBUG・詳細トレースは無効。ヘルスチェックの成功を毎回記録しない。秘密値・個人属性を含むフレームワーク既定出力がないことも確認 |
| 閲覧 | 本人のAzureアカウントでPortalのLog stream／Advanced Toolsから確認。ログ閲覧・取得権限を本人の運用範囲へ限定し、公開URLや匿名FTPを用意しない。通常はダウンロードせず閲覧 |
| 保存期間 | 日数は7。標準機能の削除周期で処理されるため、168時間ちょうどの削除時刻は保証しない。配備ログ・Azureの管理操作ログ・MySQLバックアップはこのアプリ診断ログとは別で、同じ設定で削除されると扱わない |
| 容量 | 両アプリのログはプラン容量を消費する。容量超過で7日未満のログが欠落しないか、実際の発生量・ローテーション・再起動後の取得を確認。100MBで不足ならプラン内で増枠し、プラン／費用変更が必要なら差分を提示 |
| 障害時 | ログ出力失敗を購入の失敗・未保存の根拠にしない。売上はDB照合。ログ取得不能や欠落は未確認として残し、7日保持の確認を合格にしない |

追加のログ収集サービスの費用を見込まない構成だが、既存プランの容量・実際の設定と請求は確認する。月額概算の税・通信等の除外条件はそのまま。ログを端末へ取得した場合、そのコピーにも保管先・アクセス権・削除期限を定め、Azureの保持設定だけで消えると扱わない。

実行前の設定票に、両アプリの保存方式・7日・100MBと閲覧権限を記録する。許可後、架空の機密値を含む要求に対して値がログへ漏れないこと、7日分の取得・期限処理・容量不足時の挙動を確認する。ログとDBの取引状態は別々に検証する。

根拠（2026-09-27確認）：Microsoft公式の[Linuxアプリログ設定](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs#enable-application-logging-linux-or-container)と[ログ参照](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs#access-log-files)。Webサーバーログ向け環境変数をPythonアプリログの保持設定として代用しない。
