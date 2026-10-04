# Mac継続会員遅延：実機検証結果

2026-10-04。主担当が実DB・Mac Chromeを操作し、担当Cが保存証跡を独立読取・照合する。**L1／L2のサーバー遅着不反映と通常UI再確認は下記範囲で成立。旧HTTP応答のChrome到達とTC-03全体の合格は未確認。**

対象は[TC-03](../tests/テストケース.md#tc-03)、[会員と待ちの受入](../requirements/受入条件_現行.md#r-topic-23)、[設計4.2](../design/画面と業務処理.md#sec-4-2)。実行条件は[作業票](Mac_継続残試験作業票.md)、全体の境界は[継続実行票](並行継続_実行票.md)による。

## 1. 実行対象・版・環境成立

Macは新規 `parallel-mac-next`／`tech0-pos-parallel-mac-next-mysql`／専用volume末尾 `-data`、MySQL3317・Next HTTPS8453・FastAPI HTTPS8454、架空3商品・会員のみ。Macで正規STAFF_A login→初回startし、phoneのDB・Cookie・取引を引き継がない。phone `parallel-next` の3307／8443／8444と、phone側API検証schema `pos_api_validation` は別対象として扱う。

[MySQL環境](evidence/parallel-mac-next/mysql-environment.json)は専用container ID `a11229d446c24e9cbc21c5e2ca06e2b58518b82eaaef9d1363deaa1f693c7a33`、loopback3317→3306、専用volume、TLS必須を記録。[初期DB](evidence/parallel-mac-next/mysql-snapshot.json)はMySQL8.4.11、TLS暗号接続、general／slow log無効、商品3・会員2・担当者2・カート／売上0を記録する。

[runtime](evidence/parallel-mac-next/runtime-start.json)はbuild `5_wgTZOtPLE3as7vfiFAN`、アプリ／harness hashと固定portsを記録する。アプリは[前回の197件検査・build](evidence/mac-parallel/runtime-pattern-fix.json)の成果物を使用し、今回のharness変更をアプリの新しい実装試験合格へ読み替えない。harnessの変更にはbackend設定のRuff check／format、Node構文、17profileのoffline mappingとmock guard検査を実施し、旧16profileの3307／8443／8444が維持されることを確認した。これらはDB／サーバーを実起動しない検査である。

[Mac観測端末情報](evidence/parallel-next/mac-observer-version.json)はmacOS27.0／Chrome154.0.8037.97。iPhoneの機種／OS／Chrome版をこの情報で代用しない。

[起動後の両環境証跡](evidence/parallel-next/environments-after-mac-setup.json)で別container・6ポートの受付・別backend TLS・Mac専用Next起動引数・別tunnel PID／originを確認した。記録時のBUILD_IDとmanifest hashは共通成果物のディスク値であり、各実プロセスのメモリ版を直接取得した値ではない。runtimeの版固定と併せて扱う。[読取環境script](../../tools/parallel_environment_verify.py)のDocker／process／port観測はrootが実行し、担当Cは結果だけを読んだ。

[独立環境照合](evidence/parallel-mac-next/comparison-environment-readonly.json)は保存済み証跡と現行source／buildファイルの17項目が一致したことを記録する。対象2container、6個の別PID、各専用port／TLS、別origin、source hashとディスクbuild／manifestを照合し、DB／process／portを再実行していない。

起動前のsocket観測はsandbox内で成立せずassert失敗し、原本を作成できなかった。アプリの業務不合格を示す結果ではない。起動後証跡とphone DBの前後照合を用いるが、取得していない起動前ポート／process観測を補完しない。

[phone DB前後・両環境の独立照合](evidence/parallel-mac-next/comparison-phone-noninterference.json)では、phoneの採取9集合はMac試験後も不変でUNSTARTED／カート0／売上0。[Mac起動後](evidence/parallel-next/environments-after-mac-setup.json)から[Mac業務試験後](evidence/parallel-next/environments-after-mac-flows.json)の2観測で両container／各process PID・command／tunnel PID／origin／6ポートとディスクbuild／manifestが同一だった。phoneの実機業務・カメラ合格を示す観測ではない。全認証テーブルを含む全DB状態の不変とも表現しない。

## 2. 業務試験の照合

商品0001／0002／0003、数量3／1／1なら、非会員は小計523・税47・税込570円、確認済み会員は小計493・税44・税込537円。通常POSから旧MEMBER_1を指定し、実受付COMMIT→実会員lookup完了・接続終了→反映TX前の私有gateで保留する。別タブの同一origin検証panelから正規APIで新しい会員選択を確定し、旧照会を解放する。panelはCookieを読取・移植せず、正規resumeの同cart／現版と新操作IDを使う。

| 条件 | 期待値 | 判定 |
|---|---|---|
| L1：旧MEMBER_1→新MEMBER_0 | 新MEMBER_0／CONFIRMED／537円、旧操作REJECTED／MEMBER_LOOKUP_SUPERSEDED、新操作APPLIED。旧finish前後の9DB集合不変 | 下記限定範囲で成立、独立29項目一致 |
| L2：旧MEMBER_1→非会員 | NON_MEMBER／member_id=null／570円、旧操作REJECTED／MEMBER_LOOKUP_SUPERSEDED、新操作APPLIED。旧finish前後の9DB集合不変 | 下記限定範囲で成立、独立29項目一致 |

両条件の全段階で同一cart・同じ3行ID／数量／単価／税／条件固定時刻を保持し、売上を増やさなかった。新会員選択による金額・値引き変更と、旧finishが変更してはいけない値を分けた。再確認後SYNCの版増分は旧finishに帰属させない。

L1の開始は[版6の初期DB](evidence/parallel-mac-next/db-mac-l1-before.json)で `UNSPECIFIED`、画面は「未指定の非会員」だった。作業票の明示 `NON_MEMBER` 開始とは区別し、今回成立したのは未指定非会員→旧MEMBER_1→新MEMBER_0である。旧受付で版7／PENDING／PREPARED、新MEMBER_0の正規panel PUTが200／APPLIEDで版9／CONFIRMEDを確定した。実lookup完了後の保持は55.891605秒。旧finishはREJECTED／MEMBER_LOOKUP_SUPERSEDEDを返し、[解放前](evidence/parallel-mac-next/db-mac-l1-new-before-release.json)と[旧完了後](evidence/parallel-mac-next/db-mac-l1-after-old-finish.json)の9集合は同一、版9／MEMBER_0／537円を維持した。

[通常UIの状態再確認後](evidence/parallel-mac-next/mac-l1-reconciled-dom.txt)はMEMBER_0／537円・会員選択／商品入力／購入有効を表示した。未送信の変更先欄MEMBER_1は残るが、確定会員表示とは別の入力欄であり、自動適用されていない。[再確認後DB](evidence/parallel-mac-next/db-mac-l1-reconciled.json)の版10は別SYNCの1増分で、旧finishの版変更ではない。売上0・同一cart／3行の保持条件と独立整数計算の493＋17＋27＝537円を照合した。[独立L1比較](evidence/parallel-mac-next/comparison-member-l1.json)に29項目・全参照原本・判定限界を記録する。

L2は[開始DB](evidence/parallel-mac-next/db-mac-l2-before.json)の版10／確認済みMEMBER_0／537円から、旧MEMBER_1受付で版11／PENDINGへ進んだ。保持中の旧MEMBER_0・537円は参考額と表示し、会員／商品／購入を停止した。検証panelの非会員選択が200／APPLIEDで版12／NON_MEMBER／570円を確定し、102.008728秒保留した旧lookupを解放した。旧finishはREJECTED／MEMBER_LOOKUP_SUPERSEDED、[解放前](evidence/parallel-mac-next/db-mac-l2-new-before-release.json)と[旧完了後](evidence/parallel-mac-next/db-mac-l2-after-old-finish.json)の9集合・版12・非会員状態は不変だった。

[通常UI再確認後DOM](evidence/parallel-mac-next/mac-l2-reconciled-dom.txt)と[画像](evidence/parallel-mac-next/mac-l2-reconciled.png)では570円・値引き0・購入有効を確認した。画面の既存会員文言は「未指定の非会員」であり、非会員を明示選択した事実はpanelの200／APPLIEDとDB `NON_MEMBER` による。[再確認後DB](evidence/parallel-mac-next/db-mac-l2-reconciled.json)は別SYNCで版13、同じ1cart／3行・売上0。独立整数計算の523＋17＋30＝570円と、旧MEMBER_1が未適用であることを[独立L2比較](evidence/parallel-mac-next/comparison-member-l2.json)の29項目で照合した。

サービス内部の旧OperationResultがREJECTEDでも、API応答の期待値は409／MEMBER_LOOKUP_SUPERSEDEDである。gate／lookup-finishedの保存だけではChromeの生HTTP受信を証明しない。中継10秒を超えた条件はサーバー遅着の不反映だけを判定し、旧409のChrome到達は未確認とする。通常POSの状態再確認で最新値を表示した証拠と、生HTTP到達を分ける。

9集合は[DB採取](../../tools/mac_flow_db.py)のregister／contexts／carts／lines／operations／purchases／purchase_lines／purchase_taxes／productsの公開列射影である。全DBテーブル／列、認証秘密状態、未出力の値引き候補JSON全体までの読取一致とは表現しない。

## 3. 未確認と終了

業務試験は完了し、両保留のlookup-finishedが終了前にREJECTED／MEMBER_LOOKUP_SUPERSEDEDで保存されたことを照合した。最終採取DBは版13／NON_MEMBER／570円・同じ1cart／3行・売上0。[終了原本](evidence/parallel-mac-next/shutdown-final.json)は専用profile／container、3317／8453／8454閉鎖、container exited、専用volume保持、Git候補と専用ログへのsecret値非混入を記録する。[独立終了照合](evidence/parallel-mac-next/comparison-shutdown-readonly.json)は原本と初期対象・両旧処理完了・L1／L2結果の7項目一致を確認した。担当CはDB／GUI／socket／Docker／secret scanを再実行していない。

主担当は今回のMac所有2タブを通常CUAで閉じた。Chrome全体の終了試験ではない。phoneの3307／8443／8444と別containerは今回のMac停止対象に含めず、本人の実機試験開始を待つ現行待機環境として主担当が管理する。phone実機は未実施であり、Mac停止原本でphoneの終了／実機合格まで証明しない。

変更は固定profile／port分離harness、作業票、本結果票と独立比較JSONに限り、アプリ・依存・buildの変更を行っていない。戻す場合は今回の固定profile／port分離差分のみを対象とし、保持した専用DB volume・証跡・以前の未コミット変更は削除しない。文書リンク・ID検査と差分空白検査は、業務の成立性検査と別に実施した。

本票だけではTC-03全体、通常別POSの新会員入力、旧HTTPの実到達、Chrome完全終了／状態別再認証、storage異常、iPhone／カメラ、Azure、本番、M7本人受入を合格としない。並行稼働中はbuildとChrome全体を停止・変更しない。
