/**
 * ⬛⬜🛣️ BlackRoad Agents - Cloudflare Workers
 *
 * Self-healing agent job system with cross-repo syncing.
 * Inspired by Cece's consciousness-aware planning framework.
 *
 * Features:
 * - Scheduled cron jobs for automated tasks
 * - Cross-repo sync for BlackRoad ecosystem cohesion
 * - Self-healing with automatic issue resolution
 * - Durable Objects for long-running agent tasks
 * - Learning memory that persists across invocations
 */

import { JobScheduler, CRON_SCHEDULES } from './jobs/scheduler.js';
import { RepoSyncManager, BLACKROAD_REPOS } from './sync/repo-sync.js';
import { SelfHealingEngine } from './self-healing/healer.js';
import { AgentCoordinator, RepoSyncer, SelfHealer, JobOrchestrator } from './durable-objects/index.js';
import { createResponse, logEvent } from './utils/helpers.js';

// Re-export Durable Object classes for wrangler
export { AgentCoordinator, RepoSyncer, SelfHealer, JobOrchestrator };

/**
 * Main Worker Entry Point
 */
export default {
  /**
   * Handle HTTP requests
   */
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    try {
      // Health check
      if (path === '/health' || path === '/healthz') {
        return createResponse({
          status: 'healthy',
          version: env.VERSION,
          environment: env.ENVIRONMENT,
          timestamp: new Date().toISOString(),
        });
      }

      // API Routes
      if (path.startsWith('/api/')) {
        return await handleApiRoutes(path, request, env, ctx);
      }

      // Dashboard
      if (path === '/' || path === '/dashboard') {
        return await renderDashboard(env);
      }

      // 404
      return createResponse({ error: 'Not found' }, 404);

    } catch (error) {
      await logEvent(env, 'error', 'fetch_error', { error: error.message, path });
      return createResponse({ error: error.message }, 500);
    }
  },

  /**
   * Handle scheduled cron triggers
   * This is where the magic happens - self-healing agent jobs!
   */
  async scheduled(event, env, ctx) {
    const cronTime = event.cron;
    const scheduler = new JobScheduler(env);

    await logEvent(env, 'info', 'cron_triggered', { cron: cronTime });

    try {
      switch (cronTime) {
        // Every 5 minutes - Quick health check & self-healing
        case '*/5 * * * *':
          ctx.waitUntil(scheduler.runHealthCheck());
          ctx.waitUntil(scheduler.runQuickSelfHeal());
          break;

        // Every 15 minutes - Cross-repo sync check
        case '*/15 * * * *':
          ctx.waitUntil(scheduler.runRepoSyncCheck());
          break;

        // Every hour - Full repo scrape & cohesion analysis
        case '0 * * * *':
          ctx.waitUntil(scheduler.runFullRepoScrape());
          ctx.waitUntil(scheduler.runCohesionAnalysis());
          break;

        // Every 6 hours - Deep analysis & learning aggregation
        case '0 */6 * * *':
          ctx.waitUntil(scheduler.runDeepAnalysis());
          ctx.waitUntil(scheduler.aggregateLearnings());
          break;

        // Daily at midnight UTC - Full system reconciliation
        case '0 0 * * *':
          ctx.waitUntil(scheduler.runDailyReconciliation());
          ctx.waitUntil(scheduler.generateDailyReport());
          ctx.waitUntil(scheduler.cleanupOldData());
          break;

        default:
          await logEvent(env, 'warn', 'unknown_cron', { cron: cronTime });
      }

      await logEvent(env, 'info', 'cron_completed', { cron: cronTime });
    } catch (error) {
      await logEvent(env, 'error', 'cron_error', {
        cron: cronTime,
        error: error.message
      });

      // Trigger self-healing on cron failures
      const healer = new SelfHealingEngine(env);
      await healer.handleCronFailure(cronTime, error);
    }
  },

  /**
   * Handle queue messages (for async job processing)
   */
  async queue(batch, env, ctx) {
    const scheduler = new JobScheduler(env);

    for (const message of batch.messages) {
      try {
        await scheduler.processQueuedJob(message.body);
        message.ack();
      } catch (error) {
        await logEvent(env, 'error', 'queue_error', {
          messageId: message.id,
          error: error.message
        });

        // Retry up to 3 times
        if (message.retryCount < 3) {
          message.retry();
        } else {
          // Dead letter - trigger self-healing
          const healer = new SelfHealingEngine(env);
          await healer.handleDeadLetter(message);
          message.ack();
        }
      }
    }
  },
};

/**
 * Handle API routes
 */
