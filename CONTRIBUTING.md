# Contributing

## Setup

```bash
python -m venv .venv
```

Activate the environment using the command for your operating system, then:

```bash
python -m pip install -r requirements.txt
```

## Before Submitting

```bash
python -m ruff format .
python -m ruff check .
python -m pytest
```

Keep changes focused, update tests for behavior changes, and update the README
or technical documentation when commands or integration behavior changes.

## Pull Requests

Include:

- A concise explanation of the change
- The affected factory workflow or integration
- Test results
- Screenshots only when browser or Gazebo visuals changed
