"""Generate synthetic daily sales data for offline development and demo.

The output is shaped identically to the unified schema the data loader emits
(`date, store_ref, product_ref, quantity_sold`) so the rest of the pipeline
doesn't need to know it came from a generator rather than Kaggle.

We deliberately model a few real-world signals so the resulting LightGBM model
has something meaningful to learn:

- Per-(store, product) baseline ranging 5–80 units/day
- Strong weekly seasonality (weekends ~1.4×, mid-week ~0.85×)
- Annual seasonality (mild summer dip, December holiday spike)
- Holiday bumps on a handful of fixed Western/Ethiopian holidays
- Gaussian noise (~10% of baseline)

Usage:
    python -m scripts.generate_synthetic_sales
    python -m scripts.generate_synthetic_sales --days 730 --stores 5 --products 10 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

# Anchor synthetic dataset 2 years back from today by default so the most
# recent rows align with the live calendar (useful for backtesting demos).
DEFAULT_END = date.today()
DEFAULT_START = DEFAULT_END - timedelta(days=730)

# Fixed multi-year holiday set (Western + Ethiopian).
FIXED_HOLIDAYS: set[tuple[int, int]] = {
    (1, 1),    # New Year
    (1, 7),    # Ethiopian Christmas
    (1, 19),   # Ethiopian Epiphany (Timkat)
    (3, 2),    # Adwa Victory
    (5, 1),    # Labour Day
    (5, 5),    # Patriots' Victory
    (5, 28),   # Derg Downfall
    (9, 11),   # Ethiopian New Year (Enkutatash)
    (9, 27),   # Meskel
    (12, 25),  # Christmas
}


def _is_holiday(d: date) -> bool:
    return (d.month, d.day) in FIXED_HOLIDAYS


def _weekly_multiplier(weekday: int) -> float:
    """Sat/Sun = 1.4, Fri = 1.15, Mon–Thu = 0.85–0.95."""
    return [0.88, 0.85, 0.90, 0.95, 1.15, 1.40, 1.45][weekday]


def _annual_multiplier(d: date) -> float:
    """Smooth annual cycle: peaks around Dec, dips around Feb/Jul."""
    day_of_year = d.timetuple().tm_yday
    return 1.0 + 0.18 * math.sin(2 * math.pi * (day_of_year - 80) / 365)


def generate(
    output_path: Path,
    *,
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    n_stores: int = 5,
    n_products: int = 10,
    seed: int = 42,
) -> int:
    """Writes synthetic sales rows to `output_path` and returns row count."""
    rng = random.Random(seed)

    baselines: dict[tuple[int, int], float] = {
        (s, p): rng.uniform(5.0, 80.0)
        for s in range(1, n_stores + 1)
        for p in range(1, n_products + 1)
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "store_ref", "product_ref", "quantity_sold"])

        current = start
        while current <= end:
            weekly = _weekly_multiplier(current.weekday())
            annual = _annual_multiplier(current)
            holiday_bump = 1.6 if _is_holiday(current) else 1.0

            for (store, product), base in baselines.items():
                noise = rng.gauss(1.0, 0.1)  # ~10% gaussian noise
                qty = max(0, round(base * weekly * annual * holiday_bump * noise))
                writer.writerow([current.isoformat(), f"S{store}", f"P{product}", qty])
                rows_written += 1

            current += timedelta(days=1)

    return rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic bakery sales data.")
    parser.add_argument("--output", type=Path, default=Path("data/synthetic/sales.csv"))
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--stores", type=int, default=5)
    parser.add_argument("--products", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = generate(
        args.output,
        start=args.start,
        end=args.end,
        n_stores=args.stores,
        n_products=args.products,
        seed=args.seed,
    )
    print(f"Wrote {rows} rows to {args.output}")


if __name__ == "__main__":
    main()
