-- Manual DB-client worksheet for design 9.4, not an automated recovery script.
-- DO NOT source the whole file. Execute one selected section under a separately approved change.
-- Use UTC / READ COMMITTED. No secret values in terminal history, screenshots or exported results.
-- Every section defaults to ROLLBACK. COMMIT only after the selected branch and affected rows are reviewed.

-- A. Hold first; then stop BOTH apps and confirm no in-flight DB work.
START TRANSACTION;
SELECT register_id, start_state, maintenance_hold FROM REGISTER WHERE register_id=1 FOR UPDATE;
UPDATE REGISTER SET maintenance_hold=TRUE WHERE register_id=1;
SELECT ROW_COUNT() AS affected_register;
ROLLBACK; -- replace only for an approved hold operation; then verify hold persisted

-- B. Identify original register/context/cart/staff and immutable purchase result.
SET @context_id=NULL, @cart_id=NULL, @staff_id=NULL, @expected_version=NULL;
START TRANSACTION READ ONLY;
SELECT register_id,start_state,maintenance_hold,active_context_id,current_cart_id FROM REGISTER WHERE register_id=1;
SELECT context_id,register_id,starting_staff_id,created_at,confirmed_at,last_business_at,manual_released_at,invalidated_at
  FROM BROWSER_CONTEXT WHERE context_id=@context_id;
SELECT cart_id,context_id,staff_id,state,version,member_state,active_member_operation_id,active_purchase_operation_id,purchase_prepared_version,subtotal,total,tax_breakdown
  FROM CART WHERE cart_id=@cart_id;
SELECT operation_id,kind,request_version,status,prepared_version,applied_version,result_code,next_cart_id,completed_at
  FROM CART_OPERATION WHERE cart_id=@cart_id ORDER BY operation_id;
-- In the secured DB client inspect ALL held cart lines, purchase lines/taxes and snapshot conditions.
SELECT cart_id,staff_id,subtotal,total,purchased_at FROM PURCHASE WHERE cart_id=@cart_id;
SELECT * FROM CART_LINE WHERE cart_id=@cart_id ORDER BY line_no;
SELECT * FROM PURCHASE_LINE WHERE cart_id=@cart_id ORDER BY line_no;
SELECT * FROM PURCHASE_TAX WHERE cart_id=@cart_id ORDER BY tax_rate;
ROLLBACK;

-- C. SAVING with NO sale only. Confirm actual app shutdown and metadata first.
-- PENDING uses section D; existing sale is immutable and must NOT use C.
START TRANSACTION;
SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE;
SELECT cart_id,version FROM CART WHERE cart_id=@cart_id FOR UPDATE;
SELECT operation_id,kind,status,request_version,prepared_version FROM CART_OPERATION
  WHERE cart_id=@cart_id ORDER BY operation_id FOR UPDATE;
SET @eligible=(SELECT COUNT(*) FROM REGISTER r JOIN CART c ON c.cart_id=r.current_cart_id
  JOIN BROWSER_CONTEXT b ON b.context_id=c.context_id
  JOIN CART_OPERATION o ON o.cart_id=c.cart_id AND o.operation_id=c.active_purchase_operation_id
  WHERE r.register_id=1 AND r.maintenance_hold=TRUE AND r.active_context_id=@context_id
    AND c.cart_id=@cart_id AND c.context_id=@context_id AND c.staff_id=@staff_id
    AND b.starting_staff_id=@staff_id AND b.invalidated_at IS NULL
    AND c.version=@expected_version AND c.version<18446744073709551615
    AND c.state='SAVING' AND c.member_state<>'PENDING'
    AND o.kind='PURCHASE' AND o.status='PREPARED' AND o.prepared_version=c.version
    AND o.request_version=c.purchase_prepared_version
    AND NOT EXISTS(SELECT 1 FROM PURCHASE p WHERE p.cart_id=c.cart_id));
