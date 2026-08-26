import 'common.just'

# This is the only target-project-specific recipe component. Replace the value
# with its canonical lint, test, and build command (a trusted project command).
project_verify_command := 'printf "%s\\n" "JUST_DEV_REPLACE_ME: customize project_verify_command in scripts/devtools/recipes/project.just" >&2; exit 20'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[env('JUST_DEV_PROJECT_VERIFY_COMMAND', project_verify_command)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
verify-project $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev project verify-project

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[env('JUST_DEV_PROJECT_VERIFY_COMMAND', project_verify_command)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
run-ci $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev project run-ci
