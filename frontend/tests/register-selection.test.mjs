import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHarness } from './support/register-harness.mjs';

const initial = { cart: { cart_id: '11111111-1111-4111-8111-111111111111', version: '4',
  state: 'EDITING', member_state: 'UNSPECIFIED', member_id: null,
  lines: [{ line_id: 'line', code: '0001', name: '食品', quantity: 3,
    unit_price: '103', discount_per_unit: '0', line_subtotal: '309' }],
  taxes: [{ tax_rate: '0.10', tax_amount: '30' }], subtotal: '309', total: '339' },
  purchase_status: 'NOT_REQUESTED', purchase: null };

test('deselect discards only local selection and unsent quantity while preserving the cart and camera', async () => {
  const calls = [];
  const view = registerHarness(initial, async (...args) => { calls.push(args); return initial; });
  view.flush(); await view.settle();
  view.button('商品をカメラで読む').onClick(); view.flush();
  const before = view.text(); const camera = view.camera();
  assert.equal(view.button('選択解除'), undefined);
  view.button('食品').onClick(); view.flush();
  assert.ok(view.text().includes('食品（選択中）'));
  assert.ok(view.text().includes('選択商品：食品'));
  assert.equal(view.input('数量（1〜99）').value, '3');
  view.input('数量（1〜99）').onChange({ target: { value: '8' } }); view.flush();
  assert.equal(view.input('数量（1〜99）').value, '8');
  assert.equal(view.button('選択解除').disabled, false);
  view.button('選択解除').onClick(); view.flush();
  assert.equal(view.input('数量（1〜99）'), undefined);
  assert.equal(view.button('選択解除'), undefined);
  assert.equal(view.text(), before, 'lines, registered quantities, discounts, tax and totals remain unchanged');
  assert.equal(view.camera().mode, camera.mode);
  assert.equal(view.camera().allowed, camera.allowed);
  assert.equal(view.camera().onClose, camera.onClose);
  assert.equal(calls.length, 0, 'deselect does not send a cart update, purchase, or camera scan');
  view.button('食品').onClick(); view.flush();
  assert.equal(view.input('数量（1〜99）').value, '3', 'reselect starts from the server quantity, not the unsent 8');
  view.disable();
  assert.equal(view.button('選択解除').disabled, true, 'existing edit restrictions apply');
  view.unmount();
});
