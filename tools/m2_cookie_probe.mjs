// Isolated browser fixture only. No POS API, database, credentials, or recovery logic.
import https from 'node:https';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origin = new URL(process.env.M2_PROBE_ORIGIN ?? 'https://localhost:8453');
if (origin.protocol !== 'https:' || origin.username || origin.password ||
    origin.pathname !== '/' || origin.search || origin.hash) throw new Error('Exact HTTPS origin required');
// Public, deliberately fixed fixture. Never valid in the POS application.
const fixture = Buffer.alloc(32, 0x4d).toString('base64url');
const name = '__Host-pos_resume';
const invalidName = '__Host-m2_domain_probe';
const sameHostControl = 'm2_same_host_domain_control';
const parentControl = 'm2_parent_domain_control';
const page = `<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>M2 Cookie実機確認</title>
<style>body{font:17px/1.7 system-ui;max-width:680px;margin:32px auto;padding:0 20px}button{font:inherit;padding:12px;margin:6px 0;display:block}code{overflow-wrap:anywhere}pre{white-space:pre-wrap}</style>
<h1>M2 Cookie実機確認</h1>
<p>独立した試験ページです。DB・POS認証には接続していません。以下は公開可能な固定の試験値です。</p>
<p>名前：<code>${name}</code><br>値：<code>${fixture}</code></p>
<p>手動設定する属性：Secure、HttpOnly、SameSite=Lax、Path=/、Domain属性なし、期限30日相当。</p>
<button id="issue">1. 正常Cookieをサーバーから発行</button>
<button id="check">2. 現在のCookieを照合</button>
<button id="invalid">3. Domain付きの不正な別Cookieを試す</button>
<button id="control">4. Domain付きの通常Cookieを比較用に発行</button>
<p>Web Inspectorで復帰Cookieを削除→「2」で不一致確認→同じ名前・値・属性を手動で作成→「2」で再照合します。再読込・Chrome終了後にも「2」で確認します。</p>
<p>照合成功だけでは属性・host-onlyの合格になりません。属性と送信範囲の証拠を別に確認します。</p>
<pre id="result" role="status">未確認</pre>
<script src="/probe.js"></script></html>`;
const script = `const out=document.querySelector('#result');
async function run(action){
 try{
  if(action!=='check'){
   const response=await fetch('/'+action,{method:'POST',headers:{'X-M2-Probe':'1'},credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw new Error('HTTP '+response.status);
  }
  const response=await fetch('/check',{credentials:'same-origin',cache:'no-store'});
  if(!response.ok)throw new Error('HTTP '+response.status);
  const result=await response.json();
  result.resumeVisibleToJavaScript=document.cookie.split(';').some(item=>item.trim().startsWith('${name}='));
  out.textContent=JSON.stringify(result,null,2);
 }catch(error){out.textContent='照合失敗：'+error.message;}
}
for(const action of ['issue','check','invalid','control'])document.getElementById(action).onclick=()=>run(action);`;

const server = https.createServer({
  key: readFileSync(path.join(root, '.m2-local/tls/server.key')),
  cert: readFileSync(path.join(root, '.m2-local/tls/server.crt')),
}, (request, response) => {
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Referrer-Policy', 'no-referrer');
  const send = (status, value, type = 'application/json') => {
    response.writeHead(status, { 'Content-Type': `${type}; charset=utf-8` });
    response.end(type === 'application/json' ? JSON.stringify(value) : value);
  };
  if (request.method === 'GET' && request.url === '/') return send(200, page, 'text/html');
  if (request.method === 'GET' && request.url === '/probe.js') return send(200, script, 'application/javascript');
  if (request.method === 'GET' && request.url === '/check') {
    const pairs = (request.headers.cookie ?? '').split(';').map(value => value.trim());
    return send(200, {
      resumeMatchesFixture: pairs.includes(`${name}=${fixture}`),
      domainPrefixedCookieReceived: pairs.some(value => value.startsWith(`${invalidName}=`)),
      sameHostDomainControlMatchesFixture: pairs.includes(`${sameHostControl}=${fixture}`),
      parentDomainControlMatchesFixture: pairs.includes(`${parentControl}=${fixture}`),
      attributesVerified: false,
    });
  }
  if (request.method === 'POST' && ['/issue', '/invalid', '/control'].includes(request.url)) {
    if (request.headers.origin !== origin.origin || request.headers['x-m2-probe'] !== '1') return send(403, { allowed: false });
    const invalid = request.url === '/invalid';
    const control = request.url === '/control';
    response.setHeader('Set-Cookie', `${invalid ? invalidName : control ? sameHostControl : name}=${fixture}; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax${invalid || control ? `; Domain=${origin.hostname}` : ''}`);
    return send(200, { issued: true });
  }
  send(404, { found: false });
});
server.requestTimeout = 10000;
server.headersTimeout = 10000;
server.listen(8453, '127.0.0.1', () => console.log('M2 isolated cookie probe listening on 127.0.0.1:8453'));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
