import 'common.just'

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_CONFLUENCE_PRESET', long='preset')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
preview-release-notes $JUST_DEV_RELEASE_NOTES_FILE='' $JUST_DEV_CONFLUENCE_PRESET='release-notes' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev confluence preview-release-notes {{ if HELP == '1' { '--help' } else { '' } }}

# YES is never exported: consent must be a real --yes argument on the just-dev command
# line (F6, principle 23), so it is translated back into one via conditional interpolation
# in the recipe body below.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_CONFLUENCE_PRESET', long='preset')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
[doc('Publish a markdown file as Confluence release notes.')]
publish-release-notes $JUST_DEV_RELEASE_NOTES_FILE='' $JUST_DEV_CONFLUENCE_PRESET='release-notes' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev confluence publish-release-notes {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}
