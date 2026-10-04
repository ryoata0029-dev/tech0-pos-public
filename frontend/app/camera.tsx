'use client';
import { useEffect, useRef, useState } from 'react';
import { MediaLease, ScanGate } from '../lib/scan-gate';

type Mode = 'product' | 'member';
export type ScanOutcome = { kind: 'confirmed' } | { kind: 'rejected'; message: string } | { kind: 'stopped' };
export default function Camera({ mode, allowed, onCode, onClose }: {
  mode: Mode; allowed: boolean; onCode: (code: string) => Promise<ScanOutcome>; onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const lease = useRef(new MediaLease());
  const controls = useRef<{stop: () => void} | null>(null);
  const gate = useRef(new ScanGate());
  const rejectedCode = useRef<string | null>(null);
  const handler = useRef(onCode);
  const permitted = useRef(allowed);
  const [message, setMessage] = useState('開始ボタンでカメラを許可してください。');
  const [running, setRunning] = useState(false);
  const [starting, setStarting] = useState(false);
  const startLock = useRef(false);
  useEffect(() => { handler.current = onCode; permitted.current = allowed; }, [onCode, allowed]);
  function stop() {
    lease.current.stop(); controls.current?.stop(); controls.current = null;
    if (video.current) video.current.srcObject = null;
  }
  useEffect(() => {
    const mediaLease = lease.current;
    const stopHidden = () => { if (document.hidden) { stop(); onClose(); } };
    document.addEventListener('visibilitychange', stopHidden);
    return () => { document.removeEventListener('visibilitychange', stopHidden); mediaLease.stop(); controls.current?.stop(); };
  }, [mode, onClose]);
  useEffect(() => { if (!allowed) { stop(); onClose(); } }, [allowed]);
  async function start() {
    if (!allowed || startLock.current || running) return;
    startLock.current = true; setStarting(true);
    const generation = lease.current.begin();
    try {
      const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType, NotFoundException }] = await Promise.all([
        import('@zxing/browser'), import('@zxing/library'),
      ]);
      if (!lease.current.valid(generation) || !permitted.current || document.hidden) return;
      const stream = await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'}}});
      if (!lease.current.attach(generation,stream)) return;
      if (!video.current || !permitted.current || document.hidden) { stop(); return; }
      const hints = new Map();
      hints.set(DecodeHintType.POSSIBLE_FORMATS,mode === 'member' ? [BarcodeFormat.CODE_128] : [BarcodeFormat.EAN_13,BarcodeFormat.EAN_8,BarcodeFormat.CODE_128]);
      const reader = new BrowserMultiFormatReader(hints, {delayBetweenScanAttempts:100,delayBetweenScanSuccess:100});
      const scanner = await reader.decodeFromStream(stream,video.current,(result,error) => {
        if (!lease.current.valid(generation) || !permitted.current || document.hidden) return;
        if (result) {
          const code = result.getText();
          if (gate.current.repeated(code) && rejectedCode.current !== code) setMessage('同じ商品です。追加する場合は一度枠から外してください。');
          if (!gate.current.detected(code)) return;
          rejectedCode.current = null;
          setMessage('読み取ったコードを確認しています。');
          // No queue and no automatic retry; onCode owns one immutable operation.
          void handler.current(code).then(outcome => {
            if (!lease.current.valid(generation) || !permitted.current || document.hidden) return;
            if (outcome.kind === 'stopped' || mode === 'member') { stop(); onClose(); }
            else if (outcome.kind === 'rejected') { rejectedCode.current = code; setMessage(outcome.message); }
            else setMessage('確認しました。次の商品を提示してください。');
          }).catch(() => { stop(); onClose(); }).finally(() => gate.current.completed());
        } else if (error instanceof NotFoundException) gate.current.absent(performance.now());
        else gate.current.interrupted();
        // A checksum/format failure is not proof of barcode absence.
      });
      if (!lease.current.valid(generation)) { scanner.stop(); return; }
      controls.current = scanner; setRunning(true); setMessage('コードをカメラに提示してください。');
    } catch {
      if (lease.current.valid(generation)) { stop(); setRunning(false); setMessage('カメラを開始できません。権限を確認するか手入力へ切り替えてください。'); }
    } finally { startLock.current = false; setStarting(false); }
  }
  return <section aria-label={mode === 'product' ? '商品カメラ' : '会員カメラ'}>
    <h3>{mode === 'product' ? '商品' : '会員'}のカメラ読取</h3>
    <video ref={video} autoPlay playsInline muted className="camera-preview" />
    <p role="status">{message}</p>
    <button disabled={!allowed || starting || running} onClick={() => void start()}>カメラ開始</button>
    <button className="secondary" onClick={() => { stop(); onClose(); }}>閉じて手入力へ</button>
  </section>;
}
