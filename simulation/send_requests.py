"""Send requests through the load balancer and show where each one went.

Usage (from the project root, with the stack running):
  python simulation/send_requests.py
  python simulation/send_requests.py -n 50 --interval 0.05
  python simulation/send_requests.py -n 200 --workers 10

Prints one line per request, then a summary per backend. Uses only the
standard library.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


def send(i, url, timeout):
    """Send one request; return (index, backend, status, latency_ms)."""
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read())
            status = resp.status
    except urllib.error.HTTPError as e:
        # The server answered with an error status (e.g. 500 from a backend,
        # or 503 from Envoy when it has no healthy backend).
        status = e.code
        try:
            body = json.loads(e.read())
        except ValueError:
            body = {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        latency = (time.perf_counter() - start) * 1000
        return i, f"UNREACHABLE ({getattr(e, 'reason', e)})", 0, latency
    latency = (time.perf_counter() - start) * 1000
    return i, body.get("backend", "unknown"), status, latency


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8080/hello", help="address of the load balancer")
    p.add_argument("-n", "--count", type=int, default=20, help="number of requests (default 20)")
    p.add_argument("--interval", type=float, default=0.0, help="seconds to wait between requests when --workers is 1")
    p.add_argument("--workers", type=int, default=1, help="parallel requests (default 1)")
    p.add_argument("--timeout", type=float, default=5.0, help="per-request timeout in seconds")
    args = p.parse_args()

    print(f"Sending {args.count} requests to {args.url} (workers={args.workers})\n")
    stats = defaultdict(lambda: {"count": 0, "errors": 0, "latency": 0.0})

    def record(result):
        i, backend, status, latency = result
        ok = 200 <= status < 300
        print(f"[{i:>3}] -> {backend:<14} status={status or '---':<4} {latency:7.1f} ms {'' if ok else '  <-- FAILED'}")
        s = stats[backend]
        s["count"] += 1
        s["latency"] += latency
        if not ok:
            s["errors"] += 1

    started = time.perf_counter()
    if args.workers <= 1:
        for i in range(1, args.count + 1):
            record(send(i, args.url, args.timeout))
            if args.interval:
                time.sleep(args.interval)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for result in pool.map(lambda i: send(i, args.url, args.timeout), range(1, args.count + 1)):
                record(result)
    elapsed = time.perf_counter() - started

    print("\n" + "=" * 62)
    print(f"{'backend':<16}{'requests':>9}{'share':>8}{'errors':>8}{'avg ms':>10}")
    print("-" * 62)
    for backend in sorted(stats):
        s = stats[backend]
        share = 100 * s["count"] / args.count
        print(f"{backend:<16}{s['count']:>9}{share:>7.1f}%{s['errors']:>8}{s['latency'] / s['count']:>10.1f}")
    print("-" * 62)
    print(f"total {args.count} requests in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
