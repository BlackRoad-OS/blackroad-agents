/**
 * ⬛⬜🛣️ BlackRoad Agents - Job Scheduler
 *
 * Handles scheduled cron jobs and manual job triggers.
 * Integrates with self-healing for automatic failure recovery.
 */

import { generateId, logEvent, retryWithBackoff } from '../utils/helpers.js';

/**
 * Cron schedule definitions
 */
export const CRON_SCHEDULES = {
  HEALTH_CHECK: '*/5 * * * *',
  REPO_SYNC: '*/15 * * * *',
  FULL_SCRAPE: '0 * * * *',
  DEEP_ANALYSIS: '0 */6 * * *',
  DAILY_RECONCILIATION: '0 0 * * *',
};

/**
 * Job types
 */
export const JOB_TYPES = {
  HEALTH_CHECK: 'health_check',
  REPO_SYNC: 'repo_sync',
  SELF_HEAL: 'self_heal',
  COHESION_ANALYSIS: 'cohesion_analysis',
  DEEP_ANALYSIS: 'deep_analysis',
  DAILY_RECONCILIATION: 'daily_reconciliation',
  CUSTOM: 'custom',
};

/**
 * Job status
 */
export const JOB_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
};

/**
 * Job Scheduler class
 */
export class JobScheduler {
  constructor(env) {
    this.env = env;
  }

  /**
   * Create a new job
   */
  async createJob(options) {
    const job = {
      id: generateId('job'),
      type: options.type || JOB_TYPES.CUSTOM,
      status: JOB_STATUS.PENDING,
      priority: options.priority || 5,
      payload: options.payload || {},
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      attempts: 0,
      maxAttempts: options.maxAttempts || 3,
      result: null,
      error: null,
    };

    await this.env.JOB_QUEUE.put(job.id, JSON.stringify(job));
    await logEvent(this.env, 'info', 'job_created', { jobId: job.id, type: job.type });

    return job;
  }

  /**
   * Update job status
   */
  async updateJob(jobId, updates) {
    const job = await this.env.JOB_QUEUE.get(jobId, 'json');
    if (!job) {
      throw new Error(`Job not found: ${jobId}`);
    }

    const updatedJob = {
      ...job,
      ...updates,
      updatedAt: new Date().toISOString(),
    };

    await this.env.JOB_QUEUE.put(jobId, JSON.stringify(updatedJob));
    return updatedJob;
  }

  /**
   * Trigger a job manually
   */
  async triggerJob(jobType) {
    await logEvent(this.env, 'info', 'manual_trigger', { jobType });

    switch (jobType) {
      case JOB_TYPES.HEALTH_CHECK:
      case 'health_check':
        return await this.runHealthCheck();

      case JOB_TYPES.REPO_SYNC:
      case 'repo_sync':
        return await this.runRepoSyncCheck();

      case JOB_TYPES.SELF_HEAL:
      case 'self_heal':
        return await this.runQuickSelfHeal();

      case JOB_TYPES.COHESION_ANALYSIS:
      case 'cohesion_analysis':
        return await this.runCohesionAnalysis();

      default:
        return { error: 'Unknown job type', jobType };
    }
  }

  /**
   * Process a queued job
   */
  async processQueuedJob(jobData) {
    const job = typeof jobData === 'string' ? JSON.parse(jobData) : jobData;

    await this.updateJob(job.id, { status: JOB_STATUS.RUNNING, attempts: job.attempts + 1 });

    try {
      const result = await this.executeJob(job);
      await this.updateJob(job.id, { status: JOB_STATUS.COMPLETED, result });
      return result;
    } catch (error) {
      await this.updateJob(job.id, {
        status: job.attempts >= job.maxAttempts ? JOB_STATUS.FAILED : JOB_STATUS.PENDING,
        error: error.message,
      });
      throw error;
    }
  }

  /**
   * Execute a job based on its type
   */
  async executeJob(job) {
    switch (job.type) {
      case JOB_TYPES.HEALTH_CHECK:
        return await this.runHealthCheck();
      case JOB_TYPES.REPO_SYNC:
        return await this.runRepoSyncCheck();
      case JOB_TYPES.SELF_HEAL:
        return await this.runQuickSelfHeal();
      default:
        throw new Error(`Unknown job type: ${job.type}`);
    }
  }

  // ==========================================================================
  // Scheduled Job Implementations
  // ==========================================================================

