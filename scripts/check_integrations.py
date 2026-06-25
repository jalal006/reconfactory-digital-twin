"""Print detected optional integration status."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations import check_integrations


def main() -> None:
    print(json.dumps(check_integrations(), indent=2))


if __name__ == "__main__":
    main()
