import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cameraHarness } from './support/camera-harness.mjs';
import { registerHarness } from './support/register-harness.mjs';
import { ApiError } from '../lib/pos.ts';

const initial = { cart: { cart_id: '11111111-1111-4111-8111-111111111111', version: '2',
  state: 'EDITING', member_state: 'UNSPECIFIED', lines: [], subtotal: '0', total: '0', taxes: [] },
  purchase_status: 'NOT_REQUESTED', purchase: null };
for (const [status, code, message] of [[404, 'PRODUCT_NOT_FOUND', '商品が登録されていません。'], [422, 'QUANTITY_LIMIT', '数量は99個までです。']]) {
  test(`actual register/Camera callbacks retain ${code} reason across repeated frames and accept the next product`, async () => {
    const requests = [];
    const cart = registerHarness(initial, async (path, method, body) => {
      requests.push({ path, method, body });
      if (method === 'POST' && body.code === 'REJECTED') throw new ApiError(status, message, code);
      if (method === 'POST') return { ...initial, operation_id: body.operation_id, operation_status: 'APPLIED' };
      return initial;
    });
    cart.flush(); await cart.settle(); cart.button('商品をカメラで読む').onClick(); cart.flush();
    const camera = cameraHarness(code => cart.camera().onCode(code)); await camera.start();
    await camera.detect('REJECTED'); await camera.settle(); await cart.settle();
    assert.equal(camera.message(), message);
    assert.equal(camera.closed, 0); assert.equal(camera.stoppedTracks, 0);
    for (let i = 0; i < 4; i++) await camera.detect('REJECTED');
    assert.equal(camera.message(), message, 'never replace rejection with confirmed/repeated-product text');
    assert.equal(requests.filter(request => request.method === 'POST').length, 1);
    await camera.detect('NEXT'); await cart.settle();
    assert.equal(camera.message(), '確認しました。次の商品を提示してください。');
    assert.equal(requests.filter(request => request.method === 'POST').length, 2);
    await camera.detect('NEXT');
    assert.equal(camera.message(), '同じ商品です。追加する場合は一度枠から外してください。');
    assert.equal(camera.closed, 0); camera.unmount(); cart.unmount();
  });
}

test('confirmed member closes; stopped product stops media and decoder', async () => {
  for (const [mode, outcome] of [['member', { kind: 'confirmed' }], ['product', { kind: 'stopped' }]]) {
    const camera = cameraHarness(async () => outcome, mode); await camera.start(); await camera.detect('CODE');
    assert.equal(camera.closed, 1); assert.equal(camera.stoppedTracks, 1); assert.equal(camera.stoppedDecoder, 1);
    camera.unmount();
  }
});

test('permission/state stop while a scan waits prevents a late outcome from restoring camera feedback', async () => {
  let complete;
  const pending = new Promise(resolve => { complete = resolve; });
  const camera = cameraHarness(async () => pending); await camera.start(); await camera.detect('CODE');
  camera.disable(); const message = camera.message();
  complete({ kind: 'confirmed' }); await camera.settle();
  assert.equal(camera.message(), message); assert.equal(camera.closed, 1); assert.equal(camera.stoppedTracks, 1);
  camera.unmount();
});
