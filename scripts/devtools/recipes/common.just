# Shared, portable recipe helpers. All other modules import this file.
# source_directory() remains anchored to this imported file, unlike
# justfile_directory(), which points at the host root justfile.
devtools_root := source_directory() / ".."
project_root := source_directory() / "../../.."

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
check-devtools:
    @uv run --locked just-dev check-devtools
