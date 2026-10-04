import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError, rememberPurchase } from '../lib/pos.ts';
import { Recovery } from '../lib/recovery.ts';
import { registerHarness } from './support/register-harness.mjs';
import { recoveryUiHarness } from './support/recovery-ui-harness.mjs';

const id = '11111111-1111-4111-8111-111111111111';
const op = '22222222-2222-4222-8222-222222222222';
const newerId = '33333333-3333-4333-8333-333333333333';
function state(phase = 'EDITING', cartId = id, version = '4') {
  return { cart: { cart_id: cartId, version, staff_id: 'STAFF_A', state: phase,
    member_state: 'CONFIRMED', member_id: 'MEMBER_TEST', pending_member_id: null, amounts_are_reference: false,
    lines: [{ line_id: 'line', code: '0001', name: '食品', quantity: 3, unit_price: '103', discount_per_unit: '10', line_subtotal: '279' }],
    taxes: [], subtotal: '279', total: '306' },
    purchase_status: phase === 'SAVED' ? 'SAVED' : phase === 'UNSAVED' ? 'UNSAVED' : phase === 'SAVING' ? 'UNKNOWN' : 'NOT_REQUESTED',
    purchase: phase === 'SAVED' ? { cart_id: cartId, subtotal: '279', total: '306' } : null };
}
class Store {
  values = new Map();
  get length() { return this.values.size; }
  key(i) { return [...this.values.keys()][i] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}
for (const fault of ['write-throws', 'silent-write', 'read-throws', 'broken-marker']) {
  test(`TC20 actual purchase handler stops before POST on ${fault}`, async () => {
    const calls = []; const view = registerHarness(state(), async (...args) => { calls.push(args); return state(); });
    view.flush(); await view.settle();
    if (fault === 'write-throws') view.storage.setItem = () => { throw new Error('write denied'); };
    if (fault === 'silent-write') view.storage.setItem = () => {};
    if (fault === 'read-throws') {
      view.storage.setItem('pos-purchase:unreadable', '{}'); view.storage.getItem = () => { throw new Error('read denied'); };
    }
    if (fault === 'broken-marker') view.storage.setItem('pos-purchase:broken', '{broken');
    view.button('購入確定').onClick(); await view.settle();
    assert.equal(calls.length, 0);
    assert.equal(view.button('購入確定').disabled, true);
    assert.ok(view.text().includes('食品')); assert.ok(view.text().includes('306円'));
    assert.ok(view.button('状態を再確認'));
    view.unmount();
  });
}

for (const oldStatus of ['SAVED', 'UNKNOWN']) {
  test(`TC20 Recovery resolves closed-cart marker from server ${oldStatus} before using current cart`, async () => {
    const storage = new Store(); rememberPurchase(storage, id, op, '1'); const calls = [];
    const current = state('UNSAVED', newerId);
    const recovery = new Recovery(async path => {
      calls.push(path);
      if (path === 'register/status') return { maintenance_hold: false };
      if (path === 'resume') return current;
      assert.equal(path, `carts/${id}/purchase`);
      const old = state('SAVED'); return { ...old, cart: { ...old.cart, state: 'CLOSED' }, purchase_status: oldStatus };
    });
    if (oldStatus === 'SAVED') { assert.equal((await recovery.reconcile(storage)).cart.cart_id, newerId); assert.equal(storage.length, 0); }
    else { await assert.rejects(recovery.reconcile(storage), /前の取引/); assert.equal(storage.length, 1); }
    assert.deepEqual(calls, ['register/status', 'resume', `carts/${id}/purchase`]);
  });
}

test('TC24 late successful NEXT receipt navigates using resume, never its historical next cart', async () => {
  const old = state('SAVED'); const current = state('EDITING', newerId); const calls = [];
  let resumeState = old; let release;
  const held = new Promise(resolve => { release = resolve; });
  const view = recoveryUiHarness('register', async (path, method, body) => {
    calls.push({ path, method });
    if (path === 'register/status') return { maintenance_hold: false };
    if (path === 'resume') return resumeState;
    assert.equal(path, `carts/${id}/next`);
    await held;
    const historical = state('EDITING', op);
    return { ...historical, operation_id: body.operation_id, operation_status: 'APPLIED', new_cart_id: op };
  }, old);
  view.flush(); await view.settle();
  view.button('閉じて次の取引へ').onClick(); view.flush(); await view.settle();
  assert.equal(view.next.length, 0, 'the historical next response is still held');
  assert.equal(view.button('閉じて次の取引へ').disabled, true);
  resumeState = current; release(); await view.settle();
  assert.equal(view.next.length, 1); assert.equal(view.next[0].cart.cart_id, newerId);
  assert.deepEqual(calls.filter(call => call.method === 'POST').map(call => call.path), [`carts/${id}/next`]);
  view.unmount();
});

test('TC20/28 actual Register plus Recovery stays stopped when resumed SAVING cannot be resolved', async () => {
  const initial = state('SAVING'); const calls = [];
  const view = recoveryUiHarness('register', async (path, method = 'GET') => {
    calls.push({ path, method });
    if (path === 'register/status') return { maintenance_hold: false };
    if (path === 'resume') return initial;
    assert.ok(path.includes('/operations/'));
    throw new ApiError(503, '結果を照合できません。', 'DB_UNAVAILABLE');
  }, initial);
  view.flush(); await view.settle();
  assert.equal(view.button('購入確定'), undefined);
  assert.equal(view.button('閉じて次の取引へ'), undefined);
  assert.equal(view.button('非会員として続ける').disabled, true);
  assert.ok(view.messages().includes('結果を照合できません。'));
  assert.ok(view.text().includes('食品')); assert.ok(view.text().includes('306円'));
  assert.equal(calls.filter(call => call.method === 'POST').length, 0);
  view.unmount();
});

for (const phase of ['EDITING', 'PENDING', 'SAVING', 'UNKNOWN', 'UNSAVED', 'SAVED']) {
  test(`TC28 reauthentication response loss keeps ${phase} context and inspects before enabling it`, async () => {
    const initial = state(phase === 'UNKNOWN' || phase === 'PENDING' ? 'EDITING' : phase);
    if (phase === 'PENDING') Object.assign(initial.cart, { member_state: 'PENDING', member_id: null,
      pending_member_id: 'MEMBER_PENDING', amounts_are_reference: true });
    const calls = []; let reauth = false;
    const view = recoveryUiHarness('home', async (path, method = 'GET') => {
      calls.push({ path, method });
      if (path === 'auth/status') return { authenticated: true, staff_id: 'STAFF_A', expires_at: '2099-01-01T00:00:00Z' };
      if (path === 'register/status') return { start_state: 'READY', maintenance_hold: false };
      if (path === 'resume') return initial;
      assert.equal(path, 'reauth'); reauth = true; throw new Error('lost authentication response');
    });
    if (phase === 'UNKNOWN') rememberPurchase(view.storage, id, op, '3');
    const markerKey = `pos-purchase:${id}:${op}`;
    const markerBefore = view.storage.getItem(markerKey);
    view.flush(); await view.settle(); view.cart().onAuthentication(); view.flush();
    assert.equal(view.cart().enabled, false); assert.equal(view.cart().initial, initial);
    assert.equal(view.storage.getItem(markerKey), markerBefore);
    await view.submit('STAFF_A');
    assert.equal(reauth, true); assert.equal(view.cart().enabled, true); assert.equal(view.cart().initial, initial);
    assert.equal(view.resets, 1);
    assert.deepEqual(calls.filter(call => call.method === 'POST').map(call => call.path), ['reauth']);
    assert.deepEqual(calls.slice(-3).map(call => call.path), ['auth/status', 'register/status', 'resume']);
    assert.equal(view.storage.getItem(markerKey), markerBefore, 'reauthentication does not remove an unresolved purchase marker');
    if (phase === 'UNKNOWN') {
      assert.deepEqual(JSON.parse(markerBefore), { cart_id: id, operation_id: op, version: '3' });
      assert.equal(view.storage.length, 1);
      assert.equal(initial.purchase_status, 'NOT_REQUESTED', 'EDITING in DB plus a pending local request is distinct from a normal edit');
    } else assert.equal(view.storage.length, 0);
    view.unmount();
  });
}

for (const reason of ['other-staff', 'reauth-401', 'inspection-401', 'inspection-503', 'wrong-inspected-staff']) {
  test(`TC28 ${reason} retains cart and never automatically retries authentication or purchase`, async () => {
    const initial = state('SAVED'); const calls = []; let inspecting = false;
    const view = recoveryUiHarness('home', async (path, method = 'GET') => {
      calls.push({ path, method });
      if (path === 'auth/status') {
        if (inspecting && reason === 'inspection-401') throw new ApiError(401, 'expired', 'UNAUTHENTICATED');
        if (inspecting && reason === 'inspection-503') throw new ApiError(503, 'cannot inspect', 'DB_UNAVAILABLE');
        return { authenticated: true, staff_id: inspecting && reason === 'wrong-inspected-staff' ? 'STAFF_B' : 'STAFF_A' };
      }
      if (path === 'register/status') return { start_state: 'READY', maintenance_hold: false };
      if (path === 'resume') return initial;
      assert.equal(path, 'reauth'); inspecting = true;
      if (reason === 'reauth-401') throw new ApiError(401, 'bad credentials', 'UNAUTHENTICATED');
      return { authenticated: true, staff_id: 'STAFF_A' };
    });
    view.flush(); await view.settle(); view.cart().onAuthentication(); view.flush();
    await view.submit(reason === 'other-staff' ? 'STAFF_B' : 'STAFF_A');
    assert.equal(view.cart().enabled, false); assert.equal(view.cart().initial, initial);
    assert.deepEqual(calls.filter(call => call.method === 'POST').map(call => call.path), reason === 'other-staff' ? [] : ['reauth']);
    assert.ok(!calls.some(call => call.path === 'purchases' || call.path === 'carts' || call.path === 'register/start'));
    view.unmount();
  });
}
