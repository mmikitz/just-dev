import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_BUILD_PARAMETER', long='parameter')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
run-build $JUST_DEV_BUILD_PRESET $JUST_DEV_BUILD_PARAMETER='' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jenkins run-build

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
show-build-status $JUST_DEV_BUILD_PRESET $JUST_DEV_BUILD_REFERENCE $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev jenkins show-build-status
