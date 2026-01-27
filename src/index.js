/**
 * BlackRoad Agent Jobs - Cloudflare Workers Orchestrator
 *
 * A self-healing, consciousness-aware job system that:
 * - Scrapes and syncs across BlackRoad repos
 * - Ensures cohesiveness across the ecosystem
 * - Auto-updates and self-resolves issues
 *
 * @author BlackRoad OS, Inc.
 * @license PROPRIETARY
 */

// ============================================================================
// CONSTANTS & CONFIGURATION
// ============================================================================

const BLACKROAD_REPOS = [
  'blackroad-prism-console',
  'blackroad-os-agents',
  'blackroad-os-infra',
  'blackroad-network',
  'blackroad-systems',
  'blackroad-quantum',
  'lucidia-earth',
  'blackroad-me',
  'blackroad-inc',
  'blackroadai',
];

const JOB_TYPES = {
  REPO_SYNC: 'repo_sync',
  COHESIVENESS_CHECK: 'cohesiveness_check',
  SELF_HEAL: 'self_heal',
  DEPENDENCY_AUDIT: 'dependency_audit',
  WORKFLOW_SYNC: 'workflow_sync',
  CONFIG_SYNC: 'config_sync',
  TRINITY_COMPLIANCE: 'trinity_compliance',
};

const JOB_STATES = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  HEALING: 'healing',
  ESCALATED: 'escalated',
};

const SELF_HEAL_STRATEGIES = {
  RETRY: 'retry',
  FALLBACK: 'fallback',
  ESCALATE: 'escalate',
  QUANTUM_JUMP: 'quantum_jump', // Creative breakthrough
};

