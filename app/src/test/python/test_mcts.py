"""Projection parity, tactical behavior, search contracts, and extension guards."""

import math
import random
import unittest
from unittest.mock import Mock, patch

from agents.mcts_agent import MCTSAgent
from agents.fully_observable_agent_adapter import as_unified
from core.forward_model import ForwardModel
from core.game_state import Action, GameParams, GameState, Planet, Player, Transporter, Vec2d
from core.observation import ObservationFactory
from scoring.heuristics import BoardStrengthEvaluator, BoardWeights
from search.mcts import DeterministicTacticalPolicy, MCTS, MCTSConfig, TacticalActionGenerator
from search.mcts.modern import BatchedInference, ProgressiveWidening, PUCTSelection, PyTorchPolicyValue
from core.fleet_projection import Arrival, arrival_tick, incoming_fleets, project_board, project_planet

P1, P2, NEUTRAL = Player.Player1, Player.Player2, Player.Neutral


def planet(index, owner, ships, x=0, growth=0, radius=2):
    return Planet(id=index, owner=owner, n_ships=ships, position=Vec2d(x=x, y=0),
                  growth_rate=growth, radius=radius)


def fleet(owner, ships, destination, x=0, speed=3, source=0):
    return Transporter(s=Vec2d(x=x, y=0), v=Vec2d(x=speed, y=0), owner=owner,
                       source_index=source, destination_index=destination, n_ships=ships)


def small_state():
    return GameState(planets=[planet(0, P1, 20), planet(1, P2, 5, 10),
                              planet(2, NEUTRAL, 3, 20)])


class TestFleetProjection(unittest.TestCase):
    def test_growth_tracks_multiple_ownership_changes(self):
        target = planet(0, P1, 5, growth=1)
        first = project_planet(target, [Arrival(1, P2, 10)])
        self.assertEqual((first.owner, first.ships), (P2, 4))
        result = project_planet(target, [Arrival(1, P2, 10), Arrival(3, P1, 8)])
        self.assertEqual((result.owner, result.ships), (P1, 2))

    def test_simultaneous_neutral_combat_and_ties(self):
        target = planet(0, NEUTRAL, 4, growth=10)
        tied = project_planet(target, [Arrival(8, P1, 10), Arrival(8, P2, 6)])
        self.assertEqual((tied.owner, tied.ships), (NEUTRAL, 0))
        won = project_planet(target, [Arrival(8, P1, 11), Arrival(8, P2, 6)])
        self.assertEqual((won.owner, won.ships), (P1, 1))
        owned = project_planet(planet(0, P1, 4), [Arrival(1, P2, 4)])
        self.assertEqual((owned.owner, owned.ships), (P1, 0))

    def test_discrete_arrival_and_overshooting(self):
        target = planet(1, P2, 5, x=10, radius=2)
        self.assertEqual(arrival_tick(fleet(P1, 9, 1), target, 20), 4)
        self.assertIsNone(arrival_tick(fleet(P1, 9, 1), target, 3))
        target.radius = 1
        self.assertIsNone(arrival_tick(fleet(P1, 9, 1), target, 20))
        self.assertIsNone(arrival_tick(fleet(P1, 9, 1, speed=0), target, 20))

    def test_projection_matches_forward_model_with_random_fleets(self):
        rng = random.Random(42)
        params = GameParams(max_ticks=40)
        for case in range(60):
            state = GameState(planets=[planet(0, rng.choice([P1, P2, NEUTRAL]),
                                               rng.uniform(0, 15), 20, rng.uniform(0, 2))])
            for i in range(1, 6):
                source = planet(i, rng.choice([P1, P2]), 10, -i * 10)
                source.transporter = fleet(rng.choice([P1, P2]), rng.uniform(1, 25), 0,
                                           x=rng.choice([2, 5, 8, 11, 14, 20]), source=i)
                state.planets.append(source)
            incoming = incoming_fleets(state, params)[0]
            end = max((a.tick for a in incoming), default=0)
            expected = project_planet(state.planets[0], incoming)
            model = ForwardModel(state.model_copy(deep=True), params)
            for _ in range(end):
                model.step({})
            with self.subTest(case=case):
                self.assertEqual(expected.owner, model.state.planets[0].owner)
                self.assertAlmostEqual(expected.ships, model.state.planets[0].n_ships)

    def test_horizon_excludes_fleets_arriving_after_game_end(self):
        state = small_state()
        state.game_tick = 10
        state.planets[0].transporter = fleet(P1, 50, 1)
        projected = project_board(state, GameParams(max_ticks=10))
        self.assertEqual(projected[1].owner, P2)


