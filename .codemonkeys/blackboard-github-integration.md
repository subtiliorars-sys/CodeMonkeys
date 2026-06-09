# Blackboard — github-integration

## FACTS
- GitHub bridge module (github_bridge.py, 833 lines) complete: token validation, API wrappers, repo ops, local git ops, token storage, push_current_branch convenience wrapper
- CLI commands (cmd_github in codemonkeys_cli.py) complete: login, status, push, pull, repos, token list/add/remove, commit, branch, remote
- Settings server (settings_server.py) has full GitHub UI card with: save/test/list/clear token buttons, connection status indicator, repo list display
- Settings server API handlers: GET /api/github/status, GET /api/github/repos, POST /api/github/token, DELETE /api/github/token, POST /api/github/test
- 40 unit tests for github_bridge.py, all passing. 159 total tests pass.
- Remote origin: https://github.com/subtiliorars-sys/CodeMonkeys.git

## DECISIONS
_(none yet)_

## NEXT
_(none yet)_
