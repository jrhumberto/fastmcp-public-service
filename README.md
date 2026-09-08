# 🏛️ Arquitetura MCP para Setor Público (fastmcp-public-service)

>Documento técnico completo contendo: ambiente Docker, documentação do sistema, diagramas, regras de Guardrails, integração de ferramentas de qualidade e prompt definitivo para o Agente Arquiteto de Software do Setor Público.
Importante: Em ambiente de desenvolvimento, banco utilizado SQL Server. Em Produção e Homologação, utilizo Postgresql. Camada adicional Kubernetes inserida para vislumbre dos pods.
---

# 📌 1. Servidor MCP - Características

## 1.1 Servidor MCP - Problemas/Backlog

* [x] Arquitetura Kubernetes para produção.
* [x] Gerenciar um pool de conexões de banco de dados com segurança entre chamadas assíncronas.
* [x] Impedir injeção de prompt via invocação não autorizada de ferramentas.
* [x] Rastreio na sua pilha de observabilidade - **caminho crítico**.

---


## 1.2 Funcionalidades para Produção

| Funcionalidade | Implementação |
|---|---|
| PostgreSQL assíncrono | Pool de conexão `asyncpg` (mín 5, máx 20), consultas parametrizadas |
| OpenTelemetry | Decorador `@instrument_tool` registra rastros + 4 métricas (`tool.calls`, `tool.errors`, `tool.duration`, `db.pool_size`) em cada chamada de ferramenta |
| Observabilidade multi‑backend | Configurações de coletor pré‑construídas para AWS ADOT → X‑Ray, stack Grafana LGTM e Datadog. Stack local com um comando: `make observe-up` |
| Segurança por lista de permissões | Lista de permissões baseada em YAML impede invocação não autorizada de ferramentas e injeção de prompt |
| Docker | Build multi‑stage, usuário não‑root (`mcpuser`), health check |
| Kubernetes | Chart Helm, HPA (2–8 réplicas), External Secrets Operator, sidecar ADOT opcional |
| CI/CD | GitHub Actions: Ruff + Bandit + mypy → testes unitários → testes de integração (serviço postgres) → build Docker |
| Configuração | Pydantic Settings, baseado em `.env`, compatível com 12‑factor |

---

## 1.3 Ambiente de Desenvolvimento 

### 🐳 1.3.1 Docker com SQL Server (se desejável)

### `Dockerfile.dev`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema para pyodbc e SQL Server
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Copiar código
COPY . .

# Variáveis de ambiente padrão (sobrescrevíveis via docker-compose)
ENV SQL_SERVER_HOST=localhost
ENV SQL_SERVER_DB=publico_dev
ENV SQL_SERVER_USER=sa
ENV SQL_SERVER_PASSWORD=Dev@123456
ENV SQL_ENCRYPT=no
ENV SQL_TRUST_CERT=yes

# Porta padrão do MCP (JSON-RPC sobre SSE/Stdio)
EXPOSE 8000

CMD ["python", "-m", "mcp_server"]
```

### `docker-compose.yml`
```yaml
version: '3.9'
services:
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    environment:
      - SQL_SERVER_HOST=mssql
      - SQL_SERVER_DB=publico_dev
      - SQL_SERVER_USER=sa
      - SQL_SERVER_PASSWORD=<SENHA>
      - SQL_ENCRYPT=no
      - SQL_TRUST_CERT=yes
    depends_on:
      - mssql
    volumes:
      - .:/app
      - /app/.venv

  mssql:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      - ACCEPT_EULA=Y
      - SA_PASSWORD=<SENHA>
      - MSSQL_PID=Express
    ports:
      - "1433:1433"
    volumes:
      - mssql_data:/var/opt/mssql
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql

volumes:
  mssql_data:
```

### `init-db.sql` (Exemplo de estrutura segura)
```sql
CREATE DATABASE publico_dev;
GO
USE publico_dev;
GO
CREATE TABLE servidores (
    id INT PRIMARY KEY IDENTITY(1,1),
    nome VARCHAR(100) NOT NULL,
    cpf CHAR(11) NOT NULL,
    email VARCHAR(100) NOT NULL,
    lotacao VARCHAR(100),
    criado_em DATETIME2 DEFAULT SYSUTCDATETIME()
);
GO
-- Usuário com permissão mínima (apenas SELECT)
CREATE LOGIN mcp_user WITH PASSWORD = 'Mcp@Dev123';
CREATE USER mcp_user FOR LOGIN mcp_user;
GRANT SELECT ON servidores TO mcp_user;
GO
```

---


### 1.3.2 Início Rápido para Testar Observabilidade (Docker Compose comPostgresql + Stack Completo de Observabilidade)


### 

```bash
cp .env.example .env
make observe-up
```

Inicia o servidor MCP, PostgreSQL **e** a stack completa Grafana LGTM (OpenTelemetry Collector → Tempo → Prometheus → Grafana).

| Endpoint | URL |
|---|---|
| Servidor MCP | `http://localhost:8000/mcp` |
| Dashboards Grafana | `http://localhost:3000` (sem login) |
| Métricas Prometheus | `http://localhost:9090` |

