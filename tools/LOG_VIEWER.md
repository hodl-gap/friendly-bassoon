# Pipeline Log Viewer

Converts `run_*.log` stdout into a navigable HTML trace.

## Usage

```bash
python tools/log_viewer.py logs/run_20260220_020944.log
```

Output: `logs/run_20260220_020944.html` (self-contained, open in any browser).

Custom output path: `python tools/log_viewer.py <log> -o output.html`

## Navigation

| Action | Button | Key |
|--------|--------|-----|
| Prev/next visit | `◀ Visit` / `Visit ▶` | `h`/`l` or `←`/`→` |
| Prev/next step | `▲ Step` / `▼ Step` | `k`/`j` or `↑`/`↓` |
| Prev/next key step | `◀ Key` / `Key ▶` | `p`/`n` |
| Deselect step | | `Esc` |

**Key only** checkbox filters to important steps (decisions, totals, gaps).

## Layout

- **Left panel top**: Pipeline flowchart — active node glows, visited nodes dim
- **Left panel bottom**: Execution flow — visit-by-visit timeline showing the actual order the pipeline traversed nodes
- **Right panel**: Steps for the current visit only

## Requirements

Python 3.10+ (stdlib only, no pip dependencies).
