import 'common.just'

# YES is never exported: consent must be a real --yes argument on the just-dev command
# line (F6, principle 23), so it is translated back into one via conditional interpolation
# in the recipe body below.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_BUILD_PARAMETER', long='parameter')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
[doc('Queue a Jenkins build from a named preset.')]
run-build $JUST_DEV_BUILD_PRESET='' $JUST_DEV_BUILD_PARAMETER='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev jenkins run-build {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
show-build-status $JUST_DEV_BUILD_PRESET='' $JUST_DEV_BUILD_REFERENCE='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev jenkins show-build-status {{ if HELP == '1' { '--help' } else { '' } }}
