# salesforce-agent

Salesforce CRM을 자연어로 조작하는 AI 에이전트. Google ADK + Gemini 기반.

---

## Architecture

```mermaid
flowchart TB
    User(["User"]) -->|natural language| Agent

    subgraph ADK["Google ADK Runtime"]
        Agent["Gemini Agent\nroot_agent"]
        Toolset["SalesforceToolset\n40+ FunctionTools"]
        Ops["SalesforceOperations\nsimple-salesforce"]
        Agent -->|tool calls| Toolset
        Toolset -->|API wrapper| Ops
    end

    Ops -->|Salesforce REST API| SF[("Salesforce CRM")]
    Toolset -->|OAuth 2.0| SF

    subgraph Deploy["Deployment"]
        Local["Local Dev\nadk web"]
        Cloud["Vertex AI\nAgent Engine"]
    end

    ADK -.->|runs on| Deploy
```

---

## OAuth Flow

두 가지 인증 모드를 지원합니다.

```mermaid
sequenceDiagram
    actor User
    participant Agent as Gemini Agent
    participant ADK as Google ADK
    participant SF_OAuth as Salesforce OAuth
    participant SF_API as Salesforce API

    User->>Agent: 자연어 요청

    alt Local Dev (AGENTSPACE_MODE=false)
        Agent->>ADK: tool call (AuthenticatedFunctionTool)
        ADK-->>User: OAuth 인증 URL 반환
        User->>SF_OAuth: 로그인 & 동의
        SF_OAuth-->>ADK: Authorization Code
        ADK->>SF_OAuth: code + client_secret → token 교환
        SF_OAuth-->>ADK: access_token
        ADK->>SF_API: API 호출 (Bearer token)
    else Agentspace Mode (AGENTSPACE_MODE=true)
        Note over ADK: Platform이 access_token 주입
        Agent->>ADK: tool call (FunctionTool)
        ADK->>SF_API: API 호출 (Bearer token)
    end

    SF_API-->>Agent: 결과
    Agent-->>User: 응답
```

---

## Features

| Category | Capabilities |
|---|---|
| **Query** | SOQL, SOSL, pagination (`query_more`) |
| **Records** | create, read, update, delete, upsert |
| **Metadata** | describe object/fields, list objects |
| **Reports & Dashboards** | sync/async run, refresh, describe |
| **Approvals** | submit, approve/reject, pending list |
| **Bulk & Files** | bulk CRUD, file download |

---

## Prerequisites

- Python 3.14+, [`uv`](https://docs.astral.sh/uv/)
- Google Cloud project (Vertex AI enabled)
- Salesforce Connected App (OAuth 2.0)

---

## Quick Start

**1. Install**

```bash
uv sync
```

**2. Configure** — `.env` 파일 생성:

```bash
cp .env.example .env
# .env를 열어 필수 값 입력
```

**3. Run**

```bash
uv run adk web
# → http://localhost:8000/dev-ui/
```

---

## Configuration

| Variable | Description | Default |
|---|---|---|
| `VERTEXAI_PROJECT` | Google Cloud project ID | — |
| `VERTEXAI_LOCATION` | Region | `global` |
| `AGENT_MODEL` | Gemini model ID | `gemini-2.0-flash` |
| `SALESFORCE_CLIENT_ID` | Connected App consumer key | — |
| `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret | — |
| `SALESFORCE_LOGIN_URL` | Auth endpoint | `https://login.salesforce.com` |
| `SALESFORCE_INSTANCE_URL` | Org instance URL | — |
| `SALESFORCE_API_VERSION` | API version | `65.0` |
| `AGENTSPACE_MODE` | Enable enterprise Agentspace | `false` |

---

## Deployment

Vertex AI Agent Engine에 배포하려면 [`just`](https://github.com/casey/just)를 사용합니다.

```bash
just create --display-name "Salesforce Agent"  # 배포 생성
just update --resource-name <name>             # 업데이트
just list                                      # 배포 목록 조회
just delete --resource-name <name> -y         # 삭제
```
