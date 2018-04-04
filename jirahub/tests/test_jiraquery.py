
import pytest
from ..jiraquery import JiraQuery

@pytest.mark.remote_data
def test_jira_connect():
    j  = JiraQuery('https://jira.atlassian.com/projects/JRASERVER')
