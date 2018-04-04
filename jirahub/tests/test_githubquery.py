
import pytest
from ..githubquery import GithubQuery

@pytest.mark.remote_data
def test_github_connect():
    g  = GithubQuery('eteq/jira-experimentation')
