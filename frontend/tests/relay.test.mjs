/* global process, Request, Headers, Response */
import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import { allowed, relay } from '../lib/relay.ts';

const originalFetch = globalThis.fetch;
const saved = { ...process.env };
after(() => { globalThis.fetch = originalFetch; process.env = saved; });
process.env.POS_BACKEND_URL = 'https://backend.example.invalid';
process.env.POS_FRONTEND_ORIGIN = 'https://pos.example.invalid';
process.env.POS_RELAY_SECRET = 'test-only-server-relay-not-real-secret';
const request = (method = 'GET', path = 'auth/status', headers = {}) => new Request(
  `https://pos.example.invalid/api/${path}`, { method, headers });

test('allowlist rejects unexpected paths and methods', () => {
  assert.equal(allowed('POST', 'login'), true);
  assert.equal(allowed('GET', 'products/0001'), true);
  for (const path of ['../login', 'https://evil.invalid', 'products/a/b', 'carts//'])
    assert.equal(allowed('GET', path), false);
  assert.equal(allowed('DELETE', 'carts'), false);
});

test('relay overwrites spoofed secret and preserves multiple Set-Cookie headers', async () => {
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(String(url), 'https://backend.example.invalid/api/auth/status');
    assert.equal(options.headers.get('x-pos-relay'), process.env.POS_RELAY_SECRET);
    assert.equal(options.headers.get('host'), null);
    assert.equal(options.cache, 'no-store');
    assert.equal(options.redirect, 'manual');
    const headers = new Headers({ 'Content-Type': 'application/json' });
    headers.append('Set-Cookie', '__Host-pos_session=test; Secure; HttpOnly; Path=/; SameSite=Lax');
    headers.append('Set-Cookie', '__Host-pos_resume=test; Secure; HttpOnly; Path=/; SameSite=Lax');
    return new Response('{}', { status: 200, headers });
  };
  const response = await relay(request('GET', 'auth/status', { 'x-pos-relay': 'spoofed', 'host': 'evil.invalid' }), 'auth/status');
  assert.equal(response.status, 200);
  assert.equal(response.headers.getSetCookie().length, 2);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(calls, 1);
});

test('bad origin and missing marker cause no upstream call', async () => {
  globalThis.fetch = async () => { throw new Error('must not call'); };
  for (const headers of [{}, { origin: 'null', 'x-pos-request': '1' },
    { origin: 'https://pos.example.invalid' }, { origin: 'https://pos.example.invalid/', 'x-pos-request': '1' }]) {
    const response = await relay(request('POST', 'login', headers), 'login');
    assert.equal(response.status, 403);
  }
});

test('transport failure is sanitized and is never retried', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error('PRIVATE-CREDENTIAL'); };
  const response = await relay(request('POST', 'login', { origin: process.env.POS_FRONTEND_ORIGIN, 'x-pos-request': '1' }), 'login');
  assert.equal(response.status, 503);
  assert.equal(calls, 1);
  assert.equal((await response.text()).includes('PRIVATE-CREDENTIAL'), false);
});

test('redirect and insecure upstream fail closed', async () => {
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { location: 'https://evil.invalid' } });
  assert.equal((await relay(request(), 'auth/status')).status, 503);
  process.env.POS_BACKEND_URL = 'http://backend.example.invalid';
  assert.equal((await relay(request(), 'auth/status')).status, 503);
});

test('M3 relay forwards DELETE query once and rejects extra or duplicate fields', async () => {
  process.env.POS_BACKEND_URL = 'https://backend.example.invalid';
  const id = '11111111-1111-4111-8111-111111111111';
  const path = `carts/${id}/lines/${id}`;
  const query = `operation_id=${id}&version=9007199254740993`;
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++; assert.equal(String(url), `https://backend.example.invalid/api/${path}?${query}`);
    assert.equal(options.method, 'DELETE'); return new Response('{}');
  };
  const headers = { origin: process.env.POS_FRONTEND_ORIGIN, 'x-pos-request': '1' };
  assert.equal((await relay(request('DELETE', `${path}?${query}`, headers), path)).status, 200);
  for (const suffix of ['&price=1', '&version=2']) {
    assert.equal((await relay(request('DELETE', `${path}?${query}${suffix}`, headers), path)).status, 422);
  }
  assert.equal(calls, 1);
  for (const [method, route] of [['POST', `carts/${id}/lines`], ['PUT', `carts/${id}/member`], ['PATCH',path], ['POST','purchases'], ['GET', `carts/${id}/operations/${id}`]]) assert.equal(allowed(method, route), true);
  assert.equal(allowed('POST', `carts/${id}/reopen`), true);
});
