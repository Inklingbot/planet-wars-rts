"""Capture and reinforcement candidates, sized using chronological projections."""

from dataclasses import dataclass
import math

from core.forward_model import ForwardModel
from core.game_state import Action, GameParams, GameState, Player, Transporter
from .evaluation import BoardStrengthEvaluator
from .policies import ActionGenerator, Evaluator
from .projection import Arrival, arrival_tick, incoming_fleets, project_planet, remaining_ticks


@dataclass(frozen=True)
class TacticalActionGenerator:
    safety_margin: float = 1.0

    def __post_init__(self):
        if not math.isfinite(self.safety_margin) or self.safety_margin < 0:
            raise ValueError("safety_margin must be finite and nonnegative")

    def generate(self, state: GameState, player: Player, params: GameParams) -> list[Action]:
        player.opponent()  # Reject neutral callers.
        actions = [Action.do_nothing()]
        incoming = incoming_fleets(state, params)
        projected = {p.id: project_planet(p, incoming[p.id]) for p in state.planets}
        horizon = remaining_ticks(state, params)
        for source in state.planets:
            if source.owner != player or source.transporter is not None or source.n_ships <= 0:
                continue
            for target in state.planets:
                if source.id == target.id:
                    continue
                # Already secured planets need no further launch. For friendly
                # targets, this restricts candidates to threatened reinforcements.
                if projected[target.id].owner == player:
                    continue
                fleet = Transporter(
                    s=source.position,
                    v=(target.position - source.position).normalize() * params.transporter_speed,
                    owner=player, source_index=source.id,
                    destination_index=target.id, n_ships=source.n_ships,
                )
                tick = arrival_tick(fleet, target, horizon)
                if tick is None:
                    continue
                events = incoming[target.id]

                def secured(amount):
                    return project_planet(target, events + [Arrival(tick, player, amount)]).owner == player

                if not secured(source.n_ships):
                    continue
                # Monotone ownership threshold, including later recaptures and
                # same-tick arrivals. Keep the winning upper bound for strict ties.
                low, high = 0.0, source.n_ships
                for _ in range(32):
                    middle = (low + high) / 2
                    if secured(middle):
                        high = middle
                    else:
                        low = middle
                amount = min(source.n_ships, high + self.safety_margin)
                actions.append(Action(player_id=player, source_planet_id=source.id,
                                      destination_planet_id=target.id, num_ships=amount))
        return actions


class DeterministicTacticalPolicy:
    """Choose the tactical candidate with greatest resulting board strength.

    Stable candidate order breaks ties. Both players' policies see the same
    pre-step state; this policy never receives the other player's chosen action.
    """

    def __init__(self, action_generator: ActionGenerator | None = None,
                 evaluator: Evaluator | None = None):
        self.action_generator = action_generator or TacticalActionGenerator()
        self.evaluator = evaluator or BoardStrengthEvaluator()

    def choose(self, state: GameState, player: Player, params: GameParams) -> Action:
        def score(action):
            model = ForwardModel(state.model_copy(deep=True), params, record_statistics=False)
            model.step({player: action})
            return self.evaluator.evaluate(model.state, player, params)

        actions = list(self.action_generator.generate(state, player, params))
        return max(actions, key=score) if actions else Action.do_nothing()
