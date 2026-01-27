/**
 * ⬛⬜🛣️ BlackRoad Agents - Durable Objects
 *
 * Long-running stateful objects for agent coordination,
 * repo syncing, self-healing, and job orchestration.
 *
 * Durable Objects provide:
 * - Strong consistency within a single object
 * - Automatic persistence of state
 * - WebSocket support for real-time updates
 * - Unlimited execution time for long-running tasks
 */

// =============================================================================
// Agent Coordinator
// Manages agent swarm coordination and task distribution
// =============================================================================

export class AgentCoordinator {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.sessions = new Map(); // WebSocket sessions
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    // WebSocket upgrade
    if (request.headers.get('Upgrade') === 'websocket') {
      return this.handleWebSocket(request);
    }

    // REST API
    switch (path) {
      case '/status':
        return this.getStatus();
      case '/agents':
        return this.listAgents();
      case '/register':
        return this.registerAgent(request);
      case '/heartbeat':
        return this.handleHeartbeat(request);
      case '/task/assign':
        return this.assignTask(request);
      case '/task/complete':
        return this.completeTask(request);
      default:
        return new Response('Not found', { status: 404 });
    }
  }

  async handleWebSocket(request) {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    this.state.acceptWebSocket(server);

    const sessionId = crypto.randomUUID();
    this.sessions.set(sessionId, server);

    server.addEventListener('message', async (event) => {
      const data = JSON.parse(event.data);
      await this.handleMessage(sessionId, data, server);
    });

    server.addEventListener('close', () => {
      this.sessions.delete(sessionId);
    });

    return new Response(null, { status: 101, webSocket: client });
  }

  async handleMessage(sessionId, data, socket) {
    switch (data.type) {
      case 'register':
        await this.state.storage.put(`agent:${data.agentId}`, {
          id: data.agentId,
          sessionId,
          capabilities: data.capabilities,
          status: 'active',
          registeredAt: new Date().toISOString(),
          lastSeen: new Date().toISOString(),
        });
        socket.send(JSON.stringify({ type: 'registered', agentId: data.agentId }));
        this.broadcast({ type: 'agent_joined', agentId: data.agentId });
        break;

      case 'heartbeat':
        const agent = await this.state.storage.get(`agent:${data.agentId}`);
        if (agent) {
          agent.lastSeen = new Date().toISOString();
          agent.status = data.status || 'active';
          agent.atp = data.atp;
          await this.state.storage.put(`agent:${data.agentId}`, agent);
        }
        break;

      case 'task_update':
        await this.updateTask(data.taskId, data.update);
        this.broadcast({ type: 'task_updated', taskId: data.taskId, update: data.update });
        break;

      case 'request_task':
        const task = await this.getNextTask(data.agentId, data.capabilities);
        if (task) {
          socket.send(JSON.stringify({ type: 'task_assigned', task }));
        }
        break;
    }
  }

  broadcast(message) {
    const payload = JSON.stringify(message);
    for (const socket of this.sessions.values()) {
      try {
        socket.send(payload);
      } catch (e) {
        // Socket might be closed
      }
    }
  }

  async getStatus() {
    const agents = await this.state.storage.list({ prefix: 'agent:' });
    const tasks = await this.state.storage.list({ prefix: 'task:' });

    const activeAgents = Array.from(agents.values()).filter(a => a.status === 'active');
    const pendingTasks = Array.from(tasks.values()).filter(t => t.status === 'pending');

    return Response.json({
      totalAgents: agents.size,
      activeAgents: activeAgents.length,
      totalTasks: tasks.size,
      pendingTasks: pendingTasks.length,
      sessions: this.sessions.size,
    });
  }

  async listAgents() {
    const agents = await this.state.storage.list({ prefix: 'agent:' });
    return Response.json(Array.from(agents.values()));
  }

  async registerAgent(request) {
    const data = await request.json();
    await this.state.storage.put(`agent:${data.agentId}`, {
      id: data.agentId,
      capabilities: data.capabilities,
      status: 'active',
      registeredAt: new Date().toISOString(),
      lastSeen: new Date().toISOString(),
    });
    return Response.json({ registered: true, agentId: data.agentId });
  }

  async handleHeartbeat(request) {
    const data = await request.json();
    const agent = await this.state.storage.get(`agent:${data.agentId}`);
    if (agent) {
      agent.lastSeen = new Date().toISOString();
      agent.status = data.status || 'active';
      await this.state.storage.put(`agent:${data.agentId}`, agent);
      return Response.json({ ok: true });
    }
    return Response.json({ error: 'Agent not found' }, { status: 404 });
  }

  async assignTask(request) {
    const data = await request.json();
    const taskId = `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    await this.state.storage.put(`task:${taskId}`, {
      id: taskId,
      ...data,
      status: 'pending',
      createdAt: new Date().toISOString(),
    });

    this.broadcast({ type: 'new_task', taskId, task: data });
    return Response.json({ taskId });
  }

  async completeTask(request) {
    const data = await request.json();
    const task = await this.state.storage.get(`task:${data.taskId}`);

    if (task) {
      task.status = 'completed';
      task.result = data.result;
      task.completedAt = new Date().toISOString();
      task.completedBy = data.agentId;
      await this.state.storage.put(`task:${data.taskId}`, task);

      this.broadcast({ type: 'task_completed', taskId: data.taskId, result: data.result });
      return Response.json({ ok: true });
    }

    return Response.json({ error: 'Task not found' }, { status: 404 });
  }

  async updateTask(taskId, update) {
    const task = await this.state.storage.get(`task:${taskId}`);
    if (task) {
      Object.assign(task, update, { updatedAt: new Date().toISOString() });
      await this.state.storage.put(`task:${taskId}`, task);
    }
  }

  async getNextTask(agentId, capabilities) {
    const tasks = await this.state.storage.list({ prefix: 'task:' });

    for (const [key, task] of tasks) {
      if (task.status === 'pending') {
        // Check capability match
        if (!task.requiredCapabilities ||
            task.requiredCapabilities.every(c => capabilities.includes(c))) {
          task.status = 'assigned';
          task.assignedTo = agentId;
          task.assignedAt = new Date().toISOString();
          await this.state.storage.put(key, task);
          return task;
        }
      }
    }

    return null;
  }
}

// =============================================================================
// Repo Syncer
// Manages repository synchronization state and coordination
// =============================================================================

export class RepoSyncer {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    switch (path) {
      case '/status':
        return this.getStatus();
      case '/repos':
        return this.listRepos();
      case '/sync':
        return this.triggerSync(request);
      case '/webhook':
        return this.handleWebhook(request);
      default:
        return new Response('Not found', { status: 404 });
    }
  }

  async getStatus() {
    const repos = await this.state.storage.list({ prefix: 'repo:' });
    const syncing = Array.from(repos.values()).filter(r => r.syncing);
    const failed = Array.from(repos.values()).filter(r => r.lastSyncError);

    return Response.json({
      totalRepos: repos.size,
      syncing: syncing.length,
      failed: failed.length,
      lastActivity: await this.state.storage.get('lastActivity'),
    });
  }

  async listRepos() {
    const repos = await this.state.storage.list({ prefix: 'repo:' });
    return Response.json(Array.from(repos.values()));
  }

  async triggerSync(request) {
    const data = await request.json();
    const repoKey = `repo:${data.repoName}`;

    let repo = await this.state.storage.get(repoKey);
    if (!repo) {
      repo = {
        name: data.repoName,
        owner: data.owner || 'BlackRoad-OS',
      };
    }

    repo.syncing = true;
    repo.syncStartedAt = new Date().toISOString();
    await this.state.storage.put(repoKey, repo);
    await this.state.storage.put('lastActivity', new Date().toISOString());

    // In production, would trigger actual sync here
    // For now, simulate completion after a delay
    this.state.waitUntil(this.simulateSync(repoKey));

    return Response.json({ status: 'sync_started', repo: data.repoName });
  }

  async simulateSync(repoKey) {
    await new Promise(r => setTimeout(r, 2000)); // Simulate work

    const repo = await this.state.storage.get(repoKey);
    if (repo) {
      repo.syncing = false;
      repo.lastSyncAt = new Date().toISOString();
      repo.lastSyncError = null;
      await this.state.storage.put(repoKey, repo);
    }
  }

  async handleWebhook(request) {
    const data = await request.json();

    // Handle GitHub webhook events
    const event = request.headers.get('X-GitHub-Event');

    switch (event) {
      case 'push':
        await this.handlePush(data);
        break;
      case 'pull_request':
        await this.handlePullRequest(data);
        break;
    }

    return Response.json({ received: true });
  }

  async handlePush(data) {
    const repoName = data.repository?.name;
    if (repoName) {
      const repoKey = `repo:${repoName}`;
      let repo = await this.state.storage.get(repoKey) || { name: repoName };
      repo.lastPush = new Date().toISOString();
      repo.latestSha = data.after;
      repo.needsSync = true;
      await this.state.storage.put(repoKey, repo);
    }
  }

  async handlePullRequest(data) {
    const repoName = data.repository?.name;
    if (repoName && data.action === 'closed' && data.pull_request?.merged) {
      const repoKey = `repo:${repoName}`;
      let repo = await this.state.storage.get(repoKey) || { name: repoName };
      repo.lastMerge = new Date().toISOString();
      repo.needsSync = true;
      await this.state.storage.put(repoKey, repo);
    }
  }
}

// =============================================================================
// Self Healer
// Manages self-healing state and coordination
// =============================================================================

export class SelfHealer {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    switch (path) {
      case '/status':
        return this.getStatus();
      case '/issues':
        return this.listIssues();
      case '/report':
        return this.reportIssue(request);
      case '/resolve':
        return this.resolveIssue(request);
      case '/escalate':
        return this.escalateIssue(request);
      case '/learnings':
        return this.getLearnings();
      default:
        return new Response('Not found', { status: 404 });
    }
  }

  async getStatus() {
    const issues = await this.state.storage.list({ prefix: 'issue:' });
    const learnings = await this.state.storage.list({ prefix: 'learning:' });

    const active = Array.from(issues.values()).filter(i => !i.resolved);
    const resolved = Array.from(issues.values()).filter(i => i.resolved);
    const escalated = Array.from(issues.values()).filter(i => i.escalated);

    return Response.json({
      healthy: active.length === 0,
      activeIssues: active.length,
      resolvedIssues: resolved.length,
      escalatedIssues: escalated.length,
      totalLearnings: learnings.size,
      lastHealingRun: await this.state.storage.get('lastHealingRun'),
    });
  }

  async listIssues() {
    const issues = await this.state.storage.list({ prefix: 'issue:' });
    return Response.json(Array.from(issues.values()));
  }

  async reportIssue(request) {
    const data = await request.json();
    const issueId = `issue_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    const issue = {
      id: issueId,
      ...data,
      reportedAt: new Date().toISOString(),
      resolved: false,
      escalated: false,
      attempts: 0,
    };

    await this.state.storage.put(`issue:${issueId}`, issue);
    await this.state.storage.put('lastHealingRun', new Date().toISOString());

    return Response.json({ issueId, status: 'reported' });
  }

  async resolveIssue(request) {
    const data = await request.json();
    const issue = await this.state.storage.get(`issue:${data.issueId}`);

    if (!issue) {
      return Response.json({ error: 'Issue not found' }, { status: 404 });
    }

    issue.resolved = true;
    issue.resolvedAt = new Date().toISOString();
    issue.resolution = data.resolution;
    issue.resolvedBy = data.resolvedBy || 'auto';

    await this.state.storage.put(`issue:${data.issueId}`, issue);

    // Create learning from resolution
    await this.createLearning(issue, 'resolved');

    return Response.json({ ok: true });
  }

  async escalateIssue(request) {
    const data = await request.json();
    const issue = await this.state.storage.get(`issue:${data.issueId}`);

    if (!issue) {
      return Response.json({ error: 'Issue not found' }, { status: 404 });
    }

    issue.escalated = true;
    issue.escalatedAt = new Date().toISOString();
    issue.escalationReason = data.reason;

    await this.state.storage.put(`issue:${data.issueId}`, issue);

    // Create learning from escalation
    await this.createLearning(issue, 'escalated');

    return Response.json({ ok: true });
  }

  async createLearning(issue, outcome) {
    const learningId = `learning_${Date.now()}`;
    const learning = {
      id: learningId,
      issueType: issue.type,
      outcome,
      context: issue.context,
      resolution: issue.resolution,
      createdAt: new Date().toISOString(),
    };

    await this.state.storage.put(`learning:${learningId}`, learning);
    return learning;
  }

  async getLearnings() {
    const learnings = await this.state.storage.list({ prefix: 'learning:' });
    return Response.json(Array.from(learnings.values()));
  }
}

