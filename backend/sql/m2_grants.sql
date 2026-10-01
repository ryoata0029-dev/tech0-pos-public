-- M2新規隔離DB専用。対象・アカウント作成とTLSを確認してから適用。
-- ユーザー作成・秘密値・DROP・GRANT ALLは含めない。
-- pos_app / pos_master / pos_schema は新規専用アカウント。%は隔離コンテナ内。
-- ホスト公開は127.0.0.1:3307だけ。Azureへそのまま転用しない。
GRANT SELECT ON `pos_validation`.`STAFF` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`AUTH_LOGIN_LIMIT` TO 'pos_app'@'%';
GRANT SELECT ON `pos_validation`.`MEMBER` TO 'pos_app'@'%';
GRANT SELECT ON `pos_validation`.`TAX_RATE` TO 'pos_app'@'%';
GRANT SELECT ON `pos_validation`.`PRODUCT` TO 'pos_app'@'%';
GRANT SELECT ON `pos_validation`.`DISCOUNT_CONDITION` TO 'pos_app'@'%';
GRANT SELECT ON `pos_validation`.`PRICE_HISTORY` TO 'pos_app'@'%';
GRANT SELECT, UPDATE ON `pos_validation`.`REGISTER` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`AUTH_SESSION` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`BROWSER_CONTEXT` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`CART` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON `pos_validation`.`CART_LINE` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`CART_OPERATION` TO 'pos_app'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`PURCHASE` TO 'pos_app'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`PURCHASE_LINE` TO 'pos_app'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`PURCHASE_TAX` TO 'pos_app'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`MEMBER` TO 'pos_master'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`TAX_RATE` TO 'pos_master'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`PRODUCT` TO 'pos_master'@'%';
GRANT SELECT, INSERT, UPDATE ON `pos_validation`.`DISCOUNT_CONDITION` TO 'pos_master'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`PRICE_HISTORY` TO 'pos_master'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`REGISTER` TO 'pos_master'@'%';
GRANT SELECT, INSERT ON `pos_validation`.`STAFF` TO 'pos_master'@'%';
GRANT SELECT ON `pos_validation`.`PURCHASE` TO 'pos_master'@'%';
GRANT SELECT ON `pos_validation`.`PURCHASE_LINE` TO 'pos_master'@'%';
GRANT SELECT ON `pos_validation`.`PURCHASE_TAX` TO 'pos_master'@'%';
GRANT SELECT, CREATE, ALTER, INDEX, REFERENCES ON `pos_validation`.* TO 'pos_schema'@'%';
SHOW GRANTS FOR 'pos_app'@'%';
SHOW GRANTS FOR 'pos_master'@'%';
SHOW GRANTS FOR 'pos_schema'@'%';
