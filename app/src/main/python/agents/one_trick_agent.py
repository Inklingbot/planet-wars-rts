from agents.planet_wars_agent import PlanetWarsPlayer
from core.game_state import GameState, Action, Player, GameParams, Transporter
from core.game_state_factory import GameStateFactory
from collections import Counter

class OneTrickAgent(PlanetWarsPlayer):

    def get_action(self, game_state: GameState) -> Action:
        def target_score(target):
                    distance = source.position.distance(target.position)
                    ship_strength = target.n_ships if target.owner == Player.Neutral else target.n_ships * 1.5
                    return ship_strength + (1.25* distance) - 2 *target.growth_rate
        
        my_planets = [p for p in game_state.planets
                      if p.owner == self.player and p.transporter is None and p.n_ships > 10]
        if not my_planets:
            return Action.do_nothing()

        candidate_targets = [p for p in game_state.planets if p.owner != self.player]
        if not candidate_targets:
            return Action.do_nothing()
        danger_source = assess_endangered_planet(self.player, game_state, my_planets)
        to_send = 0
        if danger_source is not None:
            source = next(p for p in my_planets if p.id == danger_source)
            to_send = source.n_ships
            target = max(candidate_targets, key=lambda p: p.growth_rate)
        else:
            source = max(my_planets, key=lambda p: p.n_ships)
            to_send = source.n_ships/2
            target = min(candidate_targets, key=target_score)

        
    
        

        distance = source.position.distance(target.position)
        eta = distance / self.params.transporter_speed
        estimated_defense = target.n_ships + target.growth_rate * eta

        if source.n_ships <= estimated_defense:
            return Action.do_nothing()

        return Action(player_id=self.player,
                      source_planet_id=source.id,
                      destination_planet_id=target.id,
                      num_ships=to_send)

    def get_agent_type(self) -> str:
        return "Abandon Ship! (Python)"


def assess_endangered_planet(player: Player, game_state: GameState, my_planets: list[Planet]) -> int | None:
    available_planet_ids = {
        planet.id
        for planet in my_planets
        if planet.transporter is None
    }
    target_counts = Counter(
        planet.transporter.destination_index
        for planet in game_state.planets
        if planet.transporter is not None and planet.transporter.owner != player
    )
    endangered = [
        (target_id, count)
        for target_id, count in target_counts.items()
        if target_id in available_planet_ids and count > 1
    ]
    return max(endangered, key=lambda item: item[1])[0] if endangered else None


# Example usage
if __name__ == "__main__":
    agent = OneTrickAgent()
    agent.prepare_to_play_as(Player.Player1, GameParams())
    game_state = GameStateFactory(GameParams()).create_game()
    action = agent.get_action(game_state)
    print(action)
