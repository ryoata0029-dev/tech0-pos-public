import type { CartResult, Operation } from './pos.ts';
import { api, allPurchases, clearFenced, clearSaved, purchaseKeys } from './pos.ts';

export type ConfirmRequest = { cart_id: string; operation_id: string; version: string };
export type Transport = typeof api;
// Held in memory until COMMIT is verified; a retry never replaces its expected version.
export class Recovery {
  confirmation: ConfirmRequest | null = null;
  sync: ConfirmRequest | null = null;
  private transport: Transport;
  constructor(transport: Transport = api) { this.transport = transport; }

  async reconcile(storage: Storage): Promise<CartResult> {
    const register = await this.transport<{ maintenance_hold: boolean }>('register/status');
    let state = await this.transport<CartResult>('resume');
    if (register.maintenance_hold) throw new Error('保守停止中です。本人による確認を待ってください。');
    // Old NEXT responses cannot hide unresolved markers belonging to a closed cart.
    for (const id of new Set(allPurchases(storage).map(marker => marker.cart_id))) {
      if (id === state.cart.cart_id) continue;
      const old = await this.transport<CartResult>(`carts/${id}/purchase`);
      if (old.purchase_status !== 'SAVED') throw new Error('前の取引の保存結果を確認できません。');
      clearSaved(storage, old);
      if (purchaseKeys(storage,id).length) throw new Error('前の取引の購入記録を確認できません。');
    }
    const id = state.cart.cart_id;
    if (state.purchase_status === 'SAVED') {
      clearSaved(storage, state);
      if (!purchaseKeys(storage,id).length) { this.confirmation = null; return state; }
    }
    if (this.confirmation || purchaseKeys(storage,id).length || state.cart.state === 'SAVING') {
      if (!this.confirmation) this.confirmation = { cart_id: id, operation_id: crypto.randomUUID(), version: state.cart.version };
      const request = this.confirmation;
      if (request.cart_id !== id) throw new Error('結果確認の対象が一致しません。');
      let result: Operation;
      try {
        const known = await this.transport<Operation>(`carts/${id}/operations/${request.operation_id}`);
        result = known.operation_status === 'APPLIED' ? known : await this.transport<Operation>(
          `carts/${id}/resolve-purchase`, 'POST', { operation_id:request.operation_id, version:request.version });
      } catch (error) {
        // VERSION_CONFLICT ends this confirmation, but is not proof that purchase was unsaved.
        if (error && typeof error === 'object' && 'code' in error && error.code === 'VERSION_CONFLICT') this.confirmation = null;
        throw error;
      }
      if (result.operation_id !== request.operation_id || result.cart.cart_id !== id || result.operation_status !== 'APPLIED') throw new Error('結果確認操作の対応を確認できません。');
      if (result.purchase_status === 'SAVED') clearSaved(storage, result);
      else clearFenced(storage,result,id,request.operation_id);
      if (purchaseKeys(storage,id).length) throw new Error('新しい購入記録が残っています。再確認してください。');
      this.confirmation = null;
      state = await this.transport<CartResult>('resume');
      // Re-fetch protects against an older success arriving after a newer purchase begins.
      if (state.cart.cart_id !== id) throw new Error('取引が切り替わりました。再確認してください。');
      if (purchaseKeys(storage,id).length || state.cart.state === 'SAVING') throw new Error('保存結果の再確認が必要です。');
    }
    if (state.cart.state === 'EDITING' && state.cart.member_state !== 'PENDING') {
      if (!this.sync) this.sync = { cart_id:id, operation_id:crypto.randomUUID(), version:state.cart.version };
      const request = this.sync;
      if (request.cart_id !== id) throw new Error('同期対象が一致しません。');
      try {
        const result = await this.transport<Operation>(`carts/${id}/sync`, 'POST', { operation_id:request.operation_id, version:request.version });
        if (result.operation_id !== request.operation_id || result.operation_status !== 'APPLIED') throw new Error('同期を確認できません。');
        state = result; this.sync = null;
      } catch (error) {
        if (error && typeof error === 'object' && 'code' in error && error.code === 'VERSION_CONFLICT') this.sync = null;
        throw error;
      }
    }
    if (state.purchase_status === 'SAVED') clearSaved(storage,state);
    if (state.cart.state === 'SAVING' || allPurchases(storage).length) throw new Error('新しい保存要求があります。状態を再確認してください。');
    return state;
  }
}
