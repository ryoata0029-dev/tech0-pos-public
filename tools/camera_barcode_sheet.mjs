// Offline fixtures only. Validate generated bars with the installed ZXing readers.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const Code128Reader = require('@zxing/library/cjs/core/oned/Code128Reader').default;
const EAN13Reader = require('@zxing/library/cjs/core/oned/EAN13Reader').default;
const EAN8Reader = require('@zxing/library/cjs/core/oned/EAN8Reader').default;
const UPCEANReader = require('@zxing/library/cjs/core/oned/UPCEANReader').default;
const BitArray = require('@zxing/library/cjs/core/common/BitArray').default;
const output = path.join(root, 'docs/implementation/evidence/camera-preparation');
fs.mkdirSync(output, { recursive: true });

function runs(widths, black) {
  let result = '';
  for (const width of widths) { result += (black ? '1' : '0').repeat(width); black = !black; }
  return result;
}
function code128(text) {
  const values = [...text].map(char => char.charCodeAt(0) - 32);
  if (values.some(value => value < 0 || value > 94)) throw new Error('ASCII set B only');
  const checksum = values.reduce((sum, value, index) => sum + value * (index + 1), 104) % 103;
  return [104, ...values, checksum, 106].map(value => runs(Code128Reader.CODE_PATTERNS[value], true)).join('');
}
function ean(text) {
  const digits = [...text].map(Number);
  const body = digits.slice(0, -1);
  const checksum = (10 - body.reduce((sum, digit, index) => sum + digit * ((body.length - index) % 2 ? 3 : 1), 0) % 10) % 10;
  if (checksum !== digits.at(-1)) throw new Error('Invalid check digit');
  const left = text.length === 13 ? digits.slice(1, 7) : digits.slice(0, 4);
  const right = text.length === 13 ? digits.slice(7) : digits.slice(4);
  const parity = text.length === 13 ? EAN13Reader.FIRST_DIGIT_ENCODINGS[digits[0]] : 0;
  return '101' + left.map((digit, index) => {
    const widths = UPCEANReader.L_PATTERNS[digit];
    return runs((parity & (1 << (5 - index))) ? [...widths].reverse() : widths, false);
  }).join('') + '01010' + right.map(digit => runs(UPCEANReader.L_PATTERNS[digit], true)).join('') + '101';
}
const fixtures = [
  ['product-0001', 'Code128', '0001', '既存商品103円'],
  ['product-0002', 'Code128', '0002', '既存商品107円'],
  ['product-missing', 'Code128', 'PRODUCT_MISSING', '未登録商品'],
  ['member-0', 'Code128', 'MEMBER_0', '架空会員'],
  ['member-missing', 'Code128', 'MEMBER_MISSING', '不存在会員'],
  ['product-case', 'Code128', 'Ab_01', '大小文字保持用・専用fixture投入が必要'],
  ['product-ean13', 'EAN13', '0001234567895', 'EAN-13・専用fixture投入が必要'],
  ['product-ean8', 'EAN8', '00123457', 'EAN-8・専用fixture投入が必要'],
];
const records = [];
for (const [id, format, text, label] of fixtures) {
  const bits = '0'.repeat(15) + (format === 'Code128' ? code128(text) : ean(text)) + '0'.repeat(15);
  const row = new BitArray(bits.length);
  for (let index = 0; index < bits.length; index++) if (bits[index] === '1') row.set(index);
  const reader = format === 'Code128' ? new Code128Reader() : format === 'EAN13' ? new EAN13Reader() : new EAN8Reader();
  const decoded = reader.decodeRow(0, row, new Map()).getText();
  if (decoded !== text) throw new Error(`Roundtrip mismatch: ${id}`);
  const rectangles = [...bits].map((bit, index) => bit === '1' ? `<rect x="${index * 3}" y="12" width="3" height="100"/>` : '').join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${bits.length * 3} 140"><rect width="100%" height="100%" fill="white"/><g fill="black">${rectangles}</g><text x="${bits.length * 1.5}" y="134" font-family="monospace" font-size="16" text-anchor="middle">${text}</text></svg>\n`;
  fs.writeFileSync(path.join(output, `${id}.svg`), svg);
  records.push({ id, format, code: text, label, decoded, decoder: '@zxing/library 0.23.0', file: `${id}.svg` });
}
const cards = records.map(record => `<article><h2>${record.label}</h2><p>${record.format} / ${record.code}</p><img src="${record.file}" alt="${record.code}"></article>`).join('\n');
fs.writeFileSync(path.join(output, 'barcodes.html'), `<!doctype html><html lang="ja"><meta charset="utf-8"><title>POS試験バーコード</title><style>body{font-family:system-ui;margin:24px;background:white;color:black}article{max-width:760px;border:1px solid #bbb;padding:16px;margin:24px 0;break-inside:avoid}img{width:100%;height:160px;object-fit:contain}h2{font-size:18px}@media print{article{margin:12px 0}button{display:none}}</style><h1>POS試験バーコード</h1><p>架空データ専用。1枚ずつカメラに提示してください。SVG読取検証済みですが、実撮影の合格ではありません。</p>${cards}</html>\n`);
fs.writeFileSync(path.join(output, 'barcode-verification.json'), JSON.stringify({ at_utc: new Date().toISOString(), result: 'offline_decode_passed', real_camera_test: 'not_run', fixtures: records }, null, 2) + '\n');
console.log(JSON.stringify({ result: 'offline_decode_passed', fixtures: records.length, output }));
