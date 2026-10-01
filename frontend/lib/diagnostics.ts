// Server only: fixed route templates, validated correlation ids and numeric status.
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
export function routeTemplate(path: string): string {
  if (/^(login|reauth|auth\/status|register\/(status|start|confirm)|resume|carts|purchases)$/.test(path)) return `/api/${path}`;
  if (/^(products|members)\/[A-Za-z0-9_-]{1,32}$/.test(path)) return `/api/${path.split('/')[0]}/{code}`;
  if (new RegExp(`^carts/${uuid}(/(purchase|sync|next|resolve-purchase|reopen|member|lines))?$`).test(path)) return `/api/${path.replace(new RegExp(uuid,'g'),'{cart_id}')}`;
  if (new RegExp(`^carts/${uuid}/(lines|operations)/${uuid}$`).test(path)) {
    const kind = path.split('/')[2]; return `/api/carts/{cart_id}/${kind}/{${kind === 'lines' ? 'line_id' : 'operation_id'}}`;
  }
  return 'UNKNOWN_ROUTE';
}
export function logRelay(path: string, requestId: string, elapsedMs: number, status: number, operationId: string | null = null) {
  const configured = process.env.POS_DEPLOYMENT_VERSION ?? 'UNSET';
  const version = /^[A-Za-z0-9_.-]{1,64}$/.test(configured) ? configured : 'INVALID';
  try {
    const emit = status >= 500 ? console.error : status >= 400 ? console.warn : console.info;
    emit(JSON.stringify({utc:new Date().toISOString(),request_id:requestId,operation_id:operationId,
      api:routeTemplate(path),elapsed_ms:Math.round(elapsedMs*100)/100,result_code:`HTTP_${status}`,db_error:'NOT_APPLICABLE',deployment_version:version}));
  } catch { /* Logging failure cannot determine DB save status. */ }
}
