# Licensed under a 3-clause BSD style license - see LICENSE.rst
# This module implements functions to compare Jira projects and Github repos

import logging

__all__ = ['how_issues_differ']

# Need a list of issues to watch and are linked together -- if not, all opened issues should be tracked

# check to see if they changd at all

# If an issue is opened in github, it creates a Jira ticket
# If an issue is opened in jira, it creates a github ticket
# When a comment is added in github, it should be added in jira
# when a comment is added in jira, it should be added in github
# when an issue is closed in github, it should be closed in jira
# when an issue is close in jira, it shoul be close in github
# milestones for jira and github should be kept in sync
# if a label is created in github, it should be added in jira
# if a label is created in jira, it should be added in github if the label exists
# there should be a link between the two issues
# There needs to be away to ignore comments opened by certain users
# Issues that are watched should be kept in synced -- comments, milestones, labels, and status

# Bonus:  Config file to link jira and github users


def how_issues_differ(github, jira, github_id, jira_id):
    """Compare a jira and github issue for the following things:
         * do they both exist?
         * are they the same status?
         * do they have the same comments?
         * do they have the same labels?
         * are they set for the same milestone?
    If they are different, return the differences

    Parameters
    ----------
    github: ~GithubQuery
        Object capable of querying a github repo

    jira: ~JiraQuery
        Object capable of querying a Jira project

    github_id: str
        Number for a github issue

    jira_id: str
        A jira ticket

    Returns
    -------
    differences: dict
        A dictionary containing the differences in status, comments, labels,
        or milestones.

    Note
    ----
    The keywords in the returned dictionary are:
        * missing: if one of the issues does not exist
        * status:  the status of each repository if different as a tuble
                   with the github status followed by the jira status
        * comments: any comments appear in one repo or the other.  Stored
                    as a dict according to the repo
        * labels: any labels that appear in one repo or th e other. Stored
                    as a dict according to the repo
        * milestones: the milestones of each repository if different as a tuble
                   with the github status followed by the jira status
    """
    differences = {}

    # get the two issues
    github.issue = github_id
    jira.issue = jira_id


    # determine if one issue is missing
    if github.issue is None and jira.issue is None:
        return {}
    elif github.issue is None:
        return {'missing': 'github'}
    elif jira.issue is None:
        return {'missing': 'jira'}

    logging.info('Comparing Jira issue {} and Github #{}'.format(jira.issue,
        github.issue.number))

    # compare the status of each issue
    if jira.issue.fields.status != github.issue.state:
        differences['status'] = (github.issue.state, jira.issue.fields.status.name)

    # compare the milestone of each issue -- assuming fixVersions for jira milestones
    if jira.issue.fields.fixVersions != github.issue.milestone:
        if not (jira.issue.fields.fixVersions == [] and github.issue.milestone is None):
            differences['milestone'] = (github.issue.milestone, jira.issue.fields.fixVersions)

    # compare the labels in each issues
    missing_jira_labels = list(filter(lambda x: x not in jira.issue.fields.labels, github.issue.labels))
    missing_github_labels = list(filter(lambda x: x not in github.issue.labels, jira.issue.fields.labels))
    differences['labels'] = {'github': missing_github_labels, 'jira': missing_jira_labels}

    # compare the comments in each issue
    github_comments = [g.body for g in github.issue.get_comments()]
    jira_comments = [j.body for j in jira.issue.fields.comment.comments]
    missing_jira_comments = list(filter(lambda x: x not in jira_comments, github_comments))
    missing_github_comments = list(filter(lambda x: x not in github_comments, jira_comments))
    differences['comments'] = {'github': missing_github_comments, 'jira': missing_jira_comments}

    if differences:
       logging.info('The following differences were found:')
       for k in differences:
            logging.info('  Difference in {}: {}'.format(k, differences[k]))

    return differences
