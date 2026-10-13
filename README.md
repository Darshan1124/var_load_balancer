# AI-Enabled Variable Load Balancer for Multi-Cloud

An Envoy-based load balancer with a custom xDS control plane and an AI engine that adjusts traffic weights across clouds. See [PLAN.md](docs/PLAN.md) for the full design and roadmap.

## Layout

| Folder | Purpose |
|---|---|
| `envoy/` | Envoy bootstrap and static configs |
| `control-plane/` | Go xDS server, guardrails, decision log |
| `ai-engine/` | Python service, models, training notebooks |
| `backends/` | Simple test backend services |
| `simulation/` | Latency/failure injection and load test scripts |
| `observability/` | Prometheus and Grafana configs |
| `infra/` | Terraform for real cloud deployment (Phase 7) |
| `docs/` | Architecture notes and evaluation reports |

## Status

Phase 0 (environment and repo setup): in progress.
