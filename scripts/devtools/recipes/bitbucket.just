import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_NO_VERIFY', long='no-verify', value='1')]
create-pull-request $JUST_DEV_PR_TITLE $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_NO_VERIFY='':
    @uv run --locked just-dev bitbucket create-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
show-pull-request $JUST_DEV_PR_ID='':
    @uv run --locked just-dev bitbucket show-pull-request