UPDATE CART_OPERATION o JOIN CART c ON c.cart_id=o.cart_id AND c.active_purchase_operation_id=o.operation_id
  SET o.status='REJECTED',o.result_code='PURCHASE_ATTEMPT_CLOSED',o.applied_version=NULL,o.completed_at=UTC_TIMESTAMP(6)
  WHERE @eligible=1 AND c.cart_id=@cart_id;
SELECT ROW_COUNT() AS affected_purchase_operation; -- must be 1
UPDATE CART SET version=version+1,state='UNSAVED',active_purchase_operation_id=NULL,purchase_prepared_version=NULL
  WHERE @eligible=1 AND cart_id=@cart_id AND version=@expected_version;
SELECT ROW_COUNT() AS affected_cart; -- must be 1
ROLLBACK;

-- D. EDITING + PENDING: keep member flags, pending ID and old reference amounts.
START TRANSACTION;
SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE;
SELECT cart_id,version FROM CART WHERE cart_id=@cart_id FOR UPDATE;
SELECT operation_id,kind,status,prepared_version FROM CART_OPERATION WHERE cart_id=@cart_id ORDER BY operation_id FOR UPDATE;
SET @eligible=(SELECT COUNT(*) FROM REGISTER r JOIN CART c ON c.cart_id=r.current_cart_id
  JOIN BROWSER_CONTEXT b ON b.context_id=c.context_id
  JOIN CART_OPERATION o ON o.cart_id=c.cart_id AND o.operation_id=c.active_member_operation_id
  WHERE r.register_id=1 AND r.maintenance_hold=TRUE AND r.active_context_id=@context_id
    AND c.cart_id=@cart_id AND c.context_id=@context_id AND c.staff_id=@staff_id
    AND b.starting_staff_id=@staff_id AND b.invalidated_at IS NULL
    AND c.version=@expected_version AND c.version<18446744073709551615
    AND c.state='EDITING' AND c.member_state='PENDING' AND c.active_purchase_operation_id IS NULL
    AND o.kind='SET_MEMBER' AND o.status IN ('PREPARED','REJECTED')
    AND NOT EXISTS(SELECT 1 FROM PURCHASE p WHERE p.cart_id=c.cart_id));
UPDATE CART_OPERATION o JOIN CART c ON c.cart_id=o.cart_id AND c.active_member_operation_id=o.operation_id
  SET o.status='REJECTED',o.result_code='MEMBER_LOOKUP_SUPERSEDED',o.applied_version=NULL,o.completed_at=UTC_TIMESTAMP(6)
  WHERE @eligible=1 AND c.cart_id=@cart_id AND o.status='PREPARED';
SELECT ROW_COUNT() AS ended_member_lookup; -- 1 for PREPARED, 0 for already REJECTED
UPDATE CART SET version=version+1 WHERE @eligible=1 AND cart_id=@cart_id AND version=@expected_version;
SELECT ROW_COUNT() AS affected_cart; -- must be 1
ROLLBACK;

-- E. Other consistent current states EDITING(no pending)/UNSAVED/SAVED.
-- First manually prove complete purchase equivalence for SAVED, and no purchase for other states.
SET @result_reviewed=FALSE;
START TRANSACTION;
SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE;
SELECT cart_id,version FROM CART WHERE cart_id=@cart_id FOR UPDATE;
SELECT operation_id,kind,status FROM CART_OPERATION WHERE cart_id=@cart_id ORDER BY operation_id FOR UPDATE;
UPDATE CART c JOIN REGISTER r ON r.current_cart_id=c.cart_id JOIN BROWSER_CONTEXT b ON b.context_id=c.context_id
  SET c.version=c.version+1
  WHERE @result_reviewed=TRUE AND r.register_id=1 AND r.maintenance_hold=TRUE
    AND r.active_context_id=@context_id AND c.context_id=@context_id AND c.cart_id=@cart_id
    AND c.staff_id=@staff_id AND b.starting_staff_id=@staff_id AND b.invalidated_at IS NULL
    AND c.version=@expected_version AND c.version<18446744073709551615
    AND c.member_state<>'PENDING' AND c.state IN ('EDITING','UNSAVED','SAVED')
    AND ((c.state='SAVED' AND EXISTS(SELECT 1 FROM PURCHASE p WHERE p.cart_id=c.cart_id))
      OR (c.state<>'SAVED' AND NOT EXISTS(SELECT 1 FROM PURCHASE p WHERE p.cart_id=c.cart_id)));
