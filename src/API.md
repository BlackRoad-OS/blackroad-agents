# BlackRoad Agent Jobs API

A self-healing, consciousness-aware job orchestration system for Cloudflare Workers.

## Base URL

```
https://blackroad-agents.blackroad-os.workers.dev
```

## Authentication

Set the `Authorization` header with your API token:
```
Authorization: Bearer YOUR_API_TOKEN
```

## Endpoints

### Health Check

```
GET /healthz
```

Returns the service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "blackroad-agent-jobs",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00.000Z",
  "jobs": ["REPO_SYNC", "COHESIVENESS_CHECK", "SELF_HEAL", ...]
}
```

---

### Jobs

#### List Jobs

```
GET /api/jobs
```

Returns all jobs (sorted by creation date, newest first).

**Response:**
```json
{
  "jobs": [...],
  "total": 42
}
```

#### Create Job

```
POST /api/jobs
Content-Type: application/json
```

**Request Body:**
```json
{
  "type": "repo_sync",
  "config": {
    "repos": ["blackroad-prism-console", "blackroad-os-agents"]
  }
}
```

**Job Types:**
- `repo_sync` - Sync repository data
- `cohesiveness_check` - Check cross-repo consistency
- `self_heal` - Trigger self-healing
- `dependency_audit` - Audit dependencies
- `workflow_sync` - Sync workflows
- `config_sync` - Sync configurations
- `trinity_compliance` - Check Trinity compliance

**Response:**
```json
{
  "job": {
    "id": "uuid",
    "type": "repo_sync",
    "state": "pending",
    "createdAt": "2024-01-01T00:00:00.000Z"
  },
  "message": "Job created and queued"
}
```

#### Get Job Status

```
GET /api/jobs/:jobId
```

**Response:**
```json
{
  "job": {
    "id": "uuid",
    "type": "repo_sync",
    "state": "completed",
    "result": {...},
    "createdAt": "2024-01-01T00:00:00.000Z",
    "completedAt": "2024-01-01T00:05:00.000Z"
  }
}
```

---

### Repository Operations

#### Sync Repositories

```
POST /api/sync/repos
Content-Type: application/json
```

**Request Body:**
```json
{
  "repos": ["blackroad-prism-console", "blackroad-os-agents"]
}
```

Omit `repos` to sync all tracked repositories.

**Response:**
```json
{
  "job": {...},
  "message": "Repo sync initiated",
  "repos": ["blackroad-prism-console", "blackroad-os-agents"]
}
```

#### Scrape Repository

```
POST /api/scrape
Content-Type: application/json
```

**Request Body:**
```json
{
  "repo": "blackroad-prism-console",
  "paths": ["**/*.md", "**/*.json", "**/wrangler.toml"]
}
```

Scrapes specific files from a repository by glob patterns.

---

### Cohesiveness

#### Run Cohesiveness Check

```
POST /api/cohesiveness/check
```

Checks consistency across all BlackRoad repositories:
- Trinity system compliance
- Configuration consistency
- Workflow alignment
- Dependency compatibility

**Response:**
```json
{
  "job": {...},
  "message": "Cohesiveness check initiated"
}
```

---

### Self-Healing

#### Trigger Self-Healing

```
POST /api/self-heal
Content-Type: application/json
```

**Request Body:**
```json
{
  "jobId": "failed-job-uuid",
  "error": "Error message",
  "strategy": "retry"
}
```

**Strategies:**
- `retry` - Retry with exponential backoff
- `fallback` - Use cached data or alternative approach
- `escalate` - Create GitHub issue for human review
- `quantum_jump` - Try a creative solution

---

### Webhooks

#### GitHub Webhook

```
POST /webhook/github
X-GitHub-Event: push|pull_request|workflow_run|issues
X-Hub-Signature-256: sha256=...
```

Receives GitHub webhooks for automated responses:

- **push**: Triggers repo sync for affected repository
- **pull_request (merged)**: Triggers cohesiveness check
- **workflow_run (failed)**: Triggers self-healing
- **issues (labeled auto-fix)**: Attempts automatic resolution

---

## Job States

| State | Description |
|-------|-------------|
| `pending` | Job is queued for processing |
| `running` | Job is currently executing |
| `completed` | Job finished successfully |
| `failed` | Job failed after all retries |
| `healing` | Self-healing in progress |
| `escalated` | Requires human intervention |

---

## Scheduled Jobs

The Worker runs scheduled jobs automatically:

| Schedule | Job |
|----------|-----|
| Every 15 minutes | Health check |
| Every 6 hours | Repository sync |
| Daily at midnight | Cohesiveness check + Dependency audit |

---

## Error Handling

All errors return JSON with appropriate HTTP status codes:

```json
{
  "error": "Error description",
  "message": "Detailed message",
  "selfHealing": "initiated"
}
```

When errors occur, the self-healing system automatically:
1. Attempts retry with exponential backoff
2. Falls back to cached data if available
3. Tries creative "quantum jump" solutions
4. Escalates to humans via GitHub issues

---

## Tracked Repositories

The system tracks these BlackRoad repositories by default:

- `blackroad-prism-console`
- `blackroad-os-agents`
- `blackroad-os-infra`
- `blackroad-network`
- `blackroad-systems`
- `blackroad-quantum`
- `lucidia-earth`
- `blackroad-me`
- `blackroad-inc`
- `blackroadai`

---

## Setup

### Cloudflare Resources Required

1. **KV Namespace**: `blackroad-agents-kv`
2. **D1 Database**: `blackroad-agents-db`
3. **Queue**: `blackroad-agent-jobs`
4. **R2 Bucket**: `blackroad-agents-artifacts` (optional)

### Secrets

Set via `wrangler secret put`:

```bash
wrangler secret put GITHUB_TOKEN
wrangler secret put GITHUB_WEBHOOK_SECRET
```

### Database Setup

```bash
wrangler d1 execute blackroad-agents-db --file=./db/schema.sql
```
