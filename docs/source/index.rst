Welcome to jirahub's documentation!
###################################

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Jirahub provides a configurable tool for synchronization of issues between a
GitHub repository and a JIRA project.  With it, you can use GitHub for coding
and ticket tracking while using JIRA for ticket tracking and project management.

Download and install
====================

To download and install:

.. code-block:: bash

    $ git clone https://github.com/spacetelescope/jirahub/tree/master
    $ cd jirahub
    $ python setup.py install

The package's sole requirements are `PyGithub <https://github.com/PyGithub/PyGithub>`_ and
`JIRA <https://github.com/pycontribs/jira>`_.  Both of these libraries are installable via pip.

Configuration
=============

Jirahub configuration is divided between environment variables (JIRA and GitHub credentials)
and a .ini file (all other parameters).

Environment variables
---------------------

Your JIRA and GitHub credentials are provided to jirahub via environment variables:

=====================  ===================================================================================================================================
Variable name          Description
=====================  ===================================================================================================================================
JIRAHUB_JIRA_USERNAME  JIRA username of your jirahub bot
JIRAHUB_JIRA_PASSWORD  JIRA password of your jirahub bot
JIRAHUB_GITHUB_TOKEN   GitHub `API token <https://help.github.com/en/articles/creating-a-personal-access-token-for-the-command-line>`_ of your jirahub bot
=====================  ===================================================================================================================================

Configuration file
------------------

The remaining parameters are specified in a configuration file in .ini format.  There are few required
parameters, but jirahub takes no actions by default, so users must explicitly enable features that
they wish to use.  The `generate-config`_ command can be used to create an initial configuration file.

List-type parameters on a single line will be treated as comma-delimited.  On multiple lines,
they will be treated as newline-delimited.

[jira] section
``````````````

