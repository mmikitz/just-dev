# Shared, portable recipe helpers. All other modules import this file.
# source_directory() remains anchored to this imported file, unlike
# justfile_directory(), which points at the host root justfile.
devtools_root := source_directory() / ".."
project_root := source_directory() / "../../.."

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
check-devtools $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev check-devtools

# The machine-readable command manifest `just --list` doesn't provide (see OPEN_ISSUES.md's U3).
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[doc('List every command as a machine-readable MCP-style tool manifest.')]
describe-commands $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev describe-commands
