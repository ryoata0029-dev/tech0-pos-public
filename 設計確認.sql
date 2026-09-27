-- 設計スキーマ.sql適用後の読取確認案。未実行。
-- 対象接続先・DB名・権限を確認してから、別途許可された範囲で実行する。
-- 件数ゼロはデータが空の場合にも成立する。これだけで試験合格にしない。
SELECT DATABASE() AS target_schema, VERSION() AS mysql_version,
       @@session.time_zone AS session_timezone, @@session.sql_mode AS sql_mode;
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME;
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLLATION_NAME
FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
-- 初期投入後の成立条件。REGISTERは必ず1件。
SELECT COUNT(*) AS register_rows FROM REGISTER;
-- 有効参照の所属不整合。期待0件。認証担当者切替の可否は設計本文で別確認。
SELECT r.register_id
FROM REGISTER r
LEFT JOIN BROWSER_CONTEXT b ON b.context_id=r.active_context_id
LEFT JOIN CART c ON c.cart_id=r.current_cart_id
WHERE (r.active_context_id IS NOT NULL AND (b.context_id IS NULL OR b.register_id<>r.register_id))
   OR (r.current_cart_id IS NOT NULL AND
       (c.cart_id IS NULL OR c.register_id<>r.register_id OR
        NOT (c.context_id <=> r.active_context_id)));
-- 売上と状態の矛盾。期待0件。
SELECT c.cart_id,c.state
FROM CART c LEFT JOIN PURCHASE p ON p.cart_id=c.cart_id
WHERE (c.state IN ('SAVED','CLOSED') AND p.cart_id IS NULL)
   OR (c.state NOT IN ('SAVED','CLOSED') AND p.cart_id IS NOT NULL);
-- 明細件数・税抜小計・税込合計の不整合。期待0件。
SELECT p.cart_id
FROM PURCHASE p
LEFT JOIN (SELECT cart_id,COUNT(*) n,SUM(line_subtotal) subtotal
           FROM PURCHASE_LINE GROUP BY cart_id) l ON l.cart_id=p.cart_id
LEFT JOIN (SELECT cart_id,SUM(tax_amount) tax
           FROM PURCHASE_TAX GROUP BY cart_id) t ON t.cart_id=p.cart_id
WHERE COALESCE(l.n,0)=0 OR NOT(p.subtotal <=> l.subtotal)
   OR NOT(p.total <=> p.subtotal+t.tax);
-- 税率別集計の不足・余剰・課税小計不一致。期待0件。
SELECT l.cart_id,l.tax_rate_snapshot
FROM (SELECT cart_id,tax_rate_snapshot,SUM(line_subtotal) subtotal
      FROM PURCHASE_LINE GROUP BY cart_id,tax_rate_snapshot) l
LEFT JOIN PURCHASE_TAX t ON t.cart_id=l.cart_id AND t.tax_rate_snapshot=l.tax_rate_snapshot
WHERE t.cart_id IS NULL OR t.taxable_subtotal<>l.subtotal
UNION ALL
SELECT t.cart_id,t.tax_rate_snapshot FROM PURCHASE_TAX t
LEFT JOIN PURCHASE_LINE l ON l.cart_id=t.cart_id AND l.tax_rate_snapshot=t.tax_rate_snapshot
WHERE l.cart_id IS NULL;
-- 金額0、税率0でも税率別行を作る。ログやデータ値を外部へ出力しない。

-- 会員属性の不整合。期待0件。氏名・電話・住所等の値は出力しない。
SELECT member_id FROM MEMBER
WHERE member_id IS NULL OR CHAR_LENGTH(member_id)=0
   OR name IS NULL OR CHAR_LENGTH(name)=0
   OR phone IS NULL OR CHAR_LENGTH(phone)=0
   OR address IS NULL OR CHAR_LENGTH(address)=0
   OR gender IS NULL OR CHAR_LENGTH(gender)=0
   OR age IS NULL OR age<0;
-- 小数・型容量超過の拒否は投入前検証と隔離環境の境界試験で別確認する。