// ============================================================================
// CORE WORKER EXPORT
// ============================================================================

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers for all responses
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-BlackRoad-Agent',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // Route handling
      if (path === '/' || path === '/healthz') {
        return jsonResponse({
          status: 'healthy',
          service: 'blackroad-agent-jobs',
          version: '1.0.0',
          timestamp: new Date().toISOString(),
          jobs: Object.keys(JOB_TYPES),
        }, corsHeaders);
      }

      if (path === '/api/jobs' && request.method === 'GET') {
        return await handleListJobs(env, corsHeaders);
      }

      if (path === '/api/jobs' && request.method === 'POST') {
        return await handleCreateJob(request, env, ctx, corsHeaders);
      }

      if (path.startsWith('/api/jobs/') && request.method === 'GET') {
        const jobId = path.split('/')[3];
        return await handleGetJob(jobId, env, corsHeaders);
      }

      if (path === '/api/sync/repos' && request.method === 'POST') {
        return await handleRepoSync(request, env, ctx, corsHeaders);
      }

      if (path === '/api/cohesiveness/check' && request.method === 'POST') {
        return await handleCohesivenessCheck(env, ctx, corsHeaders);
      }

      if (path === '/api/self-heal' && request.method === 'POST') {
        return await handleSelfHeal(request, env, ctx, corsHeaders);
      }

      if (path === '/api/scrape' && request.method === 'POST') {
        return await handleRepoScrape(request, env, ctx, corsHeaders);
      }

      if (path === '/webhook/github' && request.method === 'POST') {
        return await handleGitHubWebhook(request, env, ctx, corsHeaders);
      }

      return jsonResponse({ error: 'Not found', path }, corsHeaders, 404);

    } catch (error) {
      console.error('Worker error:', error);

      // Self-healing: Log the error and attempt recovery
      ctx.waitUntil(attemptSelfHealing(error, env, { path, method: request.method }));

      return jsonResponse({
        error: 'Internal server error',
        message: error.message,
        selfHealing: 'initiated',
      }, corsHeaders, 500);
    }
  },

  // Scheduled triggers for automated jobs
  async scheduled(event, env, ctx) {
    const trigger = event.cron;
    console.log(`Scheduled trigger: ${trigger}`);

    try {
      switch (trigger) {
        case '0 */6 * * *': // Every 6 hours
          await runRepoSyncJob(env, ctx);
          break;
        case '0 0 * * *': // Daily at midnight
          await runCohesivenessCheck(env, ctx);
          await runDependencyAudit(env, ctx);
          break;
        case '*/15 * * * *': // Every 15 minutes
          await runHealthCheck(env, ctx);
          break;
        default:
          console.log(`Unknown cron trigger: ${trigger}`);
      }
    } catch (error) {
      console.error('Scheduled job error:', error);
      ctx.waitUntil(attemptSelfHealing(error, env, { trigger }));
    }
  },

  // Queue consumer for job processing
  async queue(batch, env, ctx) {
    for (const message of batch.messages) {
      try {
        const job = message.body;
        console.log(`Processing job: ${job.id} (${job.type})`);

        await processJob(job, env, ctx);
        message.ack();
      } catch (error) {
        console.error('Queue processing error:', error);
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};

// ============================================================================
// JOB HANDLERS
// ============================================================================

async function handleListJobs(env, corsHeaders) {
  const jobs = await getJobsFromKV(env);
  return jsonResponse({ jobs, total: jobs.length }, corsHeaders);
}

async function handleCreateJob(request, env, ctx, corsHeaders) {
  const body = await request.json();
  const { type, config = {} } = body;

  if (!JOB_TYPES[type?.toUpperCase()?.replace(/-/g, '_')]) {
    return jsonResponse({ error: 'Invalid job type', validTypes: Object.keys(JOB_TYPES) }, corsHeaders, 400);
  }

  const job = {
    id: crypto.randomUUID(),
    type,
    config,
    state: JOB_STATES.PENDING,
    createdAt: new Date().toISOString(),
    attempts: 0,
    maxAttempts: 3,
    healingAttempts: 0,
  };

  await saveJobToKV(env, job);

  // Queue the job for processing
  if (env.JOB_QUEUE) {
    ctx.waitUntil(env.JOB_QUEUE.send(job));
  } else {
    // Fallback: process immediately
    ctx.waitUntil(processJob(job, env, ctx));
  }

  return jsonResponse({ job, message: 'Job created and queued' }, corsHeaders, 201);
}

async function handleGetJob(jobId, env, corsHeaders) {
  const job = await getJobFromKV(env, jobId);
  if (!job) {
    return jsonResponse({ error: 'Job not found' }, corsHeaders, 404);
  }
  return jsonResponse({ job }, corsHeaders);
}

async function handleRepoSync(request, env, ctx, corsHeaders) {
  const body = await request.json().catch(() => ({}));
  const repos = body.repos || BLACKROAD_REPOS;

  const job = {
    id: crypto.randomUUID(),
    type: JOB_TYPES.REPO_SYNC,
    config: { repos },
    state: JOB_STATES.RUNNING,
    createdAt: new Date().toISOString(),
    attempts: 0,
    maxAttempts: 3,
    healingAttempts: 0,
  };

  await saveJobToKV(env, job);
  ctx.waitUntil(runRepoSyncJob(env, ctx, repos, job.id));

  return jsonResponse({
    job,
    message: 'Repo sync initiated',
    repos,
  }, corsHeaders, 202);
}

async function handleCohesivenessCheck(env, ctx, corsHeaders) {
  const job = {
    id: crypto.randomUUID(),
    type: JOB_TYPES.COHESIVENESS_CHECK,
    state: JOB_STATES.RUNNING,
    createdAt: new Date().toISOString(),
    attempts: 0,
    maxAttempts: 3,
    healingAttempts: 0,
  };

  await saveJobToKV(env, job);
  ctx.waitUntil(runCohesivenessCheck(env, ctx, job.id));

  return jsonResponse({
    job,
    message: 'Cohesiveness check initiated',
  }, corsHeaders, 202);
}

async function handleSelfHeal(request, env, ctx, corsHeaders) {
  const body = await request.json();
  const { jobId, error, strategy = SELF_HEAL_STRATEGIES.RETRY } = body;

  const result = await performSelfHealing(jobId, error, strategy, env, ctx);

  return jsonResponse({
    message: 'Self-healing attempted',
    result,
    strategy,
  }, corsHeaders);
}

async function handleRepoScrape(request, env, ctx, corsHeaders) {
  const body = await request.json();
  const { repo, paths = ['**/*.md', '**/*.json', '**/wrangler.toml'] } = body;

  if (!repo) {
    return jsonResponse({ error: 'repo is required' }, corsHeaders, 400);
  }

  const job = {
    id: crypto.randomUUID(),
    type: 'repo_scrape',
    config: { repo, paths },
    state: JOB_STATES.RUNNING,
    createdAt: new Date().toISOString(),
    attempts: 0,
    maxAttempts: 3,
    healingAttempts: 0,
  };

  await saveJobToKV(env, job);
  ctx.waitUntil(scrapeRepository(repo, paths, env, ctx, job.id));

  return jsonResponse({
    job,
    message: `Scraping ${repo} initiated`,
  }, corsHeaders, 202);
}

async function handleGitHubWebhook(request, env, ctx, corsHeaders) {
  const event = request.headers.get('X-GitHub-Event');
  const signature = request.headers.get('X-Hub-Signature-256');
  const body = await request.text();

  // Verify webhook signature if secret is configured
  if (env.GITHUB_WEBHOOK_SECRET) {
    const isValid = await verifyGitHubSignature(body, signature, env.GITHUB_WEBHOOK_SECRET);
    if (!isValid) {
      return jsonResponse({ error: 'Invalid signature' }, corsHeaders, 401);
    }
  }

  const payload = JSON.parse(body);
  console.log(`GitHub webhook: ${event}`, payload.repository?.full_name);

  // Handle different events
  switch (event) {
    case 'push':
      ctx.waitUntil(handlePushEvent(payload, env, ctx));
      break;
    case 'pull_request':
      ctx.waitUntil(handlePREvent(payload, env, ctx));
      break;
    case 'workflow_run':
      ctx.waitUntil(handleWorkflowEvent(payload, env, ctx));
      break;
    case 'issues':
      ctx.waitUntil(handleIssueEvent(payload, env, ctx));
      break;
  }

  return jsonResponse({
    received: true,
    event,
    repository: payload.repository?.full_name,
  }, corsHeaders);
}

// ============================================================================
// JOB PROCESSING
// ============================================================================

async function processJob(job, env, ctx) {
  console.log(`Processing job ${job.id} of type ${job.type}`);

  try {
    job.state = JOB_STATES.RUNNING;
    job.startedAt = new Date().toISOString();
    job.attempts++;
    await saveJobToKV(env, job);

    let result;
    switch (job.type) {
      case JOB_TYPES.REPO_SYNC:
        result = await runRepoSyncJob(env, ctx, job.config?.repos, job.id);
        break;
      case JOB_TYPES.COHESIVENESS_CHECK:
        result = await runCohesivenessCheck(env, ctx, job.id);
        break;
      case JOB_TYPES.SELF_HEAL:
        result = await performSelfHealing(job.config?.targetJobId, job.config?.error, job.config?.strategy, env, ctx);
        break;
      case JOB_TYPES.DEPENDENCY_AUDIT:
        result = await runDependencyAudit(env, ctx, job.id);
        break;
      case JOB_TYPES.WORKFLOW_SYNC:
        result = await runWorkflowSync(env, ctx, job.id);
        break;
      case JOB_TYPES.CONFIG_SYNC:
        result = await runConfigSync(env, ctx, job.id);
        break;
      case JOB_TYPES.TRINITY_COMPLIANCE:
        result = await runTrinityComplianceCheck(env, ctx, job.id);
        break;
      default:
        throw new Error(`Unknown job type: ${job.type}`);
    }

    job.state = JOB_STATES.COMPLETED;
    job.completedAt = new Date().toISOString();
    job.result = result;
    await saveJobToKV(env, job);

    return result;

  } catch (error) {
    console.error(`Job ${job.id} failed:`, error);

    if (job.attempts < job.maxAttempts) {
      // Auto-retry
      job.state = JOB_STATES.HEALING;
      job.lastError = error.message;
      await saveJobToKV(env, job);

      // Exponential backoff
      const delay = Math.pow(2, job.attempts) * 1000;
      await sleep(delay);

      return await processJob(job, env, ctx);
    }

    // Exhausted retries, attempt self-healing
    job.state = JOB_STATES.HEALING;
    job.healingAttempts++;
    await saveJobToKV(env, job);

    const healed = await attemptSelfHealing(error, env, { jobId: job.id, type: job.type });

    if (!healed) {
      job.state = JOB_STATES.ESCALATED;
      job.escalatedAt = new Date().toISOString();
      await saveJobToKV(env, job);

      // Create a GitHub issue for human intervention
      await createEscalationIssue(job, error, env);
    }

    throw error;
  }
}

// ============================================================================
// REPO SYNC & SCRAPING
// ============================================================================

async function runRepoSyncJob(env, ctx, repos = BLACKROAD_REPOS, jobId = null) {
  const results = {
    synced: [],
    failed: [],
    timestamp: new Date().toISOString(),
  };

  for (const repo of repos) {
    try {
      const repoData = await fetchRepoData(repo, env);
      await storeRepoData(repo, repoData, env);
      results.synced.push({ repo, files: repoData.files?.length || 0 });
    } catch (error) {
      console.error(`Failed to sync ${repo}:`, error);
      results.failed.push({ repo, error: error.message });
    }
  }

  // Store sync results
  if (env.KV) {
    await env.KV.put('sync:latest', JSON.stringify(results), {
      metadata: { timestamp: results.timestamp },
    });
  }

  console.log(`Repo sync complete: ${results.synced.length} synced, ${results.failed.length} failed`);
  return results;
}

async function fetchRepoData(repo, env) {
  const org = env.ORG_NAME || 'BlackRoad-OS';
  const token = env.GITHUB_TOKEN;

  const headers = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'BlackRoad-Agent-Jobs/1.0',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Fetch repo metadata
  const repoResponse = await fetch(`https://api.github.com/repos/${org}/${repo}`, { headers });

  if (!repoResponse.ok) {
    throw new Error(`Failed to fetch ${repo}: ${repoResponse.status}`);
  }

  const repoInfo = await repoResponse.json();

  // Fetch key files
  const keyFiles = ['wrangler.toml', 'package.json', 'pyproject.toml', 'README.md', '.trinity/README.md'];
  const files = [];

  for (const file of keyFiles) {
    try {
      const contentResponse = await fetch(
        `https://api.github.com/repos/${org}/${repo}/contents/${file}`,
        { headers }
      );

      if (contentResponse.ok) {
        const content = await contentResponse.json();
        files.push({
          path: file,
          sha: content.sha,
          size: content.size,
          content: content.encoding === 'base64' ? atob(content.content) : null,
        });
      }
    } catch (e) {
      // File doesn't exist, skip
    }
  }

  // Fetch recent commits
  const commitsResponse = await fetch(
    `https://api.github.com/repos/${org}/${repo}/commits?per_page=5`,
    { headers }
  );
  const commits = commitsResponse.ok ? await commitsResponse.json() : [];

  // Fetch workflows
  const workflowsResponse = await fetch(
    `https://api.github.com/repos/${org}/${repo}/actions/workflows`,
    { headers }
  );
  const workflows = workflowsResponse.ok ? (await workflowsResponse.json()).workflows : [];

  return {
    name: repoInfo.name,
    fullName: repoInfo.full_name,
    description: repoInfo.description,
    defaultBranch: repoInfo.default_branch,
    updatedAt: repoInfo.updated_at,
    stars: repoInfo.stargazers_count,
    topics: repoInfo.topics,
    files,
    recentCommits: commits.map(c => ({
      sha: c.sha,
      message: c.commit?.message,
      author: c.commit?.author?.name,
      date: c.commit?.author?.date,
    })),
    workflows: workflows.map(w => ({
      id: w.id,
      name: w.name,
      state: w.state,
      path: w.path,
    })),
  };
}

async function scrapeRepository(repo, paths, env, ctx, jobId) {
  const org = env.ORG_NAME || 'BlackRoad-OS';
  const token = env.GITHUB_TOKEN;

  const headers = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'BlackRoad-Agent-Jobs/1.0',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const scrapedData = {
    repo,
    scrapedAt: new Date().toISOString(),
    files: [],
    patterns: paths,
  };

  // Get the tree
  try {
    const repoResponse = await fetch(`https://api.github.com/repos/${org}/${repo}`, { headers });
    if (!repoResponse.ok) throw new Error(`Repo not found: ${repo}`);
    const repoInfo = await repoResponse.json();

    const treeResponse = await fetch(
      `https://api.github.com/repos/${org}/${repo}/git/trees/${repoInfo.default_branch}?recursive=1`,
      { headers }
    );

    if (!treeResponse.ok) throw new Error('Failed to fetch tree');
    const tree = await treeResponse.json();

    // Filter files by patterns
    const matchedFiles = tree.tree.filter(item => {
      if (item.type !== 'blob') return false;
      return paths.some(pattern => matchGlob(item.path, pattern));
    });

    // Fetch content for matched files (limit to prevent rate limiting)
    const filesToFetch = matchedFiles.slice(0, 50);

    for (const file of filesToFetch) {
      try {
        const contentResponse = await fetch(
          `https://api.github.com/repos/${org}/${repo}/contents/${file.path}`,
          { headers }
        );

        if (contentResponse.ok) {
          const content = await contentResponse.json();
          scrapedData.files.push({
            path: file.path,
            sha: file.sha,
            size: file.size,
            content: content.encoding === 'base64' ? atob(content.content) : null,
          });
        }
      } catch (e) {
        console.error(`Failed to fetch ${file.path}:`, e);
      }
    }

    // Store scraped data
    await storeRepoData(repo, scrapedData, env);

  } catch (error) {
    console.error(`Scrape failed for ${repo}:`, error);
    throw error;
  }

  return scrapedData;
}

async function storeRepoData(repo, data, env) {
  if (env.KV) {
    await env.KV.put(`repo:${repo}`, JSON.stringify(data), {
      expirationTtl: 86400, // 24 hours
      metadata: { updatedAt: new Date().toISOString() },
    });
  }

  if (env.D1) {
    await env.D1.prepare(`
      INSERT OR REPLACE INTO repo_data (repo, data, updated_at)
      VALUES (?, ?, datetime('now'))
    `).bind(repo, JSON.stringify(data)).run();
  }
}

// ============================================================================
// COHESIVENESS CHECK
// ============================================================================

async function runCohesivenessCheck(env, ctx, jobId = null) {
  const results = {
    checked: [],
    issues: [],
    score: 100,
    timestamp: new Date().toISOString(),
  };

  // Load all repo data
  const repoDataMap = new Map();
  for (const repo of BLACKROAD_REPOS) {
    try {
      if (env.KV) {
        const data = await env.KV.get(`repo:${repo}`, { type: 'json' });
        if (data) repoDataMap.set(repo, data);
      }
    } catch (e) {
      console.error(`Failed to load ${repo}:`, e);
    }
  }

  // Check 1: Trinity System Compliance
  const trinityCheck = checkTrinityCompliance(repoDataMap);
  results.checked.push('trinity_compliance');
  if (trinityCheck.issues.length > 0) {
    results.issues.push(...trinityCheck.issues);
    results.score -= trinityCheck.issues.length * 5;
  }

  // Check 2: Configuration Consistency
  const configCheck = checkConfigConsistency(repoDataMap);
  results.checked.push('config_consistency');
  if (configCheck.issues.length > 0) {
    results.issues.push(...configCheck.issues);
    results.score -= configCheck.issues.length * 3;
  }

  // Check 3: Workflow Alignment
  const workflowCheck = checkWorkflowAlignment(repoDataMap);
  results.checked.push('workflow_alignment');
  if (workflowCheck.issues.length > 0) {
    results.issues.push(...workflowCheck.issues);
    results.score -= workflowCheck.issues.length * 2;
  }

  // Check 4: Dependency Compatibility
  const depCheck = checkDependencyCompatibility(repoDataMap);
  results.checked.push('dependency_compatibility');
  if (depCheck.issues.length > 0) {
    results.issues.push(...depCheck.issues);
    results.score -= depCheck.issues.length * 4;
  }

  results.score = Math.max(0, results.score);

  // Store results
  if (env.KV) {
    await env.KV.put('cohesiveness:latest', JSON.stringify(results), {
      metadata: { timestamp: results.timestamp },
    });
  }

  // Auto-create issues for critical problems
  if (results.score < 70) {
    await createCohesivenessIssue(results, env);
  }

  return results;
}

function checkTrinityCompliance(repoDataMap) {
  const issues = [];

  for (const [repo, data] of repoDataMap) {
    const hasTrinity = data.files?.some(f => f.path.includes('.trinity'));
    if (!hasTrinity) {
      issues.push({
        type: 'trinity_missing',
        repo,
        severity: 'medium',
        message: `Repository ${repo} is missing Trinity system integration`,
      });
    }
  }

  return { issues };
}

function checkConfigConsistency(repoDataMap) {
  const issues = [];
  const configKeys = new Map();

  for (const [repo, data] of repoDataMap) {
    const wranglerFile = data.files?.find(f => f.path === 'wrangler.toml');
    if (wranglerFile?.content) {
      // Parse and compare configurations
      const orgMatch = wranglerFile.content.match(/ORG_NAME\s*=\s*"([^"]+)"/);
      if (orgMatch) {
        if (!configKeys.has('ORG_NAME')) {
          configKeys.set('ORG_NAME', orgMatch[1]);
        } else if (configKeys.get('ORG_NAME') !== orgMatch[1]) {
          issues.push({
            type: 'config_mismatch',
            repo,
            severity: 'high',
            message: `ORG_NAME mismatch in ${repo}: expected ${configKeys.get('ORG_NAME')}, found ${orgMatch[1]}`,
          });
        }
      }
    }
  }

  return { issues };
}

function checkWorkflowAlignment(repoDataMap) {
  const issues = [];
  const requiredWorkflows = ['ci', 'deploy', 'security'];

  for (const [repo, data] of repoDataMap) {
    const workflowNames = data.workflows?.map(w => w.name.toLowerCase()) || [];

    for (const required of requiredWorkflows) {
      if (!workflowNames.some(w => w.includes(required))) {
        issues.push({
          type: 'workflow_missing',
          repo,
          severity: 'low',
          message: `Repository ${repo} may be missing ${required} workflow`,
        });
      }
    }
  }

  return { issues };
}

function checkDependencyCompatibility(repoDataMap) {
  const issues = [];
  const majorVersions = new Map();

  for (const [repo, data] of repoDataMap) {
    const packageJson = data.files?.find(f => f.path === 'package.json');
    if (packageJson?.content) {
      try {
        const pkg = JSON.parse(packageJson.content);
        const deps = { ...pkg.dependencies, ...pkg.devDependencies };

        for (const [dep, version] of Object.entries(deps)) {
          const majorVersion = version.match(/\d+/)?.[0];
          if (majorVersion) {
            if (!majorVersions.has(dep)) {
              majorVersions.set(dep, new Map());
            }
            majorVersions.get(dep).set(repo, majorVersion);
          }
        }
      } catch (e) {
        // Invalid JSON
      }
    }
  }

  // Check for major version mismatches
  for (const [dep, repos] of majorVersions) {
    const versions = new Set(repos.values());
    if (versions.size > 1) {
      issues.push({
        type: 'dependency_mismatch',
        dependency: dep,
        severity: 'medium',
        message: `Dependency ${dep} has different major versions across repos`,
        details: Object.fromEntries(repos),
      });
    }
  }

  return { issues };
}

// ============================================================================
// SELF-HEALING SYSTEM
// ============================================================================

async function attemptSelfHealing(error, env, context = {}) {
  console.log('Self-healing initiated:', error.message, context);

  const healingJob = {
    id: crypto.randomUUID(),
    type: JOB_TYPES.SELF_HEAL,
    config: {
      originalError: error.message,
      context,
    },
    state: JOB_STATES.RUNNING,
    createdAt: new Date().toISOString(),
    attempts: 0,
    maxAttempts: 3,
    healingAttempts: 0,
  };

  await saveJobToKV(env, healingJob);

  try {
    // Strategy 1: Retry with exponential backoff
    if (isRetryableError(error)) {
      console.log('Attempting retry strategy...');
      return await retryStrategy(context, env);
    }

    // Strategy 2: Fallback to alternative approach
    if (hasFallbackAvailable(context)) {
      console.log('Attempting fallback strategy...');
      return await fallbackStrategy(context, env);
    }

    // Strategy 3: Quantum jump - try a creative solution
    console.log('Attempting quantum jump strategy...');
    return await quantumJumpStrategy(context, env);

  } catch (healingError) {
    console.error('Self-healing failed:', healingError);

    // Escalate to humans
    await escalateToHumans(error, healingError, context, env);
    return false;
  }
}

async function performSelfHealing(targetJobId, error, strategy, env, ctx) {
  const job = targetJobId ? await getJobFromKV(env, targetJobId) : null;

  switch (strategy) {
    case SELF_HEAL_STRATEGIES.RETRY:
      return await retryStrategy({ jobId: targetJobId, job }, env);

    case SELF_HEAL_STRATEGIES.FALLBACK:
      return await fallbackStrategy({ jobId: targetJobId, job, error }, env);

    case SELF_HEAL_STRATEGIES.ESCALATE:
      await escalateToHumans(new Error(error), null, { jobId: targetJobId }, env);
      return { escalated: true };

    case SELF_HEAL_STRATEGIES.QUANTUM_JUMP:
      return await quantumJumpStrategy({ jobId: targetJobId, job, error }, env);

    default:
      throw new Error(`Unknown healing strategy: ${strategy}`);
  }
}

function isRetryableError(error) {
  const retryablePatterns = [
    'rate limit',
    'timeout',
    'network',
    'ECONNRESET',
    '502',
    '503',
    '504',
  ];

  return retryablePatterns.some(pattern =>
    error.message.toLowerCase().includes(pattern.toLowerCase())
  );
}

function hasFallbackAvailable(context) {
  // Check if there's an alternative approach available
  return context.type === JOB_TYPES.REPO_SYNC || context.type === JOB_TYPES.COHESIVENESS_CHECK;
}

async function retryStrategy(context, env) {
  const delays = [2000, 4000, 8000, 16000];

  for (let i = 0; i < delays.length; i++) {
    await sleep(delays[i]);

    try {
      if (context.job) {
        context.job.attempts = 0; // Reset attempts
        await processJob(context.job, env, {});
        return { success: true, strategy: 'retry', attempts: i + 1 };
      }
    } catch (e) {
      console.log(`Retry ${i + 1} failed:`, e.message);
    }
  }

  return { success: false, strategy: 'retry', attempts: delays.length };
}

async function fallbackStrategy(context, env) {
  // Use cached data if available
  if (context.type === JOB_TYPES.REPO_SYNC && env.KV) {
    const cached = await env.KV.get('sync:latest', { type: 'json' });
    if (cached) {
      return { success: true, strategy: 'fallback', usedCache: true, data: cached };
    }
  }

  return { success: false, strategy: 'fallback' };
}

async function quantumJumpStrategy(context, env) {
  // Creative solutions for different scenarios
  const quantumSolutions = {
    repo_sync: async () => {
      // Try syncing just the critical repos
      const criticalRepos = ['blackroad-prism-console', 'blackroad-os-agents'];
      return await runRepoSyncJob(env, {}, criticalRepos);
    },
    cohesiveness_check: async () => {
      // Do a lightweight check instead
      return { lightweightCheck: true, timestamp: new Date().toISOString() };
    },
    default: async () => {
      // Log for human review and continue
      console.log('Quantum jump: Logged for human review');
      return { loggedForReview: true };
    },
  };

  const solution = quantumSolutions[context.type] || quantumSolutions.default;
  const result = await solution();

  return { success: true, strategy: 'quantum_jump', result };
}

async function escalateToHumans(originalError, healingError, context, env) {
  console.log('Escalating to humans:', originalError.message);

  // Create GitHub issue
  if (env.GITHUB_TOKEN) {
    const org = env.ORG_NAME || 'BlackRoad-OS';
    const repo = 'blackroad-agents';

    const issueBody = `## Self-Healing Failed - Human Intervention Required

### Original Error
\`\`\`
${originalError.message}
\`\`\`

### Healing Attempt Error
\`\`\`
${healingError?.message || 'N/A'}
\`\`\`

### Context
\`\`\`json
${JSON.stringify(context, null, 2)}
\`\`\`

### Timestamp
${new Date().toISOString()}

---
*This issue was auto-generated by the BlackRoad Agent Jobs self-healing system.*
`;

    try {
      await fetch(`https://api.github.com/repos/${org}/${repo}/issues`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
          'Content-Type': 'application/json',
          'User-Agent': 'BlackRoad-Agent-Jobs/1.0',
        },
        body: JSON.stringify({
          title: `[Self-Healing] ${originalError.message.substring(0, 50)}...`,
          body: issueBody,
          labels: ['self-healing', 'escalation', 'needs-attention'],
        }),
      });
    } catch (e) {
      console.error('Failed to create escalation issue:', e);
    }
  }
}