`OTEL_ENABLED` é definido automaticamente como `true` ao usar este perfil de compose. Pare tudo com `make observe-down`.

---

## Arquitetura

### Visão Geral do Sistema

```mermaid
graph TD
    Client["🤖 Cliente MCP<br/>(LLM / Agente IA)"]

    subgraph Server["Servidor FastMCP  —  http://0.0.0.0:8000/mcp"]
        direction TB
        Transport["Transporte HTTP Streamable"]

        subgraph Middleware["Preocupações transversais"]
            Allowlist["🔒 Segurança por Lista de Permissões<br/>config/allowlist.yaml"]
            OTel["📊 OpenTelemetry<br/>Rastros · Métricas"]
            Settings["⚙️ Configurações Pydantic<br/>.env / variáveis de ambiente"]
        end

        subgraph Tools["Ferramentas Registradas"]
            T1["search_records"]
            T2["get_record_detail"]
            T3["get_statistics"]
            T4["get_pool_status"]
        end

        Pool["🗄️ DatabasePool<br/>asyncpg · min=5 · max=20"]
    end

    DB[("PostgreSQL")]
    OTelBackend["📈 Backend OTLP<br/>Jaeger / Grafana / X-Ray"]

    Client -->|"JSON-RPC over HTTP"| Transport
    Transport --> Allowlist
    Allowlist --> Tools
    Tools --> Pool
    Pool -->|"consultas assíncronas"| DB
    OTel -.->|"rastros + métricas"| OTelBackend
```

### 1.3.3 Ciclo de Vida da Requisição

```mermaid
sequenceDiagram
    participant C as Cliente MCP
    participant S as Servidor FastMCP
    participant AL as Guarda da Lista de Permissões
    participant T as Função da Ferramenta
    participant DB as PostgreSQL

    C->>S: tools/call { name, arguments }
    S->>AL: is_allowed(tool_name)?
    alt ferramenta não está na lista
        AL-->>S: PermissionError
        S-->>C: isError: true
    else ferramenta permitida
        AL-->>S: OK
        S->>T: execute(arguments)
        T->>DB: consulta parametrizada ($1, $2 ...)
        DB-->>T: rows
        T-->>S: result dict
        S-->>C: isError: false, content
    end
```

### 1.3.4 Arquitetura de Deploy (Kubernetes)

```mermaid
graph LR
    subgraph K8s["Cluster Kubernetes  —  namespace mcp-system"]
        direction TB

        subgraph Ingress["Ingress"]
            IG["Controlador de Ingress"]
        end

        subgraph Workload["Deployment  (HPA: 2–8 réplicas)"]
            P1["Pod 1<br/>Servidor MCP + Sidecar ADOT"]
            P2["Pod 2<br/>Servidor MCP + Sidecar ADOT"]
        end

        subgraph Config["Configuração"]
            CM["ConfigMap<br/>allowlist.yaml"]
            ES["ExternalSecret<br/>→ Vault"]
            SEC["Secret<br/>DATABASE_URL · API_KEY"]
        end

        subgraph Obs["Observabilidade"]
            ADOT["Coletor ADOT"]
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

### 1.3.5 Pipeline CI/CD

```mermaid
flowchart LR
    PR["Pull Request<br/>ou push para main"]
    Lint["Ruff + Bandit + mypy<br/>src/ tests/"]
    Unit["Testes unitários<br/>pytest -m 'not integration'"]
    Int["Testes de integração<br/>pytest -m integration<br/>serviço postgres:16"]
    Docker["Build Docker<br/>docker/Dockerfile"]
    Done["✅ Pronto para deploy"]

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

## ⚙ 2. Modelo de Segurança

Invocações de ferramentas são controladas por uma lista de permissões em YAML carregada na inicialização do servidor. Qualquer ferramenta que não esteja na lista gera `PermissionError` antes da execução — impedindo ataques de injeção de prompt onde um prompt malicioso tenta invocar uma ferramenta interna ou de depuração.

