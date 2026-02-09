# Development Workflow

This document outlines our standard development workflow for the Job Hunter Agent project.

## Daily Development Cycle

### 1. Feature Development
- Write code in feature files (e.g., `src/cli.py`, `src/user_profile.py`)
- Create corresponding test files in `tests/` directory with `test_` prefix
- Run tests locally: `python -m pytest tests/ -v`
- Ensure all tests pass before moving to next phase

### 2. Pre-Commit Quality Checks
All code automatically goes through pre-commit hooks before committing:
- **Black**: Auto-formats Python code for consistency
- **isort**: Organizes imports alphabetically and by category
- **Flake8**: Checks for PEP 8 violations and common errors
- **Mypy**: Performs static type checking
- **Fix End of Files**: Ensures proper file endings
- **Trim Trailing Whitespace**: Cleans up whitespace

**Important**: Pre-commit hooks will automatically modify files. After running `git commit`:
1. If hooks fail or modify files, they'll show the changes
2. Stage the modified files again: `git add <modified-files>`
3. Re-run the commit

### 3. Common Linting Issues & Fixes

**Line Too Long (E501)**
- Flake8 enforces max 88 characters per line
- Split long lines into multiple lines with proper indentation
- Example: Break function arguments or long f-strings across lines

**Unused Imports (F401, F811)**
- Remove imports that are declared but never used
- Tools like Pylance can help identify these

**Missing Type Annotations (var-annotated)**
- Mypy requires type hints for certain variables
- Example: `result: List[str] = []` instead of `result = []`

**F-String Missing Placeholders (F541)**
- Don't use f-string prefix if there are no `{}` placeholders
- Example: `"[green]Success[/green]"` not `f"[green]Success[/green]"`

**Ambiguous Variable Names (E741)**
- Avoid single-letter variables like `l` (looks like `1`), `O`, `I`
- Use descriptive names: `location`, `result`, etc.

### 4. Committing Code

```bash
# Stage all changes
git add <file1> <file2> ...

# Commit with descriptive message
git commit -m "Feature: Brief description

- Detailed point 1
- Detailed point 2
- Test coverage: X/Y passing

co-authored by GitHub Copilot"

# Pre-commit hooks run automatically
# If they modify files or fail, you'll see output
# Stage modified files and re-commit if needed

# Once successful, push to GitHub
git push origin master
```

### 5. Testing Standards

- **Test Coverage**: Aim for comprehensive test coverage
- **Test Organization**: Group related tests and use fixtures
- **Naming**: Use `test_<function>` convention
- **Assertions**: Include clear assertion messages

Example test structure:
```python
@pytest.fixture
def sample_data():
    """Setup fixture with sample data."""
    return {"key": "value"}

def test_feature_success(sample_data):
    """Test successful feature execution."""
    result = function(sample_data)
    assert result is not None
    assert "expected" in result
```

### 6. Terminal Auto-Approval

To run pytest autonomously without prompt approval, pytest commands are configured in `.vscode/settings.json`:

```json
"/^python -m pytest\\b/": true
```

This allows any pytest invocation to run without approval:
- `python -m pytest tests/`
- `python -m pytest tests/ -v`
- `python -m pytest tests/test_file.py::test_function`
- etc.

## End-of-Day Checklist

Before committing and pushing:
- [ ] All tests pass: `python -m pytest tests/ -v`
- [ ] Code quality checks pass: `pre-commit run --all-files`
- [ ] No unused imports or variables
- [ ] Type hints added where needed
- [ ] Documentation/docstrings updated
- [ ] Commit message is descriptive
- [ ] Changes pushed to GitHub: `git push origin master`

## Project Structure

```
jobhunter-agent/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Click CLI commands
│   ├── cv_parser.py        # CV file parsing
│   ├── database.py         # Database initialization
│   ├── models.py           # SQLAlchemy models
│   └── user_profile.py     # User profile management
├── tests/
│   ├── test_cli.py         # CLI tests
│   ├── test_cv_parser.py   # CV parser tests
│   ├── test_database.py    # Database tests
│   └── test_user_profile.py # Profile tests
├── job-agent               # CLI entry point
├── PROJECT_PLAN.md         # 7-day development plan
└── WORKFLOW.md            # This file
```

## Key Tools & Configuration

- **Python Version**: 3.10+
- **Test Framework**: pytest
- **Code Quality**: pre-commit hooks (black, isort, flake8, mypy)
- **CLI Framework**: Click
- **Terminal UI**: Rich
- **Database**: SQLAlchemy + SQLite
- **Type Checking**: Mypy

### Using pip in the virtual environment (SOP)

Always install or update Python packages using the project's virtual environment to ensure tooling (pre-commit, mypy, tests) run consistently.

Preferred commands:

After activating the venv:
```bash
source .venv/bin activate && python -m pip install -r requirements.txt
```

Or explicitly using the venv Python:
```bash
.venv/bin/python -m pip install -r requirements.txt
```

When installing single packages (for example, type stubs for mypy):
```bash
.venv/bin/python -m pip install types-requests
```

Note: pre-commit hooks run their own isolated environments; if mypy reports missing type stub packages during pre-commit, prefer adding `ignore_missing_imports = true` to `[tool.mypy]` in `pyproject.toml` or install the required type stubs into the project's venv as above.

## Day-by-Day Summary

- **Day 1**: CV parsing & database models ✅
- **Day 2**: User profile management & CLI interface ✅
- **Day 3**: Job scrapers (GitHub Jobs, Microsoft careers)
- **Day 4**: More job scrapers + job matching algorithm
- **Day 5**: Complete remaining scrapers
- **Day 6**: Application tracking & workflow
- **Day 7**: Polish & documentation
