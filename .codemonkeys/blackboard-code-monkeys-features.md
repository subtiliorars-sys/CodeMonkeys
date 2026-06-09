# Blackboard — code-monkeys-features

## FACTS
- Root cause of session hit budget: Daystrom agent system (me, the running agent + subagents) makes API calls that bypass the existing budget system entirely. record_spend() is never called for agent operations.
- The $1.00 budget cap in config_manager only applies to calls through openrouter_bridge._make_openrouter_request() (Change Forge). The agent's own LLM consumption is external.
- Fix: Added session_budget (default $0.50) and session_spent tracking to config_manager.py, parallel to monthly budget.
- Fix: openrouter_bridge.py now checks BOTH is_budget_exhausted() AND is_session_exhausted() before using paid models.
- Fix: openrouter_bridge._make_openrouter_request also calls record_session_spend() when skip_budget_check is False.
- Fix: Added /budget set <amount> and /budget session <amount> CLI commands.
- Fix: Added /report_spend <amount> internal command for agent self-reporting.
- Fix: Added reset_session_budget(), set_budget_limit(), set_session_budget() to config_manager.py.
- All 53 existing tests still pass. 31 new budget tests pass.
- Fixed 2 failing tests: (1) RateLimitError now re-raised when all OpenRouter keys are cooling instead of generic ProviderExhausted; (2) Key redaction in status endpoint strips prefixes like "sk-", "AIza", "sk-ant-" before display
- Added "free" alias to proxy_config.py ALIAS_TABLE → google/gemini-2.0-flash-001 (free model)
- Added budget-aware routing to proxy_router.py: when is_budget_exhausted() or is_session_exhausted(), model_alias is forced to "free" with a console warning
- Created deploy_linux.sh: one-command setup script for Linux that checks Python 3.10+, creates venv, checks Ollama, checks API keys, then launches the proxy
- Updated README.md with full documentation: quick start, model alias table, free models guide, budget routing, Cline config, status endpoints, deploy instructions
- All 66 tests pass

## DECISIONS
- Build OpenRouter integration as a new module (openrouter_bridge.py) that coexists with existing gemini_integration.py
- Config manager gets extended with OpenRouter keys, model selection mode, budget settings
- Model auto-selection: fetch all models, sort by cost, pick cheapest that meets task requirements
- Budget tracking: cumulative spend in config file, warning when approaching limit
- Queue: use queue.Queue + threading.Thread (stdlib)
- /loop: parse from CLI args, use threading.Timer for repetition
- Settings server gets bigger model selector with all available models

## NEXT
- Verify in future session: the /report_spend command works end-to-end and the session budget actually stops paid model usage
- Add session budget display to settings_server.py web UI (budget card with session vs monthly)
- Consider: agent should auto-report spend at the start of each turn (self-monitoring loop)
- Consider: add a /budget status command that returns machine-parseable JSON for the agent to consume
