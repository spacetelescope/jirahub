def failing_body_formatter(issue, body):
    raise Exception("Nope")


c.jira.issue_body_formatter = failing_body_formatter
c.github.issue_body_formatter = failing_body_formatter