class TestBoardStrength(unittest.TestCase):
    def test_features_count_fleet_owner_and_final_captures(self):
        state = GameState(planets=[planet(0, P1, 5, growth=1),
                                  planet(1, P2, 5, 10, growth=1),
                                  planet(2, NEUTRAL, 3, 20)])
        # A fleet still belongs to P1 even though its source now belongs to P2.
        state.planets[1].transporter = fleet(P1, 10, 2, x=20, source=1)
        features = BoardStrengthEvaluator().features(state, P1, GameParams())
        self.assertEqual(set(features), {"planets", "growth", "ships", "expected_captures", "planets_over_10"})
        self.assertEqual(features["planets"], 0)
        self.assertEqual(features["growth"], 0)
        self.assertAlmostEqual(features["ships"], 0.5)
        self.assertAlmostEqual(features["expected_captures"], 1 / 3)

    def test_temporary_capture_is_not_a_final_loss(self):
        state = GameState(planets=[planet(0, P1, 5, growth=1), planet(1, P2, 5, 20),
                                  planet(2, P1, 5, 30)])
        state.planets[1].transporter = fleet(P2, 10, 0, x=0, source=1)
        state.planets[2].transporter = fleet(P1, 8, 0, x=-6, source=2)
        features = BoardStrengthEvaluator().features(state, P1, GameParams())
        self.assertEqual(features["expected_captures"], 0)

    def test_weights_bounds_and_terminal_result(self):
        state = small_state()
        evaluator = BoardStrengthEvaluator(BoardWeights(planets=0, growth=0, ships=1,
                                                        expected_captures=0, planets_over_10=0))
        self.assertAlmostEqual(evaluator.evaluate(state, P1, GameParams()), 0.8)
        state.game_tick = 11
        self.assertEqual(evaluator.evaluate(state, P1, GameParams(max_ticks=10)), 1)
        self.assertEqual(evaluator.evaluate(state, P2, GameParams(max_ticks=10)), 0)
        for weights in ({"ships": -1}, {"growth": math.nan},
                        {"planets_over_10": -1},
                        {"planets": 0, "growth": 0, "ships": 0,
                         "expected_captures": 0, "planets_over_10": 0}):
            with self.assertRaises(ValueError):
                BoardWeights(**weights)

    def test_planets_over_10_counts_only_owned_stationed_ships(self):
        state = GameState(planets=[planet(0, P1, 10), planet(1, P1, 10.01),
                                  planet(2, P1, 9.99), planet(3, P2, 20),
                                  planet(4, NEUTRAL, 20)])
        state.planets[0].transporter = fleet(P1, 50, 4)
        evaluator = BoardStrengthEvaluator()
        self.assertAlmostEqual(evaluator.features(state, P1, GameParams())["planets_over_10"], 1 / 5)
        self.assertAlmostEqual(evaluator.features(state, P2, GameParams())["planets_over_10"], 1 / 5)

    def test_planets_over_10_reward_can_be_weighted_or_disabled(self):
        state = small_state()
        state.planets[0].n_ships = 10
        evaluator = BoardStrengthEvaluator(BoardWeights(
            planets=0, growth=0, ships=0, expected_captures=0, planets_over_10=1))
        before = evaluator.evaluate(state, P1, GameParams())
        state.planets[0].n_ships = 10.01
        after = evaluator.evaluate(state, P1, GameParams())
        self.assertAlmostEqual(before, 0.5)
        self.assertAlmostEqual(after - before, 1 / 6)
        disabled = BoardStrengthEvaluator(BoardWeights(
            planets=1, growth=0, ships=0, expected_captures=0, planets_over_10=0))
        score = disabled.evaluate(state, P1, GameParams())
        state.planets[0].n_ships = 10
        self.assertEqual(disabled.evaluate(state, P1, GameParams()), score)


