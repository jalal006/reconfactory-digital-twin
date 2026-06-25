"""Add sample products through the supervisor for local simulation checks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reconfactory import FactorySupervisor


def main() -> None:
    factory = FactorySupervisor(enable_database=False)
    factory.start()
    for product_type in ["red_block", "blue_cylinder", "green_component", "red_block"]:
        factory.create_product(product_type)
    factory.run_until_idle()
    print(factory.snapshot()["stats"])


if __name__ == "__main__":
    main()
