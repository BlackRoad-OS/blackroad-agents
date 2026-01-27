/**
 * ⬛⬜🛣️ BlackRoad Agents - Utility Helpers
 */

/**
 * Create a JSON response
 */
export function createResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}

/**
 * Log an event to KV and console
 */
export async function logEvent(env, level, event, data = {}) {
  const logEntry = {
    timestamp: new Date().toISOString(),
    level,
    event,
    ...data,
  };

  console.log(JSON.stringify(logEntry));

  // Store in agent state for tracking
  if (env.AGENT_STATE) {
    const key = `log:${Date.now()}:${event}`;
    await env.AGENT_STATE.put(key, JSON.stringify(logEntry), {
      expirationTtl: 86400 * 7, // Keep logs for 7 days
    });
  }

  return logEntry;
}

/**
 * Generate a unique ID
 */
export function generateId(prefix = 'job') {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 8);
  return `${prefix}_${timestamp}_${random}`;
}

/**
 * Sleep for a duration (useful for retries with backoff)
 */
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry a function with exponential backoff
 */
export async function retryWithBackoff(fn, maxRetries = 4, baseDelay = 2000) {
  let lastError;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < maxRetries - 1) {
        const delay = baseDelay * Math.pow(2, attempt);
        console.log(`Retry attempt ${attempt + 1} after ${delay}ms`);
        await sleep(delay);
      }
    }
  }

  throw lastError;
}

/**
 * Calculate hash of content (for change detection)
 */
export async function hashContent(content) {
  const encoder = new TextEncoder();
  const data = encoder.encode(content);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Parse GitHub URL to extract owner/repo
 */
export function parseGitHubUrl(url) {
  const match = url.match(/github\.com\/([^\/]+)\/([^\/]+)/);
  if (match) {
    return { owner: match[1], repo: match[2].replace('.git', '') };
  }
  return null;
}

/**
 * Format duration in human-readable form
 */
export function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

/**
 * Deep merge objects
 */
export function deepMerge(target, source) {
  const result = { ...target };

  for (const key in source) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      result[key] = deepMerge(result[key] || {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }

  return result;
}

/**
 * Truncate string with ellipsis
 */
export function truncate(str, maxLength = 100) {
  if (str.length <= maxLength) return str;
  return str.substring(0, maxLength - 3) + '...';
}

/**
 * Rate limiter using KV
 */
export async function checkRateLimit(env, key, limit = 100, windowSeconds = 60) {
  const now = Math.floor(Date.now() / 1000);
  const windowKey = `ratelimit:${key}:${Math.floor(now / windowSeconds)}`;

  const current = parseInt(await env.AGENT_STATE.get(windowKey) || '0');

  if (current >= limit) {
    return { allowed: false, remaining: 0, resetIn: windowSeconds - (now % windowSeconds) };
  }

  await env.AGENT_STATE.put(windowKey, String(current + 1), {
    expirationTtl: windowSeconds * 2,
  });

  return { allowed: true, remaining: limit - current - 1, resetIn: windowSeconds - (now % windowSeconds) };
}
