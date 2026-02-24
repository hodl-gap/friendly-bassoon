---
description: Move obsolete files to archive/ folder (never deletes, never touches parent folder)
allowed-tools: [Read, Glob, Grep, Bash, Task, Edit]
---

# Project Cleanup — Move Obsolete Files to Archive

## CRITICAL SAFETY RULES

- **SCOPE**: ONLY operate within the current project folder. NEVER NEVER NEVER touch the parent folder or any folder outside the project root.
- **MOVE ONLY**: NEVER delete files. Always MOVE obsolete files to the `archive/` folder using `mv`.
- **NO REFACTORING**: Do NOT modify, refactor, or change any file contents. This is purely a file-organization task.
- **CONFIRM BEFORE ACTING**: Always present the full list of files you plan to move and your reasoning BEFORE moving anything. Wait for user approval.

## What "Obsolete" Means

Scan the project folder for files that are no longer needed in the active workspace:

1. **Resolved issue trackers** — Markdown files tracking issues/bugs/TODOs where all items have been addressed
2. **Redundant documentation** — Markdown files whose content is already captured elsewhere (e.g., in CLAUDE.md or another active doc)
3. **Stale descriptions** — Markdown files describing components, APIs, or workflows that no longer exist in the codebase
4. **Dead code files** — Python/code files that are not imported or referenced anywhere in the project
5. **Completed plans** — PLAN_*.md, STATUS_*.md, or similar files for work that has been finished
6. **Outdated configs** — Config or data files that are no longer referenced by any active code

## What is NOT Obsolete (Do NOT Move)

- `CLAUDE.md` — project instructions, always keep
- `archive/` — already archived, skip entirely
- `.claude/` — Claude Code config, never touch
- Active code files that are imported/used by other modules
- Requirements files, pyproject.toml, .env files, .gitignore
- Any file you're uncertain about — when in doubt, leave it

## Procedure

This command is fully self-contained — it does NOT require `/read` or any prior exploration. It performs its own analysis from scratch.

1. **Map** the full project directory tree (not parent) using Glob to understand the file layout
2. **Read CLAUDE.md and other relevant .md files** to understand the project structure, active subprojects, what's current, and what's already documented elsewhere
3. **Analyze** each candidate file:
   - For markdown: read it and check if its content is still relevant to the current project state
   - For code: use Grep to check if it's imported or called anywhere in the project
4. **Compile** a list of files to archive with a one-line reason for each
5. **Present** the list to the user and wait for approval
6. **Move** approved files to `archive/` using `mv` (create `archive/` if it doesn't exist)
7. **Report** a complete summary of every file moved, showing the original path and the new archive path:

```
Moved:
  path/to/file.md → archive/file.md
  path/to/old_script.py → archive/old_script.py
```

## Output Format

Present findings as:

```
Files to archive:
  - path/to/file.md → Reason: all issues resolved, content captured in CLAUDE.md
  - path/to/old_script.py → Reason: not imported anywhere, functionality replaced by new_module.py

Files kept (uncertain):
  - path/to/maybe_old.md → Reason: unclear if still referenced, keeping to be safe
```