class TestTacticalActions(unittest.TestCase):
    def test_capture_sizes_account_for_growth_and_are_legal(self):
        state = small_state()
        state.planets[1].growth_rate = 0.5
        before = state.model_dump()
        actions = TacticalActionGenerator().generate(state, P1, GameParams())
        attack = next(a for a in actions if a.destination_planet_id == 1)
        self.assertAlmostEqual(attack.num_ships, 8, places=6)  # 5 + 4*.5 + margin
        for action in actions:
            model = ForwardModel(state.model_copy(deep=True), GameParams())
            failed = ForwardModel.n_failed_actions
            model.apply_actions({P1: action})
            self.assertEqual(ForwardModel.n_failed_actions, failed)
        self.assertEqual(state.model_dump(), before)

    def test_reinforce_only_threatened_friendly_planets(self):
        state = GameState(planets=[planet(0, P1, 30), planet(1, P1, 3, 10),
                                  planet(2, P2, 5, 20), planet(3, P1, 10, 30)])
        state.planets[2].transporter = fleet(P2, 12, 1, x=-5, source=2)
        actions = TacticalActionGenerator().generate(state, P1, GameParams())
        self.assertTrue(any(a.source_planet_id == 0 and a.destination_planet_id == 1 for a in actions))
        self.assertFalse(any(a.destination_planet_id == 3 for a in actions))
        reinforcement = next(a for a in actions if a.source_planet_id == 0 and a.destination_planet_id == 1)
        model = ForwardModel(state.model_copy(deep=True), GameParams(), record_statistics=False)
        model.step({P1: reinforcement})
        for _ in range(15):
            model.step({})
        self.assertEqual(model.state.planets[1].owner, P1)

    def test_already_secured_targets_and_busy_sources_are_excluded(self):
        state = small_state()
        state.planets[0].transporter = fleet(P1, 30, 1)
        self.assertEqual(TacticalActionGenerator().generate(state, P1, GameParams()), [Action.do_nothing()])
        state.planets.append(planet(3, P1, 20, 30))
        actions = TacticalActionGenerator().generate(state, P1, GameParams())
        self.assertFalse(any(a.destination_planet_id == 1 for a in actions))

    def test_deterministic_policy(self):
        state = small_state()
        policy = DeterministicTacticalPolicy()
        self.assertEqual(policy.choose(state, P1, GameParams()), policy.choose(state, P1, GameParams()))

    def test_terminal_tactical_candidate_bypasses_custom_heuristic(self):
        class CustomHeuristic:
            def evaluate(self, state, player, params):
                if ForwardModel(state, params).is_terminal():
                    raise AssertionError("Tactical terminal state reached the heuristic")
                return .9

        state = GameState(planets=[planet(0, P1, 20), planet(1, P2, 5, 1)])
        action = DeterministicTacticalPolicy(evaluator=CustomHeuristic()).choose(state, P1, GameParams())
        self.assertEqual(action.destination_planet_id, 1)