SELECT ROW_COUNT() AS affected_cart; -- must be 1
ROLLBACK;

-- F. Identity repair and one-time release (includes COOKIE_PENDING with no cart).
-- New random 32-byte base64url resume token is generated privately by the operator.
-- Set only its SHA256 hash here via secured DB-client parameters, never as a logged literal.
SET @new_hash=NULL, @replace_cookie=FALSE, @identity_reviewed=FALSE;
START TRANSACTION;
SELECT register_id,start_state,current_cart_id FROM REGISTER WHERE register_id=1 FOR UPDATE;
SET @identity_ok=(SELECT COUNT(*) FROM REGISTER r JOIN BROWSER_CONTEXT b ON b.context_id=r.active_context_id
  WHERE @identity_reviewed=TRUE AND r.register_id=1 AND r.maintenance_hold=TRUE
    AND b.context_id=@context_id AND b.starting_staff_id=@staff_id AND b.invalidated_at IS NULL
    AND ((r.current_cart_id=@cart_id AND EXISTS(SELECT 1 FROM CART c WHERE c.cart_id=@cart_id AND c.context_id=@context_id AND c.staff_id=@staff_id))
      OR (r.start_state='COOKIE_PENDING' AND r.current_cart_id IS NULL AND @cart_id IS NULL))
    AND (@replace_cookie=FALSE OR OCTET_LENGTH(@new_hash)=32));
UPDATE AUTH_SESSION s JOIN BROWSER_CONTEXT b ON b.starting_staff_id=s.staff_id
  SET s.revoked_at=UTC_TIMESTAMP(6) WHERE @identity_ok=1 AND b.context_id=@context_id AND s.revoked_at IS NULL;
UPDATE REGISTER SET active_session_hash=NULL WHERE @identity_ok=1 AND register_id=1;
UPDATE BROWSER_CONTEXT SET token_hash=IF(@replace_cookie=TRUE,@new_hash,token_hash),manual_released_at=UTC_TIMESTAMP(6)
  WHERE @identity_ok=1 AND context_id=@context_id;
SELECT ROW_COUNT() AS affected_context; -- must be 1
ROLLBACK;
-- Set protected Cookie in the SAME original browser only if replacement was approved.
-- Start apps WITH hold still true, reauthenticate original staff, verify GET/cart/member/result.
-- If local purchase markers survive manual fence, obtain an API resolve receipt after hold release;
-- never remove markers based only on GET NOT_FOUND/NOT_REQUESTED or the current version.

-- G. Release only after the human verifies all conditions and minimal privileges are revoked.
SET @release_reviewed=FALSE;
START TRANSACTION;
SELECT register_id FROM REGISTER WHERE register_id=1 FOR UPDATE;
UPDATE REGISTER r JOIN BROWSER_CONTEXT b ON b.context_id=r.active_context_id
  SET r.maintenance_hold=FALSE WHERE @release_reviewed=TRUE AND r.register_id=1
    AND r.active_context_id=@context_id AND b.starting_staff_id=@staff_id AND b.invalidated_at IS NULL
    AND b.manual_released_at IS NOT NULL AND b.manual_released_at>UTC_TIMESTAMP(6)-INTERVAL 24 HOUR;
SELECT ROW_COUNT() AS affected_register;
ROLLBACK;
-- Failure: ROLLBACK uncommitted branch, keep hold; never restore invalidated old authentication.
