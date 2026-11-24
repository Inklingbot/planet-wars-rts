"""Local heuristic MCTS battle and search throughput example.

From the repository root (PowerShell):
    $env:PYTHONPATH = 'app/src/main/python'
    python -m examples.mcts_battle --games 2 --max-ticks 200
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import random
import time

from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.mcts_agent import MCTSAgent
from agents.random_agents import CarefulRandomAgent
from core.forward_model import ForwardModel
from core.game_replay import GameReplayLogger, agent_analysis
from core.game_state import GameParams, Player
from core.game_state_factory import GameStateFactory
from search.mcts import MCTSConfig


def _new_replay_dir(base: Path) -> Path:
    """Create a separate replay directory for each tournament run."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%SZ")
    for index in range(1000):
        suffix = stamp if index == 0 else f"{stamp}-{index:03d}"
        directory = base.with_name(f"{base.name}-{suffix}")
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return directory
    raise FileExistsError(f"Could not reserve a replay directory for {base}")


def _play_game(game: int, settings: dict, replay_dir: Path | None,
               filename_width: int, random_seed: int | None) -> tuple[int, str, int, float, int]:
    """Play one game; a separate random seed makes parallel games independent."""
    if random_seed is not None:
        random.seed(random_seed)
    params = GameParams(max_ticks=settings["max_ticks"])
    config = MCTSConfig(iterations=settings["iterations"], tree_depth=settings["tree_depth"],
                        rollout_depth=settings["rollout_depth"],
                        exploration_constant=settings["exploration_constant"],
                        time_limit_seconds=settings["time_limit"], seed=settings["seed"])
    agent = MCTSAgent(config)
    opponent = GreedyHeuristicAgent() if settings["opponent"] == "greedy" else CarefulRandomAgent()
    side = Player.Player1 if game % 2 == 0 else Player.Player2
    agent.prepare_to_play_as(side, params)
    opponent.prepare_to_play_as(side.opponent(), params)
    model = ForwardModel(GameStateFactory(params).create_game(), params)
    logger = (GameReplayLogger(replay_dir / f"game-{game + 1:0{filename_width}d}.json")
              if replay_dir else None)
    if logger:
        logger.start(model.state, params, {
            side: agent.get_agent_type(),
            side.opponent(): opponent.get_agent_type(),
        })
    iterations = decisions = 0
    search_seconds = 0.0
    while not model.is_terminal():
        before = model.state.model_copy(deep=True)
        action = agent.get_action(model.state)
        iterations += agent.last_result.iterations
        search_seconds += agent.last_result.elapsed_seconds
        decisions += 1
        other = opponent.get_action(model.state.model_copy(deep=True))
        actions = {side: action, side.opponent(): other}
        model.step(actions)
        if logger:
            logger.record_tick(before, actions, model.state, {
                side: agent_analysis(agent),
                side.opponent(): agent_analysis(opponent),
            })
    winner = model.get_leader()
    if logger:
        logger.finish(model.state, winner)
    outcome = "draw" if winner == Player.Neutral else "mcts" if winner == side else "opponent"
    return (game, outcome, model.state.game_tick,
            search_seconds / max(decisions, 1), iterations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--max-ticks", type=int, default=200)
    parser.add_argument("--iterations", type=int, default=16)
    parser.add_argument("--tree-depth", type=int, default=10)
    parser.add_argument("--rollout-depth", type=int, default=20)
    parser.add_argument("--exploration-constant", type=float, default=2 ** 0.5)
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument("--opponent", choices=("random", "greedy"), default="greedy")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replay-dir", type=Path,
                        help="Base directory for JSON replays; a UTC timestamp is appended.")
    parser.add_argument("--workers", type=int, default=1,
                        help="Games to run concurrently (default: 1).")
    parser.add_argument("--benchmark-only", action="store_true",
                        help="Search one initial position instead of running games")
    args = parser.parse_args()
    if args.games < 1 or args.max_ticks < 0 or args.workers < 1:
        parser.error("games and workers must be positive; max-ticks must be nonnegative")
    random.seed(args.seed)
    params = GameParams(max_ticks=args.max_ticks)
    config = MCTSConfig(iterations=args.iterations, tree_depth=args.tree_depth,
                        rollout_depth=args.rollout_depth,
                        exploration_constant=args.exploration_constant,
                        time_limit_seconds=args.time_limit, seed=args.seed)
    agent = MCTSAgent(config)
    if args.benchmark_only:
        agent.prepare_to_play_as(Player.Player1, params)
        agent.get_action(GameStateFactory(params).create_game())
        result = agent.last_result
        print(f"Iterations: {result.iterations}; seconds: {result.elapsed_seconds:.3f}; "
              f"iterations/second: {result.iterations / max(result.elapsed_seconds, 1e-9):.1f}")
        print(f"Deepest tree tick: {result.deepest_tree_tick}; "
              f"deepest simulated tick: {result.deepest_simulated_tick}; action: {result.action}")
        return
    replay_dir = _new_replay_dir(args.replay_dir) if args.replay_dir else None
    results = {"mcts": 0, "opponent": 0, "draw": 0}
    started = time.perf_counter()
    settings = {"max_ticks": args.max_ticks, "iterations": args.iterations,
                "tree_depth": args.tree_depth, "rollout_depth": args.rollout_depth,
                "exploration_constant": args.exploration_constant,
                "time_limit": args.time_limit, "seed": args.seed,
                "opponent": args.opponent}
    filename_width = max(2, len(str(args.games)))

    def report(completed: tuple[int, str, int, float, int]) -> None:
        game, outcome, ticks, seconds_per_decision, iterations = completed
        results[outcome] += 1
        print(f"Game {game + 1}: {outcome}; ticks: {ticks}; "
              f"search seconds/decision: {seconds_per_decision:.4f}; "
              f"iterations: {iterations}; completed: {sum(results.values())}/{args.games}",
              flush=True)

    if args.workers == 1:
        for game in range(args.games):
            report(_play_game(game, settings, replay_dir, filename_width, None))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_play_game, game, settings, replay_dir,
                                   filename_width, args.seed + game)
                       for game in range(args.games)]
            for future in as_completed(futures):
                report(future.result())
    print(f"Results: {results}; total seconds: {time.perf_counter() - started:.2f}")
    if replay_dir:
        print(f"Replays: {replay_dir.resolve()}")


if __name__ == "__main__":
    main()
