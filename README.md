# BlackRoad Agents

**Agent API with telemetry, job scheduling, and CeCe dynamic planner.**

```bash
pip install blackroad-agents
```

## What is this?

BlackRoad Agents provides the runtime infrastructure for AI agent orchestration:

| Component | Description |
|-----------|-------------|
| **Agent API** | REST API for agent registration, health, and task dispatch |
| **Telemetry** | Real-time metrics collection and monitoring (1,298 lines) |
| **Job Scheduler** | Priority-based job queue with retries and backoff |
| **Store** | Persistent agent state and configuration storage |
| **CeCe** | Dynamic planner with self-healing orchestration |

## Quick Start

### Run the API Server

```bash
# With pip
blackroad-agent

# With Docker
docker build -t blackroad-agents .
docker run -p 8000:8000 blackroad-agents

# With Railway
railway up
```

### API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Register an agent
curl -X POST http://localhost:8000/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name": "worker-1", "capabilities": ["code-review", "testing"]}'

# Submit a job
curl -X POST http://localhost:8000/jobs/submit \
  -H "Content-Type: application/json" \
  -d '{"type": "code-review", "payload": {"pr": 123}}'

# Get telemetry
curl http://localhost:8000/telemetry/metrics
```

## CeCe - Dynamic Planner

CeCe is the intelligent planning component that:

- **Dynamic Planning** - Breaks complex tasks into executable steps
- **Self-Healing** - Automatically recovers from failures
- **Natural Memory** - Maintains context across conversations
- **Issue Creator** - Generates GitHub issues from plans

```python
from cece import DynamicPlanner, SelfHealingOrchestrator

planner = DynamicPlanner()
plan = planner.create_plan("Deploy new feature to production")

orchestrator = SelfHealingOrchestrator()
result = orchestrator.execute(plan)
```

## Architecture

```
blackroad-agents/
├── agent/
│   ├── api.py          # FastAPI endpoints (864 lines)
│   ├── telemetry.py    # Metrics collection (1,298 lines)
│   ├── jobs.py         # Job scheduler (655 lines)
│   ├── store.py        # State persistence (627 lines)
│   ├── flash.py        # Fast operations (542 lines)
│   ├── config.py       # Configuration (343 lines)
│   ├── dashboard.py    # Monitoring UI (208 lines)
│   └── discover.py     # Agent discovery (167 lines)
├── cece/
│   ├── dynamic_planner.py         # Plan generation
│   ├── self_healing_orchestrator.py  # Failure recovery
│   ├── natural_memory.py          # Context retention
│   └── issue_creator.py           # GitHub integration
├── Dockerfile
└── railway.toml
```

## Configuration

Environment variables:

```bash
# Redis for job queue (optional)
REDIS_URL=redis://localhost:6379

# Telemetry settings
TELEMETRY_INTERVAL=30
TELEMETRY_BATCH_SIZE=100

# API settings
API_HOST=0.0.0.0
API_PORT=8000
```

## Deployment

### Railway

```bash
railway login
railway link
railway up
```

### Docker Compose

```yaml
version: "3.8"
services:
  agents:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
  redis:
    image: redis:7-alpine
```

## License

MIT - See [LICENSE](LICENSE) for details.

---

Built by [BlackRoad OS](https://blackroad.io)
