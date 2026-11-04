"""UCT with one-action expansion for deterministic Planet Wars simulations."""

from dataclasses import dataclass, field
import math
import random
import time

from core.forward_model import ForwardModel
from core.game_state import Action, GameParams, GameState, Player
from .config import MCTSConfig
from .evaluation import BoardStrengthEvaluator
from .policies import ActionGenerator, Evaluator, OpponentPolicy
from .tactical import DeterministicTacticalPolicy, TacticalActionGenerator


@dataclass
class _Node:
    state: GameState
    action: Action | None = None
    visits: int = 0
    total_value: float = 0.0
    prior: float = 0.0  # Reserved for PUCT; unused by UCT.
    children: list['_Node'] = field(default_factory=list)
    untried: list[Action] | None = None
    opponent_action: Action | None = None

    @property
    def mean_value(self):
        return self.total_value / self.visits if self.visits else 0.0


@dataclass(frozen=True)
class ActionStatistics:
    action: Action
    visits: int
    mean_value: float
    prior: float


@dataclass(frozen=True)
class SearchResult:
    action: Action
    iterations: int
    deepest_tree_tick: int
    deepest_simulated_tick: int
    elapsed_seconds: float
    root_actions: tuple[ActionStatistics, ...]


class MCTS:
    """Fresh tree per call; caller-owned states and parameters remain untouched.

    Each tree edge advances both players by exactly one tick. Values always use
    the root player's perspective: opponent responses are modeled, not maximized.
    Depth limits are relative to the search root. Rollouts add up to rollout_depth
    ticks after each tree leaf, for at most tree_depth + rollout_depth total.
    """

    def __init__(self, config: MCTSConfig | None = None,
                 action_generator: ActionGenerator | None = None,
                 evaluator: Evaluator | None = None,
                 opponent_policy: OpponentPolicy | None = None):
        self.config = config or MCTSConfig()
        self.action_generator = action_generator or TacticalActionGenerator()
        self.evaluator = evaluator or BoardStrengthEvaluator()
        self.opponent_policy = opponent_policy or DeterministicTacticalPolicy(
            self.action_generator, self.evaluator)
        self.rng = random.Random(self.config.seed)

    def reset(self):
        """Reset random sampling at the start of a game."""
        self.rng = random.Random(self.config.seed)

    def _step(self, state, action, opponent_action, player, params):
        model = ForwardModel(state.model_copy(deep=True), params, record_statistics=False)
        model.step({player: action, player.opponent(): opponent_action})
        return model.state

    def _uct(self, child, parent_visits):
        if not child.visits:
            return math.inf
        return (child.mean_value + self.config.exploration_constant *
                math.sqrt(math.log(parent_visits) / child.visits))

    def search(self, state: GameState, player: Player, params: GameParams) -> SearchResult:
        player.opponent()  # Searching as Neutral is invalid.
        started = time.perf_counter()
        deadline = (started + self.config.time_limit_seconds
                    if self.config.time_limit_seconds is not None else math.inf)
        root = _Node(state.model_copy(deep=True))
        completed = deepest_tree = deepest_simulated = 0
        if ForwardModel(root.state, params).is_terminal():
            return SearchResult(Action.do_nothing(), 0, 0, 0,
                                time.perf_counter() - started, ())
        for _ in range(self.config.iterations):
            # Soft deadline: an in-progress iteration finishes before returning.
            if time.perf_counter() >= deadline:
                break
            node, depth, path = root, 0, [root]
            while depth < self.config.tree_depth and not ForwardModel(node.state, params).is_terminal():
                if node.untried is None:
                    node.untried = list(self.action_generator.generate(node.state, player, params))
                    if not node.untried:
                        node.untried = [Action.do_nothing()]
                    self.rng.shuffle(node.untried)
                    node.opponent_action = self.opponent_policy.choose(node.state, player.opponent(), params)
                if node.untried:
                    action = node.untried.pop()
                    next_state = self._step(node.state, action, node.opponent_action, player, params)
                    child = _Node(next_state, action=action,
                                  prior=1 / (len(node.untried) + len(node.children) + 1))
                    node.children.append(child)
                    node = child
                    depth += 1
                    path.append(node)
                    break
                node = max(node.children, key=lambda child: self._uct(child, node.visits))
                depth += 1
                path.append(node)
            deepest_tree = max(deepest_tree, depth)
            rollout_state = node.state
            rollout_ticks = 0
            for _ in range(self.config.rollout_depth):
                if ForwardModel(rollout_state, params).is_terminal():
                    break
                candidates = list(self.action_generator.generate(rollout_state, player, params))
                action = self.rng.choice(candidates) if candidates else Action.do_nothing()
                opponent_action = self.opponent_policy.choose(rollout_state, player.opponent(), params)
                rollout_state = self._step(rollout_state, action, opponent_action, player, params)
                rollout_ticks += 1
            deepest_simulated = max(deepest_simulated, depth + rollout_ticks)
            value = self.evaluator.evaluate(rollout_state, player, params)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Evaluator must return a finite value in [0, 1]")
            for visited in path:
                visited.visits += 1
                visited.total_value += value
            completed += 1
        best = max(root.children, key=lambda child: (child.visits, child.mean_value), default=None)
        stats = tuple(ActionStatistics(c.action, c.visits, c.mean_value, c.prior) for c in root.children)
        return SearchResult(best.action if best else Action.do_nothing(), completed,
                            deepest_tree, deepest_simulated, time.perf_counter() - started, stats)
