import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError } from '../lib/pos.ts';
import { registerHarness } from './support/register-harness.mjs';

const cartId = '11111111-1111-4111-8111-111111111111';
const initial = { cart: { cart_id: cartId, version: '4', staff_id: 'A', state: 'EDITING',
  member_state: 'CONFIRMED', member_id: 'MEMBER_0', pending_member_id: null,
  lines: [{ line_id: 'line', name: '食品', quantity: 3, unit_price: '103',
    discount_per_unit: '10', line_subtotal: '279' }], taxes: [], subtotal: '279', total: '306',
  amounts_are_reference: false }, purchase_status: 'NOT_REQUESTED', purchase: null };
const waiting = { ...initial, cart: { ...initial.cart, version: '5', member_state: 'PENDING',
  pending_member_id: 'MEMBER_1', amounts_are_reference: true } };
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function setup(transport, options) {
  const view = registerHarness(initial, transport, options); view.flush(); await view.settle();
  view.input('変更先の会員ID').onChange({ target: { value: 'MEMBER_1' } }); view.flush();
  return view;
}
function unconfirmed(view) {
  assert.ok(view.text().includes('参考額'));
  assert.ok(!view.text().includes('会員：MEMBER_0'));
  assert.ok(view.text().includes('306円'), 'retain amounts without recomputing them on the client');
  assert.equal(view.button('購入確定').disabled, true);
  assert.equal(view.button('商品をカメラで読む').disabled, true);
}

test('member change immediately marks old conditions as reference; 503 keeps uncertainty until explicit reconciliation', async () => {
  const pending = deferred(); const calls = []; let reconciled = initial;
  const view = await setup(async (...args) => { calls.push(args); return pending.promise; }, { reconcile: async () => reconciled });
  view.button('照会・再照会').onClick(); view.flush(); unconfirmed(view);
  assert.equal(view.button('非会員として続ける').disabled, true);
  pending.reject(new ApiError(503, '状態を確認できません。', 'DB_UNAVAILABLE')); await view.settle(); unconfirmed(view);
  assert.equal(calls.length, 1, 'no automatic resend or member lookup');
  reconciled = waiting;
  await view.button('状態を再確認').onClick(); await view.settle(); unconfirmed(view);
  assert.ok(view.text().includes('会員確認待ち'));
  assert.equal(view.button('非会員として続ける').disabled, false);
  assert.equal(view.button('照会・再照会').disabled, false);
  assert.equal(calls.length, 1);
  view.unmount();
});

for (const [label, error] of [
  ['network response loss', new Error('network')],
  ['authentication loss', new ApiError(401, '再認証してください。', 'UNAUTHENTICATED')],
  ['recovery expiry', new ApiError(409, '復帰期限が切れました。', 'RESUME_EXPIRED')],
]) {
  test(`member ${label} preserves reference display and explicit reason without automatic retry`, async () => {
    let calls = 0;
    const view = await setup(async () => { calls++; throw error; });
    view.button('照会・再照会').onClick(); await view.settle(); unconfirmed(view);
    assert.equal(calls, 1);
    if (error instanceof ApiError) assert.ok(view.messages().includes(error.message));
    if (error.status === 401) assert.equal(view.authentications, 1);
    if (error.code === 'RESUME_EXPIRED') assert.equal(view.button('同じ要求で再確認・再試行'), undefined);
    view.unmount();
  });
}

test('member-not-found reconciles to PENDING and retains reference amounts', async () => {
  const view = await setup(async (path, method) => {
    if (method === 'PUT') throw new ApiError(404, '会員が見つかりません。', 'MEMBER_NOT_FOUND');
    assert.equal(path, `carts/${cartId}`); return waiting;
  });
  view.button('照会・再照会').onClick(); await view.settle(); await view.settle(); unconfirmed(view);
  assert.ok(view.messages().includes('会員が見つかりません。'));
  view.unmount();
});

