from __future__ import annotations

import pytest

from just_dev.models import ProjectConfig


@pytest.fixture
def config() -> ProjectConfig:
    return ProjectConfig.model_validate(
        {
            "atlassian": {"cloud_id": "cloud-123"},
            "jira": {
                "presets": {"bug": {"project": "DEV", "issue_type": "Task", "labels": ["auto-filed"], "components": []}}
            },
            "bitbucket": {
                "workspace": "workspace",
                "repository": "repository",
                "username": "developer@example.test",
                "target_branch": "main",
                "reviewers": ["reviewer"],
            },
            "jenkins": {
                "url": "https://jenkins.example.test",
                "username": "jenkins-user",
                "presets": {"test": {"job": "folder/job/test", "allowed_parameters": ["REF"]}},
            },
            "confluence": {"presets": {"release-notes": {"page_id": "42", "title": "Release notes"}}},
            "project": {"starter_hook": False, "verify_commands": ["true"]},
        }
    )
