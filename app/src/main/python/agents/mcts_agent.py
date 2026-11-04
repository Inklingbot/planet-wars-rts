"""Fully observable MCTS agent; compatible with FullyObservableAgentAdapter."""

from agents.planet_wars_agent import PlanetWarsPlayer, DEFAULT_OPPONENT
from core.game_state import Action, GameParams, GameState, Player
from search.mcts import MCTS, MCTSConfig, SearchResult
from search.mcts.policies import ActionGenerator, Evaluator, OpponentPolicy


class MCTSAgent(PlanetWarsPlayer):
    def __init__(self, config: MCTSConfig | None = None,
                 action_generator: ActionGenerator | None = None,
                 evaluator: Evaluator | None = None,
                 opponent_policy: OpponentPolicy | None = None):
        super().__init__()
        self.search_engine = MCTS(config, action_generator, evaluator, opponent_policy)
        self.last_result: SearchResult | None = None

    def prepare_to_play_as(self, player: Player, params: GameParams,
                           opponent: str | None = DEFAULT_OPPONENT) -> str:
        player.opponent()
        self.search_engine.reset()
        self.last_result = None
        return super().prepare_to_play_as(player, params, opponent)

    def get_action(self, game_state: GameState) -> Action:
        self.last_result = self.search_engine.search(game_state, self.player, self.params)
        return self.last_result.action

    def get_agent_type(self) -> str:
        return "Heuristic UCT MCTS in Python"
