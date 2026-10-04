import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError } from '../lib/pos.ts';
import { recoveryUiHarness } from './support/recovery-ui-harness.mjs';

test('actual Home staff input has a valid HTML v pattern for the unchanged ASCII ID contract', async () => {
  const view = recoveryUiHarness('home', async path => {
    assert.equal(path, 'auth/status'); throw new ApiError(401, 'login required', 'UNAUTHENTICATED');
  });
  view.flush(); await view.settle();
  const input = view.input('staff_id');
  assert.equal(input.required, true);
  // HTML pattern uses v and checks the entire field. Require end of input explicitly
  // here so the Node companion does not accept a trailing newline via JS `$`.
  const pattern = new RegExp(`^(?:${input.pattern})(?![\\s\\S])`, 'v');
  for (const value of ['A', '0', '_', '-', '00Aa_Zz-9', 'A'.repeat(32)]) assert.equal(pattern.test(value), true, value);
  for (const value of ['', 'A'.repeat(33), 'A B', 'A\n', ' A', 'A ', 'Ａ', 'あ', 'A/B', 'A\\B', 'A|B', 'A[B]']) assert.equal(pattern.test(value), false, value);
  view.unmount();
});