```mermaid
flowchart TD
    Invoke["requisição tools/call"]
    Check{"tool_name in<br/>allowed_tools?"}
    Permit["Executar função da ferramenta"]
    Block["Levantar PermissionError<br/>isError: true"]
    Result["Retornar resultado ao cliente"]

    Invoke --> Check
    Check -->|yes| Permit --> Result
    Check -->|no| Block
```

**Configuração da lista de permissões** (`config/allowlist.yaml`):

```yaml
allowed_tools:
  - search_records
  - get_record_detail
  - get_statistics
  # get_pool_status intencionalmente omitido — saúde está sempre acessível
```

**Uso do decorador**:

```python
@require_allowlist("search_records")
async def search_records(query: str, limit: int = 20) -> dict:
    ...
```

**Prevenção de injeção SQL** — duas camadas:
1. Todos os valores fornecidos pelo usuário usam consultas parametrizadas do `asyncpg` (`$1`, `$2`)
2. `get_statistics` valida `group_by` contra uma lista de colunas permitidas antes de construir a consulta
3. `search_records` valida as chaves de `filters` contra uma lista de colunas permitidas

---

## 🎯  3. Observabilidade

Cada chamada de ferramenta é automaticamente instrumentada via o decorador `@instrument_tool`. O decorador é a **camada mais externa** — registra todas as tentativas, inclusive chamadas bloqueadas pela lista de permissões.

```mermaid
graph LR
    Call["tools/call"]
    Inst["@instrument_tool<br/>conta chamadas, erros, duração"]
    Exec["Execução da ferramenta (ou bloqueio)"]
    Emit["Emissão de rastro/ métrica"]
    Call --> Inst --> Exec --> Emit
```


-----

## 📊 4. Diagramas (Mermaid)

### 4.2 Fluxo de Operação (Tool Call)
```mermaid
sequenceDiagram
    participant C as Cliente MCP
    participant S as Servidor FastMCP
    participant G as Guardrails
    participant DB as SQL Server
    C->>S: tool_call(consultar_servidores, params)
    S->>G: validar_query(params)
    G->>G: verificar permissões & sintaxe
    G->>S: query parametrizada + audit_id
    S->>DB: execute(query, params)
    DB->>S: rows + metadata
    S->>G: mascarar PII & logar acesso
    G->>S: resposta sanitizada
    S->>C: tool_result
```

### 4.3 Controle de Segurança & LGPD
```mermaid
flowchart LR
    A[Entrada] --> B{Guardrails}
    B -->|SELECT apenas| C[Parametrização]
    B -->|DDL/DML| D[Rejeitar + Logar]
    C --> E[Execução DB]
    E --> F[Retorno]
    F --> G{Mascaramento}
    G -->|CPF/CNPJ/Email| H[Regex/Hash]
    G -->|Outros| I[Pass-through]
    H --> J[Auditoria LGPD]
    I --> J
    J --> K[Resposta Final]
```

---

## 🛡️ 5. Regras de Guardrails & Conformidade (LGPD/Segurança - Caminhos críticos observados)

| Categoria | Regra Técnica | Base Legal / Norma |
|-----------|---------------|-------------------|
| **Validação de Sintaxe** | Bloqueio de `INSERT`, `UPDATE`, `DELETE`, `DROP`, `EXEC`, `xp_` | Princípio da Mínimo Privilégio |
| **Prevenção de Injeção** | Obrigatório uso de `?` placeholders. Rejeição de strings interpoladas | OWASP ASVS 4.0.1 |
| **Mascaramento PII** | CPF: `***.***.***-XX`, CNPJ: `XX.XXX.XXX/XXXX-XX`, Email: `***@***.***` | LGPD Art. 5º, 6º, 46 |
| **Auditoria** | Log estruturado: `audit_id`, `usuario`, `query_hash`, `linhas_retornadas`, `timestamp_utc` | LGPD Art. 37, 43, 50 |
| **Retenção** | Respostas não são persistidas em cache. Logs rotacionados a 90 dias | LGPD Art. 46, ANPD Guia |
| **Criptografia** | TLS 1.2+ obrigatório. `Encrypt=yes` no driver. Chaves via `secrets` | NBR ISO 27001, LGPD Art. 46 |
| **Rate Limiting** | Máx 100 req/min por cliente. Timeout 15s por query | Resili


---
