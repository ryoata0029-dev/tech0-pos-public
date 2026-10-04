'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, CartResult } from '../lib/pos';
import RegisterCart from './register-cart';

type Auth = { authenticated: true; staff_id: string; expires_at: string };
type Register = { start_state: 'UNSTARTED' | 'COOKIE_PENDING' | 'READY'; maintenance_hold: boolean };

export default function Home() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [register, setRegister] = useState<Register | null>(null);
  const [cart, setCart] = useState<CartResult | null>(null);
  const [mode, setMode] = useState<'checking' | 'login' | 'ready' | 'stopped'>('checking');
  const [message, setMessage] = useState('認証状態を確認しています。');
  const [busy, setBusy] = useState(false);
  const [tabNotice, setTabNotice] = useState('');
  const [multipleTabs, setMultipleTabs] = useState(false);
  const inflight = useRef(false);
  const expectedStaff = useRef<string | null>(null);
  const requireAuthentication = useCallback(() => { setMode('login'); setMessage('元の担当者で再認証してください。'); }, []);

  async function inspect(submittedStaff?: string) {
    const current = await api<Auth>('auth/status');
    if ((submittedStaff && current.staff_id !== submittedStaff) || (expectedStaff.current && current.staff_id !== expectedStaff.current)) {
      throw new Error('担当者が一致しません。内容を保持して停止しました。');
    }
    expectedStaff.current = current.staff_id;
    setAuth(current);
    const state = await api<Register>('register/status');
    setRegister(state);
    if (state.start_state === 'READY') {
      try { setCart(await api<CartResult>('resume')); }
      catch (error) { if (!(error instanceof ApiError && error.status === 404)) throw error; }
    }
    setMode(state.maintenance_hold ? 'stopped' : 'ready');
    setMessage(state.maintenance_hold ? '保守停止中です。本人による確認を待ってください。' : '状態を確認しました。');
  }

  function fail(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      setMode('login'); setMessage(auth ? '元の担当者で再認証してください。' : '担当者IDまたはパスワードが正しくありません');
    } else {
      setMode('stopped');
      setMessage(error instanceof Error ? error.message : '状態を確認できません。停止しました。');
    }
  }

  async function act(work: () => Promise<void>) {
    if (inflight.current) return;
    inflight.current = true; setBusy(true);
    try { await work(); } catch (error) { fail(error); }
    finally { inflight.current = false; setBusy(false); }
  }

  useEffect(() => {
    let cancelled = false;
    // Initial mount only performs reads. No effect can create a context or a cart.
    api<Auth>('auth/status').then(async (current) => {
      if (cancelled) return;
      expectedStaff.current = current.staff_id; setAuth(current);
      const state = await api<Register>('register/status');
      if (cancelled) return;
      setRegister(state);
      if (state.start_state === 'READY') {
        try {
          const value = await api<CartResult>('resume');
          if (!cancelled) setCart(value);
        } catch (error) { if (!(error instanceof ApiError && error.status === 404)) throw error; }
      }
      if (!cancelled) {
        setMode(state.maintenance_hold ? 'stopped' : 'ready');
        setMessage(state.maintenance_hold ? '保守停止中です。' : '状態を確認しました。');
      }
    }).catch((error) => {
      if (cancelled) return;
      if (error instanceof ApiError && error.status === 401) {
        setMode('login'); setMessage('担当者IDとパスワードを入力してください。');
      } else fail(error);
    });
    let channel: BroadcastChannel | null = null;
    try { channel = new BroadcastChannel('pos-tabs'); }
    catch { setTabNotice('別タブの利用状況を確認できません。操作するタブを1つにしてください'); }
    const id = crypto.randomUUID();
    channel?.postMessage({ kind: 'hello', id });
    if (channel) channel.onmessage = (event) => {
      if (event.data?.id !== id && ['hello', 'present'].includes(event.data?.kind)) {
        setMultipleTabs(true);
        if (event.data.kind === 'hello') channel?.postMessage({ kind: 'present', id });
      }
    };
    const presence = () => { if (!document.hidden) channel?.postMessage({kind:'hello',id}); };
    document.addEventListener('visibilitychange',presence);
    return () => { cancelled = true; document.removeEventListener('visibilitychange',presence); channel?.postMessage({kind:'leaving',id}); channel?.close(); };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const staff = String(values.get('staff_id'));
    const password = String(values.get('password'));
    form.reset();
    await act(async () => {
      if (expectedStaff.current && expectedStaff.current !== staff) throw new Error('元の担当者で再認証してください。');
      try { await api<Auth>(auth ? 'reauth' : 'login', 'POST', { staff_id: staff, password }); }
      catch (error) {
        if (error instanceof ApiError && error.status < 500) throw error;
        // A lost authentication response is resolved by GET, never by an automatic POST retry.
      }
      await inspect(staff);
    });
  }

  async function update(path: string) {
    await act(async () => {
      try { await api(path, 'POST'); }
      catch (error) {
        if (error instanceof ApiError && error.status < 500 && error.status !== 409) throw error;
      }
      await inspect();
    });
  }

  return <main>
    <p className="eyebrow">Tech0 · 簡易POS</p>
    <h1>{mode === 'login' ? '担当者ログイン' : cart ? '商品登録・会計' : 'レジの利用開始'}</h1>
    <p role="status" aria-live="polite">{message}</p>
    {tabNotice && <p role="alert">{tabNotice}</p>}
    {multipleTabs && <p role="alert">複数のタブが開かれています。操作するタブを1つにしてください。</p>}
    {mode === 'login' && <form onSubmit={login}>
      <label>担当者ID<input name="staff_id" autoComplete="username" required pattern={'[A-Za-z0-9_\\-]{1,32}'} defaultValue={expectedStaff.current ?? ''} /></label>
      <label>パスワード<input name="password" type="password" autoComplete="current-password" required /></label>
      <button disabled={busy}>ログイン</button>
    </form>}
    {auth && <p>担当者：<strong>{auth.staff_id}</strong></p>}
    {cart && <RegisterCart key={cart.cart.cart_id} initial={cart} enabled={mode === 'ready'}
      onNext={setCart} onAuthentication={requireAuthentication} />}
    {mode === 'ready' && !cart && register?.start_state === 'UNSTARTED' && <button disabled={busy} onClick={() => update('register/start')}>このブラウザで利用開始</button>}
    {mode === 'ready' && register?.start_state === 'COOKIE_PENDING' && <button disabled={busy} onClick={() => update('register/confirm')}>Cookie受取を確認</button>}
    {mode === 'ready' && !cart && register?.start_state === 'READY' && <button disabled={busy} onClick={() => update('carts')}>初回カートを開く</button>}
    {mode !== 'checking' && !cart && <button className="secondary" disabled={busy} onClick={() => act(inspect)}>状態を再確認</button>}
  </main>;
}
