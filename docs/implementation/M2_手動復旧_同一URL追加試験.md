# M2：同一URLでのCookie消失・旧値拒否の追加試験

2026-10-01。本人の「すべて進めて」に基づく隔離環境のM2追加確認。[最初の作業](M2_手動復旧作業記録.md)では新ホストで元のカートへ復帰できたが、元URLの旧Cookie生値を取得できず、実HTTP拒否は未確認。今回の結果を最初の取得不能な旧値の試験へ読み替えない。

## 対象・変更・境界

対象は既存`tech0-pos-m2-browser-mysql`／`pos_validation`、hostname=`e8a3f2017ee7`、REGISTER=1、context=`e5f8b91d-f145-421b-bf38-89fcaea9552c`、cart=`213f366b-49e3-4b6c-9acb-08d051ceac3f`、STAFF_A。同じiPhone Chromeと`https://passengers-external-cst-immediately.trycloudflare.com/`を維持する。元の業務日時・作成更新日時・状態・金額・会員・操作／売上不存在を保持する。

開始前はREADY、hold=FALSE、カートEDITING・version=2、manual_released_at=`2026-10-01 05:04:13.911257 UTC`、同じ担当者の有効認証1件。再読込・完全終了後の復帰は[API・画面](evidence/m2/browser/recovery-browser-restart.txt)・[DB](evidence/m2/browser/recovery-cart-after_restart.json)・[属性](evidence/m2/browser/recovery-cookie-after_restart.txt)で確認済み。

現在有効な復帰Cookieと認証Cookieを、旧値拒否検査に必要な間だけ600のGit除外領域で扱う。秘密値・Cookieハッシュを共有記録やコマンド履歴へ残さない。新たな外部サービス・依存・API・復旧ツールは追加しない。DB、担当者、context、カートの作り直しは行わない。

## 実行順序

1. 現在pos_recoveryはUSAGEのみなので、hold開始だけは既存管理接続が行う。対象ID・版2・全状態・新旧値に使う現在のCookieと有効認証のDB一致・件数を同じTXで照合し、固定ID・READY・hold=FALSE・既知active_session_hashをWHERE条件としてREGISTERのholdだけをTRUEへ1件更新する。他項目不変を確認してCOMMIT。Inspectorでこの試験の復帰Cookie1行だけを削除する。認証status=200、register/statusとresume=403を実ブラウザで確認し、DBの対象が不変であることも確認する。認証Cookieは削除しない。
2. 全アプリを停止し、同じDBの他利用者接続と他実行中TXが0であることを確認。専用pos_recoveryへ前回と同じ9表SELECTと4表の列UPDATEのみ作業時付与。アプリへ資格情報を渡さない。
3. 下記の対象限定TXで旧認証失効・有効参照NULL・新復帰照合値・manual_released_atの新DB UTC時刻・版2→3を一括確定。今回の手動許可理由は同一URLのCookie消失試験。last_business_atと業務全属性は延長・変更しない。誤版更新0件を挟むTXを全ROLLBACKし元の状態一致も検査する。
4. 本人がInspectorのCookie追加フォームから新値を入力・保存。保護属性は前回どおり、Domain空欄、Path=/、Secure／HttpOnly、Lax、非Session、30日相当の期限。新資格情報の入力・保存は操作ツール規約により本人へ引き渡す。
5. アプリを保守停止で起動。既存のHTTPSクライアントを使い、証明書／ホスト名を検証したlocalhost:8443の同じNext.js中継へ要求する。許可Originは上記の公開オリジンと完全一致、更新にはX-POS-Request:1を付ける。旧認証Cookieでauth/status=401、旧復帰Cookie＋正しいSTAFF_A資格情報でlogin=403・新Set-Cookieなしを確認。拒否の前後で有効認証参照NULL・カート・業務日時・件数が変わらないことをDB照合する。続いて**同じクライアント・URL・Origin・専用ヘッダー・本文**で復帰Cookieだけ新値へ変え、login=200と新認証発行を成功対照とする（この対照はiPhone本人再認証の前に行う）。対照の新有効認証と旧復帰Cookieではregister/status／resume=403、新復帰Cookieでは元カート版3に一致。これにより送信元不備や資格情報誤りによる403と区別する。対照セッションは本人の次の再認証で切り替わる。秘密値はプロセス内だけでHTTPヘッダー／本文へ渡す。
6. 同じiPhone・STAFF_Aで再認証し、保守停止中のGET3経路が版3の元カートへ一致、JS非露出、更新3経路が409・MAINTENANCE_HOLDを確認。読取照合が揃った場合だけ、前回と同じ全ガードで対象1件のholdを解除。専用権限を全撤去してUSAGEのみを確認する。
7. 同じURLで再読込と完全終了／再起動を別確認。保持属性・版3・業務日時・件数を照合。検証プロセスと公開トンネルを停止しDBボリュームは保持。Inspector無効化・本人の秘密値クリップボード除去を確認する。

