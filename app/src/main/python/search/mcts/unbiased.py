"""Exhaustive single-launch action generation for fully observable states."""

import math

from core.game_state import Action, GameParams, GameState, Player


class UnbiasedActionGenerator:
    """Generate every integer ship count for every legal source/destination pair.

    This generator applies only the game's source-side legality constraints:
    the source must belong to the player, be available, and have at least one
    whole ship to send. Destinations may be friendly, neutral, or enemy planets.
    """

    def generate(self, state: GameState, player: Player,
                 params: GameParams) -> list[Action]:
        del params  # The exhaustive source/destination set is map-parameter independent.
        player.opponent()  # Reject neutral callers.
        actions = [Action.do_nothing()]

        for source in state.planets:
            if (source.owner != player or source.transporter is not None or
                    not math.isfinite(source.n_ships)):
                continue
            max_ships = math.floor(source.n_ships)
            if max_ships < 1:
                continue

            for target in state.planets:
                if source.id == target.id:
                    continue
                actions.extend(
                    Action(
                        player_id=player,
                        source_planet_id=source.id,
                        destination_planet_id=target.id,
                        num_ships=num_ships,
                    )
                    for num_ships in range(1, max_ships + 1)
                )

        return actions
