# Auth accepts the CLI's complete incremental option set, including repeated
# --entry / --remove-entry values. Positional forwarding preserves each user
# argument without evaluating it in the shell.
set positional-arguments

import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
configure-auth *args:
    @uv run --locked just-dev auth configure-auth "$@"

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
unlock-secrets *args:
    @uv run --locked just-dev auth unlock-secrets "$@"

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
show-auth-status *args:
    @uv run --locked just-dev auth show-auth-status "$@"

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
lock-secrets *args:
    @uv run --locked just-dev auth lock-secrets "$@"
