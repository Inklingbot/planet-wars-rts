#!/usr/bin/env python3
"""
Simplest example: Battle two local Python agents (no containers needed).

This demonstrates the core game-playing logic without needing to:
- Clone repositories
- Build containers
- Launch servers

Perfect for quick testing and learning the basics.
"""

from core.game_state import GameParams
from core.unified_game_runner import UnifiedGameRunner
from agents.random_agents import PureRandomAgent, CarefulRandomAgent
from agents.greedy_heuristic_agent import GreedyHeuristicAgent
from agents.fully_observable_agent_adapter import as_unified
from agents.one_trick_agent import OneTrickAgent
from agents.defensive_circle_agent import DefensiveCircleAgent


def main():
    """Run a quick battle between local Python agents."""

    print("\n" + "=" * 70)
    print("LOCAL PYTHON AGENT BATTLE")
    print("=" * 70)

    # =============================================================================
    # CUSTOMIZE THESE - Choose any two local Python agents
    # =============================================================================

    agent1 = as_unified(OneTrickAgent())
    agent2 = as_unified(CarefulRandomAgent())

    agent1_name = "PureRandomAgent"
    agent2_name = "CarefulRandomAgent"

    n_games = 10
    game_params = GameParams(num_planets=20, max_ticks=500)

    # =============================================================================

    print(f"\n🤖 Agent 1: {agent1_name}")
    print(f"🤖 Agent 2: {agent2_name}")
    print(f"🎮 Games: {n_games}")
    print(f"🌍 Planets: {game_params.num_planets}")
    print(f"⏱️  Max ticks: {game_params.max_ticks}")

    # Create runners for both fully and partially observable modes
    print("\n" + "=" * 70)
    print("FULLY OBSERVABLE MODE")
    print("=" * 70)

    runner_full = UnifiedGameRunner(
        agent1, agent2, game_params,
        partial_observability=False
    )

    print(f"\n🎮 Playing {n_games} games...")
    scores_full = runner_full.run_games(n_games)

    from core.game_state import Player

    print(f"\n📊 Results (Fully Observable):")
    print(f"   {agent1_name} (Player1): {scores_full[Player.Player1]} wins")
    print(f"   {agent2_name} (Player2): {scores_full[Player.Player2]} wins")
    if scores_full[Player.Neutral] > 0:
        print(f"   Draws: {scores_full[Player.Neutral]}")

    # Now try partially observable mode
    print("\n" + "=" * 70)
    print("PARTIALLY OBSERVABLE MODE")
    print("=" * 70)

    runner_partial = UnifiedGameRunner(
        agent1, agent2, game_params,
        partial_observability=True
    )

    print(f"\n🎮 Playing {n_games} games...")
    scores_partial = runner_partial.run_games(n_games)

    print(f"\n📊 Results (Partially Observable):")
    print(f"   {agent1_name} (Player1): {scores_partial[Player.Player1]} wins")
    print(f"   {agent2_name} (Player2): {scores_partial[Player.Player2]} wins")
    if scores_partial[Player.Neutral] > 0:
        print(f"   Draws: {scores_partial[Player.Neutral]}")

    # Compare the modes
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)

    print(f"\nHow observability affects the agents:")
    print(f"  Fully Observable:     {agent1_name} won {scores_full[Player.Player1]}/{n_games}")
    print(f"  Partially Observable: {agent1_name} won {scores_partial[Player.Player1]}/{n_games}")

    print("\n✨ Done!\n")


if __name__ == "__main__":
    main()
