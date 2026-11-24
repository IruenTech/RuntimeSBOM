#!/usr/bin/env python3
"""Bounded HTTP load generator; stdlib only. Intended for local/test endpoints."""
import argparse
import concurrent.futures
import json
import math
import statistics
import threading
import time
import urllib.request
from pathlib import Path


def quantile(sorted_ms, q):
    if not sorted_ms:
        return None
    at = (len(sorted_ms) - 1) * q
    low = int(math.floor(at)); high = int(math.ceil(at))
    return round(sorted_ms[low] + (sorted_ms[high] - sorted_ms[low]) * (at - low), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--duration', type=float, default=5)
    ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--timeout', type=float, default=2)
    ap.add_argument('--out', required=True)
    ap.add_argument('--expect', default='checksum=')
    ap.add_argument('--max-error-rate', type=float, default=0)
    args = ap.parse_args()
    if not (0.5 <= args.duration <= 3600 and 1 <= args.concurrency <= 64 and 0.1 <= args.timeout <= 30):
        ap.error('duration 0.5-3600, concurrency 1-64, timeout 0.1-30 required')
    if not args.url.startswith(('http://127.0.0.1:', 'http://localhost:')):
        ap.error('local test URL only; use an independent load tool for remote production-like environments')
    deadline = time.monotonic() + args.duration
    latencies = []; errors = []; total = 0; lock = threading.Lock()
    def worker():
        nonlocal total
        while time.monotonic() < deadline:
            start = time.perf_counter()
            ok = False; error = None
            try:
                with urllib.request.urlopen(args.url, timeout=args.timeout) as response:
                    payload = response.read(512).decode('utf-8', errors='replace')
                    ok = response.status == 200 and args.expect in payload
                    if not ok: error = 'unexpected-response'
            except Exception as exc:
                error = type(exc).__name__
            latency = (time.perf_counter() - start) * 1000
            with lock:
                total += 1
                if ok: latencies.append(latency)
                else: errors.append(error or 'unknown')
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(lambda _: worker(), range(args.concurrency)))
    elapsed = time.monotonic() - started
    sorted_ms = sorted(latencies)
    result = {'url': args.url, 'durationSeconds': round(elapsed, 3), 'concurrency': args.concurrency,
              'requests': total, 'success': len(sorted_ms), 'errors': len(errors),
              'errorRate': round(len(errors)/total if total else 1, 6),
              'tps': round(total / elapsed, 2), 'successTps': round(len(sorted_ms) / elapsed, 2),
              'latencyMs': {'p50': quantile(sorted_ms, 0.5), 'p95': quantile(sorted_ms, 0.95),
                            'p99': quantile(sorted_ms, 0.99), 'max': round(max(sorted_ms), 3) if sorted_ms else None},
              'errorSamples': errors[:10], 'validation': 'local-HTTP-fixture-not-WAS'}
    target = Path(args.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if result['errorRate'] > args.max_error_rate: raise SystemExit(3)

if __name__ == '__main__': main()