  /**
   * Health check - runs every 5 minutes
   */
  async runHealthCheck() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      checks: [],
      healthy: true,
    };

    // Check KV connectivity
    try {
      await this.env.AGENT_STATE.put('_healthcheck', Date.now().toString());
      const value = await this.env.AGENT_STATE.get('_healthcheck');
      results.checks.push({ name: 'kv_connectivity', status: 'pass' });
    } catch (error) {
      results.checks.push({ name: 'kv_connectivity', status: 'fail', error: error.message });
      results.healthy = false;
    }

    // Check job queue
    try {
      const jobs = await this.env.JOB_QUEUE.list({ limit: 10 });
      const pendingJobs = jobs.keys.length;
      results.checks.push({ name: 'job_queue', status: 'pass', pendingJobs });
    } catch (error) {
      results.checks.push({ name: 'job_queue', status: 'fail', error: error.message });
      results.healthy = false;
    }

    // Check learning memory
    try {
      const learnings = await this.env.LEARNING_MEMORY.list({ limit: 1 });
      results.checks.push({ name: 'learning_memory', status: 'pass' });
    } catch (error) {
      results.checks.push({ name: 'learning_memory', status: 'fail', error: error.message });
      results.healthy = false;
    }

    results.duration = Date.now() - startTime;

    // Store health check result
    await this.env.AGENT_STATE.put('last_health_check', JSON.stringify(results));
    await logEvent(this.env, 'info', 'health_check_completed', results);

    return results;
  }

  /**
   * Quick self-heal - runs every 5 minutes
   */
  async runQuickSelfHeal() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      issues_detected: 0,
      issues_resolved: 0,
      actions: [],
    };

    // Check for failed jobs and retry them
    const jobs = await this.env.JOB_QUEUE.list();
    for (const key of jobs.keys) {
      const job = await this.env.JOB_QUEUE.get(key.name, 'json');
      if (job && job.status === JOB_STATUS.FAILED && job.attempts < job.maxAttempts) {
        results.issues_detected++;
        try {
          await this.updateJob(key.name, { status: JOB_STATUS.PENDING });
          results.actions.push({ action: 'retry_job', jobId: key.name });
          results.issues_resolved++;
        } catch (error) {
          results.actions.push({ action: 'retry_failed', jobId: key.name, error: error.message });
        }
      }
    }

    // Check for stale state and clean up
    const staleThreshold = Date.now() - (24 * 60 * 60 * 1000); // 24 hours
    const stateKeys = await this.env.AGENT_STATE.list({ prefix: 'agent:' });
    for (const key of stateKeys.keys) {
      const state = await this.env.AGENT_STATE.get(key.name, 'json');
      if (state && new Date(state.updatedAt).getTime() < staleThreshold) {
        results.issues_detected++;
        await this.env.AGENT_STATE.delete(key.name);
        results.actions.push({ action: 'cleanup_stale_state', key: key.name });
        results.issues_resolved++;
      }
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_self_heal', JSON.stringify(results));
    await logEvent(this.env, 'info', 'quick_self_heal_completed', results);

    return results;
  }

  /**
   * Repo sync check - runs every 15 minutes
   */
  async runRepoSyncCheck() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      repos_checked: 0,
      repos_updated: 0,
      repos: [],
    };

    // Import RepoSyncManager dynamically to avoid circular deps
    const { RepoSyncManager, BLACKROAD_REPOS } = await import('../sync/repo-sync.js');
    const syncManager = new RepoSyncManager(this.env);

    for (const repo of BLACKROAD_REPOS) {
      try {
        results.repos_checked++;
        const syncResult = await syncManager.checkRepoStatus(repo.name);
        results.repos.push({
          name: repo.name,
          status: syncResult.status,
          lastSync: syncResult.lastSync,
          needsSync: syncResult.needsSync,
        });

        if (syncResult.needsSync) {
          // Queue a full sync job
          await this.createJob({
            type: JOB_TYPES.REPO_SYNC,
            payload: { repoName: repo.name },
            priority: 7,
          });
          results.repos_updated++;
        }
      } catch (error) {
        results.repos.push({
          name: repo.name,
          status: 'error',
          error: error.message,
        });
      }
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_repo_sync_check', JSON.stringify(results));
    await logEvent(this.env, 'info', 'repo_sync_check_completed', results);

    return results;
  }

  /**
   * Full repo scrape - runs every hour
   */
  async runFullRepoScrape() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      repos_scraped: 0,
      total_files: 0,
      patterns_found: [],
    };

    const { RepoSyncManager, BLACKROAD_REPOS } = await import('../sync/repo-sync.js');
    const syncManager = new RepoSyncManager(this.env);

    for (const repo of BLACKROAD_REPOS) {
      try {
        const scrapeResult = await syncManager.scrapeRepo(repo.name);
        results.repos_scraped++;
        results.total_files += scrapeResult.fileCount || 0;

        // Store scraped data in cache
        await this.env.REPO_CACHE.put(
          `scrape:${repo.name}`,
          JSON.stringify(scrapeResult),
          { expirationTtl: 3600 * 2 } // Cache for 2 hours
        );
      } catch (error) {
        await logEvent(this.env, 'error', 'repo_scrape_failed', {
          repo: repo.name,
          error: error.message
        });
      }
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_full_scrape', JSON.stringify(results));
    await logEvent(this.env, 'info', 'full_repo_scrape_completed', results);

    return results;
  }

  /**
   * Cohesion analysis - runs every hour
   */
  async runCohesionAnalysis() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      repos_analyzed: 0,
      inconsistencies: [],
      recommendations: [],
    };

    const { RepoSyncManager, BLACKROAD_REPOS } = await import('../sync/repo-sync.js');
    const syncManager = new RepoSyncManager(this.env);

    // Get all cached scrape data
    const repoData = {};
    for (const repo of BLACKROAD_REPOS) {
      const cached = await this.env.REPO_CACHE.get(`scrape:${repo.name}`, 'json');
      if (cached) {
        repoData[repo.name] = cached;
        results.repos_analyzed++;
      }
    }

    // Analyze cohesion
    const analysis = await syncManager.analyzeCohesion(repoData);
    results.inconsistencies = analysis.inconsistencies || [];
    results.recommendations = analysis.recommendations || [];

    // Store findings
    if (results.inconsistencies.length > 0) {
      await this.env.AGENT_STATE.put('cohesion_issues', JSON.stringify(results.inconsistencies));

      // Create learning from issues found
      await this.env.LEARNING_MEMORY.put(
        `cohesion:${Date.now()}`,
        JSON.stringify({
          timestamp: new Date().toISOString(),
          type: 'cohesion_analysis',
          findings: results.inconsistencies,
          recommendations: results.recommendations,
        })
      );
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_cohesion_analysis', JSON.stringify(results));
    await logEvent(this.env, 'info', 'cohesion_analysis_completed', results);

    return results;
  }

  /**
   * Deep analysis - runs every 6 hours
   */
  async runDeepAnalysis() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      analysis_type: 'deep',
      findings: [],
      patterns: [],
      improvements: [],
    };

    // Analyze patterns across all repos
    const { RepoSyncManager, BLACKROAD_REPOS } = await import('../sync/repo-sync.js');
    const syncManager = new RepoSyncManager(this.env);

    try {
      const deepAnalysis = await syncManager.runDeepAnalysis();
      results.findings = deepAnalysis.findings || [];
      results.patterns = deepAnalysis.patterns || [];
      results.improvements = deepAnalysis.improvements || [];
    } catch (error) {
      results.error = error.message;
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_deep_analysis', JSON.stringify(results));
    await logEvent(this.env, 'info', 'deep_analysis_completed', results);

    return results;
  }

  /**
   * Aggregate learnings - runs every 6 hours
   */
  async aggregateLearnings() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      learnings_aggregated: 0,
      patterns_identified: [],
      success_rates: {},
    };

    // Get all learnings
    const learningKeys = await this.env.LEARNING_MEMORY.list();
    const allLearnings = [];

    for (const key of learningKeys.keys) {
      const learning = await this.env.LEARNING_MEMORY.get(key.name, 'json');
      if (learning) {
        allLearnings.push(learning);
        results.learnings_aggregated++;
      }
    }

    // Calculate success rates by type
    const typeStats = {};
    for (const learning of allLearnings) {
      const type = learning.type || 'unknown';
      if (!typeStats[type]) {
        typeStats[type] = { total: 0, success: 0 };
      }
      typeStats[type].total++;
      if (learning.success) {
        typeStats[type].success++;
      }
    }

    for (const [type, stats] of Object.entries(typeStats)) {
      results.success_rates[type] = stats.total > 0 ? stats.success / stats.total : 0;
    }

    // Store aggregated insights
    await this.env.AGENT_STATE.put('aggregated_learnings', JSON.stringify({
      timestamp: new Date().toISOString(),
      totalLearnings: results.learnings_aggregated,
      successRates: results.success_rates,
    }));

    results.duration = Date.now() - startTime;
    await logEvent(this.env, 'info', 'learnings_aggregated', results);

    return results;
  }

  /**
   * Daily reconciliation - runs at midnight UTC
   */
  async runDailyReconciliation() {
    const startTime = Date.now();
    const results = {
      timestamp: new Date().toISOString(),
      reconciliation_type: 'daily',
      repos_reconciled: 0,
      issues_found: 0,
      issues_auto_resolved: 0,
    };

    // Full system check
    const healthCheck = await this.runHealthCheck();
    if (!healthCheck.healthy) {
      results.issues_found++;
      // Trigger comprehensive self-healing
      const healResult = await this.runQuickSelfHeal();
      results.issues_auto_resolved += healResult.issues_resolved;
    }

    // Full repo sync
    const { RepoSyncManager, BLACKROAD_REPOS } = await import('../sync/repo-sync.js');
    const syncManager = new RepoSyncManager(this.env);

    for (const repo of BLACKROAD_REPOS) {
      try {
        await syncManager.fullReconcile(repo.name);
        results.repos_reconciled++;
      } catch (error) {
        results.issues_found++;
        await logEvent(this.env, 'error', 'reconciliation_failed', {
          repo: repo.name,
          error: error.message,
        });
      }
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_reconciliation', JSON.stringify(results));
    await logEvent(this.env, 'info', 'daily_reconciliation_completed', results);

    return results;
  }

  /**
   * Generate daily report
   */
  async generateDailyReport() {
    const report = {
      timestamp: new Date().toISOString(),
      period: '24h',
      sections: {},
    };

    // Health summary
    const lastHealth = await this.env.AGENT_STATE.get('last_health_check', 'json');
    report.sections.health = lastHealth;

    // Job summary
    const jobs = await this.env.JOB_QUEUE.list();
    const jobStats = { total: 0, completed: 0, failed: 0, pending: 0 };
    for (const key of jobs.keys) {
      const job = await this.env.JOB_QUEUE.get(key.name, 'json');
      if (job) {
        jobStats.total++;
        jobStats[job.status] = (jobStats[job.status] || 0) + 1;
      }
    }
    report.sections.jobs = jobStats;

    // Sync summary
    const lastSync = await this.env.AGENT_STATE.get('last_repo_sync_check', 'json');
    report.sections.sync = lastSync;

    // Cohesion summary
    const cohesionIssues = await this.env.AGENT_STATE.get('cohesion_issues', 'json');
    report.sections.cohesion = {
      issues: cohesionIssues ? cohesionIssues.length : 0,
      details: cohesionIssues,
    };

    // Learnings summary
    const aggregatedLearnings = await this.env.AGENT_STATE.get('aggregated_learnings', 'json');
    report.sections.learnings = aggregatedLearnings;

    // Store report
    await this.env.AGENT_STATE.put(`daily_report:${new Date().toISOString().split('T')[0]}`, JSON.stringify(report));
    await logEvent(this.env, 'info', 'daily_report_generated', { sections: Object.keys(report.sections) });

    return report;
  }

  /**
   * Cleanup old data
   */
  async cleanupOldData() {
    const results = {
      timestamp: new Date().toISOString(),
      deleted: { logs: 0, jobs: 0, cache: 0 },
    };

    const thirtyDaysAgo = Date.now() - (30 * 24 * 60 * 60 * 1000);
    const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);

    // Cleanup old logs (older than 7 days)
    const logs = await this.env.AGENT_STATE.list({ prefix: 'log:' });
    for (const key of logs.keys) {
      const timestamp = parseInt(key.name.split(':')[1]);
      if (timestamp < sevenDaysAgo) {
        await this.env.AGENT_STATE.delete(key.name);
        results.deleted.logs++;
      }
    }

    // Cleanup completed/failed jobs (older than 30 days)
    const jobs = await this.env.JOB_QUEUE.list();
    for (const key of jobs.keys) {
      const job = await this.env.JOB_QUEUE.get(key.name, 'json');
      if (job && (job.status === JOB_STATUS.COMPLETED || job.status === JOB_STATUS.FAILED)) {
        const updatedAt = new Date(job.updatedAt).getTime();
        if (updatedAt < thirtyDaysAgo) {
          await this.env.JOB_QUEUE.delete(key.name);
          results.deleted.jobs++;
        }
      }
    }

    // Cleanup old cache entries (handled by TTL, but double-check)
    const cache = await this.env.REPO_CACHE.list({ prefix: 'scrape:' });
    // Cache entries have TTL, so they should auto-expire

    await logEvent(this.env, 'info', 'cleanup_completed', results);
    return results;
  }
}
