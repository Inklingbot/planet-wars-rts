"""Planet Wars strategy interfaces; implementations must not mutate inputs.

OpponentPolicy must be deterministic: the initial engine stores one state per
action edge. Stochastic opponents will require explicit chance-outcome branches.
"""

from typing import Protocol, Sequence

from core.game_state import Action, GameParams, GameState, Player


class ActionGenerator(Protocol):
    def generate(self, state: GameState, player: Player, params: GameParams) -> Sequence[Action]: ...


class Evaluator(Protocol):
    def evaluate(self, state: GameState, player: Player, params: GameParams) -> float: ...


class OpponentPolicy(Protocol):
    def choose(self, state: GameState, player: Player, params: GameParams) -> Action: ...


class PolicyValueModel(Protocol):
    """Future PyTorch adapter: one prior per candidate and a [0, 1] player value.

    Candidate scoring supports variable map sizes and custom action generators.
    Implementations will mask illegal candidates and normalize legal priors.
    """

    def predict(self, state: GameState, player: Player, params: GameParams,
                actions: Sequence[Action]) -> tuple[Sequence[float], float]: ...