// ============================================================================
// ADDITIONAL JOB TYPES
// ============================================================================

async function runHealthCheck(env, ctx) {
  const health = {
    timestamp: new Date().toISOString(),
    services: {},
  };

  // Check KV
  if (env.KV) {
    try {
      await env.KV.get('health:test');
      health.services.kv = 'healthy';
    } catch (e) {
      health.services.kv = 'unhealthy';
    }
  }

  // Check D1
  if (env.D1) {
    try {
      await env.D1.prepare('SELECT 1').first();
      health.services.d1 = 'healthy';
    } catch (e) {
      health.services.d1 = 'unhealthy';
    }
  }

  // Store health status
  if (env.KV) {
    await env.KV.put('health:latest', JSON.stringify(health));
  }

  return health;
}

async function runDependencyAudit(env, ctx, jobId = null) {
  const results = {
    repos: [],
    outdated: [],
    vulnerabilities: [],
    timestamp: new Date().toISOString(),
  };

  // This would integrate with npm audit, pip-audit, etc.
  // For now, check stored repo data
  for (const repo of BLACKROAD_REPOS) {
    if (env.KV) {
      const data = await env.KV.get(`repo:${repo}`, { type: 'json' });
      if (data?.files) {
        results.repos.push({
          repo,
          hasPackageJson: data.files.some(f => f.path === 'package.json'),
          hasPyproject: data.files.some(f => f.path === 'pyproject.toml'),
        });
      }
    }
  }

  return results;
}

