import 'common.just'

# $-prefixed parameters are exported by just. User input never enters a shell substitution.
# YES is the one exception: consent must be a real --yes argument on the just-dev command
# line (F6, principle 23), not an ambient JUST_DEV_YES export another mutation could inherit,
# so it is translated back into a literal --yes via conditional interpolation in the body below.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description', help='Plain-text description, sent as Atlassian Document Format.')]
[arg('JUST_DEV_JIRA_EXTRA_FIELDS', long='extra-fields', help="Optional JSON object merged into 'fields', e.g. for custom fields.")]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
create-jira-issue $JUST_DEV_JIRA_PRESET $JUST_DEV_JIRA_SUMMARY $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_JIRA_EXTRA_FIELDS='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira create-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_READ_FIELDS', long='fields', help='Comma-separated field list, e.g. summary,status.')]
[arg('JUST_DEV_JIRA_READ_INCLUDE', long='include', help='Comma-separated optional sections: links, attachments, comments.')]
[arg('JUST_DEV_JIRA_READ_VIEW', long='view', help='Issue view: summary or full.', pattern='|summary|full')]
[arg('JUST_DEV_JIRA_READ_EXPAND', long='expand', help="Comma-separated entities to expand, e.g. 'changelog'.")]
[arg('JUST_DEV_JIRA_READ_PROPERTIES', long='properties', help='Comma-separated entity property keys to return.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
read-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_READ_FIELDS='' $JUST_DEV_JIRA_READ_INCLUDE='' $JUST_DEV_JIRA_READ_VIEW='' $JUST_DEV_JIRA_READ_EXPAND='' $JUST_DEV_JIRA_READ_PROPERTIES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira read-jira-issue

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_SEARCH_FIELDS', long='fields', help='Comma-separated field list, e.g. summary,status.')]
[arg('JUST_DEV_JIRA_SEARCH_VIEW', long='view', help='Issue view: summary or full.', pattern='|summary|full')]
[arg('JUST_DEV_JIRA_SEARCH_LIMIT', long='limit', help='Maximum number of issues to return (1-100).')]
[arg('JUST_DEV_JIRA_SEARCH_NEXT_PAGE_TOKEN', long='next-page-token', help='Pagination token from a previous search response.')]
[arg('JUST_DEV_JIRA_SEARCH_EXPAND', long='expand', help="Comma-separated entities to expand, e.g. 'changelog'.")]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
search-jira-issues $JUST_DEV_JIRA_SEARCH_JQL $JUST_DEV_JIRA_SEARCH_FIELDS='' $JUST_DEV_JIRA_SEARCH_VIEW='' $JUST_DEV_JIRA_SEARCH_LIMIT='' $JUST_DEV_JIRA_SEARCH_NEXT_PAGE_TOKEN='' $JUST_DEV_JIRA_SEARCH_EXPAND='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira search-jira-issues

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_SUMMARY', long='summary', help='New summary.')]
[arg('JUST_DEV_JIRA_DESCRIPTION', long='description', help='New plain-text description, sent as Atlassian Document Format.')]
[arg('JUST_DEV_JIRA_LABELS', long='labels', help='Comma-separated labels; replaces all labels.')]
[arg('JUST_DEV_JIRA_PRIORITY', long='priority', help='New priority name, e.g. High.')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
update-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_UPDATE_REQUEST='' $JUST_DEV_JIRA_SUMMARY='' $JUST_DEV_JIRA_DESCRIPTION='' $JUST_DEV_JIRA_LABELS='' $JUST_DEV_JIRA_PRIORITY='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira update-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_ASSIGNEE', long='assignee', help="Assignee's Jira account ID, or their email address.")]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
assign-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_ASSIGNEE='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira assign-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
comment-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_COMMENT $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira comment-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
attach-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_FILE_PATH $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira attach-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
transition-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_STATUS $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira transition-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_JIRA_DELETE_SUBTASKS', long='delete-subtasks', value='1', help='Also delete subtasks of this issue.')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1', help='Show the request without writing.')]
[arg('YES', long='yes', value='1', help='Skip the interactive confirmation.')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format', help='Output format: text, markdown, or json.')]
[arg('JUST_DEV_SAFE', long='safe', value='1', help='Filter structural identity and URL fields.')]
delete-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY $JUST_DEV_JIRA_DELETE_SUBTASKS='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jira delete-jira-issue {{ if YES == '1' { '--yes' } else { '' } }}

# Opt-in only: hits a real, live Jira site (see QA-STRATEGY.md's "Live integration smoke tests are
# opt-in" layer). Never run by `qa`/`run-ci`. Creates and deletes two throwaway issues; requires
# unlocked credentials for the active profile. See recipes/jira_integration_smoke.py for details.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
jira-integration-smoke:
    @uv run --locked python recipes/jira_integration_smoke.py
