import { logRelay } from './diagnostics.ts';
// Server-only relay policy. Requests cannot supply upstream host or relay credentials.
const code = '[A-Za-z0-9_-]{1,32}';
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
export function allowed(method: string, path: string): boolean {
  if (method === 'POST') return /^(login|reauth|register\/(start|confirm)|carts|purchases)$/.test(path)
    || new RegExp(`^carts/${uuid}/(lines|sync|next|resolve-purchase|reopen)$`).test(path);
  if (method === 'PATCH' || method === 'DELETE') return new RegExp(`^carts/${uuid}/lines/${uuid}$`).test(path);
  if (method === 'PUT') return new RegExp(`^carts/${uuid}/member$`).test(path);
  return method === 'GET' && (['auth/status', 'register/status', 'resume'].includes(path)
    || new RegExp(`^(products|members)/${code}$`).test(path)
    || new RegExp(`^carts/${uuid}(/purchase|/operations/${uuid})?$`).test(path));
}

async function forward(request: Request, path: string): Promise<Response> {
  const fail = (status: number, code: string, message: string) => Response.json(
    { code, message }, { status, headers: { 'Cache-Control': 'no-store' } },
  );
  if (!allowed(request.method, path)) return fail(404, 'NOT_FOUND', '対象の操作は利用できません。');
  const backend = process.env.POS_BACKEND_URL;
  const secret = process.env.POS_RELAY_SECRET;
  const origin = process.env.POS_FRONTEND_ORIGIN;
  if (!backend || !secret || !origin) return fail(503, 'SERVICE_UNAVAILABLE', '接続設定を確認してください。');
  try {
    const target = new URL(backend);
    const expected = new URL(origin);
    if (target.protocol !== 'https:' || target.username || target.password || target.search
      || target.hash || target.pathname !== '/' || expected.protocol !== 'https:'
      || expected.origin !== origin || secret.length < 32) throw new Error('configuration');
    if (request.method !== 'GET' && (request.headers.get('origin') !== origin
      || request.headers.get('x-pos-request') !== '1')) {
      return fail(403, 'FORBIDDEN', '送信元を確認できません。');
    }
    const query = new URL(request.url).searchParams;
    if (request.method === 'DELETE') {
      if ([...query].length !== 2 || !query.has('operation_id') || !query.has('version')) return fail(422, 'INVALID_INPUT', '削除の入力形式を確認してください。');
    } else if (query.size) return fail(422, 'INVALID_INPUT', '未定義の入力です。');
    const headers = new Headers({ 'X-POS-Relay': secret });
    for (const key of ['cookie', 'origin', 'x-pos-request', 'content-type']) {
      const value = request.headers.get(key);
      if (value !== null) headers.set(key, value);
    }
    const upstream = await fetch(new URL(`/api/${path}${query.size ? `?${query}` : ''}`, target), {
      method: request.method, headers,
      body: request.method === 'GET' ? undefined : await request.arrayBuffer(),
      cache: 'no-store', redirect: 'manual', signal: AbortSignal.timeout(10000),
    });
    if (upstream.status >= 300 && upstream.status < 400) throw new Error('redirect');
    const outgoing = new Headers({ 'Cache-Control': 'no-store', 'Content-Type': 'application/json' });
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append('Set-Cookie', cookie);
    // Buffer before returning so a truncated response never appears to be a successful reply.
    return new Response(await upstream.arrayBuffer(), { status: upstream.status, headers: outgoing });
  } catch {
    return fail(503, 'SERVICE_UNAVAILABLE', '状態を確認できません。内容を保持して停止してください。');
  }
}

export async function relay(request: Request, path: string): Promise<Response> {
  const started = performance.now();
  const id = crypto.randomUUID();
  let status = 503;
  let operationId: string | null = null;
  try {
    try {
      const candidate = request.method === 'DELETE' ? new URL(request.url).searchParams.get('operation_id') : (await request.clone().json()).operation_id;
      if (typeof candidate === 'string' && new RegExp(`^${uuid}$`).test(candidate)) operationId = candidate;
    } catch { /* No correlation is better than logging unvalidated input. */ }
    if (request.method === 'GET' && new RegExp(`^carts/${uuid}/operations/${uuid}$`).test(path)) operationId = path.split('/')[3];
    const response = await forward(request,path);
    status = response.status; response.headers.set('X-POS-Request-ID',id);
    return response;
  } finally { logRelay(path,id,performance.now()-started,status,operationId); }
}
