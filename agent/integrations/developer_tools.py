"""Developer tools integrations for BlackRoad agents.

Provides interfaces for:
- GitHub: Repository and workflow management
- Warp: Terminal integration
- Shellfish: SSH client integration
- Working Copy: Git client for iOS
- Pyto: Python execution on iOS
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx


# ==============================================================================
# GitHub Integration
# ==============================================================================


@dataclass
class GitHubIntegration:
    """GitHub integration for repository management.

    Environment variables:
        GITHUB_TOKEN: Personal access token
        GITHUB_REPOSITORY: Default repository (owner/repo)

    Features:
        - Repository management
        - Issues and PRs
        - Workflow dispatch
        - Release management
    """

    name: str = "github"
    api_token: Optional[str] = None
    base_url: str = "https://api.github.com"
    repository: Optional[str] = None
    timeout: int = 30

    # Standard labels for issues
    LABELS: List[str] = field(default_factory=lambda: [
        "consciousness",
        "all-hands-on-deck",
        "self-healing",
        "test-cleanup",
        "workflow",
        "quantum",
        "fun",
        "learning",
    ])

    def __post_init__(self) -> None:
        self.api_token = self.api_token or os.getenv("GITHUB_TOKEN")
        self.repository = self.repository or os.getenv("GITHUB_REPOSITORY")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github.v3+json",
            }
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a GitHub issue."""
        repo = repo or self.repository
        if not repo:
            return {"ok": False, "error": "Repository not configured"}

        try:
            response = self.client.post(
                f"/repos/{repo}/issues",
                json={
                    "title": title,
                    "body": body,
                    "labels": labels or [],
                },
            )
            return {"ok": response.status_code == 201, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def trigger_workflow(
        self,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[Dict[str, str]] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a GitHub Actions workflow."""
        repo = repo or self.repository
        if not repo:
            return {"ok": False, "error": "Repository not configured"}

        try:
            response = self.client.post(
                f"/repos/{repo}/actions/workflows/{workflow_id}/dispatches",
                json={"ref": ref, "inputs": inputs or {}},
            )
            return {"ok": response.status_code == 204}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_workflows(self, repo: Optional[str] = None) -> Dict[str, Any]:
        """List repository workflows."""
        repo = repo or self.repository
        if not repo:
            return {"ok": False, "error": "Repository not configured"}

        try:
            response = self.client.get(f"/repos/{repo}/actions/workflows")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_workflow_runs(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get recent workflow runs."""
        repo = repo or self.repository
        if not repo:
            return {"ok": False, "error": "Repository not configured"}

        params = {}
        if status:
            params["status"] = status

        try:
            url = f"/repos/{repo}/actions/runs"
            if workflow_id:
                url = f"/repos/{repo}/actions/workflows/{workflow_id}/runs"
            response = self.client.get(url, params=params)
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_release(
        self,
        tag_name: str,
        name: str,
        body: str,
        draft: bool = False,
        prerelease: bool = False,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a GitHub release."""
        repo = repo or self.repository
        if not repo:
            return {"ok": False, "error": "Repository not configured"}

        try:
            response = self.client.post(
                f"/repos/{repo}/releases",
                json={
                    "tag_name": tag_name,
                    "name": name,
                    "body": body,
                    "draft": draft,
                    "prerelease": prerelease,
                },
            )
            return {"ok": response.status_code == 201, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check GitHub integration health."""
        return {
            "name": self.name,
            "configured": bool(self.api_token),
            "repository": self.repository,
            "status": "ok" if self.api_token else "not_configured",
        }


# ==============================================================================
# Warp Terminal Integration
# ==============================================================================


@dataclass
class WarpIntegration:
    """Warp terminal integration.

    Warp is a modern terminal with AI features.
    This integration provides:
        - Command execution via Warp
        - Workflow management
        - Block sharing
        - AI command suggestions

    Environment variables:
        WARP_API_KEY: API key for Warp features
    """

    name: str = "warp"
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("WARP_API_KEY")

    def open_warp(self, directory: Optional[str] = None) -> Dict[str, Any]:
        """Open Warp terminal in a directory."""
        cmd = ["open", "-a", "Warp"]
        if directory:
            cmd.extend(["--args", directory])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return {"ok": result.returncode == 0}
        except FileNotFoundError:
            return {"ok": False, "error": "Warp not installed or not on macOS"}

    def create_workflow(
        self,
        name: str,
        commands: List[str],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Warp workflow configuration."""
        workflow = {
            "name": name,
            "description": description or "",
            "steps": [{"command": cmd} for cmd in commands],
        }

        # Warp workflows are stored in ~/.warp/workflows/
        warp_dir = Path.home() / ".warp" / "workflows"
        warp_dir.mkdir(parents=True, exist_ok=True)

        workflow_file = warp_dir / f"{name}.yaml"
        try:
            import yaml
            workflow_file.write_text(yaml.dump(workflow))
            return {"ok": True, "path": str(workflow_file)}
        except ImportError:
            # Fallback to JSON
            workflow_file = warp_dir / f"{name}.json"
            workflow_file.write_text(json.dumps(workflow, indent=2))
            return {"ok": True, "path": str(workflow_file)}

    def list_workflows(self) -> Dict[str, Any]:
        """List available Warp workflows."""
        warp_dir = Path.home() / ".warp" / "workflows"
        if not warp_dir.exists():
            return {"ok": True, "workflows": []}

        workflows = []
        for f in warp_dir.glob("*"):
            if f.suffix in (".yaml", ".yml", ".json"):
                workflows.append(f.stem)

        return {"ok": True, "workflows": workflows}

    def health_check(self) -> Dict[str, Any]:
        """Check Warp integration health."""
        warp_installed = Path("/Applications/Warp.app").exists()
        return {
            "name": self.name,
            "configured": warp_installed,
            "status": "ok" if warp_installed else "not_installed",
        }


# ==============================================================================
# Shellfish SSH Integration
# ==============================================================================


@dataclass
class ShellfishIntegration:
    """Shellfish SSH client integration for iOS.

    Shellfish is an SSH client for iOS with SFTP support.
    This integration provides:
        - SSH connection management
        - SFTP file transfers
        - Shortcut automation

    Uses x-callback-url scheme: shellfish://
    """

    name: str = "shellfish"
    scheme: str = "shellfish://"

    def generate_connection_url(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_name: Optional[str] = None,
    ) -> str:
        """Generate Shellfish connection URL."""
        url = f"{self.scheme}open?host={quote(host)}&user={quote(user)}&port={port}"
        if key_name:
            url += f"&key={quote(key_name)}"
        return url

    def generate_sftp_url(
        self,
        host: str,
        user: str,
        remote_path: str = "/",
        port: int = 22,
    ) -> str:
        """Generate SFTP browse URL."""
        return f"{self.scheme}sftp?host={quote(host)}&user={quote(user)}&port={port}&path={quote(remote_path)}"

    def generate_command_url(
        self,
        host: str,
        user: str,
        command: str,
        port: int = 22,
    ) -> str:
        """Generate URL to run a command."""
        return f"{self.scheme}run?host={quote(host)}&user={quote(user)}&port={port}&command={quote(command)}"

    def get_connection_configs(self) -> Dict[str, Any]:
        """Return pre-configured connections for BlackRoad fleet."""
        connections = {
            "jetson": {
                "host": os.getenv("JETSON_HOST", "jetson.local"),
                "user": os.getenv("JETSON_USER", "jetson"),
                "port": 22,
            },
            "droplet": {
                "host": "159.65.43.12",
                "user": "root",
                "port": 22,
            },
            "lucidia-pi": {
                "host": "192.168.4.38",
                "user": "pi",
                "port": 22,
            },
            "blackroad-pi": {
                "host": "192.168.4.64",
                "user": "pi",
                "port": 22,
            },
        }

        return {
            "ok": True,
            "connections": {
                name: {
                    **config,
                    "connect_url": self.generate_connection_url(**config),
                    "sftp_url": self.generate_sftp_url(**config),
                }
                for name, config in connections.items()
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Check Shellfish integration health."""
        return {
            "name": self.name,
            "configured": True,
            "status": "ok",
            "note": "iOS app - URLs generated for x-callback",
        }


# ==============================================================================
# Working Copy Integration
# ==============================================================================


@dataclass
class WorkingCopyIntegration:
    """Working Copy git client integration for iOS.

    Working Copy is a powerful git client for iOS.
    This integration provides:
        - Repository management
        - Commit and push operations
        - Shortcut automation

    Uses x-callback-url scheme: working-copy://
    """

    name: str = "working_copy"
    scheme: str = "working-copy://"

    def generate_clone_url(
        self,
        repo_url: str,
        name: Optional[str] = None,
    ) -> str:
        """Generate URL to clone a repository."""
        url = f"{self.scheme}clone?remote={quote(repo_url)}"
        if name:
            url += f"&name={quote(name)}"
        return url

    def generate_pull_url(self, repo: str) -> str:
        """Generate URL to pull a repository."""
        return f"{self.scheme}pull?repo={quote(repo)}"

    def generate_push_url(self, repo: str) -> str:
        """Generate URL to push a repository."""
        return f"{self.scheme}push?repo={quote(repo)}"

    def generate_commit_url(
        self,
        repo: str,
        message: str,
        add_all: bool = True,
    ) -> str:
        """Generate URL to commit changes."""
        url = f"{self.scheme}commit?repo={quote(repo)}&message={quote(message)}"
        if add_all:
            url += "&add=all"
        return url

    def generate_open_url(self, repo: str, path: Optional[str] = None) -> str:
        """Generate URL to open a repository or file."""
        url = f"{self.scheme}open?repo={quote(repo)}"
        if path:
            url += f"&path={quote(path)}"
        return url

    def get_repository_configs(self) -> Dict[str, Any]:
        """Return pre-configured repositories."""
        repos = {
            "blackroad-agents": {
                "remote": "https://github.com/BlackRoad-OS/blackroad-agents",
                "name": "blackroad-agents",
            },
            "blackroad-os": {
                "remote": "https://github.com/BlackRoad-OS/blackroad-os",
                "name": "blackroad-os",
            },
            "lucidia": {
                "remote": "https://github.com/BlackRoad-OS/lucidia",
                "name": "lucidia",
            },
        }

        return {
            "ok": True,
            "repositories": {
                name: {
                    **config,
                    "clone_url": self.generate_clone_url(config["remote"], config["name"]),
                    "pull_url": self.generate_pull_url(config["name"]),
                    "push_url": self.generate_push_url(config["name"]),
                    "open_url": self.generate_open_url(config["name"]),
                }
                for name, config in repos.items()
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Check Working Copy integration health."""
        return {
            "name": self.name,
            "configured": True,
            "status": "ok",
            "note": "iOS app - URLs generated for x-callback",
        }


# ==============================================================================
# Pyto Python Integration
# ==============================================================================


@dataclass
class PytoIntegration:
    """Pyto Python IDE integration for iOS.

    Pyto is a Python IDE for iOS with full library support.
    This integration provides:
        - Script execution
        - Module management
        - Shortcut automation

    Uses x-callback-url scheme: pyto://
    """

    name: str = "pyto"
    scheme: str = "pyto://"

    def generate_run_url(
        self,
        script_path: Optional[str] = None,
        code: Optional[str] = None,
    ) -> str:
        """Generate URL to run Python code or script."""
        if code:
            return f"{self.scheme}run?code={quote(code)}"
        elif script_path:
            return f"{self.scheme}run?script={quote(script_path)}"
        return f"{self.scheme}run"

    def generate_open_url(self, path: str) -> str:
        """Generate URL to open a file."""
        return f"{self.scheme}open?path={quote(path)}"

    def get_script_templates(self) -> Dict[str, Any]:
        """Return useful script templates for BlackRoad."""
        scripts = {
            "health_check": {
                "name": "Health Check",
                "description": "Check BlackRoad agent health",
                "code": """
import httpx

endpoints = [
    "http://jetson.local:8000/health",
    "http://192.168.4.38:8000/health",
    "http://192.168.4.64:8000/health",
]

for url in endpoints:
    try:
        r = httpx.get(url, timeout=5)
        print(f"[OK] {url}: {r.json()}")
    except Exception as e:
        print(f"[ERR] {url}: {e}")
""".strip(),
            },
            "deploy_trigger": {
                "name": "Deploy Trigger",
                "description": "Trigger deployment workflow",
                "code": """
import httpx
import os

token = os.getenv("GITHUB_TOKEN", "")
repo = "BlackRoad-OS/blackroad-agents"

r = httpx.post(
    f"https://api.github.com/repos/{repo}/actions/workflows/deploy-multi-cloud.yml/dispatches",
    headers={"Authorization": f"Bearer {token}"},
    json={"ref": "main"},
)
print(f"Dispatch: {r.status_code}")
""".strip(),
            },
            "model_test": {
                "name": "Model Test",
                "description": "Test local LLM inference",
                "code": """
import httpx

agent_url = "http://jetson.local:8000"

# List models
models = httpx.get(f"{agent_url}/models").json()
print(f"Available models: {models}")

# Run inference
if models.get("models"):
    result = httpx.post(
        f"{agent_url}/models/run",
        json={"model": models["models"][0], "prompt": "Hello, ", "n": 50},
    ).json()
    print(f"Response: {result}")
""".strip(),
            },
        }

        return {
            "ok": True,
            "scripts": {
                name: {
                    **script,
                    "run_url": self.generate_run_url(code=script["code"]),
                }
                for name, script in scripts.items()
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Check Pyto integration health."""
        return {
            "name": self.name,
            "configured": True,
            "status": "ok",
            "note": "iOS app - URLs generated for x-callback",
        }