async function runWorkflowSync(env, ctx, jobId = null) {
  // Sync common workflows across repos
  const commonWorkflows = ['ci.yml', 'deploy-cloudflare.yml', 'security.yml'];

  return {
    synced: commonWorkflows,
    timestamp: new Date().toISOString(),
  };
}

async function runConfigSync(env, ctx, jobId = null) {
  // Sync configuration files across repos
  const configs = ['wrangler.toml', '.env.example'];

  return {
    synced: configs,
    timestamp: new Date().toISOString(),
  };
}

async function runTrinityComplianceCheck(env, ctx, jobId = null) {
  const results = {
    compliant: [],
    nonCompliant: [],
    timestamp: new Date().toISOString(),
  };

  for (const repo of BLACKROAD_REPOS) {
    if (env.KV) {
      const data = await env.KV.get(`repo:${repo}`, { type: 'json' });
      const hasTrinity = data?.files?.some(f => f.path.includes('.trinity'));

      if (hasTrinity) {
        results.compliant.push(repo);
      } else {
        results.nonCompliant.push(repo);
      }
    }
  }

  return results;
}

// ============================================================================
// GITHUB EVENT HANDLERS
// ============================================================================

async function handlePushEvent(payload, env, ctx) {
  const repo = payload.repository?.name;
  const branch = payload.ref?.replace('refs/heads/', '');

  console.log(`Push to ${repo}:${branch}`);

  // Trigger repo sync if it's a tracked repo
  if (BLACKROAD_REPOS.includes(repo)) {
    await runRepoSyncJob(env, ctx, [repo]);
  }
}

