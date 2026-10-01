import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Recovery } from '../lib/recovery.ts';
import { clearFenced, clearSaved, rememberPurchase } from '../lib/pos.ts';
const id = '11111111-1111-4111-8111-111111111111';
const op = '22222222-2222-4222-8222-222222222222';
class Store {
  data = new Map();
  get length() { return this.data.size; }
  key(i) { return [...this.data.keys()][i] ?? null; }
  getItem(k) { return this.data.get(k) ?? null; }
  setItem(k,v) { this.data.set(k,v); }
  removeItem(k) { this.data.delete(k); }
}
const state = (version='3', phase='UNSAVED', member='UNSPECIFIED') => ({cart: {cart_id:id,version,state:phase,member_state:member},purchase_status:phase === 'SAVED' ? 'SAVED' : phase === 'UNSAVED' ? 'UNSAVED' : 'UNKNOWN',purchase:phase === 'SAVED' ? {cart_id:id} : null});
test('lost confirmation reply retries original id and version without purchase or reopen', async () => {
  const store = new Store(); rememberPurchase(store,id,op,'1');
  const requests = []; let lost = true;
  const recovery = new Recovery(async (path,method,body) => {
    if (path === 'register/status') return {maintenance_hold:false};
    if (path === 'resume') return state();
    if (path.includes('/operations/')) return {operation_status:'NOT_FOUND'};
    assert.equal(path,`carts/${id}/resolve-purchase`);
    assert.equal(method,'POST'); requests.push(body);
    if (lost) { lost=false; throw new Error('lost after commit'); }
    return {...state('4'),operation_id:body.operation_id,operation_status:'APPLIED',applied_version:'4',code:null};
  });
  await assert.rejects(recovery.reconcile(store));
  assert.equal(store.length,1);
  await recovery.reconcile(store);
  assert.deepEqual(requests[0],requests[1]);
  assert.equal(store.length,0);
});
test('fence clears only older markers; delayed saved reply cannot clear a later purchase', () => {
  const store = new Store(); rememberPurchase(store,id,op,'1'); rememberPurchase(store,id,id,'5');
  clearFenced(store,{...state('6'),operation_id:op,operation_status:'APPLIED',applied_version:'3',code:null},id,op);
  assert.equal(store.length,1);
  clearSaved(store,state('4','SAVED'));
  assert.equal(store.length,1);
});
test('member-pending fence preserves pending and never synchronizes or purchases', async () => {
  const store = new Store(); rememberPurchase(store,id,op,'1'); let fenced=false;
  const recovery = new Recovery(async (path,method,body) => {
    if (path === 'register/status') return {maintenance_hold:false};
    if (path === 'resume') return state(fenced?'4':'3','EDITING','PENDING');
    if (path.includes('/operations/')) return {operation_status:'NOT_FOUND'};
    assert.equal(path,`carts/${id}/resolve-purchase`); fenced=true;
    return {...state('4','EDITING','PENDING'),operation_id:body.operation_id,operation_status:'APPLIED',applied_version:'4',code:'PURCHASE_FENCED_MEMBER_PENDING'};
  });
  const result = await recovery.reconcile(store);
  assert.equal(result.cart.member_state,'PENDING'); assert.equal(store.length,0);
});
test('maintenance, broken storage, or mismatched confirmation never permit editing', async () => {
  const store = new Store(); rememberPurchase(store,id,op,'1');
  const recovery = new Recovery(async path => path === 'register/status' ? {maintenance_hold:true} : state());
  await assert.rejects(recovery.reconcile(store)); assert.equal(store.length,1);
  assert.throws(() => clearFenced(store,{...state(),operation_id:id,operation_status:'APPLIED',applied_version:'3',code:null},id,op));
});

test('delayed sync receipt carrying current SAVING never enables the editor', async () => {
  const store = new Store();
  const recovery = new Recovery(async (path,method,body) => {
    if (path === 'register/status') return {maintenance_hold:false};
    if (path === 'resume') return state('3','EDITING');
    assert.equal(path,`carts/${id}/sync`);
    return {...state('5','SAVING'),operation_id:body.operation_id,operation_status:'APPLIED',applied_version:'4',code:null};
  });
  await assert.rejects(recovery.reconcile(store));
});