for (const nonmember of [false, true]) {
  test(`verified ${nonmember ? 'nonmember' : 'member'} success restores authoritative conditions`, async () => {
    const done = deferred();
    const view = await setup(async (path, method, body) => {
      const memberId = nonmember ? null : 'MEMBER_1';
      assert.equal(body.member_id, memberId);
      await done.promise;
      return { ...initial, cart: { ...initial.cart, version: '6', member_id: memberId,
        member_state: nonmember ? 'NON_MEMBER' : 'CONFIRMED', total: '340' },
        operation_id: body.operation_id, operation_status: 'APPLIED' };
    });
    view.button(nonmember ? '非会員として続ける' : '照会・再照会').onClick(); view.flush(); unconfirmed(view);
    done.resolve(); await view.settle(); await view.settle();
    assert.ok(!view.text().includes('参考額'));
    assert.ok(view.text().includes(nonmember ? '会員：未指定の非会員' : '会員：MEMBER_1'));
    assert.ok(view.text().includes('340円'));
    assert.equal(view.button('購入確定').disabled, false);
    view.unmount();
  });
}

test('failed state check must not restore old-member certainty', async () => {
  let initialized = false;
  const view = await setup(async () => { throw new ApiError(503, '照合不能', 'DB_UNAVAILABLE'); }, {
    reconcile: async () => { if (initialized) throw new ApiError(503, '照合不能', 'DB_UNAVAILABLE'); initialized = true; return initial; },
  });
  view.button('照会・再照会').onClick(); await view.settle();
  await view.button('状態を再確認').onClick(); await view.settle(); unconfirmed(view);
  assert.equal(view.button('非会員として続ける').disabled, true);
  view.unmount();
});

test('same member request retry retains operation identity and clears uncertainty only on verified success', async () => {
  const calls = []; let lost = true;
  const view = await setup(async (path, method, body) => {
    calls.push({path, method, body});
    if (lost) throw new ApiError(503, '照合不能', 'DB_UNAVAILABLE');
    return { ...initial, cart: { ...initial.cart, version: '6', member_id: 'MEMBER_1' },
      operation_id: body.operation_id, operation_status: 'APPLIED' };
  });
  view.button('照会・再照会').onClick(); await view.settle(); unconfirmed(view);
  lost = false;
  await view.button('同じ要求で再確認・再試行').onClick(); await view.settle();
  assert.deepEqual(calls[1], calls[0]);
  assert.ok(!view.text().includes('参考額'));
  assert.ok(view.text().includes('会員：MEMBER_1'));
  view.unmount();
});

test('verified PREPARED member receipt exposes PENDING choices without presenting old member as applied', async () => {
  const view = await setup(async (path, method, body) => ({ ...waiting,
    operation_id: body.operation_id, operation_status: 'PREPARED' }));
  view.button('照会・再照会').onClick(); await view.settle(); unconfirmed(view);
  assert.ok(view.text().includes('会員確認待ち'));
  assert.equal(view.button('非会員として続ける').disabled, false);
  view.unmount();
});

for (const kind of ['wrong-cart', 'invalid-prepared-state', 'notification']) {
  test(`unverified member receipt (${kind}) never restores old certainty`, async () => {
    const reply = deferred();
    const view = await setup(async (path, method, body) => {
      await reply.promise;
      return { ...initial, cart: { ...initial.cart,
        cart_id: kind === 'wrong-cart' ? '22222222-2222-4222-8222-222222222222' : cartId },
        operation_id: body.operation_id, operation_status: kind === 'invalid-prepared-state' ? 'PREPARED' : 'APPLIED' };
    });
    view.button('照会・再照会').onClick(); view.flush();
    if (kind === 'notification') view.notify();
    reply.resolve(); await view.settle(); unconfirmed(view);
    assert.equal(view.button('非会員として続ける').disabled, true);
    view.unmount();
  });
}

