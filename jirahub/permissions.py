from github import Github
from github.GithubException import BadCredentialsException, UnknownObjectException
from jira import JIRA
from jira.exceptions import JIRAError
import requests

from .config import SyncFeature
from . import jira, github
from .entities import Source


__all__ = ["check_permissions"]


def check_permissions(config):
    errors = []

    errors.extend(_check_jira_permissions(config))
    errors.extend(_check_github_permissions(config))

    return errors


def _check_jira_permissions(config):
    errors = []

    username = jira.get_username()
    if not username:
        errors.append("Missing JIRA username.  Set the JIRAHUB_JIRA_USERNAME environment variable.")

    password = jira.get_password()
    if not password:
        errors.append("Missing JIRA password.  Set the JIRAHUB_JIRA_PASSWORD environment variable.")

    if errors:
        return errors

    try:
        client = JIRA(config.jira.server, basic_auth=(username, password), max_retries=0)
    except requests.exceptions.ConnectionError:
        errors.append(f"Unable to communicate with JIRA server: {config.jira.server}")
        return errors
    except JIRAError:
        errors.append("JIRA rejected credentials.  Check JIRAHUB_JIRA_USERNAME and JIRAHUB_JIRA_PASSWORD.")
        return errors

    try:
        perms_response = client.my_permissions(projectKey=config.jira.project_key)
    except JIRAError:
        errors.append(f"JIRA project {config.jira.project_key} does not exist.")
        return errors

    perms = {k for k, v in perms_response["permissions"].items() if v["havePermission"]}

    if "BROWSE_PROJECTS" not in perms:
        errors.append("JIRA user has not been granted the BROWSE_PROJECTS permission.")

    if "EDIT_ISSUES" not in perms:
        errors.append("JIRA user has not been granted the EDIT_ISSUES permission.")

    if config.jira.issue_filter and "CREATE_ISSUES" not in perms:
        errors.append(
            "c.jira.issue_filter is defined, but JIRA user has not been granted the CREATE_ISSUES permission."
        )

    if not config.jira.notify_watchers and not perms.intersection(
        {"SYSTEM_ADMIN", "ADMINISTER", "ADMINISTER_PROJECTS"}
    ):
        errors.append(
            "c.jira.notify_watchers is False, but JIRA user has not been granted the ADMINISTER_PROJECTS permission."
        )

    for sync_feature in SyncFeature:
        for permission in sync_feature.jira_permissions_required:
            if config.is_enabled(Source.JIRA, sync_feature) and permission not in perms:
                errors.append(
                    f"c.jira.{sync_feature.key} is enabled, but JIRA user has not been granted the {permission} permission."
                )

    return errors


def _check_github_permissions(config):
    errors = []

    token = github.get_token()
    if not token:
        errors.append("Missing GitHub access token.  Set the JIRAHUB_GITHUB_TOKEN environment variable.")
        return errors

    client = Github(token)

    try:
        repo = client.get_repo(config.github.repository)
    except BadCredentialsException:
        errors.append("GitHub rejected credentials.  Check JIRAHUB_GITHUB_TOKEN and try again.")
        return errors
    except UnknownObjectException:
        errors.append(
            f"GitHub repository {config.github.repository} does not exist, or user does not have read access."
        )
        return errors

    if not repo.permissions.push:
        if config.github.issue_filter:
            errors.append("c.github.issue_filter is defined, but GitHub user has not been granted push permissions.")

        for sync_feature in SyncFeature:
            if config.is_enabled(Source.GITHUB, sync_feature) and sync_feature.github_push_required:
                errors.append(
                    f"c.github.{sync_feature.key} is enabled, but GitHub user has not been granted push permissions."
                )

    return errors