// =============================================================================
// Job Orchestrator
// Manages job scheduling and execution coordination
// =============================================================================

export class JobOrchestrator {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    switch (path) {
      case '/status':
        return this.getStatus();
      case '/jobs':
        return this.listJobs();
      case '/schedule':
        return this.scheduleJob(request);
      case '/cancel':
        return this.cancelJob(request);
      case '/run':
        return this.runJob(request);
      case '/cron':
        return this.handleCron(request);
      default:
        return new Response('Not found', { status: 404 });
    }
  }

  async getStatus() {
    const jobs = await this.state.storage.list({ prefix: 'job:' });

    const pending = Array.from(jobs.values()).filter(j => j.status === 'pending');
    const running = Array.from(jobs.values()).filter(j => j.status === 'running');
    const completed = Array.from(jobs.values()).filter(j => j.status === 'completed');
    const failed = Array.from(jobs.values()).filter(j => j.status === 'failed');

    return Response.json({
      totalJobs: jobs.size,
      pending: pending.length,
      running: running.length,
      completed: completed.length,
      failed: failed.length,
      lastRun: await this.state.storage.get('lastJobRun'),
    });
  }

  async listJobs() {
    const jobs = await this.state.storage.list({ prefix: 'job:' });
    return Response.json(Array.from(jobs.values()));
  }

  async scheduleJob(request) {
    const data = await request.json();
    const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    const job = {
      id: jobId,
      type: data.type,
      payload: data.payload,
      priority: data.priority || 5,
      status: 'pending',
      scheduledFor: data.scheduledFor || new Date().toISOString(),
      createdAt: new Date().toISOString(),
      attempts: 0,
      maxAttempts: data.maxAttempts || 3,
    };

    await this.state.storage.put(`job:${jobId}`, job);

    // If scheduled for now, set an alarm
    if (!data.scheduledFor || new Date(data.scheduledFor) <= new Date()) {
      await this.state.storage.setAlarm(Date.now() + 100);
    } else {
      await this.state.storage.setAlarm(new Date(data.scheduledFor).getTime());
    }

    return Response.json({ jobId, status: 'scheduled' });
  }

  async cancelJob(request) {
    const data = await request.json();
    const job = await this.state.storage.get(`job:${data.jobId}`);

    if (!job) {
      return Response.json({ error: 'Job not found' }, { status: 404 });
    }

    if (job.status === 'running') {
      return Response.json({ error: 'Cannot cancel running job' }, { status: 400 });
    }

    job.status = 'cancelled';
    job.cancelledAt = new Date().toISOString();
    await this.state.storage.put(`job:${data.jobId}`, job);

    return Response.json({ ok: true });
  }

  async runJob(request) {
    const data = await request.json();
    const job = await this.state.storage.get(`job:${data.jobId}`);

    if (!job) {
      return Response.json({ error: 'Job not found' }, { status: 404 });
    }

    job.status = 'running';
    job.startedAt = new Date().toISOString();
    job.attempts++;
    await this.state.storage.put(`job:${data.jobId}`, job);

    // Simulate job execution
    this.state.waitUntil(this.executeJob(data.jobId));

    return Response.json({ status: 'started' });
  }

  async executeJob(jobId) {
    const job = await this.state.storage.get(`job:${jobId}`);
    if (!job) return;

    try {
      // Simulate work
      await new Promise(r => setTimeout(r, 1000));

      job.status = 'completed';
      job.completedAt = new Date().toISOString();
      job.result = { success: true };
    } catch (error) {
      job.status = job.attempts >= job.maxAttempts ? 'failed' : 'pending';
      job.error = error.message;
    }

    await this.state.storage.put(`job:${jobId}`, job);
    await this.state.storage.put('lastJobRun', new Date().toISOString());
  }

  async handleCron(request) {
    const data = await request.json();

    // Schedule a cron-triggered job
    return this.scheduleJob(new Request(request.url, {
      method: 'POST',
      body: JSON.stringify({
        type: 'cron',
        payload: { cron: data.cron },
        priority: 10,
      }),
    }));
  }

  // Handle alarms for scheduled jobs
  async alarm() {
    const jobs = await this.state.storage.list({ prefix: 'job:' });

    for (const [key, job] of jobs) {
      if (job.status === 'pending' && new Date(job.scheduledFor) <= new Date()) {
        await this.executeJob(job.id);
      }
    }
  }
}
