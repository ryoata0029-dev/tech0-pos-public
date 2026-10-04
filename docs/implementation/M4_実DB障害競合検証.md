# M4：実DBの障害・競合検証

2026-10-01（日本時間）。本人の「次いこう」と「新規M4隔離環境で障害・競合テストを実施する」に基づく。現在の作業版。**14条件群成功、独立レビュー指摘解消。M4全体の受入・両端末確認は未了。**

対象：保存・復帰・版・再送・会員確認待ち、T02、業務手順2〜6、[受入：保存失敗・復帰・複数タブ](../requirements/受入条件_現行.md#r-topic-32)、[設計5章](../design/通信とデータ.md#sec-5)・[7章](../design/保存処理.md#sec-7)、TC-12・16〜20・24の下記条件。[COMMIT応答喪失と競合の詳細](../tests/API・DB詳細.md#tc16-fault)に従い、条件単位で判定する。全TCの合格数ではない。

## 実行環境と変更範囲

新規コンテナ `tech0-pos-m4-mysql`、volume `tech0-pos-m4-mysql-data`、DB `pos_validation`。MySQL8.4.11、loopback3307、TLS必須・証明書／ホスト名検証。現行DDL16表、架空担当者・会員・3商品、最小権限を投入。[環境](evidence/m4/mysql-environment.json)・[検査後の件数と権限](evidence/m4/mysql-snapshot.json)。MySQL8.4の既存固定イメージを使用し、新しい依存は導入していない。

共通準備器へ固定m4プロファイルを追加し、PythonとNodeの両起動器を別保存先へ対応させた。秘密値／localhost証明書／試験クライアントCookieはGit除外 `.m4-local/` へ保存。システムの証明書信頼設定・M2／M3環境・Azureは変更しない。

検証器は `tools/m4_verify_https.py`。既定は接続しない計画表示。`--run` はm4プロファイル・未開始／カート0件だけを認め、既存証跡があればDB接続前に拒否する。`--run --supplement` は完走済み記録・同じ試験クライアント・次の空カートを確認した場合だけ追加検査する。途中失敗を自動再送・DB初期化で回避しない。

## 障害注入と証拠の意味

HTTPSケースはNext.js→FastAPI→実MySQLを通す。故障位置を制御するケースは、同じFastAPI・実リポジトリ・実MySQLへASGI要求を送り、検証プロセス内だけでドライバー／SQL実行イベントを局所変更する。メモリDB・成功応答の差替え・確定結果の注入は使わない。

COMMIT応答喪失は、実MySQLへCOMMITを送信した後、成功ACKを読む直前に止める。別の新規TLS接続でSAVING/PREPAREDまたはSAVED/APPLIEDを確認し、書込接続と照合接続のIDが異なることを検査してから物理ソケットを切断する。アプリはOperationalErrorを受け503となる。受付はCOMMIT送信1回・売上INSERT0回、売上確定後はCOMMIT送信2回・売上INSERT1回を確認し、接続invalidateと売上TXの自動再実行なしを検査した。OSやネットワーク装置のパケット遮断試験ではない。

明細INSERT完了後／最初の税INSERT完了後の障害では、実TXのROLLBACKと接続破棄を通し、別接続で売上・明細・税がすべて0、受付SAVINGは保持することを検査した。照合もDB例外で不能にすると503のままで、新しい売上は作られない。復旧後、同じ購入要求の明示再送だけで保存へ進み、保存済みなら同じ日時・金額・結果を返す。

## 条件別結果

初回13項目＋補強3項目の計16実行が成功。会員PREPARED／REJECTEDの2項目は追加の版・操作記録検査付きで再実行したため、固有条件群は14。[全結果](evidence/m4/fault-races.json)・[初回ログ](evidence/m4/live.log)・[補強ログ](evidence/m4/supplement.log)。

| 条件群 | 結果・判定した内容 |
|---|---|
| TC-19 更新応答を破棄・同一再送／sync先行 | 応答をクライアントで破棄して同じID・版・商品を再送しても1個。syncを先に確定させた旧版追加は409。実ネットワーク遮断と区別する |
| TC-18 同版の数量更新2要求 | バリアで同時送信し200／409が各1件。DBの最新内容が勝者の数量・版と一致し上書きなし |
| TC-18 同時購入2要求 | 同版・別IDで同時送信し売上は1件。先行処理を後続が上書きしない。確定順そのものの固定はしない |
| TC-24 next応答を破棄 | 同一再送・操作GET・resumeが同じ次カートへ収束。操作GETは旧CLOSED対象、resumeは継続先 |
| TC-16 受付COMMIT ACK未読 | SAVING/PREPARED・売上0。アプリ503・invalidate・売上自動実行なし。GETはUNKNOWN。明示再送で売上1・明細3・税2へ収束 |
| TC-16 売上COMMIT ACK未読 | SAVED/APPLIED・売上1・明細3・税2。アプリ503・invalidate。別接続GETと明示再送で同じ保存結果、不変の購入日時／金額 |
| TC-16 明細書込完了直後の中断 | 売上・明細・税0へ一括ROLLBACK、受付SAVING保持、同じ購入の明示再送で保存 |
| TC-16 第1税書込完了直後の中断 | 上と同じ。税集計の部分保存なし |
| TC-17 resolve先行・UNSAVED再resolve・reopen／保存先行 | 最初の遅着購入とUNSAVED後の遅着再試行を旧版で409拒否、売上0。同一resolve再送は同じ結果。明示reopenは行条件・会員保持、数量編集後の435円だけ保存。保存先行なら旧版resolveも既存結果を返しreopen拒否 |
| TC-18/20 会員PREPARED＋購入遅着 | resolveでPENDING・参考額保持、1増版・同じapplied_version、NOT_REQUESTED/null。旧会員をREJECTED/MEMBER_LOOKUP_SUPERSEDEDへ終了、active_member_operation_id保持。旧購入・遅着会員結果・商品編集は拒否。業務起算・Cookie更新なし |
| TC-18/20 会員不存在REJECTED＋購入遅着 | 同じPENDING保持に加え、元の拒否理由・完了時刻不変。新しい非会員選択後だけ購入へ進む |
| TC-17 実ロックタイムアウト | 別接続でREGISTERをFOR UPDATE保持し、設定済み1秒タイムアウトでresolveは503。版・状態・売上件数・操作記録は不変。ロック解除後の同一resolve再送で確定 |
| TC-12 実照会のスナップショット | アプリがカートを読んだ後で停止し、別プロセスの正規HTTPS数量更新を確定してから後続明細SELECTを再開。照会は旧v7・537円の一式、次GETは新v8・435円。変更前後を混ぜない |
| TC-17 SAVING受付後のresolve | 受付ACK喪失後、同一resolve再送も含めUNSAVEDを確定。旧購入をREJECTED/PURCHASE_ATTEMPT_CLOSEDにし遅着保存を拒否、売上0。明示reopen→新しい購入だけ537円で保存 |

## 独立レビュー・その他の検査

独立レビューで検証器のP2「誤ったfresh再実行で完成証跡を上書きする」を検出し修正。DB接続前に再実行を拒否することと、既存結果SHA256の不変を実証した。[証跡保持検査](evidence/m4/evidence-guard.json)。補強後の再レビューで追加の確実な不具合なし。アプリ機能の新たな不具合は今回の検査範囲で見つからなかった。

`make check` 成功（Python71件・Node38件、Ruff・mypy・ESLint・TypeScript、OpenAPI22操作）。[ログ](evidence/m4/check.log)。新規終了検査器のRuff lint/format、HTTPS起動器のNode構文、文書全リンク、`git diff --check`も成功。アプリコード・依存を変更していないため、M5修正後の成功buildを引き継ぎ、今回buildは再実行していない。

初回COMMIT注入で既に閉じたドライバー接続をpoolが再度閉じる例外traceが検証ログに出た。補強実行では物理ソケット切断後の通常closeを可能にする注入へ修正し、同じACK未読・503・invalidateを確認した。初回も判定は成功、秘密値の出力なし。これは局所注入の後処理で、アプリに新しいログ出力を追加していない。

## 終了状態と残る検証

HTTPS8443/8444とMySQL3307を停止し、全ポート非待受・コンテナexited・volume保持を確認。新規 `tools/m4_verify_shutdown.py` で生成秘密値とCookieがGit候補・アプリログ・検証出力へ混入していないことを確認した。[終了記録](evidence/m4/shutdown.json)。DBは売上13件、CART14件（最後の空カートを含む）を保持。Docker Desktopは稼働したまま。

未確認：実ブラウザの通信断表示・UNKNOWN中の操作停止、localStorageとの統合、2タブ警告・通知欠落、全状態で再読込とChrome完全終了／再起動、取引中の再認証・Cookie切替・期限、両端末の撮影と表示、Azure性能／復元。GET・購入照会以外の全複数SELECT経路の一貫性、全中断位置・全順序／全境界も今回の14群だけで合格にしない。HTTP応答破棄やASGI局所障害を実ブラウザ遮断の証拠へ読み替えない。

今回の変更ファイル：`.gitignore`、`tools/m2_local_profile.py`、`tools/m2_https.mjs`、新規 `tools/m4_verify_https.py`・`tools/m4_verify_shutdown.py`、本記録・証跡。既存M5修正／M3結果を保持。要件・設計・本番API・DDLの変更、撮影、公開、Azure、commit、pushは行っていない。戻す場合はM4検証器・profile差分だけをレビューし、保存済み売上・volume・既存成果物を削除しない。
