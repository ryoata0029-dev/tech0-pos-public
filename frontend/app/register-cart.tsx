'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, allPurchases, CartResult, clearSaved, newer, Operation, purchaseKeys, rememberPurchase, requireStable } from '../lib/pos';

import { Recovery } from '../lib/recovery';
import Camera, { type ScanOutcome } from './camera';
import { measure } from '../lib/measurements';

type Pending = { path: string; method: string; body?: Record<string, unknown>; operationId: string; purchase: boolean; next: boolean; measured?: () => void };
type Product = { code: string; name: string; unit_price: string };

export default function RegisterCart({ initial, enabled, onNext, onAuthentication }: {
  initial: CartResult; enabled: boolean; onNext: (value: CartResult) => void; onAuthentication: () => void;
}) {
  const [value, setValue] = useState(initial);
  const [phase, setPhase] = useState<'checking' | 'ready' | 'uncertain'>('checking');
  const [message, setMessage] = useState('カートの状態を同期しています。');
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [code, setCode] = useState('');
  const [product, setProduct] = useState<Product | null>(null);
  const [member, setMember] = useState('');
  const [memberUnconfirmed, setMemberUnconfirmed] = useState(false);
  const [selected, setSelected] = useState('');
  const [camera, setCamera] = useState<'product' | 'member' | null>(null);
  const closeCamera = useCallback(() => setCamera(null), []);
  const [quantity, setQuantity] = useState('1');
  const current = useRef(value);
  const inputCode = useRef(code);
  const inputGeneration = useRef(0);
  const pending = useRef<Pending | null>(null);
  const inflight = useRef(false);
  const initialized = useRef(false);
  const active = useRef(true);
  const enabledNow = useRef(enabled);
  enabledNow.current = enabled;
  const recovery = useRef(new Recovery());
  const notified = useRef(0);
  const channel = useRef<BroadcastChannel | null>(null);

  function accept(next: CartResult) {
    current.current = newer(current.current, next);
    setValue(current.current);
  }

  const initialize = useCallback(async () => {
    if (inflight.current || !enabled) return;
    inflight.current = true; setBusy(true); setPhase('checking');
    const beforeNotifications = notified.current;
    try {
      const next = await recovery.current.reconcile(localStorage);
      if (next.cart.cart_id !== initial.cart.cart_id) { onNext(next); return; }
      if (notified.current !== beforeNotifications) throw new Error('別タブの操作を検知しました。状態を再確認してください。');
      pending.current = null;
      if (active.current) { accept(next); setMemberUnconfirmed(false); setPhase('ready'); setMessage('カートの状態を確認しました。'); }
    } catch (error) {
      if (active.current) {
        setPhase('uncertain'); setMessage(error instanceof Error ? error.message : '状態を確認できません。');
        if (error instanceof ApiError && error.status === 401) { initialized.current = false; onAuthentication(); }
      }
    }
    finally { inflight.current = false; setBusy(false); }
  }, [initial.cart.cart_id, onNext, onAuthentication, enabled]);

  useEffect(() => {
    active.current = true;
    if (enabled && !initialized.current) { initialized.current = true; void initialize(); }
    if (!enabled) initialized.current = false;
    return () => { active.current = false; };
  }, [enabled, initialize]);

  useEffect(() => {
    const invalidate = () => {
      notified.current++; initialized.current = false; setPhase('uncertain'); setMessage('別タブの操作を検知しました。状態を再確認してください。');
      void api<CartResult>('resume').then(state => { if (active.current) { if (state.cart.cart_id === initial.cart.cart_id) accept(state); else onNext(state); } }).catch(error => { if (error instanceof ApiError && error.status === 401) onAuthentication(); });
    };
    const storageChanged = (event: StorageEvent) => { if (event.key === null || event.key.startsWith('pos-purchase:')) invalidate(); };
    window.addEventListener('storage', storageChanged);
    try {
      channel.current = new BroadcastChannel('pos-cart-updates');
      channel.current.onmessage = invalidate;
    } catch { setMessage('タブ間通知を利用できません。別タブを閉じて状態を確認してください。'); }
    return () => { window.removeEventListener('storage', storageChanged); channel.current?.close(); channel.current = null; };
  }, [initial.cart.cart_id, onNext, onAuthentication]);

  function safeToAct() {
    try {
      if (allPurchases(localStorage).length) throw new Error('保存結果の確認が必要です。');
      return true;
    } catch (error) { setPhase('uncertain'); setMessage(error instanceof Error ? error.message : '購入記録を確認できません。'); return false; }
  }

  const cart = value.cart;
  const editing = enabled && phase === 'ready' && !busy && cart.state === 'EDITING';
  const canEdit = editing && cart.member_state !== 'PENDING';
  // Only the local code field stays editable during a read-only product lookup.
  const canEnterCode = enabled && phase === 'ready' && cart.state === 'EDITING'
    && cart.member_state !== 'PENDING' && (!busy || searching);
  const selection = cart.lines.find(line => line.line_id === selected);

  async function send(request: Pending, reportScan?: (outcome: ScanOutcome) => void) {
    if (inflight.current || !enabled) return false;
    inflight.current = true; setBusy(true); pending.current = request;
    const changingMember = request.path === `carts/${cart.cart_id}/member`;
    if (changingMember) { setMemberUnconfirmed(true); setMessage('会員指定の結果を確認しています。'); }
    if (request.purchase) setMessage('保存結果を確認しています。');
    const beforeNotifications = notified.current;
    try {
      const result = await api<Operation>(request.path, request.method, request.body);
      if (result.operation_id !== request.operationId) throw new Error('操作の対応を確認できません。');
      if (changingMember && result.cart.cart_id !== cart.cart_id) throw new Error('会員確認の対象を確認できません。');
      if (request.next) {
        if (result.operation_status !== 'APPLIED' || result.new_cart_id !== result.cart.cart_id) throw new Error('次取引の対応を確認できません。');
        // Always obtain the actual current cart; an old NEXT response cannot move backwards.
        onNext(await api<CartResult>('resume')); return true;
      }
      accept(result);
      channel.current?.postMessage('changed');
      if (request.purchase) clearSaved(localStorage,result);
      requireStable(localStorage,current.current,beforeNotifications,notified.current);
      if (result.operation_status === 'PREPARED' && request.path.endsWith('/member')
        && result.cart.state === 'EDITING' && result.cart.member_state === 'PENDING') {
        setMemberUnconfirmed(false); pending.current = null; setPhase('ready'); setMessage('会員確認待ちです。再照会または非会員を選択してください。'); return false;
      }
      if (result.operation_status !== 'APPLIED') throw new Error('操作結果を確認できません。');
      if (changingMember) setMemberUnconfirmed(false);
      pending.current = null; setPhase('ready');
      if (request.purchase ? result.purchase_status === 'SAVED' : ['CONFIRMED','NON_MEMBER'].includes(result.cart.member_state)) request.measured?.();
      if (request.path.endsWith('/lines')) {
        const added = result.cart.lines.find(line => line.code === request.body?.code);
        setMessage(added ? `${added.name}を1個追加（現在${added.quantity}個）。${product && product.unit_price !== added.unit_price ? '購入リストの登録時価格を適用しました。' : ''}` : '商品を追加しました。');
        setCode(''); inputCode.current = ''; setProduct(null);
      } else setMessage(request.purchase ? '購入完了。保存済み結果を確認しました。' : '変更を反映しました。');
      reportScan?.({ kind: 'confirmed' });
      return true;
    } catch (error) {
      // A definite product rejection may keep filming while busy/inflight and
      // ScanGate block further reads until GET verifies the current restrictions.
      const keepCamera = camera === 'product' && request.method === 'POST'
        && request.path === `carts/${cart.cart_id}/lines` && !request.purchase && !request.next
        && error instanceof ApiError && ((error.code === 'PRODUCT_NOT_FOUND' && error.status === 404)
          || (error.code === 'QUANTITY_LIMIT' && error.status === 422));
      if (!keepCamera) setPhase('uncertain');
      setMessage(error instanceof Error ? error.message : '結果を確認できません。');
      if (error instanceof ApiError && error.status === 401) { initialized.current = false; onAuthentication(); }
      if (error instanceof ApiError && ['MAINTENANCE_HOLD', 'VERSION_LIMIT', 'OPERATION_MISMATCH', 'RESUME_EXPIRED', 'FORBIDDEN'].includes(error.code)) pending.current = null;
      // Explicit business errors can be reconciled, but HTTP status alone never proves unsaved.
      if (error instanceof ApiError && ['INVALID_INPUT', 'QUANTITY_LIMIT', 'PRODUCT_NOT_FOUND', 'LINE_NOT_FOUND', 'MEMBER_NOT_FOUND', 'AMOUNT_INVALID', 'VERSION_CONFLICT', 'STATE_CONFLICT'].includes(error.code) && !request.purchase && !request.next) {
        try {
          const state = await api<CartResult>(`carts/${cart.cart_id}`);
          if (!active.current || !enabledNow.current || state.cart.cart_id !== cart.cart_id) throw new Error('操作を続けられません。状態を再確認してください。', { cause: error });
          accept(state);
          requireStable(localStorage,current.current,beforeNotifications,notified.current);
          if (changingMember) setMemberUnconfirmed(false);
          const missingMember = changingMember && request.method === 'PUT'
            && error.status === 404 && error.code === 'MEMBER_NOT_FOUND'
            && state.cart.member_state === 'PENDING' && current.current.cart.member_state === 'PENDING'
            && state.cart.pending_member_id === request.body?.member_id
            && current.current.cart.pending_member_id === request.body?.member_id
            && state.cart.version === current.current.cart.version
            && BigInt(state.cart.version) > BigInt(String(request.body?.version));
          if (state.cart.state === 'EDITING' && current.current.cart.state === 'EDITING'
            && (missingMember || (state.cart.member_state !== 'PENDING' && current.current.cart.member_state !== 'PENDING'))) {
            pending.current = null; setPhase('ready');
            if (keepCamera) reportScan?.({ kind: 'rejected', message: error.message });
            return false;
          }
        } catch (reconciliationError) {
          if (reconciliationError instanceof ApiError && reconciliationError.status === 401) { initialized.current = false; onAuthentication(); }
          // Keep the original request; a failed GET never enables another update.
        }
      }
      setPhase('uncertain');
      if (request.purchase && !(error instanceof ApiError)) setMessage('保存結果を確認できません。内容を保持して再確認してください。');
      return false;
    } finally { inflight.current = false; setBusy(false); }
  }

  async function scanned(scannedCode: string): Promise<ScanOutcome> {
    if (!enabled || phase !== 'ready' || inflight.current || !safeToAct()) return { kind: 'stopped' };
    if (camera === 'product' && !canEdit || camera === 'member' && !editing) return { kind: 'stopped' };
    const operationId = crypto.randomUUID();
    const suffix = camera === 'member' ? 'member' : 'lines';
    const body = { operation_id:operationId, version:current.current.cart.version, ...(camera === 'member' ? {member_id:scannedCode} : {code:scannedCode}) };
    let outcome: ScanOutcome = { kind: 'stopped' };
    await send({path:`carts/${cart.cart_id}/${suffix}`,method:camera === 'member' ? 'PUT' : 'POST',body,operationId,purchase:false,next:false}, result => { outcome = result; });
    return outcome;
  }

  function change(suffix: string, method: string, extra: Record<string, unknown> = {}) {
    if (!enabled || phase !== 'ready' || inflight.current || !safeToAct()) return;
    setCamera(null);
    const operationId = crypto.randomUUID();
    const body = { operation_id: operationId, version: current.current.cart.version, ...extra };
    const path = `carts/${cart.cart_id}/${suffix}`;
    void send({ path: method === 'DELETE' ? `${path}?operation_id=${operationId}&version=${body.version}` : path,
      method, body: method === 'DELETE' ? undefined : body, operationId, purchase: false, next: suffix === 'next', measured:suffix === 'member' ? measure('MEMBER') : undefined });
  }

  async function search() {
    if (!canEdit || inflight.current || !safeToAct()) return;
    setCamera(null);
    const measured = measure('PRODUCT');
    const searched = inputCode.current;
    const generation = inputGeneration.current;
    const beforeNotifications = notified.current;
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(searched)) { setMessage('商品コードの形式を確認してください。'); return; }
    const canShowResult = () => active.current && enabledNow.current
      && beforeNotifications === notified.current && current.current.cart.cart_id === cart.cart_id
      && current.current.cart.state === 'EDITING' && current.current.cart.member_state !== 'PENDING'
      && inputGeneration.current === generation && inputCode.current === searched;
    inflight.current = true; setBusy(true); setSearching(true); setProduct(null);
    try {
      const result = await api<Product>(`products/${searched}`);
      if (canShowResult()) { setProduct(result); setMessage('商品を確認しました。追加時に価格を確定します。'); measured(); }
    } catch (error) {
      const stopped = error instanceof ApiError && (error.status === 401
        || ['MAINTENANCE_HOLD', 'RESUME_EXPIRED', 'FORBIDDEN'].includes(error.code));
      if (stopped) { setPhase('uncertain'); setProduct(null); }
      if (stopped || canShowResult()) setMessage(error instanceof Error ? error.message : '商品を確認できません。');
      if (error instanceof ApiError && error.status === 401) { initialized.current = false; onAuthentication(); }
    } finally { inflight.current = false; setSearching(false); setBusy(false); }
  }

  function buy() {
    if (!(canEdit || (enabled && phase === 'ready' && !busy && cart.state === 'UNSAVED')) || !cart.lines.length || inflight.current || !safeToAct()) return;
    setCamera(null);
    const operationId = crypto.randomUUID();
    const body = { cart_id: cart.cart_id, operation_id: operationId, version: cart.version };
    try {
      if (purchaseKeys(localStorage, cart.cart_id).length) throw new Error('保存結果の確認が必要です。');
      rememberPurchase(localStorage, cart.cart_id, operationId, cart.version);
    } catch { setPhase('uncertain'); setMessage('購入補助記録を保存・確認できません。購入送信を停止しました。'); return; }
    void send({ path: 'purchases', method: 'POST', body, operationId, purchase: true, next: false, measured:measure('PURCHASE') });
  }

  return <div className="pos">
    <p role="status" aria-live="polite">{message}</p>
    <div className="pos-grid">
      <section aria-label="商品と会員の入力">
        <h2>会員</h2>
        <button className="secondary" disabled={!editing} onClick={() => setCamera('member')}>会員をカメラで読む</button>
        <p>会員：{memberUnconfirmed ? '確認待ち（指定結果は未確認）' : cart.member_state === 'PENDING' ? '会員確認待ち' : cart.member_id ?? '未指定の非会員'}</p>
        <label>変更先の会員ID<input value={member} disabled={!editing} onChange={e => setMember(e.target.value)} maxLength={32} /></label>
        <button disabled={!editing || !/^[A-Za-z0-9_-]{1,32}$/.test(member)} onClick={() => change('member', 'PUT', { member_id: member })}>照会・再照会</button>
        <button className="secondary" disabled={!editing} onClick={() => change('member', 'PUT', { member_id: null })}>非会員として続ける</button>
        <h2>商品</h2>
        <button className="secondary" disabled={!canEdit} onClick={() => setCamera('product')}>商品をカメラで読む</button>
        {camera && <Camera key={camera} mode={camera} allowed={enabled && phase === 'ready' && cart.state === 'EDITING' && (camera === 'member' || cart.member_state !== 'PENDING')} onCode={scanned} onClose={closeCamera} />}
        <label>商品コード<input value={code} disabled={!canEnterCode} onChange={e => { inputGeneration.current++; inputCode.current = e.target.value; setCode(e.target.value); setProduct(null); }} maxLength={32} /></label>
        <button disabled={!canEdit || !code} onClick={() => void search()}>検索</button>
        {product && <div><p>{product.name} ／ 税抜単価 {product.unit_price}円</p><p className="muted">追加時に価格を確定</p>
          <button disabled={!canEdit || product.code !== code} onClick={() => change('lines', 'POST', { code: product.code })}>追加</button></div>}
      </section>
      <section aria-label="購入リスト">
        <h2>購入リスト</h2>
        {(memberUnconfirmed || cart.amounts_are_reference) && <p role="alert">{memberUnconfirmed ? '変更前の参考額・会員指定の結果は未確認です。' : '変更前の参考額・会員確認待ち'}</p>}
        {!cart.lines.length && <p>商品はまだ登録されていません。</p>}
        <ul className="lines">{cart.lines.map(line => <li key={line.line_id} className={line.line_id === selected ? 'selected' : ''}>
          <button className="secondary" disabled={!canEdit} onClick={() => { setSelected(line.line_id); setQuantity(String(line.quantity)); }}>
            {line.name}{line.line_id === selected ? '（選択中）' : ''}</button>
          <p>数量 {line.quantity} ／ 税抜単価 {line.unit_price}円</p>
          <p>値引き額（行合計）{String(BigInt(line.discount_per_unit) * BigInt(line.quantity))}円 ／ 税抜小計 {line.line_subtotal}円</p>
        </li>)}</ul>
        {selection && <div><h3>選択商品：{selection.name}</h3><p>税抜単価 {selection.unit_price}円 ／ 現在 {selection.quantity}個</p>
          <label>数量（1〜99）<input type="number" min="1" max="99" step="1" value={quantity} disabled={!canEdit} onChange={e => setQuantity(e.target.value)} /></label>
          <button disabled={!canEdit || !/^[1-9][0-9]?$/.test(quantity)} onClick={() => change(`lines/${selection.line_id}`, 'PATCH', { quantity: Number(quantity) })}>数量変更</button>
          <button className="secondary" disabled={!canEdit} onClick={() => { setSelected(''); setQuantity('1'); }}>選択解除</button>
          <button className="secondary" disabled={!canEdit} onClick={() => { change(`lines/${selection.line_id}`, 'DELETE'); setSelected(''); }}>削除</button></div>}
        <p>税抜合計（値引き後）：{cart.subtotal}円</p>
        {cart.taxes.map(tax => <p key={tax.tax_rate}>消費税（{String(Number(tax.tax_rate) * 100)}％）：{tax.tax_amount}円</p>)}
        <p className="total">税込合計：{cart.total}円</p>
        {cart.state === 'UNSAVED' && phase === 'ready' && !busy && enabled && <div role="status"><p>未保存を確認しました。</p>
          <button disabled={!enabled || phase !== 'ready' || busy} onClick={buy}>そのまま再試行</button>
          <button className="secondary" disabled={!enabled || phase !== 'ready' || busy} onClick={() => change('reopen','POST')}>内容を修正する</button></div>}
        {cart.state === 'EDITING' && <button disabled={!canEdit || !cart.lines.length} onClick={buy}>購入確定</button>}
        {value.purchase_status === 'SAVED' && value.purchase && <div role="status"><h2>購入完了</h2>
          <p>税抜合計 {value.purchase.subtotal}円 ／ 税込合計 {value.purchase.total}円</p>
          <button disabled={!enabled || phase !== 'ready' || busy} onClick={() => change('next','POST')}>閉じて次の取引へ</button></div>}
      </section>
    </div>
    {phase === 'uncertain' && enabled && <button disabled={busy} onClick={() => void initialize()}>状態を再確認</button>}
    {phase === 'uncertain' && pending.current && <button disabled={busy || !enabled} onClick={() => void send(pending.current!)}>同じ要求で再確認・再試行</button>}
  </div>;
}
