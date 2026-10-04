// Isolated Mac-flow response-loss harness. Does not change app code or DB state.
import { createServer } from 'node:https';
import { readFileSync, existsSync, renameSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const profile = process.env.M2_LOCAL_PROFILE;
if (!['mac-flow','mac-recovery','mac-restart','mac-member','mac-tc03','mac-tc03-fix','mac-tc02','mac-batch','mac-parallel','parallel-next','parallel-mac-next','oct05-mac','iphone-camera'].includes(profile)) throw new Error('Dedicated Mac profiles only');
const local = `${root}.${profile}-local/`;
const evidence = `${root}docs/implementation/evidence/${profile}/`;
const frontendPort = profile === 'oct05-mac' ? 8463 : profile === 'parallel-mac-next' ? 8453 : 8443;
if (['parallel-mac-next','oct05-mac'].includes(profile) && (process.argv[2] !== '--pos-harness-profile' || process.argv[3] !== profile || process.argv[4] !== '--pos-harness-port' || process.argv[5] !== String(frontendPort))) throw new Error('Fixed Mac profile and port arguments required');
const app = require('next')({dev:false,dir:`${root}frontend`,hostname:'localhost',port:frontendPort});
await app.prepare();
const handler = app.getRequestHandler();
const control = `${local}drop-response.json`;
const server = createServer({key:readFileSync(`${local}tls/server.key`),cert:readFileSync(`${local}tls/server.crt`)}, (req,res)=>{
  const path = new URL(req.url,'https://localhost').pathname;
  if (profile === 'oct05-mac' && req.method === 'GET' && path === '/__oct05-recovery') {
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
    res.end(readFileSync(`${local}recovery-panel.html`)); return;
  }
  if (['mac-tc03','mac-tc03-fix','mac-batch','mac-parallel','parallel-next','parallel-mac-next','oct05-mac'].includes(profile) && req.method === 'GET' && path === '/__tc03') {
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
    res.end(readFileSync(`${root}tools/mac_tc03_panel.html`)); return;
  }
  let fault = null;
  if (existsSync(control)) {
    const config = JSON.parse(readFileSync(control,'utf8'));
    if (req.method === 'POST' && ((config.kind === 'purchase' && path === '/api/purchases')
      || (config.kind === 'next' && /^\/api\/carts\/[a-f0-9-]{36}\/next$/.test(path)))) {
      const tag = config.tag ?? config.kind;
      if (!/^[a-z0-9-]+$/.test(tag) || existsSync(`${evidence}response-loss-${tag}.json`)) throw new Error('Unsafe or reused fault tag');
      fault = {...config,tag};
      renameSync(control,`${local}drop-response-used-${tag}.json`);
    }
  }
  if (fault) {
    // Consume the real application's response, then sever the browser connection.
    // No response JSON, cookie/header or request body is written to evidence.
    const chunks = [];
    const collect = (chunk,encoding)=>{ if (chunk != null) chunks.push(Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk,typeof encoding==='string'?encoding:undefined)); };
    res.write = (chunk,encoding,callback)=>{ collect(chunk,encoding); (typeof encoding==='function'?encoding:callback)?.(); return true; };
    res.end = (chunk,encoding,callback)=>{
      collect(chunk,encoding);
      let value = {};
      try { value = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { /* Record classification only. */ }
      writeFileSync(`${evidence}response-loss-${fault.tag}.json`,JSON.stringify({kind:fault.kind,tag:fault.tag,method:req.method,path,status:res.statusCode,at:new Date().toISOString(),discardedAfterApplicationResponse:true,operation_id:value.operation_id,operation_status:value.operation_status,cart_id:value.cart?.cart_id,cart_state:value.cart?.state,purchase_status:value.purchase_status,new_cart_id:value.new_cart_id},null,2)+'\n',{flag:'wx'});
      res.destroy(); (typeof encoding==='function'?encoding:callback)?.(); return res;
    };
  }
  void handler(req,res);
});
server.listen(frontendPort,'127.0.0.1');
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>server.close(()=>process.exit(0)));
