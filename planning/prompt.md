# Feature Iteration Agent Instructions

1. Read `planning/current-feature.json` to find active feature
2. Read the PRD at the path specified in `prdPath` (e.g., `planning/features/feature-2-prd.json`)
3. Read `planning/progress.txt` (check Codebase Patterns first)
4. Check you're on the correct branch (from `current-feature.json`)
   - If branch doesn't exist, create it from `main`
5. Pick highest priority story where `passes: false` or this field is missing
6. Implement that ONE story completely
7. Run typecheck (`mypy --strict`) and tests (`pytest`)
8. Update AGENTS.md with learnings
9. Commit: `feat: [ID] - [Title]`
10. Update PRD: set `passes: true` for completed story
11. Append learnings to progress.txt
12. Don't ever commit DB credentials or other sensitive private data to git

## Progress Format

APPEND to progress.txt:

```
## [Date] - [Story ID]
- What was implemented
- Files changed
- **Learnings:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Codebase Patterns

Add reusable patterns to the TOP 
of progress.txt:

```
## Codebase Patterns
- Pattern name: Description
```

## For python develpment, always prefer virtualenvs over the system python interpreter!

## File Structure

```
planning/
├── current-feature.json  # READ THIS FIRST - active feature config
├── prompt.md             # These instructions
├── progress.txt          # Development log (append here)
└── features/
    ├── feature-1-prd.json
    ├── feature-1-summary.md
    ├── feature-2-prd.json   
    └── feature-2-summary.md
```

## Stop Condition

If ALL stories in current feature pass, reply:
<promise>COMPLETE</promise>

Otherwise end normally after completing one story.