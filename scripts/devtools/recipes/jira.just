import 'common.just'

# $-prefixed parameters are exported by just. User input never enters a shell substitution.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description')]
[arg('JUST_DEV_JIRA_FIELDS', long='fields')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
create-jira-issue $JUST_DEV_JIRA_PRESET $JUST_DEV_JIRA_SUMMARY $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_JIRA_FIELDS='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='':
    @uv run --locked just-dev jira create-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_READ_FIELDS', long='fields')]
[arg('JUST_DEV_JIRA_READ_EXPAND', long='expand')]
[arg('JUST_DEV_JIRA_READ_PROPERTIES', long='properties')]
read-jira-isdue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_READ_FIELDS='' $JUST_DEV_JIRA_READ_EXPAND='' $JUST_DEV_JIRA_READ_PROPERTIES='':
    @uv run --locked just-dev jira read-jira-isdue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_SUMMARY', long='summary')]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
update-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_UPDATE_REQUEST='' $JUST_DEV_JIRA_SUMMARY='' $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='':
    @uv run --locked just-dev jira update-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DELETE_SUBTASKS', long='delete-subtasks', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
delete-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_DELETE_SUBTASKS='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='':
    @uv run --locked just-dev jira delete-jira-issue
