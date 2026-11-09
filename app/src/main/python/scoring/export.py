"""Export a visual game's JSONL history to CSV and optionally a PNG plot."""

import argparse
import csv
import json
from pathlib import Path
import sys

from client_server.util import strip_type_field
from core.game_state import GameParams, GameState
from .evaluators import Comparison


def read_history(path: Path):
    records = []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index == len(lines) - 1 and not line.endswith("\n"):
                print("Ignoring an incomplete final log record", file=sys.stderr)
            else:
                raise
    return records


def export_rows(records, *, rescore_missing=False, config=None):
    start = next(r for r in records if r["event"] == "game_start")
    game_id = start["gameId"]
    if any(r.get("gameId") != game_id for r in records):
        raise ValueError("A history file must describe one game")
    metadata = next((r["metadata"] for r in records if r["event"] == "metadata"), None)
    scored = {r["tick"]: r for r in records if r["event"] == "scores"}
    if metadata and any(r["configHash"] != metadata["configHash"] for r in scored.values()):
        raise ValueError("History mixes different heuristic configurations")
    comparison = None
    if rescore_missing:
        if metadata:
            comparison = Comparison(metadata["config"], restore=True)
            if config is not None and Comparison.load(config).metadata["configHash"] != metadata["configHash"]:
                raise ValueError("Explicit config differs from the recorded configuration")
        elif config is not None:
            comparison = Comparison.load(config)
            metadata = comparison.metadata
        else:
            raise ValueError("No recorded evaluator config; supply --config when rescoring")
    ticks = {}
    for record in records:
        if record["event"] == "tick":
            if record["tick"] in ticks:
                raise ValueError("Duplicate tick record")
            ticks[record["tick"]] = record
    rows = []
    for tick, record in sorted(ticks.items()):
        result = scored.get(tick)
        status = "recorded" if result else "missing"
        if result is None and comparison is not None:
            result = comparison.score(GameState.model_validate(strip_type_field(record["state"])),
                                      GameParams.model_validate(strip_type_field(start["params"])))
            status = "rescored"
        row = {"game_id": game_id, "tick": tick,
               "heuristic_A": metadata["evaluators"]["A"]["id"] if metadata else "unknown",
               "heuristic_B": metadata["evaluators"]["B"]["id"] if metadata else "unknown"}
        for player, color in (("Player1", "red"), ("Player2", "blue")):
            for key, suffix in (("planetCount", "planets"), ("stationedShips", "stationed_ships"),
                                ("shipsInFlight", "ships_in_flight"), ("totalShips", "total_ships")):
                row[f"{color}_{suffix}"] = record["stats"][player][key]
            for slot in ("A", "B"):
                row[f"{color}_{slot}"] = result["scores"][player][slot] if result else None
        row["score_status"] = status
        rows.append(row)
    return rows, metadata


def write_csv(rows, path: Path):
    if not rows:
        raise ValueError("History has no board snapshots")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_rows(rows, metadata, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5))
    for color in ("red", "blue"):
        for slot, style in (("A", "-"), ("B", "--")):
            label = metadata["evaluators"][slot]["label"] if metadata else slot
            ax.plot([r["tick"] for r in rows], [r[f"{color}_{slot}"] for r in rows],
                    color=color, linestyle=style, label=f"{color.title()} · {slot}: {label}")
    ax.set(xlabel="Game tick", ylabel="Heuristic score", ylim=(-0.02, 1.02),
           title="Heuristic comparison over the game")
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--plot", type=Path)
    parser.add_argument("--rescore-missing", action="store_true")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    rows, metadata = export_rows(read_history(args.history),
                                rescore_missing=args.rescore_missing, config=args.config)
    output = args.csv or args.history.with_suffix(".csv")
    write_csv(rows, output)
    print(f"Wrote {len(rows)} ticks to {output}")
    if args.plot:
        plot_rows(rows, metadata, args.plot)
        print(f"Wrote plot to {args.plot}")


if __name__ == "__main__":
    main()
