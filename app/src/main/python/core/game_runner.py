from typing import Dict
from core.forward_model import ForwardModel
from core.game_state import GameParams, GameState, Player
from core.game_state_factory import GameStateFactory
from core.game_replay import GameReplayLogger, agent_analysis
from agents.random_agents import PureRandomAgent, CarefulRandomAgent  # adjust path


class GameRunner:
    def __init__(self, agent1, agent2, game_params: GameParams, replay_log_path=None):
        self.agent1 = agent1
        self.agent2 = agent2
        self.game_params = game_params
        self.game_state: GameState = GameStateFactory(game_params).create_game()
        self.forward_model: ForwardModel = ForwardModel(self.game_state.model_copy(deep=True), game_params)
        self.replay_logger = GameReplayLogger(replay_log_path) if replay_log_path else None
        self._replay_finished = False
        self.new_game()

    def run_game(self) -> ForwardModel:
        self.new_game()
        while not self.forward_model.is_terminal():
            before = self.forward_model.state.model_copy(deep=True)
            actions = {
                Player.Player1: self.agent1.get_action(self.forward_model.state.model_copy(deep=True)),
                Player.Player2: self.agent2.get_action(self.forward_model.state.model_copy(deep=True)),
            }
            self.forward_model.step(actions)
            self._record_tick(before, actions)
        self._finish_replay()
        return self.forward_model

    def new_game(self):
        if self.game_params.new_map_each_run:
            self.game_state = GameStateFactory(self.game_params).create_game()
        self.forward_model = ForwardModel(self.game_state.model_copy(deep=True), self.game_params)
        self.agent1.prepare_to_play_as(Player.Player1, self.game_params)
        self.agent2.prepare_to_play_as(Player.Player2, self.game_params)
        self._replay_finished = False
        if self.replay_logger:
            self.replay_logger.start(self.forward_model.state, self.game_params, {
                Player.Player1: self.agent1.get_agent_type(),
                Player.Player2: self.agent2.get_agent_type(),
            })

    def _record_tick(self, before, actions):
        if self.replay_logger:
            analyses = {Player.Player1: agent_analysis(self.agent1),
                        Player.Player2: agent_analysis(self.agent2)}
            self.replay_logger.record_tick(before, actions, self.forward_model.state, analyses)

    def _finish_replay(self):
        if self.replay_logger and not self._replay_finished:
            self.replay_logger.finish(self.forward_model.state, self.forward_model.get_leader())
            self._replay_finished = True

    def step_game(self) -> ForwardModel:
        if self.forward_model.is_terminal():
            self._finish_replay()
            return self.forward_model
        before = self.forward_model.state.model_copy(deep=True)
        actions = {
            Player.Player1: self.agent1.get_action(self.forward_model.state),
            Player.Player2: self.agent2.get_action(self.forward_model.state),
        }
        self.forward_model.step(actions)
        self._record_tick(before, actions)
        if self.forward_model.is_terminal():
            self._finish_replay()
        return self.forward_model

    def run_games(self, n_games: int) -> Dict[Player, int]:
        scores = {Player.Player1: 0, Player.Player2: 0, Player.Neutral: 0}
        for _ in range(n_games):
            final_model = self.run_game()
            winner = final_model.get_leader()
            scores[winner] += 1
        return scores


if __name__ == "__main__":

    game_params = GameParams(num_planets=10)
    agent1 = CarefulRandomAgent()
    agent2 = PureRandomAgent()
    runner = GameRunner(agent1, agent2, game_params)

    n_games = 10
    import time
    t0 = time.time()
    results = runner.run_games(n_games)
    t1 = time.time()

    print(results)
    print(f"Time per game: {(t1 - t0) * 1000 / n_games:.3f} ms")
    print(f"Time per step: {(t1 - t0) * 1000 / ForwardModel.n_updates:.3f} ms")
    print(f"Successful actions: {ForwardModel.n_actions}")
    print(f"Failed actions: {ForwardModel.n_failed_actions}")
