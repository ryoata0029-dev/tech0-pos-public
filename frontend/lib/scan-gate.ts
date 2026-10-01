// A single accepted code remains latched until another code or uninterrupted absence.
export class ScanGate {
  private last: string | null = null;
  private absentSince: number | null = null;
  private busy = false;
  absent(now: number) {
    if (this.busy) { this.absentSince = null; return; }
    if (this.absentSince === null) this.absentSince = now;
    if (now - this.absentSince >= 500) this.last = null;
  }
  detected(code: string): boolean {
    this.absentSince = null;
    if (this.busy || !/^[A-Za-z0-9_-]{1,32}$/.test(code) || code === this.last) return false;
    this.last = code; this.busy = true; return true;
  }
  repeated(code: string) { return !this.busy && this.last === code; }
  interrupted() { this.absentSince = null; }
  completed() { this.busy = false; this.absentSince = null; }
}
// Stop late permission results even if the view closed before getUserMedia resolved.
export class MediaLease {
  private generation = 0;
  private stream: MediaStream | null = null;
  begin(): number { this.stop(); return this.generation; }
  attach(generation: number, stream: MediaStream): boolean {
    if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); return false; }
    this.stream = stream; return true;
  }
  stop() { this.generation++; this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; }
  valid(generation: number) { return this.generation === generation; }
}
