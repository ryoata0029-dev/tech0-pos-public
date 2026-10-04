import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api, ApiError, clearSaved, newer, purchaseKeys, rememberPurchase, requireStable } from '../lib/pos.ts';
const cart = '11111111-1111-4111-8111-111111111111';
const op = '22222222-2222-4222-8222-222222222222';
test('API response loss is Japanese uncertainty, while defined server errors retain their classification', async t => {
  const mocked = t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('fetch failed'); });
  await assert.rejects(api('purchases','POST',{}), /通信結果を確認できません/);
  mocked.mock.mockImplementation(async () => new globalThis.Response('<!DOCTYPE html>proxy error',{status:502}));
  await assert.rejects(api('purchases','POST',{}), /通信結果を確認できません/);
  mocked.mock.mockImplementation(async () => new globalThis.Response('',{status:200}));
  await assert.rejects(api('purchases','POST',{}), /通信結果を確認できません/);
  mocked.mock.mockImplementation(async () => globalThis.Response.json({message:'元の拒否',code:'STATE_CONFLICT'},{status:409}));
  await assert.rejects(api('purchases','POST',{}), error => error instanceof ApiError && error.status === 409 && error.code === 'STATE_CONFLICT' && error.message === '元の拒否');
});
class MemoryStorage {
  values = new Map();
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}
test('late cart responses cannot roll back exact versions above JS integer precision', () => {
  const first = { cart: { cart_id: cart, version: '9007199254740993' } };
  const late = { cart: { cart_id: cart, version: '9007199254740992' } };
  assert.equal(newer(first, late), first);
  assert.equal(newer(first, { cart: { cart_id: op, version: '1' } }).cart.cart_id, op);
});
test('purchase storage keeps each operation and only clears verified saved cart', () => {
  const storage = new MemoryStorage();
  rememberPurchase(storage, cart, op, '1');
  rememberPurchase(storage, cart, cart, '2');
  rememberPurchase(storage, op, cart, '1');
  assert.equal(purchaseKeys(storage, cart).length, 2);
  assert.deepEqual(Object.keys(JSON.parse(storage.getItem(storage.key(0)))).sort(), ['cart_id','operation_id','version']);
  clearSaved(storage, { cart: { cart_id: cart, version: '3' }, purchase_status: 'UNKNOWN', purchase: null });
  assert.equal(storage.length, 3);
  clearSaved(storage, { cart: { cart_id: cart, version: '3' }, purchase_status: 'SAVED', purchase: { cart_id: op } });
  assert.equal(storage.length, 3);
  clearSaved(storage, { cart: { cart_id: cart, version: '3' }, purchase_status: 'SAVED', purchase: { cart_id: cart } });
  assert.equal(storage.length, 1);
});
test('broken or unreadable storage fails closed rather than meaning no pending purchase', () => {
  const storage = new MemoryStorage();
  storage.setItem(`pos-purchase:${cart}:${op}`, '{broken');
  assert.throws(() => purchaseKeys(storage, cart));
  assert.throws(() => rememberPurchase({ setItem() { throw new Error('blocked'); } }, cart, op, '1'));
});

test('late edit receipt cannot acknowledge a newer saving state or notification', () => {
  const storage = new MemoryStorage();
  assert.throws(() => requireStable(storage,{cart:{state:'SAVING'}},0,0));
  assert.throws(() => requireStable(storage,{cart:{state:'EDITING'}},0,1));
  rememberPurchase(storage,cart,op,'3');
  assert.throws(() => requireStable(storage,{cart:{state:'EDITING'}},0,0));
});