## 版2→3の対象限定TX

前回の[全属性ガードと子表ロック](M2_手動復旧作業記録.md#対象限定の1回分のsql)を省略せず適用。REGISTER→BROWSER_CONTEXT→CART→AUTH_SESSIONをFOR UPDATE、変更しない子表5表をFOR SHARE、REPEATABLE READ。context／cart各1件、商品行・操作・売上・売上明細・税0件、全アプリ停止・他接続／TX0を必須とする。

元状態は前回の復旧済み版2。旧復帰ハッシュは現在の私有recovery-secret.jsonの値に一致、旧認証ハッシュは今回保存した認証値に一致し、REGISTERの参照先は同じSTAFF_Aの未失効かつ期限内の1セッション。手動許可日時は上記の前回確定値、失効日時NULL。会員状態UNSPECIFIED、会員・操作・保存参照NULL、税[]、小計／合計0、作成更新日時とconfirmed_at／last_business_atは元状態に完全一致。新旧復帰値は相違する。

```sql
-- 上記SELECTと全条件一致を同一TXのロック下で確認。
UPDATE AUTH_SESSION SET revoked_at=UTC_TIMESTAMP(6)
WHERE token_hash=%s AND register_id=1 AND staff_id='STAFF_A' AND revoked_at IS NULL;

UPDATE REGISTER SET active_session_hash=NULL
WHERE register_id=1 AND maintenance_hold=TRUE AND start_state='READY'
  AND active_context_id='e5f8b91d-f145-421b-bf38-89fcaea9552c'
  AND current_cart_id='213f366b-49e3-4b6c-9acb-08d051ceac3f'
  AND active_session_hash=%s;

UPDATE BROWSER_CONTEXT SET token_hash=%s,manual_released_at=UTC_TIMESTAMP(6)
WHERE context_id='e5f8b91d-f145-421b-bf38-89fcaea9552c'
  AND register_id=1 AND starting_staff_id='STAFF_A' AND token_hash=%s
  AND manual_released_at='2026-10-01 05:04:13.911257' AND invalidated_at IS NULL;

UPDATE CART SET version=3
WHERE cart_id='213f366b-49e3-4b6c-9acb-08d051ceac3f'
  AND register_id=1 AND context_id='e5f8b91d-f145-421b-bf38-89fcaea9552c'
  AND staff_id='STAFF_A' AND state='EDITING' AND version=2;
-- 各更新1件を必須。前後全属性・旧認証失効・件数を照合してCOMMIT。
-- 不一致・例外はROLLBACKしholdを維持。COMMIT応答不明なら別接続照合。
```

解除は前回の対象限定停止解除を基に、期待版だけ3、期待新照合値・手動許可日時だけ今回の確定値へ変える。同じ担当者の新有効セッション・期限内・同じ元カート全属性／件数一致を必須とする。最後にREGISTERのholdだけ1件変更し、他項目不変を読み直してCOMMITする。旧Cookie／失効認証は復活させない。

## 実行結果と現在の状態

独立レビューで、hold開始の権限付与順序と、旧値403を送信元不備と区別する成功対照不足を指摘。hold開始だけを既存管理接続へ割り当て、同じHTTPSクライアント・正しいOrigin／専用ヘッダー・同じ資格情報で復帰Cookieだけを変える対照を追加し、再レビュー合格。

05:33:06.632743 UTC、REGISTERを先頭に対象全属性・旧Cookie対のDB一致をロック下で照合し、holdだけ1件更新した。[hold開始](evidence/m2/browser/case2-hold.json)。同じiPhone Chromeの復帰Cookieだけを削除し、認証200・STAFF_Aを保持したままregister/statusとresumeは403・FORBIDDENを確認した。[同一URLの消失](evidence/m2/browser/case2-cookie-loss.txt)。

全アプリ停止・他利用者接続0・他TX0・ログ無効を確認し、専用の最小権限を再付与。[停止・権限](evidence/m2/browser/case2-preflight.json)。誤版更新0件でTX全体をROLLBACKし元状態一致を検査後、4表各1件の更新をCOMMIT。元の全業務状態を維持し、version=3、旧認証失効・有効参照NULL・新復帰照合値・manual_released_at=`2026-10-01 05:35:36.806674 UTC`を確定。[追加TX](evidence/m2/browser/case2-rotation.json)。

本人の新値保存前に、保守停止でアプリを起動してHTTPクライアント側の対照を先に実施した。証明書／ホスト名検証済みlocalhost:8443の同じNext.js中継、完全一致公開Origin・X-POS-Request:1で、旧認証auth/status=401、旧復帰値login=403・Set-Cookieなし、拒否前後DB不変。Cookieだけ新値にした同じloginは200で認証を発行し、新値のregister／resumeは元カート版3へ一致。その新有効認証＋旧復帰値のGET2経路は403・DB不変だった。[旧値拒否と成功対照](evidence/m2/browser/case2-old-cookie-http.json)。これはlocalhost中継のHTTP実証であり、以下のiPhone実機確認とは別に記録する。

新Cookieの名前・Domain空欄・Path=/・Session=false・Secure／HttpOnly・Lax・期限2026/10/31 14:40:00をInspectorで準備し、新値の入力・保存だけ本人へ引き渡した。[準備済みフォーム（秘密値除外）](evidence/m2/browser/case2-cookie-form-prepared.txt)。本人の「ログインできた」後、保存値の準備値一致と保護属性、旧値とは異なる認証Cookieを確認。[保存属性](evidence/m2/browser/case2-cookie-saved-attributes.txt)。新値・現行10文字のパスワードは600・Git除外の私有ファイルだけで扱い、共有証跡へ含めていない。

同じiPhone ChromeのGET3経路でSTAFF_A・READY・元カート版3に一致し、JS非露出・保守停止表示を確認。POST start／confirm／cartsは全て409・MAINTENANCE_HOLDだった。[停止中の実機照合](evidence/m2/browser/case2-browser-hold.txt)。実機の新認証とDBの有効セッション一致・期限・全業務属性・件数をロック下で照合後、05:44:57.012946 UTCにholdだけ1件解除してCOMMIT。[停止解除](evidence/m2/browser/case2-release.json)。pos_recoveryの作業権限を全撤去し、USAGEのみを確認。[権限撤去](evidence/m2/browser/case2-revoked-grants.json)。

再読込後は05:45:44.321 UTCの[画面・API](evidence/m2/browser/case2-browser-reload.txt)と05:46:26.406314 UTCの[DB](evidence/m2/browser/case2-cart-after_reload.json)で元の版3・空カート・0円・JS非露出を確認。続いて本人がChromeを完全終了・再起動し、ログイン／利用開始なしで「もどった」と回答。05:50:22.756 UTCの[画面・API](evidence/m2/browser/case2-browser-restart.txt)、05:50:38.616879 UTCの[DB](evidence/m2/browser/case2-cart-after_restart.json)で再読込時との完全一致を確認。[Cookie属性](evidence/m2/browser/case2-cookie-after_restart.txt)も新値一致・同じ有効認証・期限・Secure／HttpOnly・Lax・Path=/を保持した。

追加試験の実証は完了。専用トンネル・POSプロセス・MySQLを停止し、3307／8443／8444／8453の非待受・コンテナrunning=false・公開URLのHTTP 530を確認。[終了証跡](evidence/m2/browser/case2-shutdown.json)。DBボリュームと600・Git除外の私有ファイルは保持し、削除していない。本人が「片付けた」と回答し、iPhone ChromeのInspector無効化とMac／iPhoneのクリップボード上書きを完了したと報告。本人報告であり、端末設定の再検査ではない。証明書信頼設定は変更していない。商品あり・保存中の復帰、実COMMIT応答喪失・実ブラウザの遅着競合、Azure性能・運用は後続工程で未確認。
