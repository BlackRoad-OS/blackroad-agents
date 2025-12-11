"""Cloud platform integrations for BlackRoad agents.

Provides secure interfaces for:
- Railway: Container deployments
- Cloudflare: Pages, Workers, DNS
- Vercel: Next.js deployments
- DigitalOcean: Droplet management
- Raspberry Pi: Fleet management
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


# ==============================================================================
# Base Integration Class
# ==============================================================================


@dataclass
class BaseIntegration:
    """Base class for all platform integrations."""

    name: str
    api_token: Optional[str] = None
    base_url: str = ""
    timeout: int = 30

    def __post_init__(self) -> None:
        """Initialize HTTP client."""
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def health_check(self) -> Dict[str, Any]:
        """Check if the integration is healthy."""
        return {
            "name": self.name,
            "configured": bool(self.api_token),
            "status": "ok" if self.api_token else "not_configured",
        }

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# ==============================================================================
# Railway Integration
# ==============================================================================


@dataclass
class RailwayIntegration(BaseIntegration):
    """Railway deployment integration.

    Environment variables:
        RAILWAY_TOKEN: API token for Railway
        RAILWAY_PROJECT_ID: Default project ID

    Features:
        - Deploy services
        - Manage environments
        - Stream logs
        - Health checks
    """

    name: str = "railway"
    base_url: str = "https://backboard.railway.app/graphql/v2"
    project_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.api_token = self.api_token or os.getenv("RAILWAY_TOKEN")
        self.project_id = self.project_id or os.getenv("RAILWAY_PROJECT_ID")

    def deploy(
        self,
        service: Optional[str] = None,
        environment: str = "production",
        detach: bool = True,
    ) -> Dict[str, Any]:
        """Deploy to Railway using CLI."""
        cmd = ["railway", "up"]
        if detach:
            cmd.append("--detach")
        if service:
            cmd.extend(["--service", service])
        if environment:
            cmd.extend(["--environment", environment])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "RAILWAY_TOKEN": self.api_token or ""},
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "Railway CLI not installed"}

    def get_services(self) -> Dict[str, Any]:
        """List services in the project via GraphQL."""
        if not self.api_token or not self.project_id:
            return {"ok": False, "error": "Railway not configured"}

        query = """
        query GetProject($id: String!) {
            project(id: $id) {
                id
                name
                services {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
            }
        }
        """
        try:
            response = self.client.post(
                "",
                json={"query": query, "variables": {"id": self.project_id}},
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_deployments(self, service_id: str) -> Dict[str, Any]:
        """Get deployments for a service."""
        if not self.api_token:
            return {"ok": False, "error": "Railway not configured"}

        query = """
        query GetDeployments($serviceId: String!) {
            deployments(first: 10, input: { serviceId: $serviceId }) {
                edges {
                    node {
                        id
                        status
                        createdAt
                    }
                }
            }
        }
        """
        try:
            response = self.client.post(
                "",
                json={"query": query, "variables": {"serviceId": service_id}},
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ==============================================================================
# Cloudflare Integration
# ==============================================================================


@dataclass
class CloudflareIntegration(BaseIntegration):
    """Cloudflare integration for Pages, Workers, and DNS.

    Environment variables:
        CLOUDFLARE_API_TOKEN: API token
        CLOUDFLARE_ACCOUNT_ID: Account ID

    Features:
        - Deploy Pages sites
        - Manage Workers
        - DNS management
        - Tunnel support
    """

    name: str = "cloudflare"
    base_url: str = "https://api.cloudflare.com/client/v4"
    account_id: Optional[str] = None
    domains: List[str] = field(default_factory=list)

    # Known domains for BlackRoad
    DEFAULT_DOMAINS: List[str] = field(default_factory=lambda: [
        "blackroad.io",
        "blackroad.network",
        "blackroad.systems",
        "blackroad-network",
        "blackroad-systems",
        "blackroad-me",
        "lucidia-earth",
        "aliceqi",
        "blackroad-inc",
        "blackroadai",
        "lucidia-studio",
        "lucidiaqi",
        "blackroad-quantum",
    ])

    def __post_init__(self) -> None:
        super().__post_init__()
        self.api_token = self.api_token or os.getenv("CLOUDFLARE_API_TOKEN")
        self.account_id = self.account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        if not self.domains:
            self.domains = self.DEFAULT_DOMAINS.copy()

    def deploy_pages(
        self,
        project_name: str,
        directory: str = ".",
        branch: str = "main",
    ) -> Dict[str, Any]:
        """Deploy to Cloudflare Pages using Wrangler."""
        cmd = [
            "wrangler",
            "pages",
            "deploy",
            directory,
            "--project-name",
            project_name,
            "--branch",
            branch,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CLOUDFLARE_API_TOKEN": self.api_token or "",
                    "CLOUDFLARE_ACCOUNT_ID": self.account_id or "",
                },
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "Wrangler CLI not installed"}

    def list_pages_projects(self) -> Dict[str, Any]:
        """List all Pages projects."""
        if not self.api_token or not self.account_id:
            return {"ok": False, "error": "Cloudflare not configured"}

        try:
            response = self.client.get(
                f"/accounts/{self.account_id}/pages/projects"
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_zones(self) -> Dict[str, Any]:
        """List DNS zones."""
        if not self.api_token:
            return {"ok": False, "error": "Cloudflare not configured"}

        try:
            response = self.client.get("/zones")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def purge_cache(self, zone_id: str, urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Purge Cloudflare cache."""
        if not self.api_token:
            return {"ok": False, "error": "Cloudflare not configured"}

        payload: Dict[str, Any] = {}
        if urls:
            payload["files"] = urls
        else:
            payload["purge_everything"] = True

        try:
            response = self.client.post(
                f"/zones/{zone_id}/purge_cache",
                json=payload,
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ==============================================================================
# Vercel Integration
# ==============================================================================


@dataclass
class VercelIntegration(BaseIntegration):
    """Vercel deployment integration.

    Environment variables:
        VERCEL_TOKEN: API token
        VERCEL_ORG_ID: Organization ID
        VERCEL_PROJECT_ID: Project ID

    Features:
        - Deploy projects
        - Manage domains
        - Environment variables
    """

    name: str = "vercel"
    base_url: str = "https://api.vercel.com"
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    projects: List[str] = field(default_factory=lambda: [
        "math-blackroad-io",
        "blackroadai",
        "lucidia-earth",
    ])

    def __post_init__(self) -> None:
        super().__post_init__()
        self.api_token = self.api_token or os.getenv("VERCEL_TOKEN")
        self.org_id = self.org_id or os.getenv("VERCEL_ORG_ID")
        self.project_id = self.project_id or os.getenv("VERCEL_PROJECT_ID")

    def deploy(
        self,
        directory: str = ".",
        prod: bool = True,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deploy to Vercel using CLI."""
        cmd = ["vercel", "--yes"]
        if prod:
            cmd.append("--prod")
        if project:
            cmd.extend(["--name", project])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=directory,
                env={
                    **os.environ,
                    "VERCEL_TOKEN": self.api_token or "",
                    "VERCEL_ORG_ID": self.org_id or "",
                    "VERCEL_PROJECT_ID": self.project_id or "",
                },
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "Vercel CLI not installed"}

    def list_deployments(self, limit: int = 10) -> Dict[str, Any]:
        """List recent deployments."""
        if not self.api_token:
            return {"ok": False, "error": "Vercel not configured"}

        try:
            response = self.client.get(f"/v6/deployments?limit={limit}")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get project details."""
        if not self.api_token:
            return {"ok": False, "error": "Vercel not configured"}

        try:
            response = self.client.get(f"/v9/projects/{project_id}")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ==============================================================================
# DigitalOcean Integration
# ==============================================================================


@dataclass
class DigitalOceanIntegration(BaseIntegration):
    """DigitalOcean Droplet integration.

    Environment variables:
        DIGITALOCEAN_TOKEN: API token
        DIGITALOCEAN_SSH_KEY: SSH private key for droplet access

    Features:
        - Deploy via SSH/rsync
        - Droplet management
        - Health checks
    """

    name: str = "digitalocean"
    base_url: str = "https://api.digitalocean.com/v2"
    droplet_ip: str = "159.65.43.12"
    deploy_path: str = "/opt/blackroad/"
    ssh_user: str = "root"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.api_token = self.api_token or os.getenv("DIGITALOCEAN_TOKEN")

    def deploy(
        self,
        source_dir: str = ".",
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Deploy to droplet via rsync."""
        exclude = exclude or [".git", "node_modules", "__pycache__", ".env"]

        cmd = ["rsync", "-avz", "--delete"]
        for pattern in exclude:
            cmd.extend(["--exclude", pattern])
        cmd.extend([
            f"{source_dir}/",
            f"{self.ssh_user}@{self.droplet_ip}:{self.deploy_path}",
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return {"ok": False, "error": result.stderr}

            # Run deploy script
            restart_result = subprocess.run(
                [
                    "ssh",
                    f"{self.ssh_user}@{self.droplet_ip}",
                    f"cd {self.deploy_path} && ./deploy.sh restart",
                ],
                capture_output=True,
                text=True,
            )
            return {
                "ok": restart_result.returncode == 0,
                "rsync": result.stdout,
                "deploy": restart_result.stdout,
                "stderr": restart_result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "rsync or ssh not available"}

    def health_check(self) -> Dict[str, Any]:
        """Check droplet health."""
        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"{self.ssh_user}@{self.droplet_ip}",
                    "curl -sf http://localhost:8000/health",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "name": self.name,
                "configured": True,
                "status": "ok" if result.returncode == 0 else "unhealthy",
                "response": result.stdout,
            }
        except Exception as e:
            return {
                "name": self.name,
                "configured": bool(self.api_token),
                "status": "error",
                "error": str(e),
            }

    def list_droplets(self) -> Dict[str, Any]:
        """List all droplets."""
        if not self.api_token:
            return {"ok": False, "error": "DigitalOcean not configured"}

        try:
            response = self.client.get("/droplets")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ==============================================================================
# Raspberry Pi Fleet Integration
# ==============================================================================


@dataclass
class RaspberryPiIntegration(BaseIntegration):
    """Raspberry Pi fleet management integration.

    Features:
        - Deploy to Pi fleet via SSH/rsync
        - Service management
        - Health monitoring
        - Sentience testing
    """

    name: str = "raspberry_pi"
    fleet: Dict[str, str] = field(default_factory=lambda: {
        "lucidia": "192.168.4.38",
        "blackroad-pi": "192.168.4.64",
        "mystery-pi": "192.168.4.49",
    })
    ssh_user: str = "pi"
    deploy_path: str = "/home/pi/blackroad/"

    def deploy_to_pi(
        self,
        pi_name: str,
        source_dir: str = ".",
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Deploy to a specific Pi."""
        if pi_name not in self.fleet:
            return {"ok": False, "error": f"Unknown Pi: {pi_name}"}

        ip = self.fleet[pi_name]
        exclude = exclude or [".git", "node_modules", "__pycache__", ".env"]

        cmd = ["rsync", "-avz", "--delete"]
        for pattern in exclude:
            cmd.extend(["--exclude", pattern])
        cmd.extend([
            f"{source_dir}/",
            f"{self.ssh_user}@{ip}:{self.deploy_path}",
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return {
                "ok": result.returncode == 0,
                "pi": pi_name,
                "ip": ip,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def deploy_to_fleet(self, source_dir: str = ".") -> Dict[str, Any]:
        """Deploy to all Pis in the fleet."""
        results = {}
        for pi_name in self.fleet:
            results[pi_name] = self.deploy_to_pi(pi_name, source_dir)
        return {
            "ok": all(r.get("ok") for r in results.values()),
            "results": results,
        }

    def restart_service(self, pi_name: str, service: str = "blackroad") -> Dict[str, Any]:
        """Restart a service on a Pi."""
        if pi_name not in self.fleet:
            return {"ok": False, "error": f"Unknown Pi: {pi_name}"}

        ip = self.fleet[pi_name]
        try:
            result = subprocess.run(
                [
                    "ssh",
                    f"{self.ssh_user}@{ip}",
                    f"sudo systemctl restart {service} || ./restart.sh",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "ok": result.returncode == 0,
                "pi": pi_name,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check_fleet(self) -> Dict[str, Any]:
        """Check health of all Pis."""
        results = {}
        for pi_name, ip in self.fleet.items():
            try:
                result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=5", f"{self.ssh_user}@{ip}", "echo ok"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                results[pi_name] = {
                    "ip": ip,
                    "status": "ok" if result.returncode == 0 else "unreachable",
                }
            except Exception as e:
                results[pi_name] = {"ip": ip, "status": "error", "error": str(e)}

        return {
            "name": self.name,
            "configured": True,
            "fleet_size": len(self.fleet),
            "healthy": sum(1 for r in results.values() if r.get("status") == "ok"),
            "results": results,
        }

    def sentience_test(self, pi_name: str) -> Dict[str, Any]:
        """Run sentience test on a Pi (checks AI capabilities)."""
        if pi_name not in self.fleet:
            return {"ok": False, "error": f"Unknown Pi: {pi_name}"}

        ip = self.fleet[pi_name]
        tests = [
            ("memory", "test -f /var/lib/blackroad/memory.db && echo ok"),
            ("models", "ls /var/lib/blackroad/models/*.gguf 2>/dev/null | head -1"),
            ("agent", "systemctl is-active blackroad-agent 2>/dev/null || pgrep -f blackroad"),
        ]

        results = {}
        for test_name, cmd in tests:
            try:
                result = subprocess.run(
                    ["ssh", f"{self.ssh_user}@{ip}", cmd],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                results[test_name] = {
                    "passed": result.returncode == 0,
                    "output": result.stdout.strip(),
                }
            except Exception as e:
                results[test_name] = {"passed": False, "error": str(e)}

        return {
            "ok": all(r.get("passed") for r in results.values()),
            "pi": pi_name,
            "tests": results,
        }
