# Evolution Engine Phase 0 Eval Guide

## Quick Start

1. Build dataset:

```bash
python3 evolution_cli.py build-dataset --skill-path /root/.openclaw/workspace/skills/weather/SKILL.md
```

2. Run baseline:

```bash
python3 evolution_cli.py eval-baseline --skill-path /root/.openclaw/workspace/skills/weather/SKILL.md
```

3. Evaluate variant:

```bash
python3 evolution_cli.py eval-variant \
  --skill-path /root/.openclaw/workspace/skills/weather/SKILL.md \
  --variant-path /root/.openclaw/workspace/evolution/staging/H001/SKILL.md
```

4. Compare two runs:

```bash
python3 evolution_cli.py eval-compare --run-a <run_a.json> --run-b <run_b.json>
```

5. Query trace stats:

```bash
python3 evolution_cli.py skill-stats --skill-name weather
```

## Notes

- Default judge mode is `auto` (fallback to `rule` without API key).
- Phase 0 does not call any external LLM API.
- Eval artifacts are under `evolution/eval/`.
