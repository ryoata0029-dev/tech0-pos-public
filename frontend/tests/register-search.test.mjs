import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError } from '../lib/pos.ts';
import { registerHarness } from './support/register-harness.mjs';

const cartId = '11111111-1111-4111-8111-111111111111';
const initial = { cart: { cart_id: cartId, version: '4', state: 'EDITING',
  member_state: 'UNSPECIFIED', member_id: null, pending_member_id: null,
  lines: [{ line_id: 'line', code: 'OLD', name: '既存商品', quantity: 1,
    unit_price: '100', discount_per_unit: '0', line_subtotal: '100' }],
  taxes: [], subtotal: '100', total: '100' }, purchase_status: 'NOT_REQUESTED', purchase: null };
const product = code => ({ code, name: `検索商品${code}`, unit_price: '103' });
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function typeCode(view, code) {
  assert.equal(view.input('商品コード').disabled, false, 'use the enabled code input without removing its disabled state');
  view.input('商品コード').onChange({ target: { value: code } }); view.flush();
}
async function setup(overrides = {}) {
  const response = deferred(); const calls = []; let resumed = initial;
  const view = registerHarness(initial, async (path, method = 'GET', body) => {
    calls.push({ path, method, body });
    if (path === 'resume') return resumed;
    if (path === 'products/0001') return response.promise;
    if (path === 'products/0002') return product('0002');
    if (method === 'POST') return { ...initial, cart: { ...initial.cart, version: '5',
      lines: [...initial.cart.lines, { ...initial.cart.lines[0], line_id: 'added', code: body.code, name: '追加商品' }] },
      operation_id: body.operation_id, operation_status: 'APPLIED' };
    throw new Error(`Unexpected request ${path}`);
  }, overrides);
  view.flush(); await view.settle();
  return { view, response, calls, resumeAs(state) { resumed = state; } };
}

for (const backToOriginal of [false, true]) {
  for (const reply of ['success', 'not-found', 'unavailable']) {
    test(`search permits code changes and ignores old ${reply}${backToOriginal ? ' after A-B-A' : ''}`, async () => {
      const { view, response, calls } = await setup();
      typeCode(view, '0001'); view.button('検索').onClick(); view.flush();
      typeCode(view, '0002'); if (backToOriginal) typeCode(view, '0001');
      assert.equal(view.button('検索').disabled, true);
      assert.equal(view.button('商品をカメラで読む').disabled, true);
      assert.equal(view.button('購入確定')?.disabled ?? true, true);
      assert.equal(view.button('非会員として続ける').disabled, true);
      view.button('検索').onClick(); view.button('購入確定').onClick();
      assert.equal(calls.length, 1, 'no additional search or update is sent while waiting');
      if (reply === 'success') response.resolve(product('0001'));
      else response.reject(new ApiError(reply === 'not-found' ? 404 : 503, '旧検索エラー', reply === 'not-found' ? 'PRODUCT_NOT_FOUND' : 'DB_UNAVAILABLE'));
      await view.settle();
      assert.ok(!view.text().includes('検索商品0001'));
      assert.ok(!view.messages().includes('旧検索エラー'));
      assert.ok(!view.messages().includes('商品を確認しました。追加時に価格を確定します。'));
      assert.equal(view.button('追加'), undefined);
      typeCode(view, '0002'); view.button('検索').onClick(); await view.settle();
      assert.ok(view.text().includes('検索商品0002'));
      assert.equal(view.button('追加').disabled, false);
      view.button('追加').onClick(); await view.settle();
      assert.equal(calls.filter(call => call.method === 'POST').length, 1);
      assert.equal(calls.at(-1).body.code, '0002');
      assert.equal(view.input('商品コード').value, '');
      view.unmount();
    });
  }
}

for (const reason of ['notification', 'disabled', 'member-pending', 'saving']) {
  for (const reply of ['success', 'error']) {
    test(`late search ${reply} preserves ${reason} stop`, async () => {
      const { view, response, resumeAs } = await setup();
      typeCode(view, '0001'); view.button('検索').onClick(); view.flush();
      if (reason === 'disabled') view.disable();
      else {
        if (reason !== 'notification') resumeAs({ ...initial, cart: { ...initial.cart, version: '5',
          ...(reason === 'member-pending' ? { member_state: 'PENDING' } : { state: 'SAVING' }) } });
        view.notify(); await view.settle();
      }
      const stoppedMessages = view.messages();
      assert.equal(view.input('商品コード').disabled, true);
      if (reply === 'success') response.resolve(product('0001'));
      else response.reject(new ApiError(404, '旧検索エラー', 'PRODUCT_NOT_FOUND'));
      await view.settle();
      assert.deepEqual(view.messages(), stoppedMessages, 'late search must not replace the reason for stopping');
      assert.equal(view.input('商品コード').disabled, true);
      assert.equal(view.button('購入確定')?.disabled ?? true, true);
      assert.equal(view.button('追加'), undefined);
      view.unmount();
    });
  }
}

for (const [status, code] of [[401, 'UNAUTHENTICATED'], [409, 'RESUME_EXPIRED'], [409, 'MAINTENANCE_HOLD'], [403, 'FORBIDDEN']]) {
  test(`search ${code} stops even after the input changed`, async () => {
    const { view, response } = await setup();
    typeCode(view, '0001'); view.button('検索').onClick(); view.flush(); typeCode(view, '0002');
    response.reject(new ApiError(status, '停止理由', code)); await view.settle();
    assert.ok(view.messages().includes('停止理由'));
    assert.equal(view.input('商品コード').disabled, true);
    assert.equal(view.button('購入確定').disabled, true);
    assert.equal(view.button('商品をカメラで読む').disabled, true);
    if (status === 401) assert.equal(view.authentications, 1);
    view.unmount();
  });
}

test('pending initialization and product update never receive the search-only input exception', async () => {
  const starting = deferred();
  const { view, response } = await setup({ reconcile: () => starting.promise });
  assert.equal(view.input('商品コード').disabled, true);
  starting.resolve(initial); await view.settle();
  typeCode(view, '0001'); view.button('検索').onClick(); view.flush();
  response.resolve(product('0001')); await view.settle();
  view.button('追加').onClick(); view.flush();
  assert.equal(view.input('商品コード').disabled, true);
  await view.settle(); view.unmount();
});

test('member and purchase requests keep the code input disabled', async () => {
  for (const button of ['照会・再照会', '購入確定']) {
    const pending = deferred(); const calls = [];
    const view = registerHarness(initial, async (...args) => { calls.push(args); return pending.promise; });
    view.flush(); await view.settle();
    view.input('変更先の会員ID').onChange({ target: { value: 'MEMBER' } }); view.flush();
    view.button(button).onClick(); view.flush();
    assert.equal(view.input('商品コード').disabled, true);
    assert.equal(calls.length, 1);
    pending.reject(new Error('network')); await view.settle();
    assert.equal(view.input('商品コード').disabled, true);
    view.unmount();
  }
});