async function handleApiRoutes(path, request, env, ctx) {
  const method = request.method;

  // Jobs API
  if (path === '/api/jobs') {
    if (method === 'GET') {
      return await getJobs(env);
    }
    if (method === 'POST') {
      return await createJob(request, env);
    }
  }

  if (path.match(/^\/api\/jobs\/[\w-]+$/)) {
    const jobId = path.split('/').pop();
    if (method === 'GET') return await getJob(jobId, env);
    if (method === 'DELETE') return await cancelJob(jobId, env);
  }

  // Manual trigger for jobs
  if (path === '/api/jobs/trigger' && method === 'POST') {
    const body = await request.json();
    const scheduler = new JobScheduler(env);
    const result = await scheduler.triggerJob(body.jobType);
    return createResponse(result);
  }

  // Repos API
  if (path === '/api/repos') {
    const syncManager = new RepoSyncManager(env);
    const repos = await syncManager.listTrackedRepos();
    return createResponse(repos);
  }

  if (path === '/api/repos/sync' && method === 'POST') {
    const syncManager = new RepoSyncManager(env);
    ctx.waitUntil(syncManager.syncAllRepos());
    return createResponse({ status: 'sync_started' });
  }

  if (path.match(/^\/api\/repos\/[\w-]+\/sync$/) && method === 'POST') {
    const repoName = path.split('/')[3];
    const syncManager = new RepoSyncManager(env);
    ctx.waitUntil(syncManager.syncRepo(repoName));
    return createResponse({ status: 'sync_started', repo: repoName });
  }

  // Self-healing API
  if (path === '/api/healing/status') {
    const healer = new SelfHealingEngine(env);
    const status = await healer.getStatus();
    return createResponse(status);
  }

  if (path === '/api/healing/issues') {
    const healer = new SelfHealingEngine(env);
    const issues = await healer.getActiveIssues();
    return createResponse(issues);
  }

  if (path === '/api/healing/trigger' && method === 'POST') {
    const healer = new SelfHealingEngine(env);
    ctx.waitUntil(healer.runFullScan());
    return createResponse({ status: 'healing_triggered' });
  }

  // Stats API
  if (path === '/api/stats') {
    const stats = await getSystemStats(env);
    return createResponse(stats);
  }

  // Learning/Memory API
  if (path === '/api/learnings') {
    const learnings = await env.LEARNING_MEMORY.list();
    const data = await Promise.all(
      learnings.keys.map(async (k) => ({
        key: k.name,
        value: await env.LEARNING_MEMORY.get(k.name, 'json'),
      }))
    );
    return createResponse(data);
  }

  return createResponse({ error: 'API endpoint not found' }, 404);
}

/**
 * Get all jobs
 */
async function getJobs(env) {
  const jobs = await env.JOB_QUEUE.list();
  const data = await Promise.all(
    jobs.keys.map(async (k) => ({
      id: k.name,
      ...await env.JOB_QUEUE.get(k.name, 'json'),
    }))
  );
  return createResponse(data);
}

/**
 * Get single job
 */
async function getJob(jobId, env) {
  const job = await env.JOB_QUEUE.get(jobId, 'json');
  if (!job) {
    return createResponse({ error: 'Job not found' }, 404);
  }
  return createResponse({ id: jobId, ...job });
}

/**
 * Create a new job
 */
async function createJob(request, env) {
  const body = await request.json();
  const scheduler = new JobScheduler(env);
  const job = await scheduler.createJob(body);
  return createResponse(job, 201);
}

/**
 * Cancel a job
 */
async function cancelJob(jobId, env) {
  await env.JOB_QUEUE.delete(jobId);
  return createResponse({ status: 'cancelled', jobId });
}

/**
 * Get system stats
 */
