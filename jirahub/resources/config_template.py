# jirahub configuration file

# URL of JIRA deployment (required)
c.jira.server =

# JIRA project key (required)
c.jira.project_key =

# Integer ID of the JIRA custom field that stores the GitHub URL of a
# linked issue.
# (required)
c.jira.github_issue_url_field_id =

# Integer ID of the JIRA custom field that stores jirahub metadata.
# (required)
c.jira.jirahub_metadata_field_id =

# JIRA statuses that will be considered closed
#c.jira.closed_statuses = ["closed"]

# JIRA status to set when issue is closed
#c.jira.close_status = "Closed"

# JIRA status to set when issue is re-opened
#c.jira.reopen_status = "Reopened"

# JIRA status to set when an issue is first opened
# (set to None to use your project's default)
#c.jira.open_status = None

# Maximum number of retries on JIRA request failure
#c.jira.max_retries = 3

# Notify watchers when an issue is updated by the bot
#c.jira.notify_watchers = True

# Create JIRA comments from GitHub comments
#c.jira.sync_comments = False

# Set the status of the JIRA issue based on the GitHub open/closed status
#c.jira.sync_status = False

# Copy labels from GitHub to JIRA
#c.jira.sync_labels = False

# Copy milestone from GitHub to JIRA's fixVersions field
#c.jira.sync_milestones = False

# Create a comment on a linked JIRA issue (not owned by the bot)
# containing a link back to GitHub.
#c.jira.create_tracking_comment = False

# Regular expressions whose matches will be redacted from issue titles,
# issue bodies, or comment bodies copied over from GitHub.
# Must be instances of re.Pattern.
#c.jira.redact_patterns = []

# Callable that transforms the GitHub issue title before creating/updating
# it in JIRA.  Accepts two arguments, the original GitHub Issue and the
# redacted/reformatted title.  The callable must return the transformed
# title as a string.
#c.jira.issue_title_formatter = None

# Callable that transforms the GitHub issue body before creating/updating
# it in JIRA.  Accepts two arguments, the original GitHub Issue and the
# redacted/reformatted body.  The callable must return the transformed
# body as a string.
#c.jira.issue_body_formatter = None

# Callable that transforms the GitHub comment body before creating/updating
# it in JIRA.  Accepts three arguments, the original GitHub Issue and Comment,
# and the redacted/reformatted body.  The callable must return the transformed
# body as a string.
# c.jira.comment_body_formatter = None

# Callable that selects GitHub issues to create in JIRA.  Should accept
# a single argument, the original GitHub Issue, and return True to create
# the issue in JIRA, False to ignore it.  Set to None to disable creating
# JIRA issues.
#c.jira.issue_filter = None

# List of callables that transform the fields used to create a new JIRA issue.
# Each callable should accept two arguments, the original GitHub Issue, and
# an initial dict of fields.  The callable must return the transformed fields
# as a dict.
#c.jira.before_issue_create = []

# GitHub repository (e.g., spacetelescope/jwst) (required)
c.github.repository =

# Maximum number of retries on GitHub request failure
#c.github.max_retries = 3

# Create GitHub comments from JIRA comments
#c.github.sync_comments = False

# Set the GitHub open/closed state based on the JIRA status
#c.github.sync_status = False

# Copy labels from JIRA to GitHub
#c.github.sync_labels = False

# Copy JIRA's fixVersions field to GitHub's milestone
#c.github.sync_milestones = False

# Create a comment on a linked GitHub issue (not owned by the bot)
# containing a link back to JIRA.
#c.github.create_tracking_comment = False

# Regular expressions whose matches will be redacted from issue titles,
# issue bodies, or comment bodies copied over from JIRA.
# Must be instances of re.Pattern.
#c.github.redact_patterns = []

# Callable that transforms the JIRA issue title before creating/updating
# it in GitHub.  Accepts two arguments, the original JIRA Issue and the
# redacted/reformatted title.  The callable must return the transformed
# title as a string.
#c.github.issue_title_formatter = None

# Callable that transforms the JIRA issue body before creating/updating
# it in GitHub.  Accepts two arguments, the original JIRA Issue and the
# redacted/reformatted body.  The callable must return the transformed
# body as a string.
#c.github.issue_body_formatter = None

# Callable that transforms the JIRA comment body before creating/updating
# it in GitHub.  Accepts three arguments, the original JIRA Issue and Comment,
# and the redacted/reformatted body.  The callable must return the transformed
# body as a string.
# c.github.comment_body_formatter = None

# Callable that selects JIRA issues to create in GitHub.  Should accept
# a single argument (instance of jirahub.entities.Issue) and return
# True to create the issue in GitHub, False to ignore it.  Set to None
# to disable creating GitHub issues.
#c.github.issue_filter = None

# List of callables that transform the fields used to create a new GitHub issue.
# Each callable should accept two arguments, the original JIRA Issue, and
# an initial dict of fields.  The callable must return the transformed fields
# as a dict.
#c.github.before_issue_create = []
