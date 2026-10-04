// Execute the actual TSX event handlers with deterministic hooks and injected I/O.
// This observes Camera props; it is not a browser, React DOM, or video decoder test.
import fs from 'node:fs';
import vm from 'node:vm';
import { URL } from 'node:url';
import { setImmediate } from 'node:timers';
import ts from 'typescript';
import * as pos from '../../lib/pos.ts';

export function registerHarness(initial, transport, { reconcile = async () => initial } = {}) {
  const slots = []; let cursor = 0; let effects = []; let tree; let dirty = true;
  const listeners = new Map(); const channels = [];
  const storage = {
    values: new Map(),
    get length() { return this.values.size; },
    key(index) { return [...this.values.keys()][index] ?? null; },
    getItem(key) { return this.values.get(key) ?? null; },
    setItem(key, value) { this.values.set(key, value); },
    removeItem(key) { this.values.delete(key); },
  };
  const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
  const hooks = {
    useState(initialValue) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: initialValue };
      return [slots[index].value, value => {
        slots[index].value = typeof value === 'function' ? value(slots[index].value) : value;
        dirty = true;
      }];
    },
    useRef(value) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { current: value };
      return slots[index];
    },
    useCallback(callback, deps) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].deps, deps)) slots[index] = { callback, deps };
      return slots[index].callback;
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].deps, deps)) {
        effects.push(() => {
          slots[index]?.cleanup?.();
          slots[index] = { deps, cleanup: effect() };
        });
      }
    },
  };
  const Camera = Symbol('Camera');
  const jsx = (type, props) => ({ type, props });
  const module = { exports: {} };
  let authentications = 0; let enabled = true;
  const props = { initial, enabled, onNext() { throw new Error('Unexpected next'); }, onAuthentication() { authentications++; } };
  const code = ts.transpileModule(fs.readFileSync(new URL('../../app/register-cart.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, {
    exports: module.exports,
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === '../lib/pos') return { ...pos, api: transport };
      if (name === '../lib/recovery') return { Recovery: class { async reconcile() { return reconcile(storage); } } };
      if (name === './camera') return { default: Camera };
      if (name === '../lib/measurements') return { measure: () => () => {} };
      throw new Error(`Unexpected import ${name}`);
    },
    localStorage: storage, crypto: globalThis.crypto, Error: globalThis.Error,
    window: { addEventListener(name, fn) { listeners.set(name, fn); }, removeEventListener(name) { listeners.delete(name); } },
    BroadcastChannel: class {
      constructor() { channels.push(this); }
      postMessage() {} close() {}
    },
  }, { filename: 'register-cart.tsx' });
  function flush() {
    for (let limit = 0; dirty; limit++) {
      if (limit > 20) throw new Error('Render loop');
      dirty = false; cursor = 0; tree = module.exports.default(props);
      const pendingEffects = effects; effects = []; pendingEffects.forEach(run => run());
    }
  }
  function nodes(node) {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(child => nodes(child));
    return [node, ...nodes(node.props?.children)];
  }
  function text(node) {
    if (typeof node === 'string' || typeof node === 'number') return String(node);
    if (Array.isArray(node)) return node.map(text).join('');
    return node && typeof node === 'object' ? text(node.props?.children) : '';
  }
  return {
    storage, flush,
    async settle() { await new Promise(resolve => setImmediate(resolve)); flush(); },
    button(label) { return nodes(tree).find(node => node.type === 'button' && text(node.props.children) === label)?.props; },
    input(label) { return nodes(tree).find(node => node.type === 'label' && node.props.children?.[0] === label)?.props.children[1].props; },
    text() { return text(tree); },
    camera() { return nodes(tree).find(node => node.type === Camera)?.props; },
    messages() { return nodes(tree).filter(node => node.props?.role === 'status').map(node => node.props.children); },
    notify() { channels[0].onmessage(); flush(); },
    disable() { enabled = false; props.enabled = enabled; dirty = true; flush(); },
    get authentications() { return authentications; },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
