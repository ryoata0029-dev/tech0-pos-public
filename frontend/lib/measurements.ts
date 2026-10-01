// Optional in-memory UI timings. No codes, identifiers, prices or credentials are captured.
export type Sample = { operation: 'PRODUCT' | 'MEMBER' | 'PURCHASE'; start_ms: number; display_ms: number; confirmed: true };
declare global { interface Window { __posMeasurements?: Sample[] } }
export function measure(operation: Sample['operation']): () => void {
  const started = performance.now();
  let finished = false;
  return () => {
    if (finished || process.env.NEXT_PUBLIC_POS_MEASUREMENTS !== '1') return;
    finished = true;
    // Finish after React's confirmed result has had a browser paint opportunity.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const rows = window.__posMeasurements ?? [];
      rows.push({operation,start_ms:started,display_ms:performance.now(),confirmed:true});
      window.__posMeasurements = rows.slice(-200);
    }));
  };
}
