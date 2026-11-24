"""Plot logistic reliability from the saved bins without rerunning searches."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def plot_reliability(reliability_csv: str | Path, output_png: str | Path, *,
                     depth: int | None = None, bot: str | None = None) -> None:
    """Draw held-out observed results against mean predicted probabilities."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Reliability plots require matplotlib; install scoring/requirements-plot.txt"
        ) from exc

    with Path(reliability_csv).open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    series = (
        ("static", "Static logistic", "tab:blue"),
        ("search", f"Search logistic (depth cap {depth})" if depth is not None
         else "Search logistic", "tab:orange"),
    )
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    for source, label, color in series:
        points = sorted(
            ((float(row["mean_prediction"]), float(row["observed_result"]))
             for row in rows if row["source"] == source and row["mean_prediction"]),
            key=lambda point: point[0],
        )
        if points:
            ax.plot([point[0] for point in points], [point[1] for point in points],
                    marker="o", color=color, label=label)
    title = "Replay outcome calibration"
    if bot and bot != "all":
        title += f"\n{bot} positions"
    ax.set(xlabel="Predicted win probability", ylabel="Observed result",
           xlim=(0, 1), ylim=(0, 1), title=title)
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    fig.tight_layout()
    Path(output_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a reliability graph from reliability.csv.")
    parser.add_argument("--reliability", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int)
    parser.add_argument("--bot", help="Bot label to show in the graph title.")
    args = parser.parse_args()
    plot_reliability(args.reliability, args.output, depth=args.depth, bot=args.bot)


if __name__ == "__main__":
    main()
