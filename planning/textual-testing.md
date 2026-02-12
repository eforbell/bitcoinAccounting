# Claude Code + Textual TUI Automation: State of the Art

## Core Constraint
Claude Code can launch your Textual app but cannot natively interact with a running TUI or observe its visual state — TUIs write raw ANSI escape sequences to a PTY with no external accessibility tree.

## Recommended Approach: Textual Pilot API

Textual ships a headless `Pilot` testing interface. This is the primary mechanism for autonomous app driving.

```python
from textual.testing import Pilot

async def test_flow():
    async with MyApp().run_test() as pilot:
        await pilot.press("tab", "enter")
        await pilot.click("#my-button")
        await pilot.app.save_screenshot("state.svg")
        assert pilot.app.query_one("#status").value == "expected"
```

Pilot supports: keypresses, clicks, focus management, widget tree assertions, and SVG screenshots.

## Agentic Testing Loop

1. Write `pytest`-based `Pilot` tests covering key user flows and suspected problem areas
2. Run tests — failures are structured and parseable by the agent
3. Call `save_screenshot()` at failure points for visual context
4. Fix → re-run → iterate

## What to Avoid
- `pyte` / `pexpect` terminal scraping — fragile escape sequence hell, unnecessary given Pilot
- tmux + screen capture → vision API — possible but requires custom scaffolding, not worth it
- Expecting Claude Code to drive a live PTY — not a native capability

## Workflow Shift
Instead of manual testing → screenshot → defect ticket, prefer:

> Describe the defect scenario → agent writes a failing Pilot test → agent fixes code until test passes

## Reference
Textual testing docs: https://textual.textualize.io/guide/testing/