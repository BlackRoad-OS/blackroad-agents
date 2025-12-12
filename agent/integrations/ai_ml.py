"""AI/ML integrations for BlackRoad agents.

Provides interfaces for:
- HuggingFace: Model hub and inference
- Open Source LLMs: Safe, forkable models registry

Security principles:
- All models are from verified, auditable sources
- No proprietary/closed-source model dependencies
- Models can be self-hosted and inspected
- Preference for Apache 2.0, MIT, and permissive licenses
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


# ==============================================================================
# HuggingFace Integration
# ==============================================================================


@dataclass
class HuggingFaceIntegration:
    """HuggingFace model hub integration.

    Environment variables:
        HF_TOKEN: API token (optional for public models)
        HF_HOME: Cache directory for models

    Features:
        - Model discovery and download
        - Inference API access
        - Model metadata retrieval
        - Safe model filtering
    """

    name: str = "huggingface"
    api_token: Optional[str] = None
    base_url: str = "https://huggingface.co/api"
    inference_url: str = "https://api-inference.huggingface.co/models"
    cache_dir: Optional[Path] = None
    timeout: int = 60

    # Trusted organizations for model sourcing
    TRUSTED_ORGS: List[str] = field(default_factory=lambda: [
        "meta-llama",
        "mistralai",
        "microsoft",
        "google",
        "EleutherAI",
        "bigscience",
        "tiiuae",
        "Qwen",
        "stabilityai",
        "TheBloke",  # Quantized models
        "NousResearch",
        "teknium",
        "Open-Orca",
        "lmsys",
    ])

    # Safe licenses for open source models
    SAFE_LICENSES: List[str] = field(default_factory=lambda: [
        "apache-2.0",
        "mit",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "openrail",
        "openrail++",
        "llama2",
        "llama3",
        "gemma",
        "cc-by-nc-4.0",  # Non-commercial but inspectable
    ])

    def __post_init__(self) -> None:
        self.api_token = self.api_token or os.getenv("HF_TOKEN")
        hf_home = os.getenv("HF_HOME")
        self.cache_dir = Path(hf_home) if hf_home else Path.home() / ".cache" / "huggingface"
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._client = httpx.Client(
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get model metadata."""
        try:
            response = self.client.get(f"{self.base_url}/models/{model_id}")
            if response.status_code != 200:
                return {"ok": False, "error": f"Model not found: {model_id}"}
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def is_safe_model(self, model_id: str) -> Dict[str, Any]:
        """Check if a model is from a trusted source with safe license."""
        info = self.get_model_info(model_id)
        if not info.get("ok"):
            return info

        data = info["data"]
        model_org = model_id.split("/")[0] if "/" in model_id else None
        license_id = data.get("cardData", {}).get("license", "unknown")

        is_trusted_org = model_org in self.TRUSTED_ORGS if model_org else False
        is_safe_license = license_id.lower() in [l.lower() for l in self.SAFE_LICENSES]

        return {
            "ok": True,
            "model_id": model_id,
            "organization": model_org,
            "license": license_id,
            "is_trusted_org": is_trusted_org,
            "is_safe_license": is_safe_license,
            "safe": is_trusted_org and is_safe_license,
            "downloads": data.get("downloads", 0),
            "likes": data.get("likes", 0),
        }

    def search_models(
        self,
        query: str,
        task: Optional[str] = None,
        library: Optional[str] = None,
        limit: int = 20,
        safe_only: bool = True,
    ) -> Dict[str, Any]:
        """Search for models on HuggingFace."""
        params: Dict[str, Any] = {
            "search": query,
            "limit": limit,
            "sort": "downloads",
            "direction": -1,
        }
        if task:
            params["filter"] = task
        if library:
            params["library"] = library

        try:
            response = self.client.get(f"{self.base_url}/models", params=params)
            models = response.json()

            if safe_only:
                # Filter to trusted orgs
                models = [
                    m for m in models
                    if m.get("modelId", "").split("/")[0] in self.TRUSTED_ORGS
                ]

            return {"ok": True, "models": models}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def download_model(
        self,
        model_id: str,
        revision: str = "main",
        verify_safe: bool = True,
    ) -> Dict[str, Any]:
        """Download a model using huggingface-cli."""
        if verify_safe:
            safety = self.is_safe_model(model_id)
            if not safety.get("ok"):
                return safety
            if not safety.get("safe"):
                return {
                    "ok": False,
                    "error": f"Model {model_id} is not from a trusted source or has unsafe license",
                    "safety_info": safety,
                }

        cmd = ["huggingface-cli", "download", model_id, "--revision", revision]
        if self.cache_dir:
            cmd.extend(["--cache-dir", str(self.cache_dir)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, "HF_TOKEN": self.api_token or ""},
            )
            return {
                "ok": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except FileNotFoundError:
            return {"ok": False, "error": "huggingface-cli not installed"}

    def inference(
        self,
        model_id: str,
        inputs: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run inference using HuggingFace Inference API."""
        if not self.api_token:
            return {"ok": False, "error": "HF_TOKEN required for inference API"}

        data: Dict[str, Any] = {"inputs": inputs}
        if parameters:
            data["parameters"] = parameters

        try:
            response = self.client.post(
                f"{self.inference_url}/{model_id}",
                json=data,
            )
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_cached_models(self) -> Dict[str, Any]:
        """List locally cached models."""
        if not self.cache_dir or not self.cache_dir.exists():
            return {"ok": True, "models": []}

        hub_dir = self.cache_dir / "hub"
        if not hub_dir.exists():
            return {"ok": True, "models": []}

        models = []
        for model_dir in hub_dir.glob("models--*"):
            # Parse model ID from directory name
            parts = model_dir.name.replace("models--", "").split("--")
            if len(parts) >= 2:
                model_id = f"{parts[0]}/{parts[1]}"
                models.append({
                    "model_id": model_id,
                    "path": str(model_dir),
                    "size_mb": sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) // (1024 * 1024),
                })

        return {"ok": True, "models": models}

    def health_check(self) -> Dict[str, Any]:
        """Check HuggingFace integration health."""
        return {
            "name": self.name,
            "configured": True,
            "has_token": bool(self.api_token),
            "cache_dir": str(self.cache_dir),
            "status": "ok",
        }


# ==============================================================================
# Open Source LLM Registry
# ==============================================================================


@dataclass
class OpenSourceLLMRegistry:
    """Registry of safe, forkable open source LLMs.

    This registry maintains a curated list of:
    - Fully open source models (weights + code)
    - Models with permissive licenses
    - Models that can be self-hosted
    - Models with published training details

    Security principles:
    - All models can be inspected and audited
    - No phone-home or telemetry requirements
    - Can be run fully offline
    - Training data is documented
    """

    name: str = "opensource_llm_registry"

    # Curated list of safe, forkable models
    # Format: model_id -> metadata
    MODELS: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        # Meta Llama Family
        "meta-llama/Llama-3.2-1B": {
            "name": "Llama 3.2 1B",
            "parameters": "1B",
            "license": "llama3.2",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "meta-llama/Llama-3.2-3B": {
            "name": "Llama 3.2 3B",
            "parameters": "3B",
            "license": "llama3.2",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "meta-llama/Llama-3.1-8B": {
            "name": "Llama 3.1 8B",
            "parameters": "8B",
            "license": "llama3.1",
            "type": "base",
            "use_cases": ["text-generation", "chat", "coding"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # Mistral Family
        "mistralai/Mistral-7B-v0.3": {
            "name": "Mistral 7B v0.3",
            "parameters": "7B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "mistralai/Mixtral-8x7B-v0.1": {
            "name": "Mixtral 8x7B MoE",
            "parameters": "47B (8x7B MoE)",
            "license": "apache-2.0",
            "type": "moe",
            "use_cases": ["text-generation", "chat", "coding"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M"],
            "safe": True,
            "self_hostable": True,
        },

        # Microsoft Phi Family
        "microsoft/phi-3-mini-4k-instruct": {
            "name": "Phi-3 Mini 4K",
            "parameters": "3.8B",
            "license": "mit",
            "type": "instruct",
            "use_cases": ["chat", "coding", "reasoning"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "microsoft/phi-2": {
            "name": "Phi-2",
            "parameters": "2.7B",
            "license": "mit",
            "type": "base",
            "use_cases": ["text-generation", "coding"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # Google Gemma Family
        "google/gemma-2-2b": {
            "name": "Gemma 2 2B",
            "parameters": "2B",
            "license": "gemma",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "google/gemma-2-9b": {
            "name": "Gemma 2 9B",
            "parameters": "9B",
            "license": "gemma",
            "type": "base",
            "use_cases": ["text-generation", "chat", "coding"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # Qwen Family
        "Qwen/Qwen2.5-0.5B": {
            "name": "Qwen 2.5 0.5B",
            "parameters": "0.5B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "edge-deployment"],
            "quantized_versions": ["Q4_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "Qwen/Qwen2.5-1.5B": {
            "name": "Qwen 2.5 1.5B",
            "parameters": "1.5B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "Qwen/Qwen2.5-7B": {
            "name": "Qwen 2.5 7B",
            "parameters": "7B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "chat", "coding"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "Qwen/Qwen2.5-Coder-7B": {
            "name": "Qwen 2.5 Coder 7B",
            "parameters": "7B",
            "license": "apache-2.0",
            "type": "coder",
            "use_cases": ["coding", "code-completion"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # TII Falcon Family
        "tiiuae/falcon-7b": {
            "name": "Falcon 7B",
            "parameters": "7B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # StabilityAI
        "stabilityai/stablelm-2-1_6b": {
            "name": "StableLM 2 1.6B",
            "parameters": "1.6B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "chat"],
            "quantized_versions": ["Q4_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },

        # EleutherAI
        "EleutherAI/pythia-1.4b": {
            "name": "Pythia 1.4B",
            "parameters": "1.4B",
            "license": "apache-2.0",
            "type": "base",
            "use_cases": ["text-generation", "research"],
            "quantized_versions": ["Q4_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
            "training_data": "The Pile (documented)",
        },

        # Specialized/Fine-tuned (from trusted sources)
        "NousResearch/Hermes-3-Llama-3.1-8B": {
            "name": "Hermes 3 Llama 3.1 8B",
            "parameters": "8B",
            "license": "llama3.1",
            "type": "instruct",
            "use_cases": ["chat", "function-calling", "agents"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
        "teknium/OpenHermes-2.5-Mistral-7B": {
            "name": "OpenHermes 2.5 Mistral 7B",
            "parameters": "7B",
            "license": "apache-2.0",
            "type": "instruct",
            "use_cases": ["chat", "function-calling"],
            "quantized_versions": ["Q4_K_M", "Q5_K_M", "Q8_0"],
            "safe": True,
            "self_hostable": True,
        },
    })

    def list_models(
        self,
        use_case: Optional[str] = None,
        max_params: Optional[str] = None,
        license_filter: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """List available models with optional filtering."""
        models = []

        for model_id, info in self.MODELS.items():
            # Filter by use case
            if use_case and use_case not in info.get("use_cases", []):
                continue

            # Filter by license
            if license_filter and info.get("license") not in license_filter:
                continue

            # Filter by size (basic string comparison)
            if max_params:
                model_params = info.get("parameters", "0B")
                # This is a simplified check
                if "B" in max_params and "B" in model_params:
                    max_val = float(max_params.replace("B", "").split("x")[-1])
                    model_val = float(model_params.replace("B", "").split("x")[-1].split()[0])
                    if model_val > max_val:
                        continue

            models.append({
                "model_id": model_id,
                **info,
            })

        return {"ok": True, "models": models, "count": len(models)}

    def get_model(self, model_id: str) -> Dict[str, Any]:
        """Get details for a specific model."""
        if model_id not in self.MODELS:
            return {"ok": False, "error": f"Model not in registry: {model_id}"}

        return {
            "ok": True,
            "model_id": model_id,
            **self.MODELS[model_id],
        }

    def get_recommended_models(
        self,
        device: str = "gpu",
        vram_gb: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get recommended models based on hardware."""
        recommendations = {
            "edge": [],      # <2B, good for RPi/edge
            "consumer": [],  # 2-7B, good for consumer GPU
            "prosumer": [],  # 7-13B, good for gaming GPU
            "server": [],    # 13B+, needs datacenter GPU
        }

        for model_id, info in self.MODELS.items():
            params = info.get("parameters", "0B")
            # Extract numeric value
            try:
                if "x" in params:  # MoE models
                    param_val = float(params.split("x")[0]) * float(params.split("x")[1].replace("B", "").split()[0])
                else:
                    param_val = float(params.replace("B", "").split()[0])
            except ValueError:
                param_val = 0

            model_entry = {"model_id": model_id, **info}

            if param_val <= 2:
                recommendations["edge"].append(model_entry)
            elif param_val <= 7:
                recommendations["consumer"].append(model_entry)
            elif param_val <= 13:
                recommendations["prosumer"].append(model_entry)
            else:
                recommendations["server"].append(model_entry)

        # Filter by VRAM if specified
        if vram_gb:
            if vram_gb <= 4:
                recommendations = {"edge": recommendations["edge"]}
            elif vram_gb <= 8:
                recommendations = {
                    "edge": recommendations["edge"],
                    "consumer": recommendations["consumer"],
                }
            elif vram_gb <= 16:
                recommendations = {
                    "edge": recommendations["edge"],
                    "consumer": recommendations["consumer"],
                    "prosumer": recommendations["prosumer"],
                }

        return {
            "ok": True,
            "device": device,
            "vram_gb": vram_gb,
            "recommendations": recommendations,
        }

    def get_quantized_path(
        self,
        model_id: str,
        quantization: str = "Q4_K_M",
    ) -> Dict[str, Any]:
        """Get the HuggingFace path for a quantized version."""
        if model_id not in self.MODELS:
            return {"ok": False, "error": f"Model not in registry: {model_id}"}

        info = self.MODELS[model_id]
        if quantization not in info.get("quantized_versions", []):
            return {
                "ok": False,
                "error": f"Quantization {quantization} not available for {model_id}",
                "available": info.get("quantized_versions", []),
            }

        # TheBloke typically hosts quantized versions
        org, name = model_id.split("/") if "/" in model_id else ("", model_id)
        quantized_id = f"TheBloke/{name}-GGUF"

        return {
            "ok": True,
            "model_id": model_id,
            "quantized_id": quantized_id,
            "quantization": quantization,
            "filename": f"{name.lower()}.{quantization}.gguf",
        }

    def health_check(self) -> Dict[str, Any]:
        """Check registry health."""
        return {
            "name": self.name,
            "configured": True,
            "total_models": len(self.MODELS),
            "status": "ok",
        }
