import 'common.just'

# $-prefixed parameters are exported by just. User input never enters a shell substitution.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description')]
[arg('JUST_DEV_JIRA_FIELDS', long='fields')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
create-jira-issue $JUST_DEV_JIRA_PRESET $JUST_DEV_JIRA_SUMMARY $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_JIRA_FIELDS='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira create-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_READ_FIELDS', long='fields')]
[arg('JUST_DEV_JIRA_READ_INCLUDE', long='include')]
[arg('JUST_DEV_JIRA_READ_VIEW', long='view')]
[arg('JUST_DEV_JIRA_READ_EXPAND', long='expand')]
[arg('JUST_DEV_JIRA_READ_PROPERTIES', long='properties')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
read-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_READ_FIELDS='' $JUST_DEV_JIRA_READ_INCLUDE='' $JUST_DEV_JIRA_READ_VIEW='' $JUST_DEV_JIRA_READ_EXPAND='' $JUST_DEV_JIRA_READ_PROPERTIES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira read-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_SUMMARY', long='summary')]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description')]
[arg('JUST_DEV_JIRA_LABELS', long='labels')]
[arg('JUST_DEV_JIRA_PRIORITY', long='priority')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
update-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_UPDATE_REQUEST='' $JUST_DEV_JIRA_SUMMARY='' $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_JIRA_LABELS='' $JUST_DEV_JIRA_PRIORITY='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira update-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_ASSIGNEE', long='assignee')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
assign-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_ASSIGNEE='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira assign-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
comment-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_COMMENT $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira comment-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
attach-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_FILE_PATH $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira attach-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
transition-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_STATUS $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira transition-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DELETE_SUBTASKS', long='delete-subtasks', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
delete-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_DELETE_SUBTASKS='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira delete-jira-issue

# Opt-in only: hits a real, live Jira site (see QA-STRATEGY.md's "Live integration smoke tests are
# opt-in" layer). Never run by `qa`/`run-ci`. Creates and deletes two throwaway issues; requires
# unlocked credentials for the active profile. See recipes/jira_integration_smoke.py for details.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
jira-integration-smoke:
    @uv run --locked python recipes/jira_integration_smoke.py
