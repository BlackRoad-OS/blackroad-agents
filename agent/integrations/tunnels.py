"""Secure tunnel integrations for BlackRoad agents.

Provides interfaces for:
- Cloudflare Tunnel: Zero-trust access to services
- ngrok: Quick tunnel for development
- Tailscale: Mesh VPN for secure networking

Security principles:
- All tunnels use encrypted connections
- No exposed ports on public internet
- Access control and authentication
- Audit logging support
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
# Cloudflare Tunnel Integration
# ==============================================================================


@dataclass
class CloudflareTunnel:
    """Cloudflare Tunnel (formerly Argo Tunnel) integration.

    Environment variables:
        CLOUDFLARE_TUNNEL_TOKEN: Tunnel token
        CLOUDFLARE_TUNNEL_ID: Tunnel ID
        CLOUDFLARE_ACCOUNT_ID: Account ID

    Features:
        - Zero-trust access to local services
        - DNS-based routing
        - Access policies
        - No exposed ports
    """

    name: str = "cloudflare_tunnel"
    tunnel_token: Optional[str] = None
    tunnel_id: Optional[str] = None
    account_id: Optional[str] = None
    config_path: Path = field(default_factory=lambda: Path.home() / ".cloudflared" / "config.yml")

    def __post_init__(self) -> None:
        self.tunnel_token = self.tunnel_token or os.getenv("CLOUDFLARE_TUNNEL_TOKEN")
        self.tunnel_id = self.tunnel_id or os.getenv("CLOUDFLARE_TUNNEL_ID")
        self.account_id = self.account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")

    def start(
        self,
        config_file: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start cloudflared tunnel."""
        cmd = ["cloudflared", "tunnel"]

        if self.tunnel_token:
            cmd.extend(["run", "--token", self.tunnel_token])
        elif config_file:
            cmd.extend(["--config", config_file, "run"])
        elif url:
            cmd.extend(["--url", url])
        else:
            return {"ok": False, "error": "Token, config, or URL required"}

        try:
            # Start in background
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            return {
                "ok": True,
                "pid": process.pid,
                "message": "Tunnel started in background",
            }
        except FileNotFoundError:
            return {"ok": False, "error": "cloudflared not installed"}

    def quick_tunnel(self, url: str = "http://localhost:8000") -> Dict[str, Any]:
        """Start a quick tunnel (no account required)."""
        cmd = ["cloudflared", "tunnel", "--url", url]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Parse the tunnel URL from output
            for line in result.stderr.split("\n"):
                if "trycloudflare.com" in line or ".cloudflare" in line:
                    return {"ok": True, "url": line.strip()}
            return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout waiting for tunnel"}
        except FileNotFoundError:
            return {"ok": False, "error": "cloudflared not installed"}

    def create_config(
        self,
        tunnel_id: str,
        ingress_rules: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a cloudflared config file."""
        config = {
            "tunnel": tunnel_id,
            "credentials-file": str(Path.home() / ".cloudflared" / f"{tunnel_id}.json"),
            "ingress": ingress_rules + [{"service": "http_status:404"}],
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            import yaml
            self.config_path.write_text(yaml.dump(config))
        except ImportError:
            # Fallback to JSON-style YAML
            lines = [
                f"tunnel: {tunnel_id}",
                f"credentials-file: {config['credentials-file']}",
                "ingress:",
            ]
            for rule in ingress_rules:
                if "hostname" in rule:
                    lines.append(f"  - hostname: {rule['hostname']}")
                    lines.append(f"    service: {rule['service']}")
                else:
                    lines.append(f"  - service: {rule['service']}")
            lines.append("  - service: http_status:404")
            self.config_path.write_text("\n".join(lines))

        return {"ok": True, "path": str(self.config_path)}

    def list_tunnels(self) -> Dict[str, Any]:
        """List existing tunnels."""
        cmd = ["cloudflared", "tunnel", "list", "--output", "json"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return {"ok": True, "tunnels": json.loads(result.stdout)}
            return {"ok": False, "error": result.stderr}
        except FileNotFoundError:
            return {"ok": False, "error": "cloudflared not installed"}

    def health_check(self) -> Dict[str, Any]:
        """Check Cloudflare Tunnel integration health."""
        # Check if cloudflared is installed
        try:
            result = subprocess.run(
                ["cloudflared", "version"],
                capture_output=True,
                text=True,
            )
            installed = result.returncode == 0
            version = result.stdout.strip() if installed else None
        except FileNotFoundError:
            installed = False
            version = None

        return {
            "name": self.name,
            "configured": bool(self.tunnel_token or self.tunnel_id),
            "cloudflared_installed": installed,
            "cloudflared_version": version,
            "status": "ok" if installed else "cloudflared_not_installed",
        }


# ==============================================================================
# ngrok Integration
# ==============================================================================


@dataclass
class NgrokTunnel:
    """ngrok tunnel integration for development.

    Environment variables:
        NGROK_AUTHTOKEN: Authentication token

    Features:
        - Quick HTTP/TCP tunnels
        - Custom domains (paid)
        - Request inspection
        - Replay requests
    """

    name: str = "ngrok"
    authtoken: Optional[str] = None
    api_url: str = "http://localhost:4040/api"

    def __post_init__(self) -> None:
        self.authtoken = self.authtoken or os.getenv("NGROK_AUTHTOKEN")

    def start(
        self,
        port: int = 8000,
        protocol: str = "http",
        subdomain: Optional[str] = None,
        region: str = "us",
    ) -> Dict[str, Any]:
        """Start an ngrok tunnel."""
        cmd = ["ngrok", protocol, str(port), "--region", region]

        if subdomain:
            cmd.extend(["--subdomain", subdomain])

        try:
            # Start in background
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                env={**os.environ, "NGROK_AUTHTOKEN": self.authtoken or ""},
            )

            # Wait a bit for tunnel to start
            import time
            time.sleep(2)

            # Get tunnel URL from API
            tunnels = self.list_tunnels()
            if tunnels.get("ok") and tunnels.get("tunnels"):
                return {
                    "ok": True,
                    "pid": process.pid,
                    "tunnels": tunnels["tunnels"],
                }

            return {
                "ok": True,
                "pid": process.pid,
                "message": "Tunnel started, check ngrok dashboard",
            }
        except FileNotFoundError:
            return {"ok": False, "error": "ngrok not installed"}

    def list_tunnels(self) -> Dict[str, Any]:
        """List active tunnels via local API."""
        try:
            response = httpx.get(f"{self.api_url}/tunnels", timeout=5)
            data = response.json()
            tunnels = [
                {
                    "name": t.get("name"),
                    "url": t.get("public_url"),
                    "protocol": t.get("proto"),
                    "config": t.get("config"),
                }
                for t in data.get("tunnels", [])
            ]
            return {"ok": True, "tunnels": tunnels}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop(self, tunnel_name: str) -> Dict[str, Any]:
        """Stop a specific tunnel."""
        try:
            response = httpx.delete(
                f"{self.api_url}/tunnels/{tunnel_name}",
                timeout=5,
            )
            return {"ok": response.status_code == 204}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_requests(self, limit: int = 50) -> Dict[str, Any]:
        """Get recent requests through the tunnel."""
        try:
            response = httpx.get(
                f"{self.api_url}/requests/http",
                params={"limit": limit},
                timeout=5,
            )
            return {"ok": True, "requests": response.json().get("requests", [])}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check ngrok integration health."""
        # Check if ngrok is installed
        try:
            result = subprocess.run(
                ["ngrok", "version"],
                capture_output=True,
                text=True,
            )
            installed = result.returncode == 0
            version = result.stdout.strip() if installed else None
        except FileNotFoundError:
            installed = False
            version = None

        return {
            "name": self.name,
            "configured": bool(self.authtoken),
            "ngrok_installed": installed,
            "ngrok_version": version,
            "status": "ok" if installed else "ngrok_not_installed",
        }


# ==============================================================================
# Tailscale Integration
# ==============================================================================


@dataclass
class TailscaleTunnel:
    """Tailscale mesh VPN integration.

    Environment variables:
        TAILSCALE_AUTHKEY: Pre-authenticated key for headless setup

    Features:
        - Mesh VPN between devices
        - MagicDNS for easy access
        - ACLs for access control
        - Funnel for public exposure
    """

    name: str = "tailscale"
    authkey: Optional[str] = None

    def __post_init__(self) -> None:
        self.authkey = self.authkey or os.getenv("TAILSCALE_AUTHKEY")

    def up(
        self,
        hostname: Optional[str] = None,
        accept_routes: bool = True,
        shields_up: bool = False,
    ) -> Dict[str, Any]:
        """Bring Tailscale up."""
        cmd = ["tailscale", "up"]

        if self.authkey:
            cmd.extend(["--authkey", self.authkey])
        if hostname:
            cmd.extend(["--hostname", hostname])
        if accept_routes:
            cmd.append("--accept-routes")
        if shields_up:
            cmd.append("--shields-up")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Timeout connecting to Tailscale"}
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def down(self) -> Dict[str, Any]:
        """Bring Tailscale down."""
        try:
            result = subprocess.run(
                ["tailscale", "down"],
                capture_output=True,
                text=True,
            )
            return {"ok": result.returncode == 0}
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def status(self) -> Dict[str, Any]:
        """Get Tailscale status."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return {"ok": True, "status": json.loads(result.stdout)}
            return {"ok": False, "error": result.stderr}
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def funnel(
        self,
        port: int = 8000,
        background: bool = True,
    ) -> Dict[str, Any]:
        """Expose a local port via Tailscale Funnel."""
        cmd = ["tailscale", "funnel", str(port)]

        if background:
            cmd.append("--bg")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def serve(
        self,
        port: int = 8000,
        https: bool = True,
    ) -> Dict[str, Any]:
        """Serve a local port to tailnet."""
        protocol = "https" if https else "http"
        cmd = ["tailscale", "serve", f"{protocol}://localhost:{port}"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def get_ip(self) -> Dict[str, Any]:
        """Get Tailscale IP addresses."""
        try:
            result = subprocess.run(
                ["tailscale", "ip"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                ips = result.stdout.strip().split("\n")
                return {
                    "ok": True,
                    "ipv4": ips[0] if ips else None,
                    "ipv6": ips[1] if len(ips) > 1 else None,
                }
            return {"ok": False, "error": result.stderr}
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def ping(self, hostname: str) -> Dict[str, Any]:
        """Ping another Tailscale device."""
        try:
            result = subprocess.run(
                ["tailscale", "ping", "--c", "3", hostname],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "ok": result.returncode == 0,
                "output": result.stdout,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Ping timeout"}
        except FileNotFoundError:
            return {"ok": False, "error": "tailscale not installed"}

    def list_peers(self) -> Dict[str, Any]:
        """List connected peers."""
        status = self.status()
        if not status.get("ok"):
            return status

        peers = []
        for peer_id, peer_info in status.get("status", {}).get("Peer", {}).items():
            peers.append({
                "id": peer_id,
                "hostname": peer_info.get("HostName"),
                "dns_name": peer_info.get("DNSName"),
                "os": peer_info.get("OS"),
                "online": peer_info.get("Online"),
                "addresses": peer_info.get("TailscaleIPs", []),
            })

        return {"ok": True, "peers": peers}

    def health_check(self) -> Dict[str, Any]:
        """Check Tailscale integration health."""
        # Check if tailscale is installed
        try:
            result = subprocess.run(
                ["tailscale", "version"],
                capture_output=True,
                text=True,
            )
            installed = result.returncode == 0
            version = result.stdout.strip().split("\n")[0] if installed else None
        except FileNotFoundError:
            installed = False
            version = None

        # Get connection status if installed
        connected = False
        if installed:
            status = self.status()
            if status.get("ok"):
                connected = status.get("status", {}).get("BackendState") == "Running"

        return {
            "name": self.name,
            "configured": bool(self.authkey) or connected,
            "tailscale_installed": installed,
            "tailscale_version": version,
            "connected": connected,
            "status": "ok" if connected else ("installed" if installed else "not_installed"),
        }