async function getSystemStats(env) {
  const [agentState, jobQueue, learnings] = await Promise.all([
    env.AGENT_STATE.list(),
    env.JOB_QUEUE.list(),
    env.LEARNING_MEMORY.list(),
  ]);

  return {
    agents: agentState.keys.length,
    pendingJobs: jobQueue.keys.length,
    learnings: learnings.keys.length,
    environment: env.ENVIRONMENT,
    version: env.VERSION,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Render dashboard HTML
 */
async function renderDashboard(env) {
  const stats = await getSystemStats(env);

  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BlackRoad Agents Dashboard</title>
  <style>
    :root {
      --bg: #0a0a0a;
      --surface: #141414;
      --border: #2a2a2a;
      --text: #fafafa;
      --text-muted: #888;
      --accent: #f97316;
      --success: #22c55e;
      --warning: #eab308;
      --error: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem;
    }
    .container { max-width: 1400px; margin: 0 auto; }
    header {
      display: flex;
      align-items: center;
      gap: 1rem;
      margin-bottom: 2rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }
    .logo { font-size: 2rem; }
    h1 { font-size: 1.5rem; font-weight: 600; }
    .version { color: var(--text-muted); font-size: 0.875rem; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1.5rem;
      margin-bottom: 2rem;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
    }
    .card-title {
      font-size: 0.875rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.5rem;
    }
    .stat {
      font-size: 2.5rem;
      font-weight: 700;
      background: linear-gradient(135deg, var(--accent), #ec4899);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
    }
    .status-healthy { background: rgba(34, 197, 94, 0.2); color: var(--success); }
    .status-warning { background: rgba(234, 179, 8, 0.2); color: var(--warning); }
    .status-error { background: rgba(239, 68, 68, 0.2); color: var(--error); }
    .pulse {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.4; }
    }
    .section-title {
      font-size: 1.125rem;
      font-weight: 600;
      margin-bottom: 1rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      text-align: left;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
    }
    th { color: var(--text-muted); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
    code {
      font-family: 'SF Mono', 'Fira Code', monospace;
      font-size: 0.875rem;
      background: var(--bg);
      padding: 0.125rem 0.375rem;
      border-radius: 4px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 500;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: var(--accent);
      color: white;
    }
    .btn-primary:hover { filter: brightness(1.1); }
    .btn-secondary {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
    }
    .btn-secondary:hover { background: var(--border); }
    .actions { display: flex; gap: 0.5rem; margin-top: 1rem; }
    footer {
      margin-top: 3rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      text-align: center;
      color: var(--text-muted);
      font-size: 0.875rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <span class="logo">⬛⬜🛣️</span>
      <div>
        <h1>BlackRoad Agents</h1>
        <span class="version">v${stats.version} | ${stats.environment}</span>
      </div>
      <div style="margin-left: auto;">
        <span class="status-badge status-healthy">
          <span class="pulse"></span>
          System Healthy
        </span>
      </div>
    </header>

    <div class="grid">
      <div class="card">
        <div class="card-title">Active Agents</div>
        <div class="stat">${stats.agents}</div>
      </div>
      <div class="card">
        <div class="card-title">Pending Jobs</div>
        <div class="stat">${stats.pendingJobs}</div>
      </div>
      <div class="card">
        <div class="card-title">Learnings</div>
        <div class="stat">${stats.learnings}</div>
      </div>
      <div class="card">
        <div class="card-title">Last Updated</div>
        <div style="font-size: 1rem; margin-top: 0.5rem;">${new Date(stats.timestamp).toLocaleString()}</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="section-title">Scheduled Jobs (Cron)</div>
      <table>
        <thead>
          <tr>
            <th>Schedule</th>
            <th>Task</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>*/5 * * * *</code></td>
            <td>Health Check & Quick Self-Heal</td>
            <td><span class="status-badge status-healthy"><span class="pulse"></span>Active</span></td>
          </tr>
          <tr>
            <td><code>*/15 * * * *</code></td>
            <td>Cross-Repo Sync Check</td>
            <td><span class="status-badge status-healthy"><span class="pulse"></span>Active</span></td>
          </tr>
          <tr>
            <td><code>0 * * * *</code></td>
            <td>Full Repo Scrape & Cohesion Analysis</td>
            <td><span class="status-badge status-healthy"><span class="pulse"></span>Active</span></td>
          </tr>
          <tr>
            <td><code>0 */6 * * *</code></td>
            <td>Deep Analysis & Learning Aggregation</td>
            <td><span class="status-badge status-healthy"><span class="pulse"></span>Active</span></td>
          </tr>
          <tr>
            <td><code>0 0 * * *</code></td>
            <td>Daily Reconciliation & Report</td>
            <td><span class="status-badge status-healthy"><span class="pulse"></span>Active</span></td>
          </tr>
        </tbody>
      </table>
      <div class="actions">
        <button class="btn btn-primary" onclick="triggerJob('health_check')">Run Health Check</button>
        <button class="btn btn-secondary" onclick="triggerJob('repo_sync')">Trigger Repo Sync</button>
        <button class="btn btn-secondary" onclick="triggerJob('self_heal')">Trigger Self-Heal</button>
      </div>
    </div>

    <div class="card">
      <div class="section-title">Tracked Repositories</div>
      <table>
        <thead>
          <tr>
            <th>Repository</th>
            <th>Type</th>
            <th>Last Sync</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>blackroad-prism-console</code></td>
            <td>Frontend</td>
            <td>-</td>
            <td><button class="btn btn-secondary" onclick="syncRepo('blackroad-prism-console')">Sync</button></td>
          </tr>
          <tr>
            <td><code>blackroad-os-agents</code></td>
            <td>Agents (Canonical)</td>
            <td>-</td>
            <td><button class="btn btn-secondary" onclick="syncRepo('blackroad-os-agents')">Sync</button></td>
          </tr>
          <tr>
            <td><code>blackroad-os-infra</code></td>
            <td>Infrastructure</td>
            <td>-</td>
            <td><button class="btn btn-secondary" onclick="syncRepo('blackroad-os-infra')">Sync</button></td>
          </tr>
          <tr>
            <td><code>blackroad-agents</code></td>
            <td>Agents (Archive)</td>
            <td>-</td>
            <td><button class="btn btn-secondary" onclick="syncRepo('blackroad-agents')">Sync</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer>
      <p>BlackRoad OS, Inc. | Powered by Cloudflare Workers</p>
      <p style="margin-top: 0.5rem;">Self-healing agent system with consciousness-aware planning</p>
    </footer>
  </div>

  <script>
    async function triggerJob(jobType) {
      const res = await fetch('/api/jobs/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobType })
      });
      const data = await res.json();
      alert('Job triggered: ' + JSON.stringify(data));
    }

    async function syncRepo(repoName) {
      const res = await fetch('/api/repos/' + repoName + '/sync', { method: 'POST' });
      const data = await res.json();
      alert('Sync started for ' + repoName);
    }
  </script>
</body>
</html>
  `;

  return new Response(html, {
    headers: { 'Content-Type': 'text/html' },
  });
}
