# AI-Enabled Variable Load Balancer for Multi-Cloud

A multi-cloud L7/L4 load balancer built on **Envoy**, with a custom **control plane** and an **AI engine** that adjusts traffic weights dynamically across AWS, Azure and GCP.

---

## 1. Goals

- Distribute traffic across multiple clouds with **variable** (dynamically changing) weights.
- Fail over between clouds automatically and safely.
- Use AI (forecasting, anomaly detection, cost/latency optimization) to tune routing, **off the request path**.
- Learn AI engineering along the way, using hardware that can run locally (RTX 4050 6 GB, 16 GB RAM).

### Non-goals

- No model call per request (adds latency and a failure point).
- No LLM making routing decisions (too slow and non-deterministic).
- No custom proxy written from scratch. Envoy is the data plane.

---

## 2. Architecture

```
Clients
   │
Global steering (Route 53 / Cloudflare / Cloud DNS)
   │
   ├──► Envoy fleet (AWS)   ─┐
   ├──► Envoy fleet (Azure) ─┼──► Backends in each cloud
   └──► Envoy fleet (GCP)   ─┘
          ▲            │
          │ xDS        │ metrics
          │            ▼
   Control plane   Telemetry store (Prometheus)
   (Go)                │
          ▲            ▼
          └──── AI engine (Python): forecast + anomaly + optimizer
                       │
                Guardrails / safety layer
```

| Component | Tech | Role |
|---|---|---|
| Data plane | Envoy | Proxying, health checks, outlier detection, LB algorithms |
| Control plane | Go + `go-control-plane` | Serves CDS/EDS/RDS/LDS over xDS, applies weights |
| AI engine | Python (scikit-learn, statsmodels, PyTorch) | Forecasts, anomaly detection, weight recommendations |
| Guardrails | Control plane module | Bounds and validates every AI decision |
| Telemetry | Prometheus + Grafana | Metrics and dashboards |
| Decision log | Postgres or JSON lines | Audit trail of every weight change |
| Global steering | DNS provider | Cross-cloud failover |

---

## 3. Key Design Principles

1. **AI is advisory and off the hot path.** Envoy only receives weights over xDS every few seconds.
2. **Guardrails always win.** Max weight change per interval (e.g. 10%), minimum share per healthy cloud, hard caps.
3. **Safe fallback.** If the AI engine fails or misbehaves, revert to static or heuristic weights automatically. A kill switch must exist.
4. **Shadow mode before active mode.** Log what the AI would do, compare with the real policy, then enable it.
5. **Baselines first.** ML must beat a tuned least-request policy and a simple heuristic scorer before it goes live.
6. **Everything auditable.** Every decision is logged with its inputs, output and reason.

---

## 4. Routing Features

