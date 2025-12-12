"""Authentication and payment integrations for BlackRoad agents.

Provides interfaces for:
- Clerk: User authentication and management
- Stripe: Payment processing
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


# ==============================================================================
# Clerk Integration
# ==============================================================================


@dataclass
class ClerkIntegration:
    """Clerk authentication integration.

    Environment variables:
        CLERK_SECRET_KEY: Backend API key
        CLERK_PUBLISHABLE_KEY: Frontend key
        CLERK_WEBHOOK_SECRET: Webhook signing secret

    Features:
        - User management
        - Session verification
        - Organization management
        - Webhook handling
    """

    name: str = "clerk"
    secret_key: Optional[str] = None
    publishable_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    base_url: str = "https://api.clerk.com/v1"
    timeout: int = 30

    def __post_init__(self) -> None:
        self.secret_key = self.secret_key or os.getenv("CLERK_SECRET_KEY")
        self.publishable_key = self.publishable_key or os.getenv("CLERK_PUBLISHABLE_KEY")
        self.webhook_secret = self.webhook_secret or os.getenv("CLERK_WEBHOOK_SECRET")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            headers = {}
            if self.secret_key:
                headers["Authorization"] = f"Bearer {self.secret_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user by ID."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        try:
            response = self.client.get(f"/users/{user_id}")
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_users(
        self,
        limit: int = 10,
        offset: int = 0,
        email_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List users."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if email_address:
            params["email_address"] = email_address

        try:
            response = self.client.get("/users", params=params)
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_user(
        self,
        email_address: str,
        password: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new user."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        data: Dict[str, Any] = {
            "email_address": [email_address],
        }
        if password:
            data["password"] = password
        if first_name:
            data["first_name"] = first_name
        if last_name:
            data["last_name"] = last_name
        if username:
            data["username"] = username

        try:
            response = self.client.post("/users", json=data)
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """Delete a user."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        try:
            response = self.client.delete(f"/users/{user_id}")
            return {"ok": response.status_code == 200}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def verify_session(self, session_token: str) -> Dict[str, Any]:
        """Verify a session token."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        try:
            response = self.client.post(
                "/sessions/verify",
                json={"token": session_token},
            )
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        timestamp: str,
    ) -> bool:
        """Verify webhook signature."""
        if not self.webhook_secret:
            return False

        # Clerk uses svix for webhooks
        signed_content = f"{timestamp}.{payload.decode()}"
        expected_sig = hmac.new(
            self.webhook_secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected_sig)

    def get_organizations(self) -> Dict[str, Any]:
        """List organizations."""
        if not self.secret_key:
            return {"ok": False, "error": "Clerk not configured"}

        try:
            response = self.client.get("/organizations")
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check Clerk integration health."""
        return {
            "name": self.name,
            "configured": bool(self.secret_key),
            "publishable_key_set": bool(self.publishable_key),
            "webhook_configured": bool(self.webhook_secret),
            "status": "ok" if self.secret_key else "not_configured",
        }


# ==============================================================================
# Stripe Integration
# ==============================================================================


@dataclass
class StripeIntegration:
    """Stripe payment integration.

    Environment variables:
        STRIPE_SECRET_KEY: API secret key
        STRIPE_PUBLISHABLE_KEY: Publishable key
        STRIPE_WEBHOOK_SECRET: Webhook signing secret

    Features:
        - Customer management
        - Payment processing
        - Subscription management
        - Webhook handling

    Security notes:
        - Never log or expose secret keys
        - Always verify webhook signatures
        - Use idempotency keys for mutations
    """

    name: str = "stripe"
    secret_key: Optional[str] = None
    publishable_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    base_url: str = "https://api.stripe.com/v1"
    timeout: int = 30

    def __post_init__(self) -> None:
        self.secret_key = self.secret_key or os.getenv("STRIPE_SECRET_KEY")
        self.publishable_key = self.publishable_key or os.getenv("STRIPE_PUBLISHABLE_KEY")
        self.webhook_secret = self.webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            auth = None
            if self.secret_key:
                auth = (self.secret_key, "")
            self._client = httpx.Client(
                base_url=self.base_url,
                auth=auth,
                timeout=self.timeout,
            )
        return self._client

    def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a Stripe customer."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        data: Dict[str, Any] = {"email": email}
        if name:
            data["name"] = name
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = value

        try:
            response = self.client.post("/customers", data=data)
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get customer by ID."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        try:
            response = self.client.get(f"/customers/{customer_id}")
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_customers(self, limit: int = 10) -> Dict[str, Any]:
        """List customers."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        try:
            response = self.client.get("/customers", params={"limit": limit})
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        mode: str = "subscription",
    ) -> Dict[str, Any]:
        """Create a checkout session."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        data = {
            "customer": customer_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

        try:
            response = self.client.post("/checkout/sessions", data=data)
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_payment_intent(
        self,
        amount: int,
        currency: str = "usd",
        customer_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a payment intent."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        data: Dict[str, Any] = {
            "amount": str(amount),
            "currency": currency,
        }
        if customer_id:
            data["customer"] = customer_id
        if metadata:
            for key, value in metadata.items():
                data[f"metadata[{key}]"] = value

        try:
            response = self.client.post("/payment_intents", data=data)
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription by ID."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        try:
            response = self.client.get(f"/subscriptions/{subscription_id}")
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> Dict[str, Any]:
        """Cancel a subscription."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        try:
            if at_period_end:
                response = self.client.post(
                    f"/subscriptions/{subscription_id}",
                    data={"cancel_at_period_end": "true"},
                )
            else:
                response = self.client.delete(f"/subscriptions/{subscription_id}")
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        tolerance: int = 300,
    ) -> Dict[str, Any]:
        """Verify webhook signature and return event."""
        if not self.webhook_secret:
            return {"ok": False, "error": "Webhook secret not configured"}

        try:
            # Parse signature header
            elements = dict(item.split("=") for item in signature.split(","))
            timestamp = int(elements.get("t", "0"))
            v1_signature = elements.get("v1", "")

            # Check timestamp tolerance
            if abs(time.time() - timestamp) > tolerance:
                return {"ok": False, "error": "Timestamp outside tolerance"}

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected_sig = hmac.new(
                self.webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(v1_signature, expected_sig):
                return {"ok": False, "error": "Invalid signature"}

            import json
            return {"ok": True, "event": json.loads(payload)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_products(self, active: bool = True) -> Dict[str, Any]:
        """List products."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        try:
            response = self.client.get(
                "/products",
                params={"active": str(active).lower()},
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_prices(self, product_id: Optional[str] = None) -> Dict[str, Any]:
        """List prices."""
        if not self.secret_key:
            return {"ok": False, "error": "Stripe not configured"}

        params = {}
        if product_id:
            params["product"] = product_id

        try:
            response = self.client.get("/prices", params=params)
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> Dict[str, Any]:
        """Check Stripe integration health."""
        if not self.secret_key:
            return {
                "name": self.name,
                "configured": False,
                "status": "not_configured",
            }

        try:
            response = self.client.get("/balance")
            return {
                "name": self.name,
                "configured": True,
                "publishable_key_set": bool(self.publishable_key),
                "webhook_configured": bool(self.webhook_secret),
                "status": "ok" if response.status_code == 200 else "error",
            }
        except Exception as e:
            return {
                "name": self.name,
                "configured": True,
                "status": "error",
                "error": str(e),
            }
