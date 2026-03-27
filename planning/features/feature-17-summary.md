# Feature 17: MCP Stdio Server — Bitcoin Treasury Tools

**Status**: In Progress
**Branch**: `feature/mcp-stdio-server`
**Stories**: MCP-001 through MCP-004 (4 stories, ~500 lines)

## Summary

Exposes the Bitcoin Accounting data layer as a read-only MCP stdio server
so AI clients (primarily Claude Desktop) can query treasury details,
capital gains, tax summaries, and integrity health directly. Primary use
case: financial planning, mid-year tax optimization, and 1099-B generation
awareness via Claude Desktop as a life-coach / financial advisor.

### Goals
- Enable Claude Desktop to answer "what's my tax exposure this year?" and
  "which lots should I sell for best tax treatment?" using live ledger data
- Expose 10 focused read-only tools — zero write operations via MCP
- Add `bitcoin-mcp` CLI entry point alongside existing `bitcoin-accounting`
  and `bitcoin-integrity` commands

## File Structure

```
src/python/
└── mcp_server.py           NEW — FastMCP server, 10 tools, main()

tests/
└── test_mcp_server.py      NEW — unit + integration tests

pyproject.toml              MODIFIED — mcp dep, bitcoin-mcp script
```

## Tool Groups

| Group | Tools | Primary Value |
|-------|-------|---------------|
| Financial Snapshot | get_treasury_summary, get_wallet_balances, get_transactions | Portfolio awareness |
| **Tax & Capital Gains** | **get_purchase_lots, forecast_capital_gains, get_tax_summary** | **Financial planning** |
| Integrity & Attestation | get_treasury_health, get_unresolved_findings, run_integrity_check_tool, get_attestation_bundle | Audit & monitoring |

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Write ops** | None exposed | AI advises, human executes in TUI |
| **DB lifecycle** | Open/close per tool call | Matches CLI pattern; avoids async/sync contention |
| **Tax year** | Current year supported | YTD gains is the core mid-year planning use case |
| **Lot unrealized P&L** | Computed at call time via price_lookup | Foundation for tax-optimal lot selection advice |

## Story Breakdown

| ID | Title | Lines | Key Deliverable |
|----|-------|-------|-----------------|
| MCP-001 | Server scaffold | +80 | FastMCP server starts, bitcoin-mcp entry point works |
| MCP-002 | Financial snapshot tools | +120 | 3 portfolio tools |
| MCP-003 | Tax & capital gains tools | +140 | 3 tax planning tools |
| MCP-004 | Integrity & attestation tools | +160 | 4 audit tools |

## Verification

```bash
# Install
pip install -e .

# Confirm FastMCP import works
python -c "from mcp.server.fastmcp import FastMCP; print('OK')"

# Run tests
python -m pytest tests/test_mcp_server.py -v

# Manual smoke test (stdio mode)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | bitcoin-mcp
```

## Risk Areas

**High:** FastMCP import path must be verified against installed mcp version before writing tool code.

**Medium:** `get_purchase_lots` unrealized P&L requires a current price — must handle missing price gracefully. `get_attestation_bundle` runs all 4 integrity checks and can be slow.

- PRD: [feature-17-prd.json](feature-17-prd.json)
