"""Configuration and public result objects, kept independent of SDK wrappers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AtlassianSettings(StrictModel):
    cloud_id: str


class JiraPreset(StrictModel):
    project: str
    issue_type: str
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)


class JiraSettings(StrictModel):
    presets: dict[str, JiraPreset] = Field(default_factory=dict)


class BitbucketSettings(StrictModel):
    workspace: str
    repository: str
    username: str
    target_branch: str = "main"
    reviewers: list[str] = Field(default_factory=list)
    api_base: str = "https://api.bitbucket.org/2.0"


class JenkinsPreset(StrictModel):
    job: str
    allowed_parameters: list[str] = Field(default_factory=list)


class JenkinsSettings(StrictModel):
    url: str
    username: str
    presets: dict[str, JenkinsPreset] = Field(default_factory=dict)


class ConfluencePreset(StrictModel):
    page_id: str
    title: str


class ConfluenceSettings(StrictModel):
    presets: dict[str, ConfluencePreset] = Field(default_factory=dict)


class ProjectSettings(StrictModel):
    starter_hook: bool = True
    verify_commands: list[str] = Field(default_factory=list)


class ProjectConfig(StrictModel):
    atlassian: AtlassianSettings
    jira: JiraSettings
    bitbucket: BitbucketSettings
    jenkins: JenkinsSettings
    confluence: ConfluenceSettings
    project: ProjectSettings


class IssueResult(StrictModel):
    key: str
    status: str | None = None
    summary: str
    assignee: str | None = None
    url: str | None = None


class PullRequestResult(StrictModel):
    id: int | str
    title: str
    source_branch: str
    target_branch: str
    url: str | None = None
    existing: bool = False


class BuildResult(StrictModel):
    preset: str
    queue_id: int | None = None
    build_number: int | None = None
    status: str
    url: str | None = None


class PageResult(StrictModel):
    page_id: str
    title: str
    version: int | None = None
    url: str | None = None
    body: str | None = None


class VerificationResult(StrictModel):
    command: str
    returncode: int
    output: str = ""


class PreviewResult(StrictModel):
    action: str
    details: dict[str, Any]


class BrokerStatus(StrictModel):
    active: bool
    expires_at: datetime | None = None
    platform: str | None = None
    pid: int | None = None
