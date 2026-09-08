# fastmcp-production-template

> Production-ready MCP server template with async PostgreSQL, OpenTelemetry, tool-level security allowlisting, Docker, and Kubernetes Helm chart. Zero to deployed in 10 minutes.

[![CI](https://github.com/ManjunathGovindaraju/fastmcp-production-template/actions/workflows/ci.yml/badge.svg)](https://github.com/ManjunathGovindaraju/fastmcp-production-template/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/ManjunathGovindaraju/fastmcp-production-template/branch/main/graph/badge.svg)](https://codecov.io/gh/ManjunathGovindaraju/fastmcp-production-template)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.x-green.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Read the full write-up: [Building a Production-Ready MCP Server: Async PostgreSQL, OpenTelemetry, and Kubernetes in One Template](https://dev.to/manjunathgovindaraju/building-a-production-ready-mcp-server-async-postgresql-opentelemetry-and-kubernetes-in-one-37co)

## Why this template exists

Over the past year I built and deployed **20+ MCP servers in production** inside a regulated life sciences environment — powering AI agents that search 57M+ research records, automate scientific workflows, and surface real-time data to LLMs via 150+ registered tools.

Every new server started the same way: copy the FastMCP quickstart, then spend days re-solving the same four problems:

- Async database connections that deadlock under concurrent agent calls
- No guardrails against prompt injection via unauthorized tool invocation
- Zero observability — no traces, no metrics, no idea what the LLM was actually calling
- Kubernetes deployments cobbled together from unrelated examples

After the third server, I extracted the patterns that actually held up in production and built this template. The allowlist security pattern came directly from needing to prevent AI agents from invoking internal debug tools in a HIPAA-adjacent environment. The asyncpg pool configuration comes from real connection exhaustion incidents at 20 concurrent agents. The OpenTelemetry setup is what we use to debug tool call latency today.

This is not a toy demo. Fork it, rename the tools to match your domain, and ship.

---

## The problems it solves

Most MCP server examples stop before the hard parts. The moment you try to deploy one in production you hit the same set of problems:

- How do I manage a database connection pool safely across async tool calls?
- How do I prevent prompt injection via unauthorized tool invocation?
- How do I get distributed traces into my existing observability stack?
- How do I deploy this to Kubernetes with proper secrets management?

This template solves all of that.

---

## Demo

![FastMCP server startup and tool call demo](docs/demo.gif)

---

## Features

| Feature | Implementation |
|---|---|
| Async PostgreSQL | `asyncpg` connection pool (min 5, max 20), parameterized queries |
| OpenTelemetry | `@instrument_tool` decorator records traces + 4 metrics (`tool.calls`, `tool.errors`, `tool.duration`, `db.pool_size`) on every tool call |
| Multi-backend observability | Pre-built collector configs for AWS ADOT → X-Ray, Grafana LGTM stack, and Datadog. One-command local stack: `make observe-up` |
| Security allowlist | YAML-based tool allowlist prevents unauthorized tool invocation and prompt injection |
| Docker | Multi-stage build, non-root user (`mcpuser`), health check |
| Kubernetes | Helm chart, HPA (2–8 replicas), External Secrets Operator, optional ADOT sidecar |
| CI/CD | GitHub Actions: Ruff + Bandit + mypy → unit tests → integration tests (postgres service) → Docker build |
| Configuration | Pydantic Settings, `.env` based, 12-factor compliant |

---

## Quick Start

### Option 1: Docker Compose (2 minutes)

```bash
git clone https://github.com/ManjunathGovindaraju/fastmcp-production-template.git
cd fastmcp-production-template
cp .env.example .env
docker compose -f docker/docker-compose.yml up
```

The MCP server starts at `http://localhost:8000/mcp`. PostgreSQL starts with sample data loaded from `docker/init.sql`.

### Option 2: Docker Compose + Full Observability Stack

```bash
cp .env.example .env
make observe-up
```

Starts the MCP server, PostgreSQL, **and** the full Grafana LGTM stack (OpenTelemetry Collector → Tempo → Prometheus → Grafana).

| Endpoint | URL |
|---|---|
| MCP server | `http://localhost:8000/mcp` |
| Grafana dashboards | `http://localhost:3000` (no login) |
| Prometheus metrics | `http://localhost:9090` |

`OTEL_ENABLED` is automatically set to `true` when using this compose profile. Stop everything with `make observe-down`.

### Option 3: Local Python

```bash
git clone https://github.com/ManjunathGovindaraju/fastmcp-production-template.git
cd fastmcp-production-template

# Install uv if needed: https://docs.astral.sh/uv/
uv sync

cp .env.example .env
# Edit .env — set DATABASE_URL to your PostgreSQL connection string

python -m src.server.main
```

---

## Architecture

### System Overview

```mermaid
graph TD
    Client["🤖 MCP Client<br/>(LLM / AI Agent)"]

    subgraph Server["FastMCP Server  —  http://0.0.0.0:8000/mcp"]
        direction TB
        Transport["Streamable HTTP Transport"]

        subgraph Middleware["Cross-cutting concerns"]
            Allowlist["🔒 Allowlist Security<br/>config/allowlist.yaml"]
            OTel["📊 OpenTelemetry<br/>Traces · Metrics"]
            Settings["⚙️ Pydantic Settings<br/>.env / env vars"]
        end

        subgraph Tools["Registered Tools"]
            T1["search_records"]
            T2["get_record_detail"]
            T3["get_statistics"]
            T4["get_pool_status"]
        end

        Pool["🗄️ DatabasePool<br/>asyncpg · min=5 · max=20"]
    end

    DB[("PostgreSQL")]
    OTelBackend["📈 OTLP Backend<br/>Jaeger / Grafana / X-Ray"]

    Client -->|"JSON-RPC over HTTP"| Transport
    Transport --> Allowlist
    Allowlist --> Tools
    Tools --> Pool
    Pool -->|"async queries"| DB
    OTel -.->|"traces + metrics"| OTelBackend
```

### Request Lifecycle

```mermaid
sequenceDiagram
    participant C as MCP Client
    participant S as FastMCP Server
    participant AL as Allowlist Guard
    participant T as Tool Function
    participant DB as PostgreSQL

    C->>S: tools/call { name, arguments }
    S->>AL: is_allowed(tool_name)?
    alt tool not in allowlist
        AL-->>S: PermissionError
        S-->>C: isError: true
    else tool allowed
        AL-->>S: OK
        S->>T: execute(arguments)
        T->>DB: parameterized query ($1, $2 ...)
        DB-->>T: rows
        T-->>S: result dict
        S-->>C: isError: false, content
    end
```

### Deployment Architecture (Kubernetes)

```mermaid
graph LR
    subgraph K8s["Kubernetes Cluster  —  mcp-system namespace"]
        direction TB

        subgraph Ingress["Ingress"]
            IG["Ingress Controller"]
        end

        subgraph Workload["Deployment  (HPA: 2–8 replicas)"]
            P1["Pod 1<br/>MCP Server + ADOT Sidecar"]
            P2["Pod 2<br/>MCP Server + ADOT Sidecar"]
        end

        subgraph Config["Configuration"]
            CM["ConfigMap<br/>allowlist.yaml"]
            ES["ExternalSecret<br/>→ Vault"]
            SEC["Secret<br/>DATABASE_URL · API_KEY"]
        end

        subgraph Obs["Observability"]
            ADOT["ADOT Collector"]
            XRay["AWS X-Ray"]
        end
    end

    IG --> P1
    IG --> P2
    CM -->|"volumeMount"| P1
    CM -->|"volumeMount"| P2
    ES --> SEC
    SEC -->|"envFrom"| P1
    SEC -->|"envFrom"| P2
    P1 --> ADOT --> XRay
    P2 --> ADOT
```

### CI/CD Pipeline

```mermaid
flowchart LR
    PR["Pull Request<br/>or push to main"]
    Lint["Ruff + Bandit + mypy<br/>src/ tests/"]
    Unit["Unit tests<br/>pytest -m 'not integration'"]
    Int["Integration tests<br/>pytest -m integration<br/>postgres:16 service"]
    Docker["Docker Build<br/>docker/Dockerfile"]
    Done["✅ Ready to deploy"]

    PR --> Lint
    Lint -->|pass| Unit
    Unit -->|pass| Int & Docker
    Int -->|pass| Done
    Docker -->|pass| Done
    Lint -->|fail| X1["❌"]
    Unit -->|fail| X2["❌"]
    Int -->|fail| X3["❌"]
    Docker -->|fail| X4["❌"]
```

---

## Security Model

Tool invocations are gated by a YAML allowlist loaded at server startup. Any tool not on the list raises `PermissionError` before execution — preventing prompt injection attacks where a malicious prompt attempts to invoke an internal or debugging tool.

```mermaid
flowchart TD
    Invoke["tools/call request"]
    Check{"tool_name in<br/>allowed_tools?"}
    Permit["Execute tool function"]
    Block["Raise PermissionError<br/>isError: true"]
    Result["Return result to client"]

    Invoke --> Check
    Check -->|yes| Permit --> Result
    Check -->|no| Block
```

**Allowlist config** (`config/allowlist.yaml`):

```yaml
allowed_tools:
  - search_records
  - get_record_detail
  - get_statistics
  # get_pool_status intentionally omitted — health is always reachable
```

**Decorator usage**:

```python
@require_allowlist("search_records")
async def search_records(query: str, limit: int = 20) -> dict:
    ...
```

**SQL injection prevention** — two layers:
1. All user-supplied values use `asyncpg` parameterized queries (`$1`, `$2`)
2. `get_statistics` validates `group_by` against a hardcoded column allowlist before query construction
3. `search_records` validates `filters` keys against a hardcoded column allowlist

---

## Observability

Every tool call is automatically instrumented via the `@instrument_tool` decorator. The decorator is the **outermost** layer — it records all attempts including allowlist-blocked calls.

```mermaid
graph LR
    Call["tools/call"]
    Inst["@instrument_tool<br/>counter · histogram · span"]
    AL["@require_allowlist"]
    Fn["Tool function"]

    Call --> Inst --> AL --> Fn
```

### Metrics emitted

| Metric | Type | Attributes |
|---|---|---|
| `mcp.tool.calls` | Counter | `tool` |
| `mcp.tool.errors` | Counter | `tool` |
| `mcp.tool.duration` | Histogram (ms) | `tool` |
| `mcp.db.pool_size` | Gauge | — |

### How it works

```python
# Decorator order in every tool file:
@instrument_tool("search_records")   # outermost — records all attempts
@require_allowlist("search_records") # inner — may raise PermissionError
async def search_records(...):
    ...
```

The `Telemetry` instance is initialized in `main.py` and stored in `observability/context.py` (a singleton mirroring `db/pool.py`). If `get_telemetry()` returns `None` (e.g., in unit tests), the decorator is a zero-overhead pass-through.

### Backend routing

The app emits standard OTLP and is backend-agnostic. The `collector/` directory provides pre-built configs for three deployment targets:

| File | Routes to |
|---|---|
| `collector/adot-aws.yaml` | AWS X-Ray (traces) + CloudWatch EMF (metrics) via ADOT sidecar |
| `collector/otelcol-grafana.yaml` | Grafana Tempo (traces) + Prometheus (metrics) |
| `collector/otelcol-datadog.yaml` | Datadog APM + Datadog Metrics |

```mermaid
graph LR
    Server["FastMCP Server<br/>OTLP gRPC :4317"]

    subgraph Collector["OTel Collector (ADOT or otelcol-contrib)"]
        C["collector/*.yaml"]
    end

    subgraph Backends["Observability Backends"]
        B1["AWS X-Ray + CloudWatch"]
        B2["Grafana Tempo + Prometheus"]
        B3["Datadog APM"]
    end

    Server -->|"OTLP"| Collector
    Collector --> B1
    Collector --> B2
    Collector --> B3
```

### Local observability with Grafana LGTM

```bash
make observe-up   # starts MCP server + postgres + otelcol + Tempo + Prometheus + Grafana
# Open http://localhost:3000 — traces and metrics appear immediately
make observe-down
```

### Configure in `.env`

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # collector endpoint
OTEL_SERVICE_NAME=fastmcp-production-template
```

Set `OTEL_ENABLED=false` in local dev to write spans to stdout instead.

---

## Kubernetes Deployment

```bash
# Install with Helm
helm install fastmcp-server k8s/helm/ \
  --set image.repository=your-registry/fastmcp-production-template \
  --set image.tag=1.0.0 \
  --namespace mcp-system \
  --create-namespace

# Scale manually
kubectl scale deployment fastmcp-server --replicas=4 -n mcp-system

# Check HPA status
kubectl get hpa -n mcp-system
```

The Helm chart includes:
- HPA: auto-scales 2–8 replicas at 70% CPU
- External Secrets Operator integration (pulls `DATABASE_URL`, `API_KEY` from HashiCorp Vault)
- ADOT sidecar annotation support for AWS X-Ray tracing
- Non-root security context (`runAsNonRoot: true`)
- ConfigMap volume mount for `allowlist.yaml`

---

## Project Structure

```
fastmcp-production-template/
├── src/server/
│   ├── main.py                  # FastMCP entry point, lifespan hooks
│   ├── config/
│   │   ├── settings.py          # Pydantic Settings (env / .env)
│   │   └── security.py          # Allowlist loader + @require_allowlist decorator
│   ├── db/
│   │   ├── connection.py        # asyncpg DatabasePool (fetch/execute helpers)
│   │   └── pool.py              # Module-level singleton — tools call get_pool()
│   ├── observability/
│   │   ├── telemetry.py         # OTel setup — OTLP (prod) or console (dev) exporter
│   │   ├── context.py           # Telemetry singleton — set_telemetry/get_telemetry
│   │   └── instrument.py        # @instrument_tool decorator (metrics + trace span)
│   └── tools/
│       ├── search.py            # search_records — full-text search with pagination
│       ├── detail.py            # get_record_detail — fetch single record by ID
│       ├── stats.py             # get_statistics — aggregate counts by field
│       └── health.py            # get_pool_status — DB pool health (no allowlist)
├── collector/
│   ├── adot-aws.yaml            # ADOT collector → AWS X-Ray + CloudWatch
│   ├── otelcol-grafana.yaml     # otelcol-contrib → Grafana Tempo + Prometheus
│   └── otelcol-datadog.yaml     # otelcol-contrib → Datadog APM + Metrics
├── config/
│   └── allowlist.yaml           # Tool allowlist (edit to expose/hide tools)
├── docker/
│   ├── Dockerfile               # Multi-stage build (builder + runtime, non-root)
│   ├── docker-compose.yml       # MCP server + PostgreSQL with health check
│   ├── docker-compose.observe.yml  # Adds Grafana LGTM stack (make observe-up)
│   ├── init.sql                 # Sample schema and seed data
│   ├── tempo.yaml               # Grafana Tempo config for local stack
│   ├── prometheus.yml           # Prometheus scrape config for local stack
│   └── grafana/provisioning/    # Auto-provisioned datasources + dashboards
├── k8s/helm/
│   ├── values.yaml              # Helm values (HPA, ESO, optional ADOT sidecar)
│   └── templates/
│       └── deployment.yaml      # K8s Deployment with security context
├── tests/
│   ├── conftest.py              # mock_telemetry fixture
│   ├── test_security.py         # Allowlist enforcement tests
│   ├── test_telemetry.py        # context singleton + @instrument_tool + setup_telemetry
│   ├── test_tools.py            # Tool behavior + SQL injection prevention (unit, mocked DB)
│   └── test_integration.py      # Real DB tests — skipped unless DATABASE_URL is set
├── .github/workflows/
│   ├── ci.yml                   # Lint → unit tests → integration tests → Docker build
│   └── release.yml              # Tag-based release workflow
├── pyproject.toml               # uv/hatch project config
└── .env.example                 # Configuration reference
```

---

## Extending This Template

Adding a new tool takes three steps:

**Step 1 — Create the tool** in `src/server/tools/your_tool.py`:

```python
from ..config.security import require_allowlist
from ..db.pool import get_pool
from ..observability.instrument import instrument_tool

@instrument_tool("your_tool_name")   # outermost — records metrics + trace span
@require_allowlist("your_tool_name") # inner — blocks if not in allowlist
async def your_tool_name(param: str) -> dict:
    row = await get_pool().fetchrow(
        "SELECT * FROM your_table WHERE id = $1", param
    )
    return dict(row) if row else {}
```

**Step 2 — Register it** in `src/server/main.py`:

```python
from .tools import your_tool
mcp.add_tool(your_tool.your_tool_name)
```

**Step 3 — Add it to the allowlist** in `config/allowlist.yaml`:

```yaml
allowed_tools:
  - your_tool_name
```

---

## Running Tests

### Unit tests (no database required)

```bash
make test-unit        # default — safe for pre-commit, CI, offline dev
```

28 tests covering: allowlist enforcement, telemetry singleton, `@instrument_tool` decorator (call counting, error counting, duration recording, span wrapping, `functools.wraps`), `setup_telemetry` console and OTLP modes, all four tool functions with mocked DB, and SQL injection prevention.

### Integration tests (requires PostgreSQL)

```bash
# Start postgres first (uses the same docker-compose as `make observe-up`):
docker compose -f docker/docker-compose.yml up -d postgres

# Run integration tests:
DATABASE_URL=postgresql://mcpuser:mcppassword@localhost:5432/mcpdb make test-integration
```

21 tests covering: real `DatabasePool` lifecycle, `search_records` (pagination, filters, limit capping), `get_record_detail` (found / not-found paths), `get_statistics` (grouping, totals), and SQL injection prevention against a live database.

### All checks (lint + type check + unit tests)

```bash
make check
```

### Coverage

Unit tests alone reach **82% coverage** (entry-point files `main.py` and `settings.py` excluded — covered by integration tests). The 75% threshold is enforced in CI on both test phases.

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `fastmcp-production-template` | MCP server name |
| `PORT` | `8000` | Uvicorn listen port |
| `DATABASE_URL` | — | asyncpg DSN (`postgresql://user:pass@host/db`) |
| `DB_POOL_MIN` | `5` | Minimum pool connections |
| `DB_POOL_MAX` | `20` | Maximum pool connections |
| `ALLOWLIST_PATH` | `config/allowlist.yaml` | Path to tool allowlist |
| `API_KEY_ENABLED` | `true` | Enable API key auth |
| `API_KEY` | — | Bearer token for requests |
| `OTEL_ENABLED` | `true` | Enable OpenTelemetry export |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector endpoint |

---

## Author

**Manjunath Govindaraju** — Principal Software Engineer with 23 years building production systems. Currently focused on AI platform engineering: multi-agent orchestration (LangGraph), MCP servers, async data pipelines, and enterprise Kubernetes deployments.

[LinkedIn](https://www.linkedin.com/in/manjunathgovindaraju/) · [GitHub](https://github.com/ManjunathGovindaraju)

---

## License

MIT — fork freely, use in production, no attribution required.
