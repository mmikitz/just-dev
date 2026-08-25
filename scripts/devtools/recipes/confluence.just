import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_CONFLUENCE_PRESET', long='preset')]
preview-release-notes $JUST_DEV_RELEASE_NOTES_FILE $JUST_DEV_CONFLUENCE_PRESET='release-notes':
    @uv run --locked just-dev confluence preview-release-notes

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_CONFLUENCE_PRESET', long='preset')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('JUST_DEV_YES', long='yes', value='1')]
publish-release-notes $JUST_DEV_RELEASE_NOTES_FILE $JUST_DEV_CONFLUENCE_PRESET='release-notes' $JUST_DEV_DRY_RUN='' $JUST_DEV_YES='':
    @uv run --locked just-dev confluence publish-release-notes
