"""Command-line entry point for the compact replay analysis."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import math
from pathlib import Path
import platform
import sys

from replay_analysis.analysis import write_analysis
from replay_analysis.dataset import collect_positions
from replay_analysis.heuristics import resolve_heuristic
from replay_analysis.metrics import calibrate_scores
from replay_analysis.search import search_positions
from search.mcts import TacticalActionGenerator, UnbiasedActionGenerator
from scoring.evaluators import code_revision


def _collect_replay_paths(inputs: list[str]) -> list[Path]:
    paths: set[Path] = set()
    for item in inputs:
        path = Path(item)
        if path.is_file() and path.suffix.lower() == ".json":
            paths.add(path.resolve())
        elif path.is_dir():
            paths.update(candidate.resolve() for candidate in path.rglob("*.json"))
        else:
            paths.update(Path(candidate).resolve() for candidate in glob.glob(item, recursive=True)
                         if Path(candidate).is_file() and Path(candidate).suffix.lower() == ".json")
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write positions, root actions, logistic reliability and graph, and tournament metadata.")
    parser.add_argument("--replays", nargs="+", required=True,
                        help="Replay JSON files, directories, or glob patterns.")
    parser.add_argument("--output", type=Path, required=True,
                        help="Base folder name; each run creates a timestamped sibling folder.")
    parser.add_argument("--tournament-name",
                        help="Name stored in tournament.json (defaults to the output directory name).")
    parser.add_argument("--heuristic", default="mcts_board_strength",
                        help="Built-in evaluator type or profile ID from --heuristic-config.")
    parser.add_argument("--heuristic-config", type=Path,
                        help="Evaluator profile YAML.")
    parser.add_argument("--stride", type=int, default=20,
                        help="Sample every Nth replay tick (default: 20).")
    parser.add_argument("--max-positions-per-game", type=int,
                        help="Maximum sampled ticks per replay; each tick yields two player positions.")
    parser.add_argument("--no-verify-replays", action="store_true",
                        help="Skip replay re-simulation and snapshot checks.")
    parser.add_argument("--no-plot", action="store_true",
                        help="Skip the reliability PNG (the CSV remains available).")
    parser.add_argument("--depth", type=int, default=8,
                        help="Single MCTS tree-depth cap in game ticks (default: 8).")
    parser.add_argument("--iterations", type=int, default=32,
                        help="MCTS simulations per sampled player position (default: 32).")
    parser.add_argument("--action-generator", choices=("tactical", "unbiased"),
                        default="tactical",
                        help="Root and tree action generator (default: tactical).")
    parser.add_argument("--rollout-depth", type=int, default=0,
                        help="Extra rollout ticks after the tree leaf (default: 0).")
    parser.add_argument("--exploration-constant", type=float, default=math.sqrt(2),
                        help="UCT exploration constant (default: sqrt(2)).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed for search and whole-game calibration split.")
    parser.add_argument("--test-fraction", type=float, default=0.25,
                        help="Fraction of games held out for reliability (default: 0.25).")
    parser.add_argument("--calibration-bot",
                        help="Exact bot name to calibrate; use 'all' only to pool policies.")
    parser.add_argument("--bins", type=int, default=10,
                        help="Number of reliability bins (default: 10).")
    return parser


def _new_output_dir(base: Path, started_at: datetime) -> Path:
    """Reserve a timestamped sibling without reusing an earlier run folder."""
    stamp = started_at.strftime("%Y-%m-%d_%H-%M-%SZ")
    for index in range(1000):
        suffix = stamp if index == 0 else f"{stamp}-{index:03d}"
        output = base.with_name(f"{base.name}-{suffix}")
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return output
    raise FileExistsError(f"Could not reserve a unique output folder for {base}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started_at = datetime.now(timezone.utc)
    if args.stride < 1 or args.depth < 1 or args.iterations < 1 or args.rollout_depth < 0:
        parser.error("stride, depth, and iterations must be positive; rollout-depth cannot be negative")
    if args.max_positions_per_game is not None and args.max_positions_per_game < 1:
        parser.error("max-positions-per-game must be positive")
    if not 0 < args.test_fraction < 1 or args.bins < 1:
        parser.error("test-fraction must be between 0 and 1; bins must be positive")
    if args.exploration_constant < 0 or not math.isfinite(args.exploration_constant):
        parser.error("exploration-constant must be finite and nonnegative")

    replay_paths = _collect_replay_paths(args.replays)
    if not replay_paths:
        parser.error("No replay JSON files matched --replays")
    evaluator, heuristic = resolve_heuristic(args.heuristic, args.heuristic_config)
    print(f"Loading {len(replay_paths)} replay(s)...", flush=True)
    positions = collect_positions(
        replay_paths, evaluator, stride=args.stride,
        verify_replays=not args.no_verify_replays,
        max_positions_per_game=args.max_positions_per_game)
    if not positions:
        parser.error("No positions selected")
    bot_names = sorted({position.bot for position in positions})
    if args.calibration_bot == "all":
        calibration_bot = None
    elif args.calibration_bot is None:
        if len(bot_names) != 1:
            parser.error("Multiple bots are present; choose --calibration-bot from: " +
                         ", ".join(bot_names) + "; or use 'all' to pool them")
        calibration_bot = bot_names[0]
    elif args.calibration_bot in bot_names:
        calibration_bot = args.calibration_bot
    else:
        parser.error("Unknown calibration bot; available: " + ", ".join(bot_names))
    calibration_positions = [position for position in positions
                             if calibration_bot is None or position.bot == calibration_bot]
    print(f"Searching {len(positions)} player positions at depth cap {args.depth}...", flush=True)

    def progress(done: int, total: int) -> None:
        if done % max(50, total // 20) == 0 or done == total:
            print(f"  searched {done}/{total}", flush=True)

    action_generator = (UnbiasedActionGenerator() if args.action_generator == "unbiased"
                        else TacticalActionGenerator())
    search_rows = search_positions(
        positions, evaluator, depth=args.depth, iterations=args.iterations,
        rollout_depth=args.rollout_depth,
        exploration_constant=args.exploration_constant, seed=args.seed,
        action_generator=action_generator,
        progress=progress)
    by_position = {row["position_id"]: row for row in search_rows}
    score_rows = [
        {"game_id": position.game_id, "outcome": position.outcome,
         "static_value": position.static_value,
         "search_value": by_position[position.position_id]["search_value"]}
        for position in calibration_positions
    ]
    search_scores = [row for row in score_rows if row["search_value"] is not None]
    if not search_scores:
        parser.error("Search produced no root values to calibrate")
    calibrations = {
        "static": calibrate_scores(score_rows, score_key="static_value",
                                   bins=args.bins, test_fraction=args.test_fraction, seed=args.seed),
        "search": calibrate_scores(search_scores, score_key="search_value",
                                   bins=args.bins, test_fraction=args.test_fraction, seed=args.seed),
    }
    metadata = {
        "name": args.tournament_name or args.output.name,
        "created_at_utc": started_at.isoformat(),
        "python_version": platform.python_version(),
        "code_revision": code_revision(),
        "heuristic": heuristic,
        "sampling": {"stride": args.stride,
                     "max_positions_per_game": args.max_positions_per_game,
                     "verify_replays": not args.no_verify_replays},
        "search": {"algorithm": "MCTS/UCT", "depth_cap_ticks": args.depth,
                   "iterations": args.iterations, "rollout_depth": args.rollout_depth,
                   "exploration_constant": args.exploration_constant,
                   "seed": args.seed,
                   "action_generator": args.action_generator,
                   "opponent_policy": "deterministic one-step evaluator using the selected action generator"},
        "reliability": {"method": "logistic", "bins": args.bins,
                        "test_fraction": args.test_fraction,
                        "split_unit": "game", "seed": args.seed,
                        "bot": calibration_bot or "all",
                        "position_count": len(calibration_positions)},
    }
    output_dir = _new_output_dir(args.output, started_at)
    write_analysis(output_dir, positions, search_rows, replay_paths=replay_paths,
                   calibrations=calibrations, metadata=metadata,
                   make_plot=not args.no_plot)
    print(f"Wrote analysis files to {output_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
