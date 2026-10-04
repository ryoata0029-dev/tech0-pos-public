// Actual Home/Register TSX handlers with fake hooks, browser storage and network.
// Child components remain boundaries; no React DOM, Chrome session or DB is used.
import fs from 'node:fs';
import vm from 'node:vm';
import { URL } from 'node:url';
import { setImmediate } from 'node:timers';
import ts from 'typescript';
import * as pos from '../../lib/pos.ts';
import { Recovery } from '../../lib/recovery.ts';

export function recoveryUiHarness(component, transport, initial) {
  const slots = []; let cursor = 0; let dirty = true; let effects = []; let tree;
  const values = new Map(); const storage = { get length() { return values.size; },
    key: i => [...values.keys()][i] ?? null, getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
  const hooks = {
    useState(value) { const i = cursor++; if (!slots[i]) slots[i] = { value };
      return [slots[i].value, next => { slots[i].value = typeof next === 'function' ? next(slots[i].value) : next; dirty = true; }]; },
    useRef(value) { const i = cursor++; if (!slots[i]) slots[i] = { current: value }; return slots[i]; },
    useCallback(callback, deps) { const i = cursor++; if (!slots[i] || !same(slots[i].deps, deps)) slots[i] = { callback, deps }; return slots[i].callback; },
    useEffect(effect, deps) { const i = cursor++; if (!slots[i] || !same(slots[i].deps, deps)) effects.push(() => { slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: effect() }; }); },
  };
  const Register = Symbol('Register'); const Camera = Symbol('Camera');
  const jsx = (type, props) => ({ type, props }); const module = { exports: {} };
  const next = []; let authentications = 0; let resets = 0;
  const props = { initial, enabled: true, onNext(value) { next.push(value); }, onAuthentication() { authentications++; } };
  const source = component === 'home' ? '../../app/page.tsx' : '../../app/register-cart.tsx';
  const code = ts.transpileModule(fs.readFileSync(new URL(source, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports: module.exports, localStorage: storage,
    crypto: globalThis.crypto, Error: globalThis.Error,
    document: { hidden: false, addEventListener() {}, removeEventListener() {} },
    window: { addEventListener() {}, removeEventListener() {} },
    BroadcastChannel: class { postMessage() {} close() {} },
    FormData: class { constructor(form) { this.values = form.values; } get(key) { return this.values[key]; } },
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === '../lib/pos') return { ...pos, api: transport };
      if (name === '../lib/recovery') return { Recovery: class extends Recovery { constructor() { super(transport); } } };
      if (name === './register-cart') return { default: Register };
      if (name === './camera') return { default: Camera };
      if (name === '../lib/measurements') return { measure: () => () => {} };
      throw new Error(`Unexpected import ${name}`);
    },
  }, { filename: source });
  function flush() { for (let count = 0; dirty; count++) {
    if (count > 20) throw new Error('Render loop'); dirty = false; cursor = 0;
    tree = module.exports.default(props); const pending = effects; effects = []; pending.forEach(run => run());
  } }
  function nodes(node) { if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(nodes); return [node, ...nodes(node.props?.children)]; }
  function text(node) { if (typeof node === 'string' || typeof node === 'number') return String(node);
    if (Array.isArray(node)) return node.map(text).join(''); return node && typeof node === 'object' ? text(node.props?.children) : ''; }
  async function settle() { await new Promise(resolve => setImmediate(resolve)); flush(); }
  return { storage, next, flush, settle,
    button(label) { return nodes(tree).find(node => node.type === 'button' && text(node.props.children) === label)?.props; },
    input(name) { return nodes(tree).find(node => node.type === 'input' && node.props.name === name)?.props; },
    cart() { return nodes(tree).find(node => node.type === Register)?.props; },
    messages() { return nodes(tree).filter(node => node.props?.role === 'status').map(node => text(node.props.children)); },
    text() { return text(tree); },
    async submit(staff) {
      const form = { values: { staff_id: staff, password: 'fake-test-password' }, reset() { resets++; } };
      await nodes(tree).find(node => node.type === 'form').props.onSubmit({ preventDefault() {}, currentTarget: form });
      await settle();
    },
    get authentications() { return authentications; }, get resets() { return resets; },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
