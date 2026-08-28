import 'common.just'

# YES (unlike other flags here) is never exported: consent must be a real --yes argument
# on the just-dev command line (F6, principle 23), so it is translated back into one via
# conditional interpolation in each mutation's recipe body below.
[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PR_DESCRIPTION', long='description')]
[arg('JUST_DEV_PR_REVIEWER', long='reviewer')]
[arg('JUST_DEV_PR_CLOSE_SOURCE_BRANCH', long='close-source-branch', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_NO_VERIFY', long='no-verify', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
[doc('Create a new Bitbucket pull request from the current branch.')]
create-pull-request $JUST_DEV_PR_TITLE='' $JUST_DEV_PR_DESCRIPTION='' $JUST_DEV_PR_REVIEWER='' $JUST_DEV_PR_CLOSE_SOURCE_BRANCH='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_NO_VERIFY='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket create-pull-request {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
show-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='':
    @uv run --locked just-dev bitbucket show-pull-request

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
approve-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket approve-pull-request {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
decline-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket decline-pull-request {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
comment-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_PR_COMMENT='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket comment-pull-request {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
add-pull-request-reviewer $JUST_DEV_PR_ID='' $JUST_DEV_PR_REVIEWER_NAME='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket add-pull-request-reviewer {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}

[working-directory(devtools_root)]
[env('JUST_DEV_PROJECT_ROOT', project_root)]
[arg('JUST_DEV_PR_MESSAGE', long='message')]
[arg('JUST_DEV_PR_MERGE_STRATEGY', long='merge-strategy')]
[arg('JUST_DEV_PR_CLOSE_SOURCE_BRANCH', long='close-source-branch', value='1')]
[arg('JUST_DEV_DRY_RUN', long='dry-run', value='1')]
[arg('YES', long='yes', value='1')]
[arg('JUST_DEV_PROFILE', long='profile', help='Local auth profile.')]
[arg('JUST_DEV_FORMAT', long='format')]
[arg('JUST_DEV_SAFE', long='safe', value='1')]
[arg('HELP', long='help', value='1', help='Show command help and exit.')]
merge-pull-request $JUST_DEV_PR_ID='' $JUST_DEV_PR_MESSAGE='' $JUST_DEV_PR_MERGE_STRATEGY='' $JUST_DEV_PR_CLOSE_SOURCE_BRANCH='' $JUST_DEV_DRY_RUN='' YES='' $JUST_DEV_PROFILE='' $JUST_DEV_FORMAT='' $JUST_DEV_SAFE='' HELP='':
    @uv run --locked just-dev bitbucket merge-pull-request {{ if YES == '1' { '--yes' } else { '' } }} {{ if HELP == '1' { '--help' } else { '' } }}
