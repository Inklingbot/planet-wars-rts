"""Local heuristic MCTS battle and search throughput example.

From the repository root (PowerShell):
    $env:PYTHONPATH = 'app/src/main/python'
    python -m examples.mcts_battle --games 2 --max-ticks 200
"""

import argparse
import random
import time

from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.mcts_agent import MCTSAgent
from agents.random_agents import CarefulRandomAgent
from core.forward_model import ForwardModel
from core.game_state import GameParams, Player
from core.game_state_factory import GameStateFactory
from search.mcts import MCTSConfig


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
    parser.add_argument("--benchmark-only", action="store_true",
                        help="Search one initial position instead of running games")
    args = parser.parse_args()
    if args.games < 1 or args.max_ticks < 0:
        parser.error("games must be positive and max-ticks nonnegative")
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
    results = {"mcts": 0, "opponent": 0, "draw": 0}
    started = time.perf_counter()
    for game in range(args.games):
        opponent = GreedyHeuristicAgent() if args.opponent == "greedy" else CarefulRandomAgent()
        side = Player.Player1 if game % 2 == 0 else Player.Player2
        agent.prepare_to_play_as(side, params)
        opponent.prepare_to_play_as(side.opponent(), params)
        model = ForwardModel(GameStateFactory(params).create_game(), params)
        iterations = decisions = 0
        search_seconds = 0.0
        while not model.is_terminal():
            action = agent.get_action(model.state)
            iterations += agent.last_result.iterations
            search_seconds += agent.last_result.elapsed_seconds
            decisions += 1
            other = opponent.get_action(model.state.model_copy(deep=True))
            model.step({side: action, side.opponent(): other})
        winner = model.get_leader()
        outcome = "draw" if winner == Player.Neutral else "mcts" if winner == side else "opponent"
        results[outcome] += 1
        print(f"Game {game + 1}: {outcome}; ticks: {model.state.game_tick}; "
              f"search seconds/decision: {search_seconds / max(decisions, 1):.4f}; "
              f"iterations: {iterations}")
    print(f"Results: {results}; total seconds: {time.perf_counter() - started:.2f}")


if __name__ == "__main__":
    main()