- Built-in algorithms: round robin, least request, ring hash, Maglev (switchable per cluster via xDS).
- Locality-weighted load balancing: prefer the local cloud, spill over on failure.
- Weighted clusters and endpoint weights, updated dynamically.
- Active health checks plus passive outlier ejection.
- Retries, timeouts, circuit breaking.
- Optional: L4 (TCP/UDP) listeners.
- Optional: custom algorithm via Wasm or Lua filter (only if built-ins aren't enough).

---

## 5. AI Capabilities

| Capability | Approach | Phase |
|---|---|---|
| Heuristic scoring | Weighted score of latency, error rate, saturation, cost | 4 |
| Anomaly detection | EWMA and z-score first, then Isolation Forest | 5 |
| Traffic forecasting | Prophet / SARIMA, then gradient boosting or LSTM | 5 |
| Cost-aware routing | Optimize performance per dollar, including egress costs | 6 |
| Adaptive weights | Contextual bandit with bounded exploration | 6 |
| Autoscaling hints | Forecast-driven capacity recommendations | 7 |
| Operator assistant (optional) | Small local LLM (Llama 3.2 3B via Ollama) explaining traffic shifts | 7 |

Reinforcement learning is deferred. If used, it only runs in simulation first.

---

## 6. Phased Roadmap

### Phase 0: Environment setup
- Install Docker Desktop, Go, Python 3.11+, Git, Ollama.
- Verify the GPU with `ollama run llama3.2:3b`.
- Create the repo structure (see section 8).

### Phase 1: Envoy basics
- Run one Envoy locally with a static config and two test backends.
- Learn listeners, clusters, routes, endpoints, admin interface.
- **Done when:** traffic splits across both backends and the Envoy stats are visible.

### Phase 2: Control plane with xDS
- Build the Go control plane with `go-control-plane`.
- Serve clusters and endpoints from a YAML file or REST API.
- Hot-reload weights without restarting Envoy.
- **Done when:** changing a weight in the API changes live traffic distribution.

### Phase 3: Multi-cloud simulation and failover
- Simulate 3 "clouds" using Docker networks with injected latency and failure (e.g. Toxiproxy or `tc`).
- Configure locality-weighted LB, health checks, outlier detection.
- **Done when:** killing one "cloud" shifts traffic automatically with no failed requests beyond the detection window.

### Phase 4: Telemetry and heuristic scorer
- Prometheus scraping of Envoy; Grafana dashboards.
- Control-plane module that computes backend scores from metrics and updates weights.
- Add the guardrails and the decision log.
- **Done when:** weights adapt to injected latency or errors, and every change is logged.

### Phase 5: AI engine in shadow mode
- Python service exposing gRPC or REST: `POST /recommend` returns weights.
- Anomaly detection and traffic forecasting.
- Run alongside the heuristic scorer in shadow mode; compare outcomes offline.
- **Done when:** a report shows the AI recommendation vs the actual policy over a test run.

### Phase 6: AI-driven active mode
- Add cost-aware optimization and a contextual bandit.
- Enable active mode behind a feature flag, with guardrails and automatic fallback.
- **Done when:** the AI policy beats the baseline on latency, cost, or both in load tests, and the fallback is proven by fault injection.

### Phase 7: Real multi-cloud deployment and polish
- Deploy Envoy and backends on at least two real clouds (free tiers or small instances).
- Global steering via DNS with health checks.
- Autoscaling hints, optional LLM operator assistant, documentation, demo.
- **Done when:** a live demo shows traffic shifting across real clouds under load.

---

## 7. Testing and Validation

- **Load testing:** k6 or Vegeta, with spike, ramp and soak scenarios.
- **Chaos testing:** kill backends, add latency, drop packets, take a whole cloud down.
- **AI evaluation:** forecast error (MAPE), anomaly precision/recall, and end-to-end p50/p95/p99 latency, error rate and cost vs baselines.
- **Safety tests:** AI engine crash, garbage output, slow response. The guardrails and fallback must hold.
- **Benchmark:** compare against plain Envoy with static weights and a plain least-request policy.

---

## 8. Proposed Repo Structure

```
load_balancer/
├── README.md
├── docker-compose.yml
├── envoy/                  # bootstrap and static configs
├── control-plane/          # Go xDS server, guardrails, decision log
├── ai-engine/              # Python service, models, training notebooks
├── backends/               # simple test backend services
├── simulation/             # latency/failure injection, load test scripts
├── observability/          # Prometheus and Grafana configs
├── infra/                  # Terraform for real cloud deployment (Phase 7)
└── docs/                   # PLAN.md, architecture notes, evaluation reports
```

---

## 9. Hardware Notes (RTX 4050 6 GB, 16 GB RAM)

- Forecasting, anomaly detection and bandits run fine on CPU.
- Local LLMs: 1-4B models fit fully on the GPU; 7-8B at Q4 fit barely with a short context.
- Use Ollama or LM Studio for local models; QLoRA fine-tuning is possible on 1-3B models.
- Use Colab or Kaggle for heavier training.
- Running Docker plus several services at once is the main memory pressure, so keep the simulated environment lean.

---

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| AI makes bad routing decisions | Guardrails, shadow mode, kill switch, fallback |
| Weight oscillation or flapping | Damping, minimum hold time, bounded change per interval |
| Control plane is a single point of failure | Envoy keeps last-known config; run replicas later |
| Cloud costs during real deployment | Free tiers, small instances, tear down after demos |
| ML does not beat baselines | Keep the heuristic scorer as the production policy; report honestly |
| Scope creep | Finish each phase's "done when" before moving on |

---

## 11. Open Decisions

- Control plane language: Go (recommended) or Java.
- Traffic type: HTTP only, or TCP/UDP as well.
- Which two or three clouds for Phase 7.
- Whether to include the LLM operator assistant.

---

## 12. Success Criteria

- Traffic is distributed across clouds with live, variable weights.
- A cloud failure is handled automatically with minimal failed requests.
- The AI policy measurably improves latency or cost over the baseline, with evidence.
- Every AI decision is bounded, logged and reversible.
- A working demo and documentation that show the full system end to end.
