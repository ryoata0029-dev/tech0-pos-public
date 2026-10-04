import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHarness } from './support/register-harness.mjs';
import { ApiError } from '../lib/pos.ts';

const initial = { cart: { cart_id: '11111111-1111-4111-8111-111111111111', version: '4',
  state: 'UNSAVED', member_state: 'UNSPECIFIED', lines: [{line_id:'line', name:'食品', quantity:1,
    unit_price:'100', discount_per_unit:'0', line_subtotal:'100'}], taxes: [], total:'100', subtotal:'100' },
  purchase_status:'UNSAVED', purchase:null };

test('UNSAVED retry hides stale certainty while sending and after response loss; same request is retained', async () => {
  let reject; const calls = []; let lost = true;
  const sending = new Promise((resolve, no) => { reject = no; });
  const view = registerHarness(initial, async (path, method, body) => {
    calls.push({path, method, body});
    if (lost) return sending;
    return { ...initial, cart:{...initial.cart,state:'SAVED',version:'6'},
      purchase_status:'SAVED', purchase:{cart_id:initial.cart.cart_id,subtotal:'100',total:'100'},
      operation_id:body.operation_id, operation_status:'APPLIED' };
  });
  view.flush(); await view.settle();
  assert.ok(view.button('そのまま再試行'));
  view.button('そのまま再試行').onClick(); view.flush();
  assert.equal(view.button('そのまま再試行'), undefined);
  assert.equal(view.button('内容を修正する'), undefined);
  assert.ok(view.messages().includes('保存結果を確認しています。'));
  reject(new Error('Unexpected token <')); await view.settle();
  assert.equal(view.button('そのまま再試行'), undefined);
  assert.ok(view.messages().includes('保存結果を確認できません。内容を保持して再確認してください。'));
  assert.equal(view.button('非会員として続ける').disabled, true);
  assert.equal(calls.length, 1);
  assert.equal(view.storage.length, 1);
  lost = false;
  await view.button('同じ要求で再確認・再試行').onClick(); await view.settle();
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(view.storage.length, 0);
  assert.equal(view.button('閉じて次の取引へ').disabled, false);
  view.unmount();
});

test('cross-tab uncertainty hides previous UNSAVED choices without discarding the cart', async () => {
  const view = registerHarness(initial, async () => initial);
  view.flush(); await view.settle(); view.notify(); await view.settle();
  assert.equal(view.button('そのまま再試行'), undefined);
  assert.equal(view.button('内容を修正する'), undefined);
  assert.equal(view.button('非会員として続ける').disabled, true);
  view.unmount();
});

test('purchase preserves an explicit recovery-expiry reason and stays stopped', async () => {
  const view = registerHarness(initial, async () => { throw new ApiError(409,'復帰期限が切れました。本人の確認が必要です。','RESUME_EXPIRED'); });
  view.flush(); await view.settle();
  view.button('そのまま再試行').onClick(); await view.settle();
  assert.ok(view.messages().includes('復帰期限が切れました。本人の確認が必要です。'));
  assert.equal(view.button('そのまま再試行'), undefined);
  assert.equal(view.button('同じ要求で再確認・再試行'), undefined);
  assert.equal(view.button('非会員として続ける').disabled, true);
  assert.equal(view.storage.length, 1);
  view.unmount();
});
