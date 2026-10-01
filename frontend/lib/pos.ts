// Client state uses exact decimal versions. Only identifiers go into purchase storage.
export type Line = { line_id: string; line_no: number; code: string; name: string;
  quantity: number; unit_price: string; tax_rate: string; discount_per_unit: string;
  net_unit_price: string; line_subtotal: string };
export type Tax = { tax_rate: string; taxable_subtotal: string; tax_amount: string };
export type CartResult = { cart: { cart_id: string; version: string; staff_id: string;
  state: string; member_state: string; member_id: string | null; pending_member_id: string | null;
  lines: Line[]; subtotal: string; total: string; taxes: Tax[]; amounts_are_reference: boolean };
  purchase_status: string; purchase: { cart_id: string; subtotal: string; total: string;
    purchased_at: string; lines: Line[]; taxes: Tax[] } | null };
export type Operation = CartResult & { operation_id: string; operation_status: string;
  applied_version: string | null; code: string | null; new_cart_id?: string | null };
export class ApiError extends Error {
  status: number; code: string;
  constructor(status: number, message: string, code: string) { super(message); this.status = status; this.code = code; }
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/${path}`, { method, cache: 'no-store', credentials: 'same-origin',
    signal: AbortSignal.timeout(15000),
    headers: method === 'GET' ? {} : { 'X-POS-Request': '1', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok) throw new ApiError(response.status, value.message ?? '状態を確認できません。', value.code ?? 'UNKNOWN');
  return value as T;
}
export function newer(previous: CartResult | null, next: CartResult): CartResult {
  if (previous?.cart.cart_id === next.cart.cart_id && BigInt(previous.cart.version) > BigInt(next.cart.version)) return previous;
  return next;
}
const prefix = 'pos-purchase:';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export function purchaseKeys(storage: Storage, cartId: string): string[] {
  const keys: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (!key?.startsWith(prefix)) continue;
    const value = JSON.parse(storage.getItem(key) ?? 'null');
    if (!value || Object.keys(value).sort().join(',') !== 'cart_id,operation_id,version'
      || !uuid.test(value.cart_id) || !uuid.test(value.operation_id)
      || typeof value.version !== 'string' || !/^[1-9][0-9]{0,19}$/.test(value.version)
      || BigInt(value.version) > BigInt('18446744073709551615')
      || key !== `${prefix}${value.cart_id}:${value.operation_id}`) throw new Error('購入補助記録を確認できません。停止してください。');
    if (value.cart_id === cartId) keys.push(key);
  }
  return keys;
}
export function rememberPurchase(storage: Storage, cartId: string, operationId: string, version: string): void {
  const key = `${prefix}${cartId}:${operationId}`;
  const value = JSON.stringify({ cart_id: cartId, operation_id: operationId, version });
  storage.setItem(key, value);
  if (storage.getItem(key) !== value) throw new Error('購入補助記録を保存できません。');
}
export function clearSaved(storage: Storage, value: CartResult): void {
  if (value.purchase_status !== 'SAVED' || value.purchase?.cart_id !== value.cart.cart_id) return;
  for (const key of purchaseKeys(storage, value.cart.cart_id)) {
    const marker = JSON.parse(storage.getItem(key)!);
    if (BigInt(marker.version) < BigInt(value.cart.version)) storage.removeItem(key);
  }
}
export type PurchaseMarker = { cart_id: string; operation_id: string; version: string };
export function allPurchases(storage: Storage): PurchaseMarker[] {
  // purchaseKeys validates the entire namespace before any marker is acted upon.
  purchaseKeys(storage, '');
  const result: PurchaseMarker[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key?.startsWith(prefix)) result.push(JSON.parse(storage.getItem(key)!));
  }
  return result;
}
export function clearFenced(storage: Storage, value: Operation, cartId: string, operationId: string): void {
  if (value.operation_id !== operationId || value.cart.cart_id !== cartId
    || value.operation_status !== 'APPLIED' || value.applied_version === null) throw new Error('結果確認操作の対応を確認できません。');
  const memberFence = value.code === 'PURCHASE_FENCED_MEMBER_PENDING';
  if (!memberFence && value.purchase_status !== 'UNSAVED' && value.purchase_status !== 'SAVED') throw new Error('保存結果を確定できません。');
  for (const key of purchaseKeys(storage, cartId)) {
    const marker = JSON.parse(storage.getItem(key)!);
    if (BigInt(marker.version) < BigInt(value.applied_version)) storage.removeItem(key);
  }
}
export function mayRecoverInput(error: ApiError): boolean {
  return ['INVALID_INPUT','QUANTITY_LIMIT','PRODUCT_NOT_FOUND','LINE_NOT_FOUND','MEMBER_NOT_FOUND',
    'AMOUNT_INVALID','VERSION_CONFLICT','STATE_CONFLICT'].includes(error.code);
}

export function requireStable(storage: Storage, state: CartResult, started: number, notified: number): void {
  if (started !== notified || state.cart.state === 'SAVING' || allPurchases(storage).length) {
    throw new Error('新しい操作または購入記録があります。状態を再確認してください。');
  }
}
