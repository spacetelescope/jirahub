import urllib.parse

from .entities import Source


__all__ = ["UrlHelper", "isolate_regions"]


class UrlHelper:
    @classmethod
    def from_config(cls, config):
        return cls(jira_server=config.jira.server, github_repository=config.github.repository)

    def __init__(self, jira_server, github_repository):
        self._jira_server = jira_server
        self._github_repository = github_repository

    def get_issue_url(self, issue=None, source=None, issue_id=None):
        assert issue or source and issue_id

        if issue:
            source = issue.source
            issue_id = issue.issue_id

        if source == Source.JIRA:
            return f"{self._jira_server}/browse/{issue_id}"
        else:
            return f"https://github.com/{self._github_repository}/issues/{issue_id}"

    def get_pull_request_url(self, pull_request_id):
        return f"https://github.com/{self._github_repository}/pull/{pull_request_id}"

    def get_comment_url(self, issue=None, comment=None, source=None, issue_id=None, comment_id=None):
        assert issue or source and issue_id
        assert comment or source and comment_id

        if issue:
            source = issue.source
            issue_id = issue.issue_id

        if comment:
            source = comment.source
            comment_id = comment.comment_id

        if source == Source.JIRA:
            return f"{self._jira_server}/browse/{issue_id}?focusedCommentId={comment_id}#comment-{comment_id}"
        else:
            return f"https://github.com/{self._github_repository}/issues/{issue_id}#issuecomment-{comment_id}"

    def get_user_profile_url(self, user=None, source=None, username=None):
        assert user or source and username

        if user:
            source = user.source
            username = user.username

        if source == Source.JIRA:
            return f"{self._jira_server}/secure/ViewProfile.jspa?name={urllib.parse.quote(username)}"
        else:
            return f"https://github.com/{urllib.parse.quote(username)}"


def isolate_regions(regions, open_re, close_re, content_handler):
    new_regions = []
    for content, formatted in regions:
        if not formatted:
            new_regions.append((content, formatted))
        else:
            current_index = 0
            while current_index < len(content):
                open_match = open_re.search(content, current_index)
                if open_match:
                    if open_match.start() > current_index:
                        new_regions.append((content[current_index : open_match.start()], True))

                    start_index = open_match.end()
                    close_match = close_re.search(content, start_index)
                    if close_match:
                        end_index = close_match.start()
                    else:
                        end_index = len(content)
                    region = content_handler(content[start_index:end_index], open_match)
                    new_regions.append(region)
                    if close_match:
                        current_index = close_match.end()
                    else:
                        current_index = len(content)
                else:
                    new_regions.append((content[current_index:], True))
                    current_index = len(content)
    return new_regions
