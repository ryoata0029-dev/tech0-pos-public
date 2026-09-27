-- 設計仕様書 v0.33 / MySQL 8.4 / 初期スキーマ草案（未実行）
-- 新しい空スキーマへの適用を想定。既存DBへの適用・課金の許可ではない。
-- CREATE DATABASE / USE / GRANT / 初期データ / DROPは含めない。
-- 適用前に対象DB・MySQL版・UTC・STRICT_ALL_TABLES等の厳格モードを確認。
-- DDLは暗黙COMMITを伴う。途中失敗時は停止してSHOW CREATE TABLEで照合する。
-- 会員属性の必須方針・JSON構造・SQL外の制約は設計仕様書6.2.2を参照。

CREATE TABLE STAFF (
  staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY CHECK (CHAR_LENGTH(staff_id) BETWEEN 1 AND 32 AND NOT REGEXP_LIKE(staff_id, '[^A-Za-z0-9_-]')),
  password_hash VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- 不存在の入力IDも同一の制限を適用するためSTAFFへのFKは設けない。
CREATE TABLE AUTH_LOGIN_LIMIT (
  staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY
    CHECK (CHAR_LENGTH(staff_id) BETWEEN 1 AND 32 AND NOT REGEXP_LIKE(staff_id, '[^A-Za-z0-9_-]')),
  failure_times JSON NOT NULL CHECK (JSON_TYPE(failure_times)='ARRAY' AND JSON_LENGTH(failure_times)<=5),
  locked_until DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE MEMBER (
  member_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY CHECK (CHAR_LENGTH(member_id) BETWEEN 1 AND 32 AND NOT REGEXP_LIKE(member_id, '[^A-Za-z0-9_-]')),
  name TEXT NOT NULL CHECK (CHAR_LENGTH(name) > 0),
  phone TEXT NOT NULL CHECK (CHAR_LENGTH(phone) > 0),
  address TEXT NOT NULL CHECK (CHAR_LENGTH(address) > 0),
  gender TEXT NOT NULL CHECK (CHAR_LENGTH(gender) > 0),
  age INT UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE TAX_RATE (
  tax_rate_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  rate DECIMAL(5,4) NOT NULL CHECK (rate BETWEEN 0 AND 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE PRODUCT (
  product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL CHECK (CHAR_LENGTH(code) BETWEEN 1 AND 32 AND NOT REGEXP_LIKE(code, '[^A-Za-z0-9_-]')),
  UNIQUE (code),
  name TEXT NOT NULL,
  unit_price DECIMAL(12,0) NOT NULL CHECK (unit_price >= 0),
  tax_rate_id BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (tax_rate_id) REFERENCES TAX_RATE (tax_rate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE DISCOUNT_CONDITION (
  condition_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  product_id BIGINT UNSIGNED NOT NULL,
  valid_from DATETIME(6) NOT NULL,
  valid_to DATETIME(6) NOT NULL,
  kind VARCHAR(10) NOT NULL CHECK (kind IN ('RATE','AMOUNT')),
  rate DECIMAL(5,4) NULL,
  amount DECIMAL(12,0) NULL,
  CHECK (valid_from < valid_to),
  CHECK ((kind='RATE' AND rate IS NOT NULL AND rate BETWEEN 0 AND 1 AND amount IS NULL) OR (kind='AMOUNT' AND amount IS NOT NULL AND amount >= 0 AND rate IS NULL)),
  INDEX ix_discount_product_period (product_id,valid_from),
  FOREIGN KEY (product_id) REFERENCES PRODUCT (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE PRICE_HISTORY (
  history_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  product_id BIGINT UNSIGNED NOT NULL,
  old_price DECIMAL(12,0) NULL CHECK (old_price >= 0),
  new_price DECIMAL(12,0) NOT NULL CHECK (new_price >= 0),
  changed_at DATETIME(6) NOT NULL,
  CHECK (old_price IS NULL OR old_price <> new_price),
  INDEX ix_price_product_time (product_id,changed_at,history_id),
  FOREIGN KEY (product_id) REFERENCES PRODUCT (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE REGISTER (
  register_id TINYINT UNSIGNED NOT NULL PRIMARY KEY CHECK (register_id=1),
  start_state VARCHAR(16) NOT NULL CHECK (start_state IN ('UNSTARTED','COOKIE_PENDING','READY')),
  maintenance_hold BOOLEAN NOT NULL DEFAULT FALSE CHECK (maintenance_hold IN (0,1)),
  active_context_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  current_cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  active_session_hash BINARY(32) NULL,
  CHECK ((start_state='UNSTARTED' AND active_context_id IS NULL AND current_cart_id IS NULL) OR (start_state IN ('COOKIE_PENDING','READY') AND active_context_id IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE AUTH_SESSION (
  token_hash BINARY(32) NOT NULL PRIMARY KEY,
  staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  register_id TINYINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  revoked_at DATETIME(6) NULL,
  CHECK (created_at < expires_at),
  FOREIGN KEY (staff_id) REFERENCES STAFF (staff_id),
  FOREIGN KEY (register_id) REFERENCES REGISTER (register_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE BROWSER_CONTEXT (
  context_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  register_id TINYINT UNSIGNED NOT NULL,
  starting_staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  token_hash BINARY(32) NOT NULL UNIQUE,
  created_at DATETIME(6) NOT NULL,
  confirmed_at DATETIME(6) NULL,
  last_business_at DATETIME(6) NULL,
  manual_released_at DATETIME(6) NULL,
  invalidated_at DATETIME(6) NULL,
  FOREIGN KEY (register_id) REFERENCES REGISTER (register_id),
  FOREIGN KEY (starting_staff_id) REFERENCES STAFF (staff_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE CART (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  register_id TINYINT UNSIGNED NOT NULL,
  context_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  state VARCHAR(12) NOT NULL CHECK (state IN ('EDITING','SAVING','UNSAVED','SAVED','CLOSED')),
  version BIGINT UNSIGNED NOT NULL CHECK (version >= 1),
  member_state VARCHAR(12) NOT NULL CHECK (member_state IN ('UNSPECIFIED','PENDING','CONFIRMED','NON_MEMBER')),
  member_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  pending_member_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  active_member_operation_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  active_purchase_operation_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  purchase_prepared_version BIGINT UNSIGNED NULL CHECK (purchase_prepared_version >= 1),
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  result_closed_at DATETIME(6) NULL,
  subtotal DECIMAL(12,0) NOT NULL CHECK (subtotal >= 0),
  total DECIMAL(12,0) NOT NULL CHECK (total >= 0),
  tax_breakdown JSON NOT NULL CHECK (JSON_TYPE(tax_breakdown)='ARRAY'),
  CHECK (member_state <> 'CONFIRMED' OR member_id IS NOT NULL),
  CHECK (member_state NOT IN ('UNSPECIFIED','NON_MEMBER') OR member_id IS NULL),
  CHECK (member_state <> 'PENDING' OR (pending_member_id IS NOT NULL AND active_member_operation_id IS NOT NULL)),
  CHECK (member_state='PENDING' OR (pending_member_id IS NULL AND active_member_operation_id IS NULL)),
  CHECK (state <> 'SAVING' OR (active_purchase_operation_id IS NOT NULL AND purchase_prepared_version IS NOT NULL)),
  CHECK ((state='CLOSED' AND result_closed_at IS NOT NULL) OR (state<>'CLOSED' AND result_closed_at IS NULL)),
  FOREIGN KEY (register_id) REFERENCES REGISTER (register_id),
  FOREIGN KEY (context_id) REFERENCES BROWSER_CONTEXT (context_id),
  FOREIGN KEY (staff_id) REFERENCES STAFF (staff_id),
  FOREIGN KEY (member_id) REFERENCES MEMBER (member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE CART_LINE (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  line_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  product_id BIGINT UNSIGNED NOT NULL,
  line_no INT UNSIGNED NOT NULL CHECK (line_no >= 1),
  code_snapshot VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  name_snapshot TEXT NOT NULL,
  quantity TINYINT UNSIGNED NOT NULL CHECK (quantity BETWEEN 1 AND 99),
  unit_price_snapshot DECIMAL(12,0) NOT NULL CHECK (unit_price_snapshot >= 0),
  tax_rate_snapshot DECIMAL(5,4) NOT NULL CHECK (tax_rate_snapshot BETWEEN 0 AND 1),
  discount_candidates JSON NOT NULL CHECK (JSON_TYPE(discount_candidates)='ARRAY'),
  discount_snapshot JSON NULL,
  discount_per_unit DECIMAL(12,0) NOT NULL CHECK (discount_per_unit >= 0),
  net_unit_price DECIMAL(12,0) NOT NULL CHECK (net_unit_price >= 0),
  line_subtotal DECIMAL(12,0) NOT NULL CHECK (line_subtotal >= 0),
  conditions_fixed_at DATETIME(6) NOT NULL,
  PRIMARY KEY (cart_id,line_id),
  UNIQUE (cart_id,product_id),
  UNIQUE (cart_id,line_no),
  CHECK (discount_per_unit <= unit_price_snapshot),
  CHECK (net_unit_price=unit_price_snapshot-discount_per_unit),
  CHECK (line_subtotal=net_unit_price*quantity),
  FOREIGN KEY (cart_id) REFERENCES CART (cart_id),
  FOREIGN KEY (product_id) REFERENCES PRODUCT (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE CART_OPERATION (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  operation_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  kind VARCHAR(24) NOT NULL CHECK (kind IN ('ADD_LINE','SET_QUANTITY','DELETE_LINE','SET_MEMBER','PURCHASE','RESOLVE_PURCHASE','REOPEN','NEXT','SYNC')),
  request_version BIGINT UNSIGNED NOT NULL CHECK (request_version >= 1),
  request_payload JSON NOT NULL,
  status VARCHAR(10) NOT NULL CHECK (status IN ('PREPARED','APPLIED','REJECTED')),
  prepared_version BIGINT UNSIGNED NULL CHECK (prepared_version >= 1),
  applied_version BIGINT UNSIGNED NULL CHECK (applied_version >= 1),
  result_code VARCHAR(64) NULL,
  result_payload JSON NULL,
  next_cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  created_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  CHECK ((status='PREPARED' AND completed_at IS NULL) OR (status IN ('APPLIED','REJECTED') AND completed_at IS NOT NULL)),
  PRIMARY KEY (cart_id,operation_id),
  FOREIGN KEY (cart_id) REFERENCES CART (cart_id),
  FOREIGN KEY (next_cart_id) REFERENCES CART (cart_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE PURCHASE (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  staff_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  member_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
  purchased_at DATETIME(6) NOT NULL,
  subtotal DECIMAL(12,0) NOT NULL CHECK (subtotal >= 0),
  total DECIMAL(12,0) NOT NULL CHECK (total >= 0),
  FOREIGN KEY (cart_id) REFERENCES CART (cart_id),
  FOREIGN KEY (staff_id) REFERENCES STAFF (staff_id),
  FOREIGN KEY (member_id) REFERENCES MEMBER (member_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE PURCHASE_LINE (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  line_no INT UNSIGNED NOT NULL CHECK (line_no >= 1),
  product_id BIGINT UNSIGNED NOT NULL,
  code_snapshot VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  name_snapshot TEXT NOT NULL,
  quantity TINYINT UNSIGNED NOT NULL CHECK (quantity BETWEEN 1 AND 99),
  unit_price_snapshot DECIMAL(12,0) NOT NULL CHECK (unit_price_snapshot >= 0),
  tax_rate_snapshot DECIMAL(5,4) NOT NULL CHECK (tax_rate_snapshot BETWEEN 0 AND 1),
  discount_snapshot JSON NULL,
  discount_per_unit DECIMAL(12,0) NOT NULL CHECK (discount_per_unit >= 0),
  net_unit_price DECIMAL(12,0) NOT NULL CHECK (net_unit_price >= 0),
  line_subtotal DECIMAL(12,0) NOT NULL CHECK (line_subtotal >= 0),
  PRIMARY KEY (cart_id,line_no),
  UNIQUE (cart_id,product_id),
  CHECK (discount_per_unit <= unit_price_snapshot),
  CHECK (net_unit_price=unit_price_snapshot-discount_per_unit),
  CHECK (line_subtotal=net_unit_price*quantity),
  FOREIGN KEY (cart_id) REFERENCES PURCHASE (cart_id),
  FOREIGN KEY (product_id) REFERENCES PRODUCT (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

CREATE TABLE PURCHASE_TAX (
  cart_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  tax_rate_snapshot DECIMAL(5,4) NOT NULL CHECK (tax_rate_snapshot BETWEEN 0 AND 1),
  taxable_subtotal DECIMAL(12,0) NOT NULL CHECK (taxable_subtotal >= 0),
  tax_amount DECIMAL(12,0) NOT NULL CHECK (tax_amount >= 0),
  PRIMARY KEY (cart_id,tax_rate_snapshot),
  CHECK (tax_amount=FLOOR(taxable_subtotal*tax_rate_snapshot)),
  FOREIGN KEY (cart_id) REFERENCES PURCHASE (cart_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;

-- 相互参照の作成順を解くため、空の全テーブル作成後に追加する。
ALTER TABLE REGISTER
  ADD FOREIGN KEY (active_context_id) REFERENCES BROWSER_CONTEXT (context_id),
  ADD FOREIGN KEY (current_cart_id) REFERENCES CART (cart_id),
  ADD FOREIGN KEY (active_session_hash) REFERENCES AUTH_SESSION (token_hash);
-- FKは既定のRESTRICT。初期REGISTER=1は、承認済み初期投入工程で用意する。
