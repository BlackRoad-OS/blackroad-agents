/**
 * ⬛⬜🛣️ BlackRoad Agents - Cross-Repo Sync System
 *
 * Scrapes and syncs across the BlackRoad ecosystem for cohesiveness.
 * Uses GitHub API to fetch repo information and detect changes.
 */

import { logEvent, hashContent, retryWithBackoff } from '../utils/helpers.js';

/**
 * BlackRoad repositories to track for cohesion
 */
export const BLACKROAD_REPOS = [
  {
    name: 'blackroad-prism-console',
    owner: 'BlackRoad-OS',
    type: 'frontend',
    description: 'Main console/dashboard UI',
    patterns: ['apps/', 'packages/', 'components/'],
    critical: true,
  },
  {
    name: 'blackroad-os-agents',
    owner: 'BlackRoad-OS',
    type: 'agents',
    description: 'Canonical agent repository',
    patterns: ['cece/', 'runtime/', 'agents/'],
    critical: true,
  },
  {
    name: 'blackroad-os-infra',
    owner: 'BlackRoad-OS',
    type: 'infrastructure',
    description: 'Infrastructure definitions and configs',
    patterns: ['.trinity/', 'terraform/', 'k8s/'],
    critical: true,
  },
  {
    name: 'blackroad-agents',
    owner: 'BlackRoad-OS',
    type: 'agents-archive',
    description: 'Archived agent repo (this one)',
    patterns: ['agent/', 'cece/', 'src/'],
    critical: false,
  },
  {
    name: 'lucidia-ai',
    owner: 'BlackRoad-OS',
    type: 'ai-core',
    description: 'Core AI/ML systems',
    patterns: ['models/', 'inference/', 'training/'],
    critical: false,
  },
  {
    name: 'blackroad-quantum',
    owner: 'BlackRoad-OS',
    type: 'quantum',
    description: 'Quantum computing experiments',
    patterns: ['circuits/', 'algorithms/'],
    critical: false,
  },
];

/**
 * Patterns to watch for cohesion
 */
export const COHESION_PATTERNS = {
  // Shared config patterns
  configs: [
    'package.json',
    'tsconfig.json',
    'pyproject.toml',
    'wrangler.toml',
    '.env.example',
  ],
  // Trinity system files
  trinity: [
    '.trinity/',
    'TRINITY.md',
    'light-trinity.json',
  ],
  // Shared types/interfaces
  types: [
    'types/',
    'interfaces/',
    'schemas/',
  ],
  // Documentation
  docs: [
    'README.md',
    'CONTRIBUTING.md',
    'docs/',
  ],
};

/**
 * Repo Sync Manager class
 */
export class RepoSyncManager {
  constructor(env) {
    this.env = env;
    this.githubToken = env.GITHUB_TOKEN;
    this.baseUrl = 'https://api.github.com';
  }

  /**
   * Make a GitHub API request
   */
  async githubRequest(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;

    const headers = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'BlackRoad-Agents/2.0',
    };

    if (this.githubToken) {
      headers['Authorization'] = `Bearer ${this.githubToken}`;
    }

    const response = await retryWithBackoff(async () => {
      const res = await fetch(url, { ...options, headers });
      if (!res.ok) {
        const error = await res.text();
        throw new Error(`GitHub API error: ${res.status} - ${error}`);
      }
      return res;
    });

