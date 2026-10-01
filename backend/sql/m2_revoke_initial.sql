-- 初期投入照合後だけ実行。初回専用追加権限を外す。
REVOKE SELECT, INSERT ON `pos_validation`.`REGISTER` FROM 'pos_master'@'%';
REVOKE SELECT, INSERT ON `pos_validation`.`STAFF` FROM 'pos_master'@'%';
SHOW GRANTS FOR 'pos_master'@'%';
