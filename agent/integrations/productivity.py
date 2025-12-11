"""Productivity tool integrations for BlackRoad agents.

Provides interfaces for:
- Asana: Task and project management
- Notion: Workspace and documentation
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


# ==============================================================================
# Asana Integration
# ==============================================================================


@dataclass
class AsanaIntegration:
    """Asana task management integration.

    Environment variables:
        ASANA_TOKEN: Personal access token
        ASANA_WORKSPACE_ID: Default workspace
        ASANA_PROJECT_ID: Default project

    Features:
        - Task creation and management
        - Project tracking
        - Deployment task updates
        - Team collaboration
    """

    name: str = "asana"
    api_token: Optional[str] = None
    base_url: str = "https://app.asana.com/api/1.0"
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    timeout: int = 30

    def __post_init__(self) -> None:
        self.api_token = self.api_token or os.getenv("ASANA_TOKEN")
        self.workspace_id = self.workspace_id or os.getenv("ASANA_WORKSPACE_ID")
        self.project_id = self.project_id or os.getenv("ASANA_PROJECT_ID")
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

    def create_task(
        self,
        name: str,
        notes: Optional[str] = None,
        due_on: Optional[str] = None,
        assignee: Optional[str] = None,
        project_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an Asana task."""
        if not self.api_token:
            return {"ok": False, "error": "Asana not configured"}

        project = project_id or self.project_id
        if not project:
            return {"ok": False, "error": "Project ID required"}

        data: Dict[str, Any] = {
            "name": name,
            "projects": [project],
        }

        if notes:
            data["notes"] = notes
        if due_on:
            data["due_on"] = due_on
        if assignee:
            data["assignee"] = assignee
        if tags:
            data["tags"] = tags

        try:
            response = self.client.post("/tasks", json={"data": data})
            return {"ok": response.status_code == 201, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def complete_task(self, task_id: str) -> Dict[str, Any]:
        """Mark a task as complete."""
        if not self.api_token:
            return {"ok": False, "error": "Asana not configured"}

        try:
            response = self.client.put(
                f"/tasks/{task_id}",
                json={"data": {"completed": True}},
            )
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def add_comment(self, task_id: str, text: str) -> Dict[str, Any]:
        """Add a comment to a task."""
        if not self.api_token:
            return {"ok": False, "error": "Asana not configured"}

        try:
            response = self.client.post(
                f"/tasks/{task_id}/stories",
                json={"data": {"text": text}},
            )
            return {"ok": response.status_code == 201, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_tasks(
        self,
        project_id: Optional[str] = None,
        completed: bool = False,
    ) -> Dict[str, Any]:
        """Get tasks from a project."""
        if not self.api_token:
            return {"ok": False, "error": "Asana not configured"}

        project = project_id or self.project_id
        if not project:
            return {"ok": False, "error": "Project ID required"}

        try:
            response = self.client.get(
                "/tasks",
                params={
                    "project": project,
                    "completed_since": "now" if not completed else None,
                },
            )
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def log_deployment(
        self,
        platforms: List[str],
        status: str = "success",
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a deployment to Asana."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_name = f"Deployment: {', '.join(platforms)} - {timestamp}"

        notes = f"""Deployment Log
--------------
Timestamp: {timestamp}
Status: {status}
Platforms: {', '.join(platforms)}

{details or 'Deployment completed successfully.'}
"""

        return self.create_task(
            name=task_name,
            notes=notes,
            tags=["deployment", status],
        )

    def health_check(self) -> Dict[str, Any]:
        """Check Asana integration health."""
        if not self.api_token:
            return {
                "name": self.name,
                "configured": False,
                "status": "not_configured",
            }

        try:
            response = self.client.get("/users/me")
            return {
                "name": self.name,
                "configured": True,
                "status": "ok" if response.status_code == 200 else "error",
                "user": response.json().get("data", {}).get("name"),
            }
        except Exception as e:
            return {
                "name": self.name,
                "configured": True,
                "status": "error",
                "error": str(e),
            }


# ==============================================================================
# Notion Integration
# ==============================================================================


@dataclass
class NotionIntegration:
    """Notion workspace integration.

    Environment variables:
        NOTION_TOKEN: Integration token
        NOTION_DATABASE_ID: Default database

    Features:
        - Page creation
        - Database management
        - Deployment logging
        - Documentation sync
    """

    name: str = "notion"
    api_token: Optional[str] = None
    base_url: str = "https://api.notion.com/v1"
    database_id: Optional[str] = None
    api_version: str = "2022-06-28"
    timeout: int = 30

    def __post_init__(self) -> None:
        self.api_token = self.api_token or os.getenv("NOTION_TOKEN")
        self.database_id = self.database_id or os.getenv("NOTION_DATABASE_ID")
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            headers = {
                "Notion-Version": self.api_version,
            }
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def create_page(
        self,
        title: str,
        content: List[Dict[str, Any]],
        parent_page_id: Optional[str] = None,
        database_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a Notion page."""
        if not self.api_token:
            return {"ok": False, "error": "Notion not configured"}

        # Determine parent
        if database_id or self.database_id:
            parent = {"database_id": database_id or self.database_id}
        elif parent_page_id:
            parent = {"page_id": parent_page_id}
        else:
            return {"ok": False, "error": "Parent page or database required"}

        # Build properties
        page_properties = properties or {}
        if "title" not in page_properties and "Name" not in page_properties:
            page_properties["Name"] = {
                "title": [{"text": {"content": title}}]
            }

        data = {
            "parent": parent,
            "properties": page_properties,
            "children": content,
        }

        try:
            response = self.client.post("/pages", json=data)
            return {"ok": response.status_code == 200, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def query_database(
        self,
        database_id: Optional[str] = None,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Query a Notion database."""
        if not self.api_token:
            return {"ok": False, "error": "Notion not configured"}

        db_id = database_id or self.database_id
        if not db_id:
            return {"ok": False, "error": "Database ID required"}

        data: Dict[str, Any] = {}
        if filter_obj:
            data["filter"] = filter_obj
        if sorts:
            data["sorts"] = sorts

        try:
            response = self.client.post(f"/databases/{db_id}/query", json=data)
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def search(self, query: str, filter_type: Optional[str] = None) -> Dict[str, Any]:
        """Search Notion workspace."""
        if not self.api_token:
            return {"ok": False, "error": "Notion not configured"}

        data: Dict[str, Any] = {"query": query}
        if filter_type:
            data["filter"] = {"property": "object", "value": filter_type}

        try:
            response = self.client.post("/search", json=data)
            return {"ok": True, "data": response.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def log_deployment(
        self,
        platforms: List[str],
        status: str = "success",
        details: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a deployment to Notion."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create content blocks
        content = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Deployment Details"}}]
                },
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"Timestamp: {timestamp}"}}]
                },
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"Status: {status}"}}]
                },
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"Platforms: {', '.join(platforms)}"}}]
                },
            },
        ]

        if commit_sha:
            content.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": f"Commit: {commit_sha}"}}]
                },
            })

        if details:
            content.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": details}}]
                },
            })

        # Properties for database entry
        properties = {
            "Name": {"title": [{"text": {"content": f"Deployment {timestamp}"}}]},
            "Status": {"select": {"name": status}},
            "Platforms": {"multi_select": [{"name": p} for p in platforms]},
        }

        return self.create_page(
            title=f"Deployment {timestamp}",
            content=content,
            properties=properties,
        )

    def health_check(self) -> Dict[str, Any]:
        """Check Notion integration health."""
        if not self.api_token:
            return {
                "name": self.name,
                "configured": False,
                "status": "not_configured",
            }

        try:
            response = self.client.get("/users/me")
            return {
                "name": self.name,
                "configured": True,
                "status": "ok" if response.status_code == 200 else "error",
            }
        except Exception as e:
            return {
                "name": self.name,
                "configured": True,
                "status": "error",
                "error": str(e),
            }
