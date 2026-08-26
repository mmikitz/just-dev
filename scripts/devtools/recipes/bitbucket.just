import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PR_DESCRIPTION', long='description')]
[arg('JUST_DEV_PR_REVIEWER', long='reviewer')]
[arg('JUST_DEV_PR_CLOSE_SOURCE_BRANCH', long='close-source-branch', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_NO_VERIFY', long='no-verify', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
create-pull-request $JUST_DEV_PR_TITLE $JUST_DEV_PR_DESCRIPTION='' $JUST_DEV_PR_REVIEWER='' $JUST_DEV_PR_CLOSE_SOURCE_BRANCH='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_NO_VERIFY='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket create-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
show-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket show-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
approve-pull-request $JUST_DEV_PR_ID $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket approve-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
decline-pull-request $JUST_DEV_PR_ID $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket decline-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
comment-pull-request $JUST_DEV_PR_ID $JUST_DEV_PR_COMMENT $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket comment-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
add-pull-request-reviewer $JUST_DEV_PR_ID $JUST_DEV_PR_REVIEWER_NAME $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket add-pull-request-reviewer

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PR_MESSAGE', long='message')]
[arg('JUST_DEV_PR_MERGE_STRATEGY', long='merge-strategy')]
[arg('JUST_DEV_PR_CLOSE_SOURCE_BRANCH', long='close-source-branch', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
merge-pull-request $JUST_DEV_PR_ID $JUST_DEV_PR_MESSAGE='' $JUST_DEV_PR_MERGE_STRATEGY='' $JUST_DEV_PR_CLOSE_SOURCE_BRANCH='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket merge-pull-request
