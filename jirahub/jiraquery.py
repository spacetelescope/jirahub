# Licensed under a 3-clause BSD style license - see LICENSE.rst
# This module implements the JiraQuery class.

from jira import JIRA, JIRAError

__all__ = ['JiraQuery']


class JiraQuery(object):
    """Class to query and update a jira project compared to a Github repository
    """

    def __init__(self, jira, key=None, user=None, password=None):
        """Class to query and update a jira project compared to a Github repository

        Parameters
        ----------
        jira: str
            Name of a repository to track and update the issues.  The name of
            the repository should be in the form of 'url/project/name'

        key: str
            Authentification token for the current user

        user: str
            Username for the current user

        password: str
            password for the current user
        """
        # link to the current rero
        site, repo_name = jira.split('/projects/')
        self.repo = repo_name

        # authenticate with github
        if key:
            self.jira = JIRA(site, oauth=key)
        elif user is not None:
            self.jira = JIRA(site, basic_auth=(user, password))
        else:
             self.jira = JIRA(site)

    @property
    def issue(self):
        return self._issue

    @issue.setter
    def issue(self, issue_id):
        try:
            self._issue = self.jira.issue(issue_id)
        except JIRAError:
            self._issue = None

    def add_comment(self, comment):
        """Add a comment to an issue.  

        Parameters
        ----------
        comment: str
            Comment to be added to an issue
        """
        self.jira.add_comment(self.issue, comment)
