import 'common.just'

# This is the only target-project-specific recipe component. Replace the value
# with its canonical lint, test, and build command (a trusted project command).
project_verify_command := 'printf "%s\\n" "JUST_DEV_REPLACE_ME: customize project_verify_command in scripts/devtools/recipes/project.just" >&2; exit 20'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[env('JUST_DEV_PROJECT_VERIFY_COMMAND', project_verify_command)]
verify-project:
    @uv run --locked just-dev project verify-project

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[env('JUST_DEV_PROJECT_VERIFY_COMMAND', project_verify_command)]
run-ci:
    @uv run --locked just-dev project run-ci
