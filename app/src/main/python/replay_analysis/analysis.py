"""Write the compact replay-analysis artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

from core.game_replay import load_replay
from core.game_state import Player
from replay_analysis.dataset import Position


POSITION_FIELDS = (
    "position_id", "game_id", "tick", "player", "bot", "outcome",
    "static_value", "features", "search_value", "played_action",
    "played_action_value", "best_action", "best_action_value", "regret",
)
ROOT_ACTION_FIELDS = (
    "position_id", "game_id", "tick", "player", "action", "visits",
    "search_value", "heuristic_value", "heuristic_terms", "is_best", "is_played",
)
RELIABILITY_FIELDS = (
    "source", "bin", "lower", "upper", "count", "weight",
    "mean_prediction", "observed_result",
)
def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _tournament_games(replay_paths: Sequence[str | Path],
                      positions: Sequence[Position]) -> tuple[list[dict], dict]:
    sampled_counts: dict[str, int] = {}
    for position in positions:
        sampled_counts[position.game_id] = sampled_counts.get(position.game_id, 0) + 1
    games = []
    bot_results: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for path_value in replay_paths:
        path = Path(path_value).resolve()
        game_id = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
        if game_id in seen:
            continue
        seen.add(game_id)
        replay = load_replay(path)
        winner = replay["winner"]
        agents = replay.get("agents", {})
        games.append({
            "game_id": game_id,
            "replay_path": str(path),
            "replay_schema_version": replay["schemaVersion"],
            "params": replay["params"],
            "bots": agents,
            "winner": winner,
            "ticks": len(replay["ticks"]),
            "sampled_positions": sampled_counts.get(game_id, 0),
        })
        for player in (Player.Player1, Player.Player2):
            name = str(agents.get(player.value, player.value))
            result = bot_results.setdefault(name, {"games": 0, "wins": 0,
                                                   "losses": 0, "draws": 0})
            result["games"] += 1
            if winner == Player.Neutral.value:
                result["draws"] += 1
            elif winner == player.value:
                result["wins"] += 1
            else:
                result["losses"] += 1
    return games, bot_results


def write_analysis(output_dir: str | Path, positions: Sequence[Position],
                   search_rows: Sequence[dict], *, replay_paths: Sequence[str | Path],
                   calibrations: dict, metadata: dict,
                   make_plot: bool = True) -> None:
    """Write position/root tables, logistic reliability, optional graph, and metadata."""
    if make_plot:
        from replay_analysis.plot import plot_reliability

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    names = ("positions.csv", "root_actions.csv", "reliability.csv",
             "reliability.png", "tournament.json")
    existing = [name for name in names if (output / name).exists()]
    if existing:
        raise FileExistsError(f"Analysis output already exists in {output}: {', '.join(existing)}")
    by_position = {row["position_id"]: row for row in search_rows}
    position_rows = []
    root_rows = []
    for position in positions:
        search = by_position[position.position_id]
        played_action = position.played_action.model_dump(mode="json", by_alias=True)
        best_action = search["best_action"]
        position_rows.append({
            **position.row(),
            "search_value": search["search_value"],
            "played_action_value": search["played_action_value"],
            "best_action": ("unchanged" if best_action == played_action else
                            json.dumps(best_action, sort_keys=True) if best_action is not None else None),
            "best_action_value": search["best_action_value"],
            "regret": search["regret"],
        })
        for action in search["root_actions"]:
            root_rows.append({
                "position_id": position.position_id,
                "game_id": position.game_id,
                "tick": position.tick,
                "player": position.player.value,
                "action": json.dumps(action["action"], sort_keys=True),
                "visits": action["visits"],
                "search_value": action["search_value"],
                "heuristic_value": action["heuristic_value"],
                "heuristic_terms": json.dumps(action["heuristic_terms"], sort_keys=True),
                "is_best": action["is_best"],
                "is_played": action["is_played"],
            })
    reliability_rows = [
        {"source": source, **bin_row}
        for source, calibration in calibrations.items()
        for bin_row in calibration["bins"]
    ]
    games, bots = _tournament_games(replay_paths, positions)
    tournament = {
        "schema_version": 1,
        **metadata,
        "position_count": len(positions),
        "root_action_count": len(root_rows),
        "games": games,
        "bots": bots,
        "calibration": {
            source: {key: value for key, value in calibration.items() if key != "bins"}
            for source, calibration in calibrations.items()
        },
    }
    _write_csv(output / "positions.csv", POSITION_FIELDS, position_rows)
    _write_csv(output / "root_actions.csv", ROOT_ACTION_FIELDS, root_rows)
    _write_csv(output / "reliability.csv", RELIABILITY_FIELDS, reliability_rows)
    if make_plot:
        plot_reliability(output / "reliability.csv", output / "reliability.png",
                         depth=metadata.get("search", {}).get("depth_cap_ticks"),
                         bot=metadata.get("reliability", {}).get("bot"))
    (output / "tournament.json").write_text(
        json.dumps(tournament, indent=2, allow_nan=False) + "\n", encoding="utf-8")
