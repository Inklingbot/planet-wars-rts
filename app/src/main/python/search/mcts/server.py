"""Serve Planet Wars MCTS for GUI games and headless evaluation.

Run with ``python -m search.mcts.server`` from the Python source path.
"""

import argparse
import asyncio
from dataclasses import asdict

from agents.mcts_agent import MCTSAgent
from client_server.game_agent_server import GameServerAgent
from .config import MCTSConfig
from scoring.heuristics import default_mcts_evaluator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--iterations", type=int, default=128)
    parser.add_argument("--tree-depth", type=int, default=20)
    parser.add_argument("--rollout-depth", type=int, default=20)
    parser.add_argument("--time-limit", type=float, default=0.05,
                        help="Soft search deadline in seconds per decision")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--evaluator", help="Evaluator profile ID from heuristic_comparison.yaml")
    parser.add_argument("--evaluator-config", help="Optional evaluator profile YAML file")
    args = parser.parse_args()
    if args.evaluator_config and not args.evaluator:
        parser.error("--evaluator-config requires --evaluator")
    evaluator = None
    evaluator_spec = {"type": "mcts_board_strength", "weights": asdict(default_mcts_evaluator().weights)}
    if args.evaluator:
        from scoring.evaluators import Comparison, DEFAULT_CONFIG
        comparison = Comparison.load(args.evaluator_config or DEFAULT_CONFIG)
        if args.evaluator not in comparison.evaluators:
            parser.error(f"Unknown evaluator profile: {args.evaluator}")
        evaluator = comparison.evaluators[args.evaluator]
        evaluator_spec = {"id": args.evaluator, **comparison.config["evaluators"][args.evaluator]}
    config = MCTSConfig(iterations=args.iterations, tree_depth=args.tree_depth,
                        rollout_depth=args.rollout_depth, seed=args.seed,
                        time_limit_seconds=args.time_limit)

    # GameServerAgent creates fresh instances by type for each client. Keep the
    # configured constructor on that type so the server preserves this budget.
    class VisualMCTSAgent(MCTSAgent):
        def __init__(self):
            super().__init__(config, evaluator=evaluator)

        def get_agent_type(self):
            name = super().get_agent_type()
            return f"{name} [{args.evaluator}]" if args.evaluator else name

        def get_action(self, game_state):
            action = super().get_action(game_state)
            if game_state.game_tick % 25 == 0:
                result = self.last_result
                print(f"tick={game_state.game_tick} iterations={result.iterations} "
                      f"search_ms={result.elapsed_seconds * 1000:.1f} "
                      f"tree_ticks={result.deepest_tree_tick} action={action}", flush=True)
            return action

    print(f"MCTS config: {config}", flush=True)
    print(f"MCTS evaluator: {evaluator_spec}", flush=True)
    asyncio.run(GameServerAgent(host="localhost", port=args.port, agent=VisualMCTSAgent()).start())


if __name__ == "__main__":
    main()
