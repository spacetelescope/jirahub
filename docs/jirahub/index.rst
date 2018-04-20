*********************
jirahub Documentation
*********************

Jirahub provides tools for the syncronization between a Github repository and a
Jira project.  With it, you can use Github for coding and ticket tracking while
using JIRA for ticket tracking and project management.

Download and Install
--------------------

To download and install::

     git clone https://github.com/spacetelescope/jirahub/tree/master
     cd jirahub
     python setup.py install

The package has several requirements included `PyGithub
<https://github.com/PyGithub/PyGithub>` and `JIRA
<https://github.com/pycontribs/jira>`.  Both of these
libraries are installable via pip.

Quick Start Up
--------------

Here is a quick start up guide to running the software.  

1. Before starting, you will need to know the following information

* name of the github repository being used in the format of '[username]/[name]'
* name of the Jira project being used in the format of '[url]/projects/[name]'
* A list of issues common between the two projects if issues or tickets already exist.

The list of issues should be a ascii file with github issues listed in 
the first column followed by Jira issues in the second column.  One matched
set of issues and tickets should be listed per row. 

For the ability to fully sync the two repositories, you will also need the
information:

* Authentication for a user with write permission to the github repository.
* Authentication for a user with write permissions to the Jira project.

These authentications can either be a username and password or authentication
key.  

2. Update the template script to your work flow.  The default template script
assumes a kanban work flow and will keep the issues, status, labels, and comments
up to date between the two repositories.  Update the template to work with your 
workflow as well as how you want issues opened and closed, comments to be tracked, 
or milestones to be updated.  Milestones in Jira are currently tracked as 
`FixVersions`. 

3. Pass the authentication information and the list of issues to the template and
the issues between the two repositories will automatically sync.

4. If it does work, set the script to run regularly as a task and it should
keep the two projects in sync.

Requirements
------------

The following are the requirements for the development of jirahub:

* Need a list of issues to watch and are linked together -- if not, all opened issues should be tracked
* check to see if any issues changed at all
* If an issue is opened in github, it creates a Jira ticket
* If an issue is opened in jira, it creates a github ticket
* When a comment is added in github, it should be added in jira
* when a comment is added in jira, it should be added in github
* when an issue is closed in github, it should be closed in jira
* when an issue is close in jira, it shoul be close in github
* milestones for jira and github should be kept in sync
* if a label is created in github, it should be added in jira
* if a label is created in jira, it should be added in github if the label exists
* there should be a link between the two issues
* There needs to be away to ignore comments opened by certain users
* Issues that are watched should be kept in synced -- comments, milestones, labels, and status
* Bonus:  Config file to link jira and github users



Reference/API
-------------

.. automodapi:: jirahub