    return response.json();
  }

  /**
   * List all tracked repos
   */
  async listTrackedRepos() {
    const repos = [];

    for (const repo of BLACKROAD_REPOS) {
      const cachedStatus = await this.env.REPO_CACHE.get(`status:${repo.name}`, 'json');

      repos.push({
        ...repo,
        status: cachedStatus || { lastSync: null, healthy: null },
      });
    }

    return repos;
  }

  /**
   * Check repo status (is sync needed?)
   */
  async checkRepoStatus(repoName) {
    const repo = BLACKROAD_REPOS.find(r => r.name === repoName);
    if (!repo) {
      throw new Error(`Unknown repo: ${repoName}`);
    }

    try {
      // Get latest commit
      const commits = await this.githubRequest(
        `/repos/${repo.owner}/${repo.name}/commits?per_page=1`
      );

      const latestCommit = commits[0];
      const latestSha = latestCommit?.sha;
      const commitDate = latestCommit?.commit?.committer?.date;

      // Check cached state
      const cached = await this.env.REPO_CACHE.get(`sha:${repoName}`);
      const lastSync = await this.env.REPO_CACHE.get(`sync:${repoName}`, 'json');

      const needsSync = !cached || cached !== latestSha;

      const status = {
        repo: repoName,
        status: 'ok',
        lastSync: lastSync?.timestamp || null,
        latestCommit: latestSha,
        latestCommitDate: commitDate,
        needsSync,
      };

      // Cache the status
      await this.env.REPO_CACHE.put(`status:${repoName}`, JSON.stringify(status));

      return status;
    } catch (error) {
      await logEvent(this.env, 'error', 'repo_status_check_failed', {
        repo: repoName,
        error: error.message,
      });

      return {
        repo: repoName,
        status: 'error',
        error: error.message,
        needsSync: true, // Assume yes on error
      };
    }
  }

  /**
   * Sync a specific repo
   */
  async syncRepo(repoName) {
    const repo = BLACKROAD_REPOS.find(r => r.name === repoName);
    if (!repo) {
      throw new Error(`Unknown repo: ${repoName}`);
    }

    await logEvent(this.env, 'info', 'repo_sync_started', { repo: repoName });

    try {
      // Get latest commit SHA
      const commits = await this.githubRequest(
        `/repos/${repo.owner}/${repo.name}/commits?per_page=1`
      );
      const latestSha = commits[0]?.sha;

      // Get repo tree
      const tree = await this.githubRequest(
        `/repos/${repo.owner}/${repo.name}/git/trees/${latestSha}?recursive=1`
      );

      // Analyze the tree
      const analysis = this.analyzeTree(tree.tree, repo.patterns);

      // Store sync data
      await this.env.REPO_CACHE.put(`sha:${repoName}`, latestSha);
      await this.env.REPO_CACHE.put(`sync:${repoName}`, JSON.stringify({
        timestamp: new Date().toISOString(),
        sha: latestSha,
        fileCount: tree.tree.length,
        analysis,
      }));
      await this.env.REPO_CACHE.put(`tree:${repoName}`, JSON.stringify(tree.tree));

      await logEvent(this.env, 'info', 'repo_sync_completed', {
        repo: repoName,
        sha: latestSha,
        files: tree.tree.length,
      });

      return {
        success: true,
        repo: repoName,
        sha: latestSha,
        fileCount: tree.tree.length,
        analysis,
      };
    } catch (error) {
      await logEvent(this.env, 'error', 'repo_sync_failed', {
        repo: repoName,
        error: error.message,
      });

      return {
        success: false,
        repo: repoName,
        error: error.message,
      };
    }
  }

  /**
   * Sync all repos
   */
  async syncAllRepos() {
    const results = [];

    for (const repo of BLACKROAD_REPOS) {
      const result = await this.syncRepo(repo.name);
      results.push(result);
    }

    return results;
  }

  /**
   * Scrape a repo (deeper analysis)
   */
  async scrapeRepo(repoName) {
    const repo = BLACKROAD_REPOS.find(r => r.name === repoName);
    if (!repo) {
      throw new Error(`Unknown repo: ${repoName}`);
    }

    try {
      // Get the tree from cache or fetch
      let tree = await this.env.REPO_CACHE.get(`tree:${repoName}`, 'json');

      if (!tree) {
        const syncResult = await this.syncRepo(repoName);
        if (!syncResult.success) {
          throw new Error(syncResult.error);
        }
        tree = await this.env.REPO_CACHE.get(`tree:${repoName}`, 'json');
      }

      // Analyze patterns
      const patterns = {};
      const fileTypes = {};

      for (const item of tree) {
        if (item.type === 'blob') {
          // Count file types
          const ext = item.path.split('.').pop();
          fileTypes[ext] = (fileTypes[ext] || 0) + 1;

          // Check for important patterns
          for (const [category, patternList] of Object.entries(COHESION_PATTERNS)) {
            for (const pattern of patternList) {
              if (item.path.includes(pattern) || item.path.endsWith(pattern)) {
                if (!patterns[category]) {
                  patterns[category] = [];
                }
                patterns[category].push(item.path);
              }
            }
          }
        }
      }

      return {
        repo: repoName,
        fileCount: tree.length,
        fileTypes,
        patterns,
        scrapedAt: new Date().toISOString(),
      };
    } catch (error) {
      await logEvent(this.env, 'error', 'repo_scrape_failed', {
        repo: repoName,
        error: error.message,
      });

      return {
        repo: repoName,
        error: error.message,
      };
    }
  }

  /**
   * Analyze a file tree
   */
  analyzeTree(tree, watchPatterns) {
    const analysis = {
      totalFiles: 0,
      totalDirs: 0,
      watchedFiles: [],
      filesByType: {},
    };

    for (const item of tree) {
      if (item.type === 'blob') {
        analysis.totalFiles++;

        // Track file types
        const ext = item.path.split('.').pop() || 'none';
        analysis.filesByType[ext] = (analysis.filesByType[ext] || 0) + 1;

        // Check if this matches watch patterns
        for (const pattern of watchPatterns) {
          if (item.path.startsWith(pattern) || item.path.includes(pattern)) {
            analysis.watchedFiles.push(item.path);
            break;
          }
        }
      } else if (item.type === 'tree') {
        analysis.totalDirs++;
      }
    }

    return analysis;
  }

  /**
   * Analyze cohesion across repos
   */
  async analyzeCohesion(repoData) {
    const analysis = {
      inconsistencies: [],
      recommendations: [],
      cohesionScore: 100,
    };

    // Check for Trinity system consistency
    const trinityRepos = Object.entries(repoData)
      .filter(([_, data]) => data.patterns?.trinity?.length > 0);

    if (trinityRepos.length > 0 && trinityRepos.length < Object.keys(repoData).length) {
      analysis.inconsistencies.push({
        type: 'missing_trinity',
        severity: 'medium',
        message: 'Some repos missing Trinity system files',
        repos: Object.keys(repoData).filter(
          repo => !repoData[repo].patterns?.trinity?.length
        ),
      });
      analysis.cohesionScore -= 10;
    }

    // Check for consistent package.json versions/deps
    const packageJsonRepos = Object.entries(repoData)
      .filter(([_, data]) => data.patterns?.configs?.some(f => f.endsWith('package.json')));

    if (packageJsonRepos.length > 1) {
      // Would need to fetch and compare actual contents for detailed analysis
      analysis.recommendations.push({
        type: 'verify_dependencies',
        message: 'Multiple repos with package.json - verify dependency versions are aligned',
        repos: packageJsonRepos.map(([name]) => name),
      });
    }

    // Check for documentation consistency
    const reposWithDocs = Object.entries(repoData)
      .filter(([_, data]) => data.patterns?.docs?.length > 0);

    const reposWithoutDocs = Object.keys(repoData)
      .filter(repo => !repoData[repo].patterns?.docs?.length);

    if (reposWithoutDocs.length > 0) {
      analysis.inconsistencies.push({
        type: 'missing_docs',
        severity: 'low',
        message: 'Some repos missing documentation',
        repos: reposWithoutDocs,
      });
      analysis.cohesionScore -= 5;
    }

    // Check for shared type definitions
    const reposWithTypes = Object.entries(repoData)
      .filter(([_, data]) => data.patterns?.types?.length > 0);

    if (reposWithTypes.length > 1) {
      analysis.recommendations.push({
        type: 'shared_types',
        message: 'Multiple repos with type definitions - consider consolidating',
        repos: reposWithTypes.map(([name]) => name),
      });
    }

    return analysis;
  }

  /**
   * Run deep analysis across all repos
   */
  async runDeepAnalysis() {
    const results = {
      findings: [],
      patterns: [],
      improvements: [],
      analyzedAt: new Date().toISOString(),
    };

    // Collect all scraped data
    const repoData = {};
    for (const repo of BLACKROAD_REPOS) {
      const cached = await this.env.REPO_CACHE.get(`scrape:${repo.name}`, 'json');
      if (cached) {
        repoData[repo.name] = cached;
      }
    }

    // Cross-repo pattern analysis
    const allFileTypes = {};
    let totalFiles = 0;

    for (const [repoName, data] of Object.entries(repoData)) {
      if (data.fileTypes) {
        totalFiles += data.fileCount || 0;
        for (const [ext, count] of Object.entries(data.fileTypes)) {
          allFileTypes[ext] = (allFileTypes[ext] || 0) + count;
        }
      }
    }

    // Find dominant file types (potential tech stack)
    const sortedTypes = Object.entries(allFileTypes)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10);

    results.patterns.push({
      type: 'tech_stack',
      description: 'Dominant file types across ecosystem',
      data: sortedTypes,
    });

    // Check for potential code duplication patterns
    const sharedPatternCounts = {};
    for (const [repoName, data] of Object.entries(repoData)) {
      if (data.patterns) {
        for (const [category, files] of Object.entries(data.patterns)) {
          if (!sharedPatternCounts[category]) {
            sharedPatternCounts[category] = new Set();
          }
          sharedPatternCounts[category].add(repoName);
        }
      }
    }

    // Find patterns present in multiple repos
    for (const [category, repos] of Object.entries(sharedPatternCounts)) {
      if (repos.size > 1) {
        results.findings.push({
          type: 'shared_pattern',
          category,
          repos: Array.from(repos),
          recommendation: `Consider consolidating ${category} across repos`,
        });
      }
    }

    // Generate improvement suggestions
    if (totalFiles > 10000) {
      results.improvements.push({
        type: 'monorepo_consideration',
        message: 'Large codebase - consider monorepo structure for better cohesion',
        totalFiles,
      });
    }

    // Store analysis results
    await this.env.AGENT_STATE.put('deep_analysis_results', JSON.stringify(results));

    return results;
  }

  /**
   * Full reconciliation for a repo
   */
  async fullReconcile(repoName) {
    await logEvent(this.env, 'info', 'full_reconcile_started', { repo: repoName });

    // 1. Sync repo
    const syncResult = await this.syncRepo(repoName);
    if (!syncResult.success) {
      return { success: false, step: 'sync', error: syncResult.error };
    }

    // 2. Scrape repo
    const scrapeResult = await this.scrapeRepo(repoName);
    if (scrapeResult.error) {
      return { success: false, step: 'scrape', error: scrapeResult.error };
    }

    // 3. Update status
    await this.env.REPO_CACHE.put(`status:${repoName}`, JSON.stringify({
      lastSync: new Date().toISOString(),
      healthy: true,
      sha: syncResult.sha,
      fileCount: syncResult.fileCount,
    }));

    await logEvent(this.env, 'info', 'full_reconcile_completed', {
      repo: repoName,
      fileCount: syncResult.fileCount,
    });

    return {
      success: true,
      repo: repoName,
      sync: syncResult,
      scrape: scrapeResult,
    };
  }
}
