// Execute the actual Camera TSX and decoder callback with fake media/ZXing I/O.
// No browser, camera permission, physical frames, or React DOM is exercised.
import fs from 'node:fs';
import vm from 'node:vm';
import { URL } from 'node:url';
import { setImmediate } from 'node:timers';
import ts from 'typescript';
import * as scanning from '../../lib/scan-gate.ts';

export function cameraHarness(onCode, mode = 'product') {
  const slots = []; let cursor = 0; let dirty = true; let effects = []; let tree;
  let decoder; let closed = 0; let stoppedTracks = 0; let stoppedDecoder = 0;
  const listeners = new Map(); const video = { srcObject: null };
  const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
  const hooks = {
    useState(value) {
      const i = cursor++; if (!slots[i]) slots[i] = { value };
      return [slots[i].value, next => { slots[i].value = next; dirty = true; }];
    },
    useRef(value) { const i = cursor++; if (!slots[i]) slots[i] = { current: value }; return slots[i]; },
    useEffect(effect, deps) {
      const i = cursor++;
      if (!slots[i] || !same(slots[i].deps, deps)) effects.push(() => {
        slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: effect() };
      });
    },
  };
  const jsx = (type, props) => {
    if (type === 'video') props.ref.current = video;
    return { type, props };
  };
  class NotFoundException extends Error {}
  const document = { hidden: false,
    addEventListener(name, callback) { listeners.set(name, callback); },
    removeEventListener(name) { listeners.delete(name); } };
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(new URL('../../app/camera.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, {
    exports: module.exports, document, performance: globalThis.performance,
    navigator: { mediaDevices: { async getUserMedia() { return { getTracks: () => [{ stop() { stoppedTracks++; } }] }; } } },
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === '../lib/scan-gate') return scanning;
      if (name === '@zxing/library') return { NotFoundException, BarcodeFormat: { CODE_128: 1, EAN_13: 2, EAN_8: 3 }, DecodeHintType: { POSSIBLE_FORMATS: 1 } };
      if (name === '@zxing/browser') return { BrowserMultiFormatReader: class {
        async decodeFromStream(stream, target, callback) {
          if (target !== video || typeof stream.getTracks !== 'function') throw new Error('Unexpected media target');
          decoder = callback; return { stop() { stoppedDecoder++; } };
        }
      } };
      throw new Error(`Unexpected import ${name}`);
    },
  }, { filename: 'camera.tsx' });
  const props = { mode, allowed: true, onCode, onClose() { closed++; } };
  function flush() {
    for (let count = 0; dirty; count++) {
      if (count > 20) throw new Error('Render loop');
      dirty = false; cursor = 0; tree = module.exports.default(props);
      const pending = effects; effects = []; pending.forEach(run => run());
    }
  }
  function nodes(node) {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(nodes);
    return [node, ...nodes(node.props?.children)];
  }
  async function settle() { await new Promise(resolve => setImmediate(resolve)); flush(); }
  flush();
  return {
    async start() { nodes(tree).find(node => node.type === 'button' && node.props.children === 'カメラ開始').props.onClick(); await settle(); },
    async detect(code) { decoder({ getText: () => code }); await settle(); },
    settle,
    message() { return nodes(tree).find(node => node.props?.role === 'status').props.children; },
    disable() { props.allowed = false; dirty = true; flush(); },
    get closed() { return closed; },
    get stoppedTracks() { return stoppedTracks; },
    get stoppedDecoder() { return stoppedDecoder; },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
