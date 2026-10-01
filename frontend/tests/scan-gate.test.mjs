import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ScanGate, MediaLease } from '../lib/scan-gate.ts';
test('same code never repeats by time alone; different code unlocks', () => {
  const gate = new ScanGate(); assert.equal(gate.detected('0001'),true); gate.completed();
  for (let i=0;i<100;i++) assert.equal(gate.detected('0001'),false);
  assert.equal(gate.detected('0002'),true); gate.completed(); assert.equal(gate.detected('0001'),true);
});
test('absence must be continuous for 500ms and excludes API busy interval', () => {
  const gate = new ScanGate(); gate.detected('A'); gate.absent(0); gate.absent(5000);
  assert.equal(gate.detected('B'),false); gate.completed();
  gate.absent(5001); gate.absent(5500); assert.equal(gate.detected('A'),false);
  gate.absent(5600); gate.absent(6100); assert.equal(gate.detected('A'),true);
});
test('whole ASCII code only; no trim or queued detection', () => {
  const gate = new ScanGate();
  for (const code of [' A','A\n','あ','A'.repeat(33),'']) assert.equal(gate.detected(code),false);
  assert.equal(gate.detected('ABC_01-'),true); assert.equal(gate.detected('NEXT'),false);
});
test('late media permission and attached streams stop on close', () => {
  const lease = new MediaLease(); let stopped=0;
  const stream = {getTracks:()=>[{stop:()=>stopped++}]};
  const first=lease.begin(); lease.stop(); assert.equal(lease.attach(first,stream),false);
  const second=lease.begin(); assert.equal(lease.attach(second,stream),true); lease.stop();
  assert.equal(stopped,2); assert.equal(lease.valid(second),false);
});

test('checksum/format failure interrupts absence rather than proving an empty frame', () => {
  const gate = new ScanGate(); gate.detected('A'); gate.completed();
  gate.absent(0); gate.interrupted(); gate.absent(501);
  assert.equal(gate.detected('A'),false);
  gate.absent(600); gate.absent(1100); assert.equal(gate.detected('A'),true);
});
