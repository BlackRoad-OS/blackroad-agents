"""Security utilities for BlackRoad agent integrations.

Provides:
- Credential validation
- Security scanning for configurations
- Audit logging
- Secret detection
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ==============================================================================
# Secret Patterns for Detection
# ==============================================================================


SECRET_PATTERNS: Dict[str, re.Pattern] = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_key": re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"),
    "github_token": re.compile(r"gh[ps]_[A-Za-z0-9]{36,}"),
    "github_oauth": re.compile(r"gho_[A-Za-z0-9]{36}"),
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z-]+"),
    "stripe_key": re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
    "stripe_restricted": re.compile(r"rk_live_[0-9a-zA-Z]{24,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "jwt_token": re.compile(r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+"),
    "generic_secret": re.compile(r"(?i)(password|secret|token|api_key|apikey|auth)[\s]*[=:]\s*['\"]?[A-Za-z0-9+/=_-]{16,}['\"]?"),
    "clerk_key": re.compile(r"sk_(?:test|live)_[A-Za-z0-9]{24,}"),
    "notion_token": re.compile(r"secret_[A-Za-z0-9]{43}"),
    "cloudflare_api": re.compile(r"[A-Za-z0-9_-]{37}"),
    "railway_token": re.compile(r"railway_[A-Za-z0-9]{32,}"),
    "vercel_token": re.compile(r"[A-Za-z0-9]{24}"),
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{34}"),
}


# Files that should never be committed
SENSITIVE_FILES: Set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
    "secrets.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".htpasswd",
    "database.yml",
    "config.yaml",  # May contain secrets
    "application.properties",
}


# ==============================================================================
# Security Checker
# ==============================================================================


@dataclass
class SecurityChecker:
    """Security utilities for integration validation.

    Features:
    - Scan for exposed secrets in code
    - Validate configuration security
    - Generate secure tokens
    - Audit logging
    """

    name: str = "security_checker"
    audit_log_path: Optional[Path] = None
    ignored_patterns: Set[str] = field(default_factory=set)

    def scan_file_for_secrets(self, file_path: Path) -> Dict[str, Any]:
        """Scan a file for potential secrets."""
        if not file_path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        try:
            content = file_path.read_text(errors="ignore")
        except Exception as e:
            return {"ok": False, "error": str(e)}

        findings: List[Dict[str, Any]] = []

        for secret_type, pattern in SECRET_PATTERNS.items():
            if secret_type in self.ignored_patterns:
                continue

            for match in pattern.finditer(content):
                # Get line number
                line_num = content[:match.start()].count("\n") + 1

                # Redact the actual secret
                secret_value = match.group()
                redacted = f"{secret_value[:8]}...{secret_value[-4:]}" if len(secret_value) > 12 else "***"

                findings.append({
                    "type": secret_type,
                    "line": line_num,
                    "redacted_value": redacted,
                    "severity": "high" if "private_key" in secret_type or "password" in secret_type else "medium",
                })

        return {
            "ok": True,
            "file": str(file_path),
            "findings": findings,
            "has_secrets": len(findings) > 0,
        }

    def scan_directory(
        self,
        directory: Path,
        extensions: Optional[List[str]] = None,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Scan a directory for secrets."""
        extensions = extensions or [
            ".py", ".js", ".ts", ".json", ".yaml", ".yml",
            ".env", ".cfg", ".conf", ".ini", ".toml",
        ]
        exclude_dirs = exclude_dirs or [
            ".git", "node_modules", "__pycache__", ".venv",
            "venv", ".tox", "dist", "build", ".eggs",
        ]

        all_findings: List[Dict[str, Any]] = []
        files_scanned = 0
        sensitive_files_found: List[str] = []

        for file_path in directory.rglob("*"):
            # Skip excluded directories
            if any(excluded in file_path.parts for excluded in exclude_dirs):
                continue

            # Check for sensitive file names
            if file_path.name in SENSITIVE_FILES:
                sensitive_files_found.append(str(file_path))

            # Skip non-matching extensions
            if file_path.suffix not in extensions:
                continue

            if not file_path.is_file():
                continue

            files_scanned += 1
            result = self.scan_file_for_secrets(file_path)

            if result.get("has_secrets"):
                all_findings.append(result)

        return {
            "ok": True,
            "directory": str(directory),
            "files_scanned": files_scanned,
            "files_with_secrets": len(all_findings),
            "sensitive_files": sensitive_files_found,
            "findings": all_findings,
            "secure": len(all_findings) == 0 and len(sensitive_files_found) == 0,
        }

    def validate_env_security(self) -> Dict[str, Any]:
        """Validate security of environment variables."""
        issues: List[Dict[str, Any]] = []

        # Check for common insecure configurations
        checks = [
            ("DEBUG", lambda v: v.lower() in ("true", "1", "yes"), "Debug mode enabled in production"),
            ("SECRET_KEY", lambda v: len(v) < 32, "Secret key too short (should be 32+ chars)"),
            ("DATABASE_URL", lambda v: "password" in v.lower() and "@" in v, "Database URL may contain plain password"),
        ]

        for env_var, check_fn, message in checks:
            value = os.getenv(env_var)
            if value and check_fn(value):
                issues.append({
                    "variable": env_var,
                    "issue": message,
                    "severity": "high",
                })

        # Check for sensitive variables that shouldn't be set
        sensitive_vars = ["AWS_SECRET_ACCESS_KEY", "STRIPE_SECRET_KEY", "GITHUB_TOKEN"]
        for var in sensitive_vars:
            if os.getenv(var):
                # Just note that they're set, not a security issue per se
                pass

        return {
            "ok": True,
            "issues": issues,
            "secure": len(issues) == 0,
        }

    def generate_secure_token(
        self,
        length: int = 32,
        prefix: Optional[str] = None,
    ) -> str:
        """Generate a cryptographically secure token."""
        token = secrets.token_urlsafe(length)
        if prefix:
            return f"{prefix}_{token}"
        return token

    def hash_secret(self, secret: str, salt: Optional[str] = None) -> str:
        """Create a secure hash of a secret."""
        if salt is None:
            salt = secrets.token_hex(16)

        key = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            salt.encode(),
            100000,
        )
        return f"{salt}${key.hex()}"

    def verify_secret_hash(self, secret: str, hashed: str) -> bool:
        """Verify a secret against its hash."""
        try:
            salt, key_hex = hashed.split("$")
            expected_key = hashlib.pbkdf2_hmac(
                "sha256",
                secret.encode(),
                salt.encode(),
                100000,
            )
            return hmac.compare_digest(key_hex, expected_key.hex())
        except Exception:
            return False

    def audit_log(
        self,
        action: str,
        details: Dict[str, Any],
        user: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log an auditable action."""
        timestamp = datetime.utcnow().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "action": action,
            "user": user or os.getenv("USER", "system"),
            "details": details,
        }

        if self.audit_log_path:
            try:
                self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.audit_log_path.open("a") as f:
                    import json
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                log_entry["log_error"] = str(e)

        return {"ok": True, "entry": log_entry}

    def check_integration_security(
        self,
        integration_name: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check security of an integration configuration."""
        issues: List[Dict[str, Any]] = []

        # Check for hardcoded secrets
        for key, value in config.items():
            if not isinstance(value, str):
                continue

            # Check if value looks like a secret
            for secret_type, pattern in SECRET_PATTERNS.items():
                if pattern.search(value):
                    issues.append({
                        "field": key,
                        "issue": f"Possible {secret_type} in configuration",
                        "severity": "high",
                        "recommendation": f"Use environment variable instead of hardcoded value",
                    })
                    break

        # Check for insecure URLs
        url_keys = ["url", "endpoint", "base_url", "api_url", "webhook_url"]
        for key in url_keys:
            if key in config:
                url = config[key]
                if isinstance(url, str) and url.startswith("http://"):
                    issues.append({
                        "field": key,
                        "issue": "Using HTTP instead of HTTPS",
                        "severity": "medium",
                        "recommendation": "Use HTTPS for secure communication",
                    })

        return {
            "ok": True,
            "integration": integration_name,
            "issues": issues,
            "secure": len([i for i in issues if i["severity"] == "high"]) == 0,
        }

    def generate_env_template(
        self,
        integrations: List[str],
    ) -> str:
        """Generate a .env.example template for integrations."""
        templates = {
            "railway": [
                "RAILWAY_TOKEN=",
                "RAILWAY_PROJECT_ID=",
            ],
            "cloudflare": [
                "CLOUDFLARE_API_TOKEN=",
                "CLOUDFLARE_ACCOUNT_ID=",
                "CLOUDFLARE_TUNNEL_TOKEN=",
            ],
            "vercel": [
                "VERCEL_TOKEN=",
                "VERCEL_ORG_ID=",
                "VERCEL_PROJECT_ID=",
            ],
            "digitalocean": [
                "DIGITALOCEAN_TOKEN=",
                "DIGITALOCEAN_SSH_KEY=",
            ],
            "github": [
                "GITHUB_TOKEN=",
                "GITHUB_REPOSITORY=",
            ],
            "clerk": [
                "CLERK_SECRET_KEY=",
                "CLERK_PUBLISHABLE_KEY=",
                "CLERK_WEBHOOK_SECRET=",
            ],
            "stripe": [
                "STRIPE_SECRET_KEY=",
                "STRIPE_PUBLISHABLE_KEY=",
                "STRIPE_WEBHOOK_SECRET=",
            ],
            "notion": [
                "NOTION_TOKEN=",
                "NOTION_DATABASE_ID=",
            ],
            "asana": [
                "ASANA_TOKEN=",
                "ASANA_WORKSPACE_ID=",
                "ASANA_PROJECT_ID=",
            ],
            "huggingface": [
                "HF_TOKEN=",
                "HF_HOME=",
            ],
            "ngrok": [
                "NGROK_AUTHTOKEN=",
            ],
            "tailscale": [
                "TAILSCALE_AUTHKEY=",
            ],
            "agent": [
                "AGENT_AUTH_TOKEN=",
                "JETSON_HOST=jetson.local",
                "JETSON_USER=jetson",
            ],
        }

        lines = [
            "# BlackRoad Agent Configuration",
            "# Copy this file to .env and fill in the values",
            "# NEVER commit .env to version control",
            "",
        ]

        for integration in integrations:
            if integration in templates:
                lines.append(f"# {integration.upper()}")
                lines.extend(templates[integration])
                lines.append("")

        return "\n".join(lines)

    def health_check(self) -> Dict[str, Any]:
        """Check security module health."""
        return {
            "name": self.name,
            "configured": True,
            "patterns_loaded": len(SECRET_PATTERNS),
            "sensitive_files_known": len(SENSITIVE_FILES),
            "status": "ok",
        }
