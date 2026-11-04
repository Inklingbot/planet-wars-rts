"""Serve heuristic MCTS for the Kotlin viewer's runVisualMCTS task."""

import argparse
import asyncio

from agents.mcts_agent import MCTSAgent
from client_server.game_agent_server import GameServerAgent
from search.mcts import MCTSConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--iterations", type=int, default=128)
    parser.add_argument("--tree-depth", type=int, default=20)
    parser.add_argument("--rollout-depth", type=int, default=20)
    parser.add_argument("--time-limit", type=float, default=0.05,
                        help="Soft search deadline in seconds per decision")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    config = MCTSConfig(iterations=args.iterations, tree_depth=args.tree_depth,
                        rollout_depth=args.rollout_depth, seed=args.seed,
                        time_limit_seconds=args.time_limit)

    # GameServerAgent creates fresh instances by type for each client. Keep the
    # configured constructor on that type so the server preserves this budget.
    class VisualMCTSAgent(MCTSAgent):
        def __init__(self):
            super().__init__(config)

        def get_action(self, game_state):
            action = super().get_action(game_state)
            if game_state.game_tick % 25 == 0:
                result = self.last_result
                print(f"tick={game_state.game_tick} iterations={result.iterations} "
                      f"search_ms={result.elapsed_seconds * 1000:.1f} "
                      f"tree_ticks={result.deepest_tree_tick} action={action}", flush=True)
            return action

    print(f"MCTS config: {config}", flush=True)
    asyncio.run(GameServerAgent(host="localhost", port=args.port, agent=VisualMCTSAgent()).start())


if __name__ == "__main__":
    main()