These are parameters particular to JIRA.  The ``server`` and ``project_key`` parameters are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - server
     - The URL of your JIRA server (e.g., https://my-jira.example.com)
   * - project_key
     - The project key of the JIRA project that will be synced
   * - github_repository_field
     - The name of a JIRA custom field in which jirahub will write the name of an issue's
       linked GitHub repository.  Useful when a JIRA project has multiple linked repositories.
   * - github_issue_id_field
     - The name of a JIRA custom field in which jirahub will write the number of an issue's
       synced GitHub issue.  This field can also be used to manually link existing JIRA and
       GitHub issues.
   * - closed_statuses
     - List of JIRA statuses that will be considered closed.  All others will be treated as
       open, for the purposes of syncing GitHub open/closed status and filtering issues.
       These values are case-insensitive.
   * - close_status
     - JIRA status set on an issue when closed by the bot
   * - reopen_status
     - JIRA status set on an issue when re-opened by the bot
   * - open_status
     - JIRA status set on a newly created issue.  Leave un-set to use your project's
       default for new issues.
   * - max_retries
     - Maximum number of retries on request failure

[jira:sync] section
```````````````````

These parameters control what data is written to JIRA.  None are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - create_issues
     - Set to True if JIRA issues should be created from GitHub issues
   * - sync_comments
     - Set to True if JIRA comments should be created from GitHub comments
   * - sync_status
     - Set to True if the JIRA issue status should be set based on the GitHub open/closed status
   * - sync_labels
     - Set to True if the JIRA issue's labels should match GitHub's labels
   * - sync_milestones
     - Set to True if the JIRA issue's fixVersions field should match GitHub's milestone
   * - labels
     - Labels to add to synced JIRA issues.  These labels are exempted from the sync process.
   * - redact_regexes
     - List of regular expressions whose matches will be redacted from issue titles,
       issue bodies, and comment bodies copied over from GitHub

[jira:filter] section
`````````````````````

These parameters filter the GitHub issues that are created in JIRA.  None are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - min_created_at
     - Accept only GitHub issues created after this timestamp.  Format is ISO-8601 in UTC with
       no timezone suffix, e.g., ``1983-11-20T11:00:00``.
   * - include_labels
     - Accept only GitHub issues that include one or more of these labels
   * - exclude_labels
     - Accept only GitHub issues without any of these labels
   * - open_only
     - Accept only open GitHub issues

[jira:defaults] section
```````````````````````

Default field values for new JIRA issues.  These fields do not exist in GitHub and are
unaffected by the sync.  None are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - issue_type
     - Issue type set on new JIRA issues.  Leave un-set to use your project's default.
   * - priority
     - Priority set on new JIRA issues.  Leave un-set to use your project's default.
   * - components
     - List of components to be set on new JIRA issues

[github] section
````````````````

These are parameters particular to GitHub.  The ``repository`` parameter is required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - repository
     - GitHub repository name with organization, e.g., spacetelescope/jwst
   * - max_retries
     - Maximum number of retries on request failure

[github:sync] section
`````````````````````

These parameters control what data is written to GitHub.  None are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - create_issues
     - Set to True if GitHub issues should be created from JIRA issues
   * - sync_comments
     - Set to True if GitHub comments should be created from JIRA comments
   * - sync_status
     - Set to True if the GitHub issue's open/closed status should be set based on the JIRA
       issue status
   * - sync_labels
     - Set to True if the GitHub issue's labels should match JIRA's labels
   * - sync_milestones
     - Set to True if the GitHub issue's milestone should match JIRA's fixVersions field
   * - labels
     - Labels to add to synced GitHub issues.  These labels are exempted from the sync process.
   * - redact_regexes
     - List of regular expressions whose matches will be redacted from issue titles,
       issue bodies, and comment bodies copied over from JIRA

[github:filter] section
```````````````````````

These parameters filter the JIRA issues that are created in GitHub.  None are required.

.. list-table::
   :header-rows: 1

   * - Name
     - Description
   * - min_created_at
     - Accept only JIRA issues created after this timestamp.  Format is ISO-8601 in UTC with
       no timezone suffix, e.g., ``1983-11-20T11:00:00``.
   * - include_issue_types
     - Accept only JIRA issues with one of these issue types
   * - exclude_issue_types
     - Accept only JIRA issues without any of these issue types
   * - include_components
     - Accept only JIRA issues with one or more of these components
   * - exclude_components
     - Accept only JIRA issues without any of these components
   * - include_labels
     - Accept only JIRA issues with one or more of these labels
   * - exclude_labels
     - Accept only JIRA issues without any of these labels
   * - open_only
     - Accept only open JIRA issues, where "open" is defined by the ``closed_statuses`` parameter

Multiple configuration files
````````````````````````````

To facilitate re-use of common parameters, jirahub commands will accept multiple
configuration file paths.

Command-line interface
======================

Jirahub is controlled with the ``jirahub`` command.  There are three subcommands: ``generate-config``,
``check-permissions``, and ``sync``.

generate-config
---------------

The ``generate-config`` command will print a template jirahub configuration file to stdout:

.. code-block:: bash

    $ jirahub generate-config > my-jirahub-config.ini

check-permissions
-----------------

Once you're satisfied with your configuration file, you can submit it to the ``check-permissions``
command for verification.  Jirahub will attempt to connect to your JIRA server and GitHub
repository and report any failures.  It will also list any missing permissions from JIRA or GitHub
that are required for the features selected in the configuration file.  A successful check looks
like this:

.. code-block:: bash

    $ jirahub check-permissions my-jirahub-config.ini
    JIRA and GitHub permissions are sufficient

And an unsuccessful check:

.. code-block:: bash

    $ jirahub check-permissions my-jirahub-config.ini
    JIRA and/or GitHub permissions must be corrected:
    sync_comments is enabled, but JIRA user has not been granted the DELETE_OWN_COMMENTS permission.
    sync_status is enabled, but JIRA user has not been granted the CLOSE_ISSUES permission.
    GitHub rejected credentials.  Check JIRAHUB_GITHUB_TOKEN and try again.

sync
----

The ``sync`` command does the work of syncing issues and comments.  At minimum, you must
specify a configuration file.  Additional options include:

* **--min-updated-at**: Restrict jirahub's activity to issues updated after this timestamp.  The timestamp
  format is ISO-8601 in UTC with no timezone suffix (e.g., 1983-11-20T11:00:00).

* **--placeholder-path**: Path to a placeholder file containing the same timestamp described above.  The
  file will be updated with a new timestamp after each run.

* **--dry-run**: Query issues and report changes to the (verbose) log, but do not change any data.

* **--verbose**: Enable verbose logging

Jirahub sync as a cron job
``````````````````````````

Users will likely want to run ``jirahub sync`` in a cron job, so that it can regularly poll JIRA/GitHub
for changes.  We recommend use of the `lockrun <http://www.unixwiz.net/tools/lockrun.html>`_ tool to
avoid overlap between jirahub processes.  Your cron line might look something like this::

    */5 * * * * lockrun --lockfile=/path/to/jirahub.lockrun -- jirahub sync /path/to/my-jirahub-config.ini --placeholder-path /path/to/jirahub-placeholder.txt >> /path/to/jirahub.log 2>&1
