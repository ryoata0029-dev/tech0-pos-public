# POSバックエンド：M2作業版

採用系列はPython 3.13。M1計算に加え、M2の認証・初回開始API・MySQL接続／TX基盤を実装した。実DB接続とHTTPS中継の初回フローを検証済み。Chrome実機条件は未確認。導入・検査・起動は[開発環境](../docs/implementation/開発環境.md)、最新状況は[M2実装記録](../docs/implementation/M2_実装記録.md)を参照。

リポジトリの`backend/`を作業ディレクトリとして実行する。

```sh
python3.13 --version
python3.13 -m unittest discover -s tests -v
python3.13 -m compileall -q app tests
```

`app/services/validation.py`はコード・数量・円額・率・内部ID・期間の境界を検証する。APIの円額／率は十進文字列、計算内部は整数円／整数の0.01％単位を使う。日時はタイムゾーン付き`datetime`を受け、UTCへ変換する。HTTP日時文字列の解析・レスポンス直列化はAPI層で今後実装する。

`app/services/pricing.py`はサーバーが取得した商品行の保持条件を受け、値引き・税率別税・合計を計算する。最新マスタを参照せず、入力を変更しない。HTTPの入力をそのまま保持条件へ変換して信用してはならない。保持条件の取得・永続化・原子的更新はM2〜M4で実装する。

編集中の空カートは合計0円を表示できる。購入時は`require_purchasable`で空を拒否する。APIでの409／STATE_CONFLICT対応、会員確認待ちと購入状態の確認は今後の呼出側の責務。確認失敗を`is_member=False`として購入に進めてはならない。

## 後続工程

- M2の残りはChrome実機のCookie条件・独立レビュー等。実DB結果は[実DB検証記録](../docs/implementation/M2_実DB検証記録.md)を参照。
- 秘密値なし設定例は`.env.example`。検証DB・HTTPSの対象案と実行条件は開発環境の文書を参照。
- Linux／Azureの提供ランタイム、環境条件付き依存、接続・実機の適合は後続で確認する。

旧`.local-validation/`・`validation/.venv/`や既存DBは使用していない。新しい試験データは`tests/`と`fixtures/`の架空値。後続の本人許可により新規隔離DBへ投入して検証し、停止・保持した。端末の証明書信頼設定は残していない。

詳細な対象・結果・未確認範囲は[実装記録](../docs/implementation/M1_実装記録.md)を参照。
