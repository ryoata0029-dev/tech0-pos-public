import assert from 'node:assert/strict';
import { test } from 'node:test';
import { routeTemplate } from '../lib/diagnostics.ts';
test('logs use templates and never echo member attributes, query strings or unknown paths', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  assert.equal(routeTemplate('members/PRIVATE_MEMBER'),'/api/members/{code}');
  assert.equal(routeTemplate(`carts/${id}/operations/${id}`),'/api/carts/{cart_id}/operations/{operation_id}');
  for (const path of ['members/private?secret=PASSWORD','unknown/PRIVATE',`carts/${id}/not-allowed`]) assert.equal(routeTemplate(path),'UNKNOWN_ROUTE');
});