for (const hasLines of [false, true]) {
  for (const wasMember of [false, true]) {
    for (const chooseNonmember of [false, true]) {
      test(`member-not-found permits ${chooseNonmember ? 'nonmember' : 'new member'} without extra reconcile (${hasLines ? 'lines' : 'empty'}, ${wasMember ? 'change' : 'initial'})`, async () => {
        const start = { ...initial, cart: { ...initial.cart,
          member_state: wasMember ? 'CONFIRMED' : 'NON_MEMBER', member_id: wasMember ? 'MEMBER_0' : null,
          lines: hasLines ? initial.cart.lines : [], total: hasLines ? initial.cart.total : '0' } };
        const missing = { ...start, cart: { ...start.cart, version: '5', member_state: 'PENDING',
          pending_member_id: 'MEMBER_MISSING', amounts_are_reference: true } };
        const calls = [];
        const view = registerHarness(start, async (path, method = 'GET', body) => {
          calls.push({ path, method, body });
          if (method === 'GET') { assert.equal(path, `carts/${cartId}`); return missing; }
          if (calls.length === 1) throw new ApiError(404, '会員が見つかりません。再入力または非会員を選択してください。', 'MEMBER_NOT_FOUND');
          assert.equal(path, `carts/${cartId}/member`);
          assert.equal(body.version, '5');
          assert.notEqual(body.operation_id, calls[0].body.operation_id);
          assert.equal(body.member_id, chooseNonmember ? null : 'MEMBER_1');
          return { ...start, cart: { ...start.cart, version: '7', pending_member_id: null,
            member_state: chooseNonmember ? 'NON_MEMBER' : 'CONFIRMED', member_id: body.member_id,
            amounts_are_reference: false }, operation_id: body.operation_id, operation_status: 'APPLIED' };
        });
        view.flush(); await view.settle();
        view.input('変更先の会員ID').onChange({ target: { value: 'MEMBER_MISSING' } }); view.flush();
        view.button('照会・再照会').onClick(); await view.settle(); await view.settle();
        assert.equal(calls.length, 2, 'one PUT and one automatic cart GET; no extra retry');
        assert.equal(view.input('変更先の会員ID').disabled, false);
        assert.equal(view.button('照会・再照会').disabled, false);
        assert.equal(view.button('非会員として続ける').disabled, false);
        assert.equal(view.button('商品をカメラで読む').disabled, true);
        assert.equal(view.input('商品コード').disabled, true);
        assert.equal(view.button('購入確定').disabled, true);
        assert.ok(view.text().includes('参考額'));
        assert.ok(!view.text().includes('会員：MEMBER_0'));
        assert.ok(view.messages().some(message => message.includes('会員が見つかりません')));
        assert.equal(view.button('状態を再確認'), undefined);
        assert.equal(view.button('同じ要求で再確認・再試行'), undefined);
        if (!chooseNonmember) { view.input('変更先の会員ID').onChange({ target: { value: 'MEMBER_1' } }); view.flush(); }
        view.button(chooseNonmember ? '非会員として続ける' : '照会・再照会').onClick(); await view.settle();
        assert.equal(calls.length, 3);
        assert.ok(!view.text().includes('参考額'));
        assert.equal(view.input('商品コード').disabled, false);
        assert.equal(view.button('購入確定').disabled, !hasLines);
        view.unmount();
      });
    }
  }
}

for (const kind of ['failed-get', 'wrong-cart', 'old-version', 'other-member', 'saving', 'notification', 'disabled', 'broken-record', 'purchase-record', 'wrong-status', 'state-conflict']) {
  test(`member-not-found recovery stays stopped with ${kind}`, async () => {
    const reply = deferred(); let put = false;
    const view = await setup(async (path, method) => {
      if (path === 'resume') return waiting;
      if (method === 'PUT') {
        put = true;
        throw new ApiError(kind === 'wrong-status' ? 503 : kind === 'state-conflict' ? 409 : 404,
          '操作を確認してください。', kind === 'state-conflict' ? 'STATE_CONFLICT' : 'MEMBER_NOT_FOUND');
      }
      await reply.promise;
      if (kind === 'failed-get') throw new ApiError(503, '照合不能', 'DB_UNAVAILABLE');
      return { ...waiting, cart: { ...waiting.cart,
        cart_id: kind === 'wrong-cart' ? '22222222-2222-4222-8222-222222222222' : cartId,
        version: kind === 'old-version' ? '4' : '5',
        pending_member_id: kind === 'other-member' ? 'MEMBER_2' : 'MEMBER_1',
        state: kind === 'saving' ? 'SAVING' : 'EDITING' } };
    });
    view.button('照会・再照会').onClick(); await view.settle(); assert.equal(put, true);
    if (kind === 'notification') view.notify();
    if (kind === 'disabled') view.disable();
    if (kind === 'broken-record') view.storage.setItem('pos-purchase:broken', '{');
    if (kind === 'purchase-record') view.storage.setItem(`pos-purchase:${cartId}:33333333-3333-4333-8333-333333333333`, JSON.stringify({ cart_id: cartId, operation_id: '33333333-3333-4333-8333-333333333333', version: '4' }));
    reply.resolve(); await view.settle(); await view.settle();
    assert.equal(view.button('非会員として続ける').disabled, true);
    assert.equal(view.input('変更先の会員ID').disabled, true);
    assert.equal(view.button('商品をカメラで読む').disabled, true);
    assert.notEqual(view.button('購入確定')?.disabled, false);
    view.unmount();
  });
}
