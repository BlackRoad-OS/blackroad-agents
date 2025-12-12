"""Platform integrations module for BlackRoad agents.

This module provides secure, unified interfaces for:
- Cloud Platforms: Railway, Cloudflare, Vercel, DigitalOcean
- Developer Tools: GitHub, Warp, Shellfish, Working Copy, Pyto
- Productivity: Asana, Notion
- Auth & Payments: Clerk, Stripe
- AI/ML: HuggingFace, Open Source LLMs
- Networking: Tunnels (Cloudflare, ngrok, Tailscale)
"""
from __future__ import annotations

from .platforms import (
    CloudflareIntegration,
    DigitalOceanIntegration,
    RailwayIntegration,
    RaspberryPiIntegration,
    VercelIntegration,
)
from .developer_tools import (
    GitHubIntegration,
    PytoIntegration,
    ShellfishIntegration,
    WarpIntegration,
    WorkingCopyIntegration,
)
from .productivity import (
    AsanaIntegration,
    NotionIntegration,
)
from .auth_payments import (
    ClerkIntegration,
    StripeIntegration,
)
from .ai_ml import (
    HuggingFaceIntegration,
    OpenSourceLLMRegistry,
)
from .tunnels import (
    CloudflareTunnel,
    NgrokTunnel,
    TailscaleTunnel,
)
from .security import SecurityChecker

__all__ = [
    # Cloud Platforms
    "CloudflareIntegration",
    "DigitalOceanIntegration",
    "RailwayIntegration",
    "RaspberryPiIntegration",
    "VercelIntegration",
    # Developer Tools
    "GitHubIntegration",
    "PytoIntegration",
    "ShellfishIntegration",
    "WarpIntegration",
    "WorkingCopyIntegration",
    # Productivity
    "AsanaIntegration",
    "NotionIntegration",
    # Auth & Payments
    "ClerkIntegration",
    "StripeIntegration",
    # AI/ML
    "HuggingFaceIntegration",
    "OpenSourceLLMRegistry",
    # Tunnels
    "CloudflareTunnel",
    "NgrokTunnel",
    "TailscaleTunnel",
    # Security
    "SecurityChecker",
]
