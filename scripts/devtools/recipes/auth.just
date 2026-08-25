import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
configure-auth:
    @uv run --locked just-dev auth configure-auth

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
unlock-secrets:
    @uv run --locked just-dev auth unlock-secrets

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
show-auth-status:
    @uv run --locked just-dev auth show-auth-status

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
lock-secrets:
    @uv run --locked just-dev auth lock-secrets
