# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What We're Building

Room 4's hackathon submission for the APAC Claude Code Workshop. We're extending the [inventory-management](https://github.com/beck-source/inventory-management) starter app — a FastAPI backend with in-memory mock data representing a factory inventory system.

**Our focus:** [replace with your team's chosen problem / feature area]

## Running the Stack

```bash
# Backend (from inventory-management/server/)
cd ../inventory-management/server
uv run python main.py          # http://localhost:8001
                               # API docs: http://localhost:8001/docs

# Tests
uv run pytest                  # all tests
uv run pytest tests/ -v -k "inventory"   # filter by name
```

## Backend Architecture

Single-file FastAPI app (`main.py`) backed by in-memory mock data — no database, restarts reset state.

```
inventory-management/server/
├── main.py          ← all routes; import point for the whole app
├── mock_data.py     ← in-memory lists loaded from data/ at startup
├── models_api.py    ← Pydantic models for request/response validation
└── data/            ← JSON source files (edit here to change seed data)
```

**Existing API surface:**

| Group | Endpoints |
|-------|-----------|
| Inventory | `GET /api/inventory`, `GET /api/inventory/{id}` |
| Orders | `GET /api/orders`, `GET /api/orders/{id}` |
| Backlog | `GET /api/backlog` |
| Demand | `GET /api/demand` |
| Spending | `GET /api/spending/{summary,monthly,categories,transactions}` |
| Reports | `GET /api/reports/{quarterly,monthly-trends}` |
| Dashboard | `GET /api/dashboard/summary` |

**Filtering convention:** query params `warehouse`, `category`, `status`, `month` (or quarter e.g. `Q1-2025`). Value `all` skips that filter. Use the existing `apply_filters()` and `filter_by_month()` helpers.

**Adding an endpoint:**
1. Define a Pydantic model in `models_api.py`
2. Add the route in `main.py`
3. Re-use `apply_filters()` / `filter_by_month()` for consistency

## Claude API / Bedrock

```python
from anthropic import AnthropicBedrock
client = AnthropicBedrock(aws_region="us-west-2", aws_profile="bootcamp")
# model: "us.anthropic.claude-haiku-4-5-20251001-v1:0"
```

AWS login if token expired: `aws login --profile bootcamp`

See `../testclaude.py` for the full agent-loop pattern (tool use, `ToolUseBlock` handling, token tracking).

## Our Conventions

- All new endpoints must have a Pydantic `response_model`
- Filter on copies — never mutate the global mock-data lists
- New tools added to Claude must have a corresponding entry in `TOOL_REGISTRY`
- [Add any other conventions your team decides on]

## Submission Checklist

- [ ] `README.md` — problem, solution, Claude Code usage, what's next
- [ ] `presentation.html` — self-contained slide (inline CSS/JS, no external deps)
- [ ] `CLAUDE.md` — this file, kept up to date as we build
- [ ] PR open to `apac-cc-workshop-acn/hackathon/submissions/room4_<name>/` before 15:15 SGT
