import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError, rememberPurchase } from '../lib/pos.ts';
import { ScanGate } from '../lib/scan-gate.ts';
import { registerHarness } from './support/register-harness.mjs';

const cartId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
function state(version = '2', changes = {}) {
  return { cart: { cart_id: cartId, version, staff_id: 'A', state: 'EDITING', member_state: 'UNSPECIFIED',
    member_id: null, pending_member_id: null, lines: [], subtotal: '0', total: '0', taxes: [],
    amounts_are_reference: false, ...changes }, purchase_status: 'NONE', purchase: null };
}
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function setup(error) {
  const get = deferred(); const calls = []; let rejected = false;
  const initial = state();
  const view = registerHarness(initial, async (path, method = 'GET', body) => {
    calls.push({ path, method, body });
    if (method === 'POST') {
      if (!rejected) { rejected = true; throw error; }
      return { ...state('3'), operation_id: body.operation_id, operation_status: 'APPLIED', applied_version: '3', code: null };
    }
    if (path === 'resume') return initial;
    return get.promise;
  });
  view.flush(); await view.settle();
  view.button('商品をカメラで読む').onClick(); view.flush();
  return { view, get, calls };
}

for (const [code, status] of [['PRODUCT_NOT_FOUND', 404], ['QUANTITY_LIMIT', 422]]) {
  test(`${code}: delayed reconciliation keeps Camera allowed, blocks new operations, then accepts a different code`, async () => {
    const { view, get, calls } = await setup(new ApiError(status, code, code));
    const gate = new ScanGate(); assert.equal(gate.detected('MISSING'), true);
    const outcome = view.camera().onCode('MISSING');
    await view.settle();
    assert.equal(view.camera().allowed, true, 'Camera must not stop during a definite rejection GET');
    assert.equal(view.button('購入確定').disabled, true);
    assert.equal(view.button('商品をカメラで読む').disabled, true);
    assert.equal(view.button('非会員として続ける').disabled, true);
    assert.equal(gate.detected('NEXT'), false);
    assert.equal((await view.camera().onCode('NEXT')).kind, 'stopped');
    assert.equal(calls.filter(call => call.method === 'POST').length, 1);
    get.resolve(state()); assert.deepEqual({ ...await outcome }, { kind: 'rejected', message: code }); await view.settle(); gate.completed();
    assert.equal(view.camera().allowed, true);
    assert.ok(view.messages().includes(code), 'definite rejection remains visible without an add-success message');
    assert.equal(gate.detected('MISSING'), false, 'same rejected code remains suppressed');
    assert.equal(gate.detected('NEXT'), true);
    assert.equal((await view.camera().onCode('NEXT')).kind, 'confirmed'); await view.settle();
    assert.equal(calls.filter(call => call.method === 'POST').length, 2);
    view.unmount();
  });
}

for (const kind of ['get-failure', 'get-401', 'get-503', 'notification', 'member-pending', 'saving', 'new-marker', 'other-cart-marker', 'broken-storage', 'disabled', 'wrong-cart']) {
  test(`definite rejection stops Camera when reconciliation encounters ${kind}`, async () => {
    const { view, get } = await setup(new ApiError(404, 'not found', 'PRODUCT_NOT_FOUND'));
    const outcome = view.camera().onCode('MISSING'); await view.settle();
    if (kind === 'notification') view.notify();
    if (kind === 'new-marker') rememberPurchase(view.storage, cartId, operationId, '2');
    if (kind === 'other-cart-marker') rememberPurchase(view.storage, operationId, cartId, '2');
    if (kind === 'broken-storage') view.storage.setItem(`pos-purchase:${cartId}:${operationId}`, '{broken');
    if (kind === 'disabled') view.disable();
    if (kind === 'get-failure') get.reject(new Error('network'));
    else if (kind === 'get-401') get.reject(new ApiError(401, 'expired', 'UNAUTHENTICATED'));
    else if (kind === 'get-503') get.reject(new ApiError(503, 'unknown', 'DB_UNAVAILABLE'));
    else get.resolve(state('3', kind === 'member-pending' ? { member_state: 'PENDING' } : kind === 'saving' ? { state: 'SAVING' } : kind === 'wrong-cart' ? { cart_id: operationId } : {}));
    assert.equal((await outcome).kind, 'stopped'); await view.settle();
    assert.equal(view.camera().allowed, false);
    if (kind === 'get-401') assert.equal(view.authentications, 1);
    view.unmount();
  });
}

for (const error of [new Error('network'), new ApiError(503, 'unknown', 'DB_UNAVAILABLE'), new ApiError(401, 'expired', 'UNAUTHENTICATED'), new ApiError(409, 'conflict', 'VERSION_CONFLICT')]) {
  test(`uncertain/unauthorized/conflicting update stops Camera: ${error.code ?? error.message}`, async () => {
    const { view, get, calls } = await setup(error);
    const outcome = view.camera().onCode('CODE'); await view.settle();
    assert.equal(view.camera().allowed, false);
    get.resolve(state()); await outcome; await view.settle();
    assert.equal(calls.filter(call => call.method === 'POST').length, 1, 'never automatically resend');
    if (error.status === 401) assert.equal(view.authentications, 1);
    view.unmount();
  });
}