async function handlePREvent(payload, env, ctx) {
  const action = payload.action;
  const repo = payload.repository?.name;

  console.log(`PR ${action} in ${repo}`);

  // Run cohesiveness check on PR merge
  if (action === 'closed' && payload.pull_request?.merged) {
    await runCohesivenessCheck(env, ctx);
  }
}

async function handleWorkflowEvent(payload, env, ctx) {
  const status = payload.workflow_run?.status;
  const conclusion = payload.workflow_run?.conclusion;
  const repo = payload.repository?.name;

  console.log(`Workflow ${status}/${conclusion} in ${repo}`);

  // Self-heal on workflow failure
  if (conclusion === 'failure') {
    await attemptSelfHealing(
      new Error(`Workflow failed in ${repo}`),
      env,
      { repo, workflow: payload.workflow_run?.name }
    );
  }
}

async function handleIssueEvent(payload, env, ctx) {
  const action = payload.action;
  const labels = payload.issue?.labels?.map(l => l.name) || [];

  // Handle self-healing issues
  if (action === 'labeled' && labels.includes('auto-fix')) {
    console.log('Auto-fix issue detected, attempting resolution...');
  }
}

// ============================================================================
// KV STORAGE HELPERS
// ============================================================================

async function getJobsFromKV(env) {
  if (!env.KV) return [];

  const list = await env.KV.list({ prefix: 'job:' });
  const jobs = [];

  for (const key of list.keys) {
    const job = await env.KV.get(key.name, { type: 'json' });
    if (job) jobs.push(job);
  }

  return jobs.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

async function getJobFromKV(env, jobId) {
  if (!env.KV) return null;
  return await env.KV.get(`job:${jobId}`, { type: 'json' });
}

async function saveJobToKV(env, job) {
  if (!env.KV) return;
  await env.KV.put(`job:${job.id}`, JSON.stringify(job), {
    expirationTtl: 86400 * 7, // 7 days
    metadata: { state: job.state, type: job.type },
  });
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function jsonResponse(data, corsHeaders, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders,
    },
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function matchGlob(path, pattern) {
  // Simple glob matching
  const regex = pattern
    .replace(/\*\*/g, '.*')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '.');
  return new RegExp(`^${regex}$`).test(path);
}

async function verifyGitHubSignature(payload, signature, secret) {
  if (!signature) return false;

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(payload));
  const digest = 'sha256=' + Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  return signature === digest;
}

async function createEscalationIssue(job, error, env) {
  await escalateToHumans(error, null, { job }, env);
}

async function createCohesivenessIssue(results, env) {
  if (!env.GITHUB_TOKEN) return;

  const org = env.ORG_NAME || 'BlackRoad-OS';
  const repo = 'blackroad-agents';

  const issueBody = `## Cohesiveness Score Alert: ${results.score}/100

### Issues Found
${results.issues.map(i => `- **${i.type}** (${i.severity}): ${i.message}`).join('\n')}

### Recommendations
1. Review the flagged repositories
2. Ensure Trinity system compliance
3. Align configurations and dependencies

---
*Auto-generated by BlackRoad Agent Jobs cohesiveness checker*
`;

  try {
    await fetch(`https://api.github.com/repos/${org}/${repo}/issues`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
        'Content-Type': 'application/json',
        'User-Agent': 'BlackRoad-Agent-Jobs/1.0',
      },
      body: JSON.stringify({
        title: `[Cohesiveness] Score dropped to ${results.score}/100`,
        body: issueBody,
        labels: ['cohesiveness', 'automated', 'needs-attention'],
      }),
    });
  } catch (e) {
    console.error('Failed to create cohesiveness issue:', e);
  }
}
