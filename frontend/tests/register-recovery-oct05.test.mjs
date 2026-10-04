// Offline composition checks for the served fixture and current app handlers.
// Fake capacity/DOM/fetch here are not evidence of native Chrome storage faults.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { URL } from 'node:url';
import { performance } from 'node:perf_hooks';
import { setTimeout } from 'node:timers';
import { Recovery } from '../lib/recovery.ts';
import { registerHarness } from './support/register-harness.mjs';

const a = '11111111-1111-4111-8111-111111111111';
const b = '22222222-2222-4222-8222-222222222222';
const value = (id = a, state = 'EDITING', version = '2') => ({
  cart: { cart_id: id, staff_id: 'STAFF_A', state, version, member_state: 'UNSPECIFIED',
    member_id: null, pending_member_id: null, amounts_are_reference: false,
    lines: [{ line_id: 'line', code: '0001', name: '演習食品103円', quantity: 1,
      unit_price: '103', net_unit_price: '103', discount_per_unit: '0', line_subtotal: '103' }],
    subtotal: '103', total: '113', taxes: [] },
  purchase_status: state === 'SAVED' ? 'SAVED' : 'NOT_REQUESTED',
  purchase: state === 'SAVED' ? { cart_id: id, subtotal: '103', total: '113' } : null,
});
function store() {
  const values = new Map();
  return { values, get length() { return values.size; }, key: i => [...values.keys()][i] ?? null,
    getItem: key => values.get(key) ?? null, setItem: (key, data) => values.set(key, data),
    removeItem: key => values.delete(key) };
}
function panel(storage, fetchValue = async () => ({ status: 200, value: value() })) {
  const html = fs.readFileSync(new URL('../../tools/oct05_recovery_panel.html', import.meta.url), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = new Map(); const requests = [];
  const element = name => {
    if (!elements.has(name)) elements.set(name, { textContent: '', replaceChildren() {}, append() {} });
    return elements.get(name);
  };
  const context = vm.createContext({ localStorage: storage, crypto: globalThis.crypto, performance,
    AbortSignal: globalThis.AbortSignal, Date, JSON, Error, setTimeout,
    document: { querySelector: name => name === 'iframe' ? null : element(name),
      querySelectorAll: () => [], createElement: () => ({}) },
    fetch: async (path, options) => {
      requests.push({ path, method: options.method, body: options.body ? JSON.parse(options.body) : null });
      const result = await fetchValue(path, options);
      return { status: result.status, ok: result.status >= 200 && result.status < 300, json: async () => result.value };
    },
  });
  vm.runInContext(script, context, { filename: 'served-oct05-recovery-panel.js' });
  return { requests, run: code => vm.runInContext(code, context), text: () => element('#result').textContent };
}

test('served quota fixture makes current Register purchase stop before POST; cleanup restores only own filler', async () => {
  const calls = []; const view = registerHarness(value(), async (...args) => { calls.push(args); return value(); });
  view.flush(); await view.settle();
  view.storage.setItem('unrelated', 'retained');
  const write = view.storage.setItem.bind(view.storage);
  view.storage.setItem = (key, data) => {
    const bytes = [...view.storage.values].filter(([k]) => k !== key)
      .reduce((sum, [k, v]) => sum + k.length + v.length, 0) + key.length + data.length;
    if (bytes > 4096) throw new globalThis.DOMException('simulated quota', 'QuotaExceededError');
    write(key, data);
  };
  const fixture = panel(view.storage);
  await fixture.run('fill()');
  assert.match(fixture.text(), /purchase_sized_probe_failed/);
  view.button('購入確定').onClick(); await view.settle();
  assert.equal(calls.length, 0); assert.equal(view.button('購入確定').disabled, true);
  assert.ok(view.text().includes('113円')); assert.ok(view.text().includes('演習食品103円'));
  await fixture.run('clean()');
  assert.equal(view.storage.getItem('unrelated'), 'retained');
  assert.equal(view.storage.length, 1);
  view.unmount();
});

test('served multiple-key mismatch stops actual Recovery before any resolve/sync and preserves both records', async () => {
  const storage = store(); const fixture = panel(storage);
  await fixture.run('corrupt(true)'); const before = [...storage.values]; const calls = [];
  const recovery = new Recovery(async path => {
    calls.push(path);
    if (path === 'register/status') return { maintenance_hold: false };
    if (path === 'resume') return value();
    throw new Error('Unexpected resolution or update');
  });
  await assert.rejects(recovery.reconcile(storage), /購入補助記録/);
  assert.deepEqual(calls, ['register/status', 'resume']);
  assert.deepEqual([...storage.values], before); assert.equal(storage.length, 2);
});

test('fixture cleanup retains unknown B helper purchase identity without notifying the actual A UI or retrying', async () => {
  const storage = store(); let resumes = 0;
  const fixture = panel(storage, async (path, options) => {
    if (path === '/api/resume') {
      const current = ++resumes === 1 ? value(a, 'SAVED') : value(b);
      if (resumes > 1) current.cart.lines = [];
      return { status: 200, value: current };
    }
    if (path === `/api/carts/${b}/lines`) return { status: 200,
      value: { ...value(b), operation_status: 'APPLIED', operation_id: JSON.parse(options.body).operation_id } };
    assert.equal(path, '/api/purchases');
    return { status: 503, value: { code: 'DB_UNAVAILABLE', message: 'unknown' } };
  });
  await assert.rejects(fixture.run('advance()'), /503/);
  const before = [...storage.values]; assert.equal(before.length, 1);
  assert.match(before[0][0], /^oct05-recovery-pending:/);
  assert.ok(!before[0][0].startsWith('pos-purchase:'), 'do not trigger A storage-event navigation before the held NEXT response');
  assert.equal(JSON.parse(before[0][1]).cart_id, b);
  await fixture.run('clean()');
  assert.deepEqual([...storage.values], before);
  assert.equal(fixture.requests.filter(r => r.path === '/api/purchases').length, 1);
  assert.equal(fixture.requests.filter(r => /\/next$/.test(r.path)).length, 0);
});

test('served fixture refuses preexisting purchase records without overwriting or sending an update', async () => {
  const storage = store(); storage.setItem('pos-purchase:existing', 'retain-unknown');
  const fixture = panel(storage);
  await assert.rejects(fixture.run('fill()'), /既存/);
  await assert.rejects(fixture.run('corrupt(true)'), /既存/);
  assert.equal(storage.getItem('pos-purchase:existing'), 'retain-unknown');
  assert.equal(fixture.requests.length, 0);
});