class TestSearch(unittest.TestCase):
    def test_terminal_outcomes_bypass_heuristics_and_backpropagate_for_both_players(self):
        class OnlyWait:
            def generate(self, state, player, params):
                return [Action.do_nothing()]

        class WaitOpponent:
            def choose(self, state, player, params):
                return Action.do_nothing()

        # End either on the tree edge or one tick later inside the rollout.
        for rollout_depth, max_ticks in ((0, 0), (1, 1)):
            for ships1, ships2, value1 in ((20, 5, 1.0), (5, 20, 0.0), (5, 5, 0.5)):
                for player, expected in ((P1, value1), (P2, 1 - value1)):
                    with self.subTest(rollout=rollout_depth, ships=(ships1, ships2), player=player):
                        state = GameState(planets=[planet(0, P1, ships1), planet(1, P2, ships2, 10)])
                        before = state.model_dump()
                        evaluator = Mock()
                        evaluator.evaluate.side_effect = AssertionError("Terminal states must bypass the heuristic")
                        result = MCTS(MCTSConfig(iterations=4, tree_depth=1, rollout_depth=rollout_depth),
                                      OnlyWait(), evaluator, WaitOpponent()).search(
                                          state, player, GameParams(max_ticks=max_ticks))
                        evaluator.evaluate.assert_not_called()
                        self.assertEqual(result.iterations, 4)
                        self.assertEqual(result.root_actions[0].visits, 4)
                        self.assertEqual(result.root_actions[0].mean_value, expected)
                        self.assertEqual(state.model_dump(), before)

    def test_nonterminal_leaves_still_use_custom_heuristic(self):
        class OnlyWait:
            def generate(self, state, player, params):
                return [Action.do_nothing()]

        class WaitOpponent:
            def choose(self, state, player, params):
                return Action.do_nothing()

        evaluator = Mock()
        evaluator.evaluate.return_value = .37
        result = MCTS(MCTSConfig(iterations=4, tree_depth=1, rollout_depth=0),
                      OnlyWait(), evaluator, WaitOpponent()).search(small_state(), P1, GameParams())
        self.assertEqual(evaluator.evaluate.call_count, 4)
        self.assertEqual(result.root_actions[0].mean_value, .37)

    def test_elimination_win_overrides_custom_heuristic(self):
        class WaitOpponent:
            def choose(self, state, player, params):
                return Action.do_nothing()

        class CustomHeuristic:
            def evaluate(self, state, player, params):
                if ForwardModel(state, params).is_terminal():
                    raise AssertionError("Terminal capture reached the heuristic")
                return .9

        for player in (P1, P2):
            state = GameState(planets=[planet(0, player, 20), planet(1, player.opponent(), 5, 1)])
            result = MCTS(MCTSConfig(iterations=8, tree_depth=1, rollout_depth=0, seed=3),
                          evaluator=CustomHeuristic(), opponent_policy=WaitOpponent()).search(
                              state, player, GameParams())
            capture = next(a for a in result.root_actions if a.action.destination_planet_id == 1)
            self.assertEqual(capture.mean_value, 1)

    def test_depths_visits_seed_and_input_isolation(self):
        state = small_state()
        before = state.model_dump()
        config = MCTSConfig(iterations=16, tree_depth=2, rollout_depth=3, seed=7)
        result = MCTS(config).search(state, P1, GameParams())
        again = MCTS(config).search(state, P1, GameParams())
        self.assertEqual(result.action, again.action)
        self.assertEqual(result.root_actions, again.root_actions)
        self.assertEqual(result.iterations, 16)
        self.assertEqual(sum(a.visits for a in result.root_actions), 16)
        self.assertEqual(result.deepest_tree_tick, 2)
        self.assertLessEqual(result.deepest_simulated_tick, 5)
        self.assertEqual(state.model_dump(), before)

    def test_search_finds_immediate_winning_capture(self):
        state = GameState(planets=[planet(0, P1, 20), planet(1, P2, 5, 1)])
        result = MCTS(MCTSConfig(iterations=40, tree_depth=2, rollout_depth=0, seed=3)).search(
            state, P1, GameParams())
        self.assertEqual(result.action.destination_planet_id, 1)
        self.assertGreater(result.action.num_ships, 5)

    def test_player_two_search_uses_its_own_perspective(self):
        state = GameState(planets=[planet(0, P1, 5), planet(1, P2, 20, 1)])
        result = MCTS(MCTSConfig(iterations=40, tree_depth=2, rollout_depth=0, seed=3)).search(
            state, P2, GameParams())
        self.assertEqual(result.action.source_planet_id, 1)
        self.assertEqual(result.action.destination_planet_id, 0)

    def test_simulations_leave_live_statistics_unchanged(self):
        before = (ForwardModel.n_updates, ForwardModel.n_actions, ForwardModel.n_failed_actions)
        MCTS(MCTSConfig(iterations=4, tree_depth=2, rollout_depth=2)).search(
            small_state(), P1, GameParams())
        self.assertEqual(before, (ForwardModel.n_updates, ForwardModel.n_actions,
                                  ForwardModel.n_failed_actions))
        # Explicit opt-out also suppresses rejected-action counters.
        model = ForwardModel(small_state(), GameParams(), record_statistics=False)
        model.step({P1: Action(player_id=P1, source_planet_id=-1,
                               destination_planet_id=1, num_ships=3)})
        self.assertEqual(before, (ForwardModel.n_updates, ForwardModel.n_actions,
                                  ForwardModel.n_failed_actions))

    def test_soft_deadline_can_return_safely_before_first_iteration(self):
        config = MCTSConfig(time_limit_seconds=0.01)
        with patch("search.mcts.engine.time.perf_counter", side_effect=[0.0, 0.02, 0.02]):
            result = MCTS(config).search(small_state(), P1, GameParams())
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.action, Action.do_nothing())

    def test_exploration_constant_changes_selection(self):
        from search.mcts.engine import _Node
        good = _Node(small_state(), visits=90, total_value=72)
        rare = _Node(small_state(), visits=1, total_value=0.1)
        greedy, exploratory = MCTS(MCTSConfig(exploration_constant=0)), MCTS(MCTSConfig(exploration_constant=2))
        self.assertGreater(greedy._uct(good, 91), greedy._uct(rare, 91))
        self.assertGreater(exploratory._uct(rare, 91), exploratory._uct(good, 91))

    def test_terminal_and_no_launch_states(self):
        state = small_state()
        state.planets[0].n_ships = 0
        result = MCTS(MCTSConfig(iterations=3, rollout_depth=0)).search(state, P1, GameParams())
        self.assertEqual(result.action, Action.do_nothing())
        state.game_tick = 11
        result = MCTS().search(state, P1, GameParams(max_ticks=10))
        self.assertEqual(result.iterations, 0)

    def test_opponent_uses_pre_step_state(self):
        state = small_state()
        seen = []
        class Observer:
            def choose(self, observed, player, params):
                seen.append((player, observed.game_tick, observed.planets[0].n_ships))
                return Action.do_nothing()
        MCTS(MCTSConfig(iterations=1, tree_depth=1, rollout_depth=0),
             opponent_policy=Observer()).search(state, P1, GameParams())
        self.assertEqual(seen, [(P2, 0, 20)])

    def test_agent_and_unified_adapter(self):
        agent = MCTSAgent(MCTSConfig(iterations=3, tree_depth=1, rollout_depth=0, seed=4))
        adapter = as_unified(agent)
        adapter.prepare_to_play_as(P1, GameParams())
        state = small_state()
        observation = ObservationFactory.create(state, {P1, P2, NEUTRAL})
        adapter.get_action(observation)
        self.assertEqual(agent.last_result.iterations, 3)

    def test_custom_components_and_invalid_values(self):
        class OnlyWait:
            def generate(self, state, player, params):
                return [Action.do_nothing()]
        class BadValue:
            def evaluate(self, state, player, params):
                return math.nan
        class WaitOpponent:
            def choose(self, state, player, params):
                return Action.do_nothing()
        search = MCTS(MCTSConfig(iterations=1, rollout_depth=0), OnlyWait(), BadValue(), WaitOpponent())
        with self.assertRaises(ValueError):
            search.search(small_state(), P1, GameParams())

    def test_modern_options_fail_explicitly(self):
        for option in ({"selection": "puct"}, {"expansion": "progressive_widening"},
                       {"evaluation": "network"}, {"evaluation": "hybrid"},
                       {"priors": "network"}, {"priors": "heuristic"},
                       {"inference_batch_size": 4}, {"reuse_tree": True},
                       {"root_noise": True}, {"temperature": 1}, {"inference_cache": True}):
            with self.subTest(option=option), self.assertRaises(NotImplementedError):
                MCTSConfig(**option)
        for stub in (PUCTSelection, ProgressiveWidening, PyTorchPolicyValue, BatchedInference):
            with self.assertRaises(NotImplementedError):
                stub()
        for option in ({"iterations": 0}, {"tree_depth": 0}, {"rollout_depth": -1},
                       {"exploration_constant": math.nan}, {"exploration_constant": -1},
                       {"time_limit_seconds": 0}, {"selection": "unknown"}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                MCTSConfig(**option)


if __name__ == "__main__":
    unittest.main()
