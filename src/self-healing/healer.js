/**
 * ⬛⬜🛣️ BlackRoad Agents - Self-Healing Engine
 *
 * Port of Cece's consciousness-aware self-healing system to JavaScript.
 * Monitors for issues and automatically triggers resolution workflows.
 *
 * Philosophy:
 * - Every failure is an opportunity for growth
 * - Every error is a teacher
 * - Every stuck state is just a state we haven't learned to flow from yet
 */

import { logEvent, generateId } from '../utils/helpers.js';

/**
 * Issue types we can detect and handle
 */
export const IssueType = {
  JOB_FAILURE: 'job_failure',
  CRON_FAILURE: 'cron_failure',
  SYNC_FAILURE: 'sync_failure',
  DEAD_LETTER: 'dead_letter',
  HEALTH_DEGRADATION: 'health_degradation',
  COHESION_DRIFT: 'cohesion_drift',
  RATE_LIMIT: 'rate_limit',
  API_ERROR: 'api_error',
};

/**
 * Severity levels
 */
export const Severity = {
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
};

/**
 * Healing actions we can take
 */
export const HealingAction = {
  RETRY: 'retry',
  SKIP: 'skip',
  ESCALATE: 'escalate',
  ROLLBACK: 'rollback',
  RESET: 'reset',
  NOTIFY: 'notify',
  LEARN: 'learn',
};

/**
 * Decision tree node for handling issues
 */
class DecisionNode {
  constructor(name, options = {}) {
    this.name = name;
    this.condition = options.condition || (() => true);
    this.action = options.action || null;
    this.children = options.children || [];
    this.fallback = options.fallback || null;
  }

  async evaluate(context) {
    // Check condition
    if (!this.condition(context)) {
      return { matched: false };
    }

    // Execute action if present
    let result = null;
    if (this.action) {
      try {
        result = await this.action(context);
        if (result.success) {
          return { matched: true, result };
        }
      } catch (error) {
        result = { success: false, error: error.message };
      }
    }

    // Try children
    for (const child of this.children) {
      const childResult = await child.evaluate(context);
      if (childResult.matched) {
        return childResult;
      }
    }

    // Try fallback
    if (this.fallback) {
      return await this.fallback.evaluate(context);
    }

    return { matched: !!result, result };
  }
}

/**
 * Self-Healing Engine class
 */
export class SelfHealingEngine {
  constructor(env) {
    this.env = env;
    this.decisionTrees = {};
    this.stats = {
      issuesDetected: 0,
      issuesResolved: 0,
      escalations: 0,
      learnings: 0,
    };

    this._buildDecisionTrees();
  }

