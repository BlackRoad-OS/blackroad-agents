-- BlackRoad Agent Jobs D1 Database Schema
--
-- A comprehensive schema for job orchestration, repo tracking,
-- and self-healing state management.
--
-- Run: wrangler d1 execute blackroad-agents-db --file=./db/schema.sql

-- ============================================================================
-- JOBS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  config TEXT,  -- JSON config
  result TEXT,  -- JSON result
  error TEXT,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  healing_attempts INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME,
  completed_at DATETIME,
  escalated_at DATETIME,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

-- ============================================================================
-- REPO DATA TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS repo_data (
  repo TEXT PRIMARY KEY,
  data TEXT NOT NULL,  -- JSON blob with repo metadata
  files_count INTEGER DEFAULT 0,
  workflows_count INTEGER DEFAULT 0,
  last_commit_sha TEXT,
  last_commit_date DATETIME,
  trinity_compliant BOOLEAN DEFAULT FALSE,
  cohesiveness_score INTEGER DEFAULT 100,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_repo_data_updated_at ON repo_data(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_repo_data_trinity ON repo_data(trinity_compliant);

-- ============================================================================
-- COHESIVENESS CHECKS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS cohesiveness_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  score INTEGER NOT NULL,
  issues TEXT,  -- JSON array of issues
  repos_checked INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cohesiveness_created_at ON cohesiveness_checks(created_at DESC);

-- ============================================================================
-- SELF HEALING LOG TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS self_healing_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT,
  original_error TEXT NOT NULL,
  strategy TEXT NOT NULL,
  success BOOLEAN DEFAULT FALSE,
  result TEXT,  -- JSON result
  healing_error TEXT,
  escalated BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_healing_job_id ON self_healing_log(job_id);
CREATE INDEX IF NOT EXISTS idx_healing_success ON self_healing_log(success);
CREATE INDEX IF NOT EXISTS idx_healing_escalated ON self_healing_log(escalated);

-- ============================================================================
-- REPO SYNC HISTORY TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT,
  repos_synced TEXT,  -- JSON array of repo names
  repos_failed TEXT,  -- JSON array of failed repos
  total_synced INTEGER DEFAULT 0,
  total_failed INTEGER DEFAULT 0,
  duration_ms INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_sync_created_at ON sync_history(created_at DESC);

-- ============================================================================
-- WORKFLOW RUNS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS workflow_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  workflow_name TEXT NOT NULL,
  workflow_id TEXT,
  run_id TEXT,
  status TEXT,
  conclusion TEXT,
  head_sha TEXT,
  event TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflow_repo ON workflow_runs(repo);
CREATE INDEX IF NOT EXISTS idx_workflow_conclusion ON workflow_runs(conclusion);
CREATE INDEX IF NOT EXISTS idx_workflow_created_at ON workflow_runs(created_at DESC);

-- ============================================================================
-- DEPENDENCY AUDIT TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS dependency_audits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT,
  outdated_count INTEGER DEFAULT 0,
  vulnerability_count INTEGER DEFAULT 0,
  repos_audited INTEGER DEFAULT 0,
  details TEXT,  -- JSON with full audit details
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at ON dependency_audits(created_at DESC);

-- ============================================================================
-- GITHUB ISSUES TABLE (for tracking auto-created issues)
-- ============================================================================

CREATE TABLE IF NOT EXISTS github_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  issue_number INTEGER,
  issue_url TEXT,
  title TEXT NOT NULL,
  type TEXT NOT NULL,  -- 'escalation', 'cohesiveness', 'self-healing', etc.
  job_id TEXT,
  state TEXT DEFAULT 'open',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_issues_repo ON github_issues(repo);
CREATE INDEX IF NOT EXISTS idx_issues_type ON github_issues(type);
CREATE INDEX IF NOT EXISTS idx_issues_state ON github_issues(state);

-- ============================================================================
-- HEALTH CHECKS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS health_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kv_healthy BOOLEAN DEFAULT TRUE,
  d1_healthy BOOLEAN DEFAULT TRUE,
  queue_healthy BOOLEAN DEFAULT TRUE,
  r2_healthy BOOLEAN DEFAULT TRUE,
  overall_healthy BOOLEAN DEFAULT TRUE,
  details TEXT,  -- JSON with service details
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_health_created_at ON health_checks(created_at DESC);

-- ============================================================================
-- CONFIG SYNC TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS config_sync (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  config_type TEXT NOT NULL,  -- 'wrangler', 'package.json', etc.
  source_repo TEXT NOT NULL,
  target_repos TEXT,  -- JSON array
  synced_count INTEGER DEFAULT 0,
  failed_count INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Recent jobs view
CREATE VIEW IF NOT EXISTS recent_jobs AS
SELECT
  id,
  type,
  state,
  attempts,
  healing_attempts,
  created_at,
  completed_at,
  CASE
    WHEN completed_at IS NOT NULL
    THEN (julianday(completed_at) - julianday(started_at)) * 86400000
    ELSE NULL
  END as duration_ms
FROM jobs
ORDER BY created_at DESC
LIMIT 100;

-- Job statistics view
CREATE VIEW IF NOT EXISTS job_stats AS
SELECT
  type,
  COUNT(*) as total,
  SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END) as completed,
  SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
  SUM(CASE WHEN state = 'escalated' THEN 1 ELSE 0 END) as escalated,
  AVG(attempts) as avg_attempts
FROM jobs
GROUP BY type;

-- Repo health view
CREATE VIEW IF NOT EXISTS repo_health AS
SELECT
  repo,
  trinity_compliant,
  cohesiveness_score,
  files_count,
  workflows_count,
  last_commit_date,
  updated_at
FROM repo_data
ORDER BY cohesiveness_score ASC;

-- Self-healing success rate view
CREATE VIEW IF NOT EXISTS healing_stats AS
SELECT
  strategy,
  COUNT(*) as total_attempts,
  SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
  SUM(CASE WHEN escalated THEN 1 ELSE 0 END) as escalations,
  ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM self_healing_log
GROUP BY strategy;
