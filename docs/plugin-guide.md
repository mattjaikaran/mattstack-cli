# mattstack plugin guide

Write custom audit rules by dropping Python files into `mattstack-plugins/` in your project root.

## Quick start

1. Create `mattstack-plugins/` in your project root
2. Add a `.py` file with a `BaseAuditor` subclass
3. Run `mattstack audit` -- your plugin runs automatically

## Write an auditor

This example flags literal `api_key` assignments in Python source. It is a
project rule, not a complete secret scanner. It does not find runtime values,
multiline assignments, or credentials with other names.

```python
"""Flag literal API keys in project Python source."""
import re

from mattstack.auditors.base import AuditFinding, AuditType, BaseAuditor, Severity


class ApiKeyAuditor(BaseAuditor):
    audit_type = AuditType.QUALITY
    assignment = re.compile(r"\bapi_key\s*=\s*['\"][^'\"]+['\"]")

    def run(self) -> list[AuditFinding]:
        excluded = {".git", ".venv", "node_modules", "mattstack-plugins"}
        for source in self.config.project_path.rglob("*.py"):
            if excluded.intersection(source.parts):
                continue
            for number, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
                if self.assignment.search(line):
                    self.add_finding(
                        Severity.WARNING,
                        self._rel(source),
                        number,
                        "Review a literal API key assignment",
                        "Read real credentials from the environment",
                    )
        return self.findings
```

Return `AuditFinding` objects through `self.add_finding()`. Keep the path and
line number so callers can locate the finding. Do not print credential values.

## Optional plugin metadata

Add a `PLUGIN_META` dict for richer display:

```python
PLUGIN_META = {
    "name": "API Key Scanner",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "Scans for hardcoded API keys and secrets",
}
```

## Audit categories

| Value | Description |
|-------|-------------|
| `AuditType.TYPES` | Type safety checks |
| `AuditType.QUALITY` | Code quality |
| `AuditType.ENDPOINTS` | Route/endpoint analysis |
| `AuditType.TESTS` | Test coverage |
| `AuditType.DEPENDENCIES` | Dependency checks |
| `AuditType.VULNERABILITIES` | Security vulnerabilities |

## Severity levels

| Level | Meaning |
|-------|-------------|
| `Severity.ERROR` | The rule identifies an error |
| `Severity.WARNING` | Review the finding before you proceed |
| `Severity.INFO` | Read the information or recommendation |

## Tips

- Use `self._rel(path)` to convert absolute paths to relative
- Use `self.add_finding()` instead of appending to `self.findings` directly
- Keep plugins focused -- one concern per plugin
- Plugins are sorted alphabetically by filename
- Files starting with `_` are skipped

## Trust and failure behavior

Install only trusted plugins. The loader imports each file as Python code, so
module-level code runs with the CLI's permissions. Keep one auditor subclass
per file; the loader selects the first subclass it finds.

If an import fails, the loader prints a warning and skips that plugin. Review
those warnings: an unloaded auditor does not prove that its rule passed.

Use `mattstack audit --no-todo` to leave the task file unchanged. See the
[audit command reference](commands.md#audit) for output and failure behavior.