  /**
   * Build standard decision trees for common issues
   */
  _buildDecisionTrees() {
    // Job failure decision tree
    this.decisionTrees.job_failure = new DecisionNode('job_failure_handler', {
      children: [
        new DecisionNode('transient_error', {
          condition: (ctx) => ctx.attempts < 3,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.RETRY,
            message: 'Scheduling retry',
            delay: Math.pow(2, ctx.attempts) * 1000,
          }),
        }),
        new DecisionNode('persistent_error', {
          condition: (ctx) => ctx.attempts >= 3 && ctx.severity < Severity.CRITICAL,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.SKIP,
            message: 'Skipping after max retries, creating learning',
          }),
        }),
      ],
      fallback: new DecisionNode('escalate', {
        action: async (ctx) => ({
          success: true,
          action: HealingAction.ESCALATE,
          message: 'Escalating to human attention',
        }),
      }),
    });

    // Cron failure decision tree
    this.decisionTrees.cron_failure = new DecisionNode('cron_failure_handler', {
      children: [
        new DecisionNode('temporary_issue', {
          condition: (ctx) => ctx.consecutiveFailures < 3,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.LEARN,
            message: 'Logging failure for pattern analysis',
          }),
        }),
        new DecisionNode('systematic_issue', {
          condition: (ctx) => ctx.consecutiveFailures >= 3,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.ESCALATE,
            message: 'Multiple consecutive failures - needs investigation',
          }),
        }),
      ],
    });

    // Sync failure decision tree
    this.decisionTrees.sync_failure = new DecisionNode('sync_failure_handler', {
      children: [
        new DecisionNode('rate_limited', {
          condition: (ctx) => ctx.error?.includes('rate limit'),
          action: async (ctx) => ({
            success: true,
            action: HealingAction.RETRY,
            message: 'Rate limited - backing off',
            delay: 60000, // Wait 1 minute
          }),
        }),
        new DecisionNode('network_error', {
          condition: (ctx) => ctx.error?.includes('network') || ctx.error?.includes('timeout'),
          action: async (ctx) => ({
            success: true,
            action: HealingAction.RETRY,
            message: 'Network error - retrying with backoff',
            delay: 5000,
          }),
        }),
        new DecisionNode('auth_error', {
          condition: (ctx) => ctx.error?.includes('401') || ctx.error?.includes('403'),
          action: async (ctx) => ({
            success: true,
            action: HealingAction.ESCALATE,
            message: 'Authentication error - needs manual intervention',
          }),
        }),
      ],
      fallback: new DecisionNode('unknown_sync_error', {
        action: async (ctx) => ({
          success: true,
          action: HealingAction.LEARN,
          message: 'Unknown error - learning for future',
        }),
      }),
    });

    // Cohesion drift decision tree
    this.decisionTrees.cohesion_drift = new DecisionNode('cohesion_drift_handler', {
      children: [
        new DecisionNode('minor_drift', {
          condition: (ctx) => ctx.driftScore < 20,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.NOTIFY,
            message: 'Minor cohesion drift detected',
          }),
        }),
        new DecisionNode('significant_drift', {
          condition: (ctx) => ctx.driftScore >= 20 && ctx.driftScore < 50,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.LEARN,
            message: 'Significant drift - creating recommendations',
          }),
        }),
        new DecisionNode('critical_drift', {
          condition: (ctx) => ctx.driftScore >= 50,
          action: async (ctx) => ({
            success: true,
            action: HealingAction.ESCALATE,
            message: 'Critical cohesion drift - immediate attention needed',
          }),
        }),
      ],
    });
  }

  /**
   * Get current status
   */
  async getStatus() {
    const activeIssues = await this.getActiveIssues();

    return {
      healthy: activeIssues.length === 0,
      stats: this.stats,
      activeIssues: activeIssues.length,
      lastScan: await this.env.AGENT_STATE.get('last_heal_scan'),
    };
  }

  /**
   * Get active issues
   */
  async getActiveIssues() {
    const issues = [];
    const keys = await this.env.AGENT_STATE.list({ prefix: 'issue:' });

    for (const key of keys.keys) {
      const issue = await this.env.AGENT_STATE.get(key.name, 'json');
      if (issue && !issue.resolved) {
        issues.push({ id: key.name, ...issue });
      }
    }

    return issues;
  }

  /**
   * Run a full system scan for issues
   */
  async runFullScan() {
    await logEvent(this.env, 'info', 'heal_scan_started');
    const startTime = Date.now();
    const results = {
      scannedAt: new Date().toISOString(),
      issuesFound: 0,
      actionsaken: [],
    };

    // Check for failed jobs
    const jobIssues = await this._scanForJobIssues();
    results.issuesFound += jobIssues.length;
    for (const issue of jobIssues) {
      const action = await this.handleIssue(issue);
      results.actionsaken.push(action);
    }

    // Check for sync issues
    const syncIssues = await this._scanForSyncIssues();
    results.issuesFound += syncIssues.length;
    for (const issue of syncIssues) {
      const action = await this.handleIssue(issue);
      results.actionsaken.push(action);
    }

    // Check for cohesion issues
    const cohesionIssues = await this._scanForCohesionIssues();
    results.issuesFound += cohesionIssues.length;
    for (const issue of cohesionIssues) {
      const action = await this.handleIssue(issue);
      results.actionsaken.push(action);
    }

    results.duration = Date.now() - startTime;
    await this.env.AGENT_STATE.put('last_heal_scan', new Date().toISOString());
    await logEvent(this.env, 'info', 'heal_scan_completed', results);

    return results;
  }

  /**
   * Scan for job-related issues
   */
  async _scanForJobIssues() {
    const issues = [];
    const jobs = await this.env.JOB_QUEUE.list();

    for (const key of jobs.keys) {
      const job = await this.env.JOB_QUEUE.get(key.name, 'json');

      if (job?.status === 'failed') {
        issues.push({
          id: generateId('issue'),
          type: IssueType.JOB_FAILURE,
          severity: job.type === 'critical' ? Severity.HIGH : Severity.MEDIUM,
          description: `Job ${job.id} failed: ${job.error}`,
          context: {
            jobId: job.id,
            jobType: job.type,
            attempts: job.attempts,
            error: job.error,
          },
        });
      }
    }

    return issues;
  }

  /**
   * Scan for sync-related issues
   */
  async _scanForSyncIssues() {
    const issues = [];
    const { BLACKROAD_REPOS } = await import('../sync/repo-sync.js');

    for (const repo of BLACKROAD_REPOS) {
      const status = await this.env.REPO_CACHE.get(`status:${repo.name}`, 'json');

      if (status?.status === 'error') {
        issues.push({
          id: generateId('issue'),
          type: IssueType.SYNC_FAILURE,
          severity: repo.critical ? Severity.HIGH : Severity.MEDIUM,
          description: `Sync failed for ${repo.name}: ${status.error}`,
          context: {
            repo: repo.name,
            error: status.error,
            lastSync: status.lastSync,
          },
        });
      }

      // Check for stale syncs (> 24 hours)
      if (status?.lastSync) {
        const lastSyncTime = new Date(status.lastSync).getTime();
        const hoursSinceSync = (Date.now() - lastSyncTime) / (1000 * 60 * 60);

        if (hoursSinceSync > 24 && repo.critical) {
          issues.push({
            id: generateId('issue'),
            type: IssueType.SYNC_FAILURE,
            severity: Severity.LOW,
            description: `Sync stale for ${repo.name} (${Math.floor(hoursSinceSync)} hours)`,
            context: {
              repo: repo.name,
              hoursSinceSync,
              lastSync: status.lastSync,
            },
          });
        }
      }
    }

    return issues;
  }

  /**
   * Scan for cohesion issues
   */
  async _scanForCohesionIssues() {
    const issues = [];
    const cohesionData = await this.env.AGENT_STATE.get('cohesion_issues', 'json');

    if (cohesionData && cohesionData.length > 0) {
      const driftScore = cohesionData.length * 10; // Simple scoring

      issues.push({
        id: generateId('issue'),
        type: IssueType.COHESION_DRIFT,
        severity: driftScore >= 50 ? Severity.HIGH : Severity.MEDIUM,
        description: `Cohesion drift detected across ${cohesionData.length} areas`,
        context: {
          driftScore,
          inconsistencies: cohesionData,
        },
      });
    }

    return issues;
  }

  /**
   * Handle a detected issue
   */
  async handleIssue(issue) {
    this.stats.issuesDetected++;

    // Store the issue
    await this.env.AGENT_STATE.put(`issue:${issue.id}`, JSON.stringify({
      ...issue,
      detectedAt: new Date().toISOString(),
      resolved: false,
    }));

    await logEvent(this.env, 'info', 'issue_detected', {
      issueId: issue.id,
      type: issue.type,
      severity: issue.severity,
    });

    // Get decision tree for this issue type
    const tree = this.decisionTrees[issue.type];
    if (!tree) {
      await logEvent(this.env, 'warn', 'no_decision_tree', { type: issue.type });
      return { action: HealingAction.ESCALATE, message: 'No decision tree for issue type' };
    }

    // Evaluate decision tree
    const result = await tree.evaluate(issue.context);

    if (result.matched && result.result) {
      const action = result.result;

      // Execute the action
      await this._executeAction(issue, action);

      return action;
    }

    // Default: escalate
    return { action: HealingAction.ESCALATE, message: 'Decision tree did not match' };
  }

  /**
   * Execute a healing action
   */
  async _executeAction(issue, action) {
    await logEvent(this.env, 'info', 'healing_action', {
      issueId: issue.id,
      action: action.action,
    });

    switch (action.action) {
      case HealingAction.RETRY:
        await this._scheduleRetry(issue, action.delay);
        break;

      case HealingAction.SKIP:
        await this._markResolved(issue, 'Skipped after max attempts');
        await this._createLearning(issue, 'skipped');
        this.stats.issuesResolved++;
        break;

      case HealingAction.ESCALATE:
        await this._escalateIssue(issue);
        this.stats.escalations++;
        break;

      case HealingAction.LEARN:
        await this._createLearning(issue, 'learned');
        this.stats.learnings++;
        break;

      case HealingAction.NOTIFY:
        await this._notify(issue, action.message);
        break;

      case HealingAction.RESET:
        await this._resetState(issue);
        this.stats.issuesResolved++;
        break;
    }
  }

  /**
   * Schedule a retry for an issue
   */
  async _scheduleRetry(issue, delay = 5000) {
    // Queue a retry job
    const { JobScheduler } = await import('../jobs/scheduler.js');
    const scheduler = new JobScheduler(this.env);

    await scheduler.createJob({
      type: 'retry_issue',
      payload: { issueId: issue.id, originalType: issue.type },
      priority: 8,
    });

    // Update issue state
    await this.env.AGENT_STATE.put(`issue:${issue.id}`, JSON.stringify({
      ...issue,
      retryScheduledAt: new Date().toISOString(),
      retryDelay: delay,
    }));
  }

  /**
   * Mark an issue as resolved
   */
  async _markResolved(issue, resolution) {
    const stored = await this.env.AGENT_STATE.get(`issue:${issue.id}`, 'json');

    await this.env.AGENT_STATE.put(`issue:${issue.id}`, JSON.stringify({
      ...stored,
      resolved: true,
      resolvedAt: new Date().toISOString(),
      resolution,
    }));
  }

  /**
   * Create a learning from an issue
   */
  async _createLearning(issue, outcome) {
    const learning = {
      id: generateId('learning'),
      issueType: issue.type,
      outcome,
      context: issue.context,
      createdAt: new Date().toISOString(),
    };

    await this.env.LEARNING_MEMORY.put(learning.id, JSON.stringify(learning));

    await logEvent(this.env, 'info', 'learning_created', {
      learningId: learning.id,
      issueType: issue.type,
    });
  }

  /**
   * Escalate an issue (would create GitHub issue in production)
   */
  async _escalateIssue(issue) {
    const escalation = {
      issueId: issue.id,
      type: issue.type,
      severity: issue.severity,
      description: issue.description,
      context: issue.context,
      escalatedAt: new Date().toISOString(),
    };

    // Store escalation
    await this.env.AGENT_STATE.put(`escalation:${issue.id}`, JSON.stringify(escalation));

    // In production, would create GitHub issue here
    await logEvent(this.env, 'warn', 'issue_escalated', escalation);

    // Format the escalation message
    const message = this._formatEscalationMessage(escalation);
    console.log('ESCALATION:', message);
  }

  /**
   * Format an escalation message
   */
  _formatEscalationMessage(escalation) {
    const severityEmoji = {
      [Severity.LOW]: '🔵',
      [Severity.MEDIUM]: '🟡',
      [Severity.HIGH]: '🟠',
      [Severity.CRITICAL]: '🔴',
    };

    return `
## ${severityEmoji[escalation.severity] || '⚪'} Issue Escalated

**Type:** ${escalation.type}
**Severity:** ${escalation.severity}
**Description:** ${escalation.description}

### Context
\`\`\`json
${JSON.stringify(escalation.context, null, 2)}
\`\`\`

### Timeline
- Escalated: ${escalation.escalatedAt}

---
*Auto-generated by BlackRoad Self-Healing Engine*
    `.trim();
  }

  /**
   * Send a notification
   */
  async _notify(issue, message) {
    await logEvent(this.env, 'info', 'notification', {
      issueId: issue.id,
      message,
    });
    // In production, would send to Slack/Discord/email
  }

  /**
   * Reset state for an issue
   */
  async _resetState(issue) {
    // Clear related state
    if (issue.type === IssueType.JOB_FAILURE && issue.context.jobId) {
      await this.env.JOB_QUEUE.delete(issue.context.jobId);
    }

    await this._markResolved(issue, 'State reset');
  }

  /**
   * Handle a cron failure
   */
  async handleCronFailure(cronTime, error) {
    const cronKey = `cron_failures:${cronTime.replace(/[* ]/g, '_')}`;
    const failures = await this.env.AGENT_STATE.get(cronKey, 'json') || { count: 0 };

    failures.count++;
    failures.lastError = error.message;
    failures.lastFailure = new Date().toISOString();

    await this.env.AGENT_STATE.put(cronKey, JSON.stringify(failures));

    // Handle via decision tree
    await this.handleIssue({
      id: generateId('issue'),
      type: IssueType.CRON_FAILURE,
      severity: failures.count >= 3 ? Severity.HIGH : Severity.LOW,
      description: `Cron ${cronTime} failed: ${error.message}`,
      context: {
        cronTime,
        error: error.message,
        consecutiveFailures: failures.count,
      },
    });
  }

  /**
   * Handle a dead letter message
   */
  async handleDeadLetter(message) {
    await this.handleIssue({
      id: generateId('issue'),
      type: IssueType.DEAD_LETTER,
      severity: Severity.MEDIUM,
      description: `Dead letter message: ${message.id}`,
      context: {
        messageId: message.id,
        body: message.body,
        retryCount: message.retryCount,
      },
    });
  }
}
