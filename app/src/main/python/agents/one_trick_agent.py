from agents.planet_wars_agent import PlanetWarsPlayer
from core.game_state import GameState, Action, Player, GameParams
from core.game_state_factory import GameStateFactory

class OneTrickAgent(PlanetWarsPlayer):

    def get_action(self, game_state: GameState) -> Action:

        my_planets = [p for p in game_state.planets
                      if p.owner == self.player and p.transporter is None and p.n_ships > 15]
        if not my_planets:
            return Action.do_nothing()

        candidate_targets = [p for p in game_state.planets if p.owner != self.player]
        if not candidate_targets:
            return Action.do_nothing()

        source = max(my_planets, key=lambda p: p.n_ships)

        def target_score(target):
            distance = source.position.distance(target.position)
            ship_strength = target.n_ships if target.owner == Player.Neutral else target.n_ships * 1.5
            return ship_strength + (1.25* distance) - 2 *target.growth_rate

        target = min(candidate_targets, key=target_score)

        distance = source.position.distance(target.position)
        eta = distance / self.params.transporter_speed
        estimated_defense = target.n_ships + target.growth_rate * eta

        if source.n_ships <= estimated_defense:
            return Action.do_nothing()

        return Action(player_id=self.player,
                      source_planet_id=source.id,
                      destination_planet_id=target.id,
                      num_ships=source.n_ships/2)

    def get_agent_type(self) -> str:
        return "Quickly created agent that loves to send away all agents from small planets. (Python)"

# Example usage
if __name__ == "__main__":
    agent = OneTrickAgent()
    agent.prepare_to_play_as(Player.Player1, GameParams())
    game_state = GameStateFactory(GameParams()).create_game()
    action = agent.get_action(game_state)
    print(action)