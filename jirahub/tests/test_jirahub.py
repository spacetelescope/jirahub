
import pytest
from ..jiraquery import JiraQuery
from ..githubquery import GithubQuery
from ..jirahub import *

@pytest.mark.remote_data
def test_jira_how_issues_differ():
    j  = JiraQuery('https://jira.atlassian.com/projects/JRASERVER')
    g  = GithubQuery('eteq/jira-experimentation')
    d = how_issues_differ(g, j, '1000', 'TGH-7')
    assert d == {}
