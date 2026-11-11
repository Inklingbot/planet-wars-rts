import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

from websockets import connect, serve
from core.game_state import GameState, GameParams, Planet, Player, Transporter, Vec2d
from scoring.evaluators import Comparison
from scoring.heuristics import (BoardStrengthEvaluator, ShipAdvantageEvaluator, ThreeFactorAdvantageEvaluator,
                        ThreeFactorWeights, team_stats)
from scoring.server import ScoringService
from scoring.export import export_rows, read_history, write_csv, plot_rows
from search.mcts.engine import MCTS


def state():
    return GameState(planets=[
        Planet(id=0, owner=Player.Player1, n_ships=20, position=Vec2d(x=100), growth_rate=.1, radius=10),
        Planet(id=1, owner=Player.Player2, n_ships=10, position=Vec2d(x=300), growth_rate=.1, radius=10),
        Planet(id=2, owner=Player.Neutral, n_ships=4, position=Vec2d(x=500), growth_rate=.1, radius=10),
    ])


def config():
    return {"comparison": {"A": "ships", "B": "mcts"}, "evaluators": {
        "ships": {"type": "ship_advantage", "label": "Ship Advantage"},
        "mcts": {"type": "mcts_board_strength", "label": "MCTS Strength"}}}


def history(comparison, boards):
    records = [{"event": "game_start", "gameId": "game", "params": GameParams().model_dump(by_alias=True)},
               {"event": "metadata", "gameId": "game", "metadata": comparison.metadata}]
    for board in boards:
        records.append({"event": "tick", "gameId": "game", "tick": board.game_tick,
                        "state": board.model_dump(by_alias=True), "stats": team_stats(board)})
    return records


class TestComparison(unittest.TestCase):
    def test_ship_advantage_includes_fleets_by_owner(self):
        board = state()
        board.planets[1].transporter = Transporter(s=Vec2d(x=200), v=Vec2d(x=3), owner=Player.Player1,
                                                  source_index=1, destination_index=2, n_ships=5.5)
        result = team_stats(board)
        self.assertEqual(result['Player1'], {"planetCount": 1, "stationedShips": 20,
                                             "shipsInFlight": 5.5, "totalShips": 25.5})
        evaluator = ShipAdvantageEvaluator()
        red = evaluator.evaluate(board, Player.Player1, GameParams())
        blue = evaluator.evaluate(board, Player.Player2, GameParams())
        self.assertAlmostEqual(red, 25.5 / 35.5)
        self.assertAlmostEqual(red + blue, 1)

    def test_zero_totals_are_neutral(self):
        board = state()
        board.planets[0].n_ships = board.planets[1].n_ships = 0
        self.assertEqual(ShipAdvantageEvaluator().evaluate(board, Player.Player1, GameParams()), .5)

    def test_display_matches_mcts_and_does_not_mutate_board(self):
        board = state()
        before = board.model_dump()
        comparison = Comparison(config())
        result = comparison.score(board, GameParams())
        for player in (Player.Player1, Player.Player2):
            self.assertEqual(result['scores'][player.value]['B'], MCTS().evaluator.evaluate(board, player, GameParams()))
        self.assertEqual(before, board.model_dump())

    def test_slots_can_select_the_same_evaluator(self):
        settings = config()
        settings['comparison']['B'] = 'ships'
        values = Comparison(settings).score(state(), GameParams())['scores']
        self.assertEqual(values['Player1']['A'], values['Player1']['B'])

    def test_custom_profiles_and_restored_weights(self):
        settings = config()
        settings['evaluators']['mcts'] = {"type": "board_strength", "weights": {
            "planets": 0, "growth": 0, "ships": 1, "expected_captures": 0, "planets_over_10": 0}}
        original = Comparison(settings)
        restored = Comparison(original.metadata['config'], restore=True)
        self.assertEqual(original.metadata['configHash'], restored.metadata['configHash'])
        self.assertEqual(original.score(state(), GameParams()), restored.score(state(), GameParams()))

    def test_invalid_names_and_options_fail(self):
        settings = config()
        settings['comparison']['A'] = 'unknown'
        with self.assertRaises(ValueError): Comparison(settings)
        settings = config()
        settings['evaluators']['ships']['type'] = 'unknown'
        with self.assertRaises(ValueError): Comparison(settings)
        settings = config()
        settings['evaluators']['mcts']['weights'] = {'ships': 2}
        with self.assertRaises(ValueError): Comparison(settings)

    def test_terminal_profiles_use_outcomes(self):
        board = state()
        board.game_tick = 2001
        scores = Comparison(config()).score(board, GameParams())['scores']
        self.assertEqual(scores['Player1']['A'], 1)
        self.assertEqual(scores['Player1']['B'], 1)
        self.assertEqual(scores['Player2'], {'A': 0, 'B': 0})

    def test_all_standalone_heuristics_agree_on_terminal_values(self):
        evaluators = (ShipAdvantageEvaluator(), ThreeFactorAdvantageEvaluator(), BoardStrengthEvaluator())
        for end_by_elimination in (False, True):
            for ships1, ships2, expected in ((20, 10, 1), (10, 20, 0), (10, 10, .5)):
                board = state()
                board.game_tick = 0 if end_by_elimination else 2001
                board.planets[0].n_ships = ships1
                board.planets[1].n_ships = ships2
                if end_by_elimination:
                    board.planets[1].owner = Player.Player1
                    expected = 1
                # The existing winner rule excludes ships still in flight.
                board.planets[2].transporter = Transporter(
                    s=Vec2d(x=400), v=Vec2d(x=3), owner=Player.Player2,
                    source_index=2, destination_index=0, n_ships=1000)
                before = board.model_dump()
                for evaluator in evaluators:
                    for player, value in ((Player.Player1, expected), (Player.Player2, 1 - expected)):
                        with self.subTest(evaluator=type(evaluator).__name__, elimination=end_by_elimination,
                                          ships=(ships1, ships2), player=player):
                            self.assertEqual(evaluator.evaluate(board, player, GameParams()), value)
                self.assertEqual(board.model_dump(), before)

    def test_version_one_histories_retain_original_terminal_scores(self):
        settings = config()
        settings['evaluators']['ships']['version'] = 1
        settings['evaluators']['mcts'] = {'type': 'three_factor_advantage', 'version': 1,
                                         'weights': {'ships': .3, 'planets': .4, 'growth': .3}}
        legacy = Comparison(settings)
        restored = Comparison(legacy.config, restore=True)
        board = state()
        board.game_tick = 2001
        self.assertEqual(legacy.metadata['configHash'], restored.metadata['configHash'])
        self.assertEqual(legacy.score(board, GameParams()), restored.score(board, GameParams()))
        rows, _ = export_rows(history(legacy, [board]), rescore_missing=True)
        self.assertAlmostEqual(rows[0]['red_A'], 2 / 3)
        self.assertAlmostEqual(rows[0]['red_B'], .3 * (2 / 3) + .4 / 3 + .3 * .5)
        settings['evaluators']['ships'].pop('version')
        settings['evaluators']['mcts'].pop('version')
        current = Comparison(settings)
        self.assertNotEqual(current.metadata['configHash'], legacy.metadata['configHash'])
        self.assertEqual(current.metadata['evaluators']['A']['version'], 2)
        self.assertEqual(current.metadata['evaluators']['B']['version'], 2)
        self.assertEqual(current.score(board, GameParams())['scores']['Player1'], {'A': 1, 'B': 1})


class TestThreeFactorAdvantage(unittest.TestCase):
    def test_average_uses_all_planets_and_excludes_neutral_ships_and_growth(self):
        board = state()
        board.planets[0].growth_rate = .3
        board.planets[2].n_ships = 1000
        board.planets[2].growth_rate = 10
        # A red fleet remains red even though its source planet is now blue.
        board.planets[1].transporter = Transporter(
            s=Vec2d(x=200), v=Vec2d(x=3), owner=Player.Player1,
            source_index=1, destination_index=2, n_ships=5.5)
        before = board.model_dump()
        evaluator = ThreeFactorAdvantageEvaluator()
        red = evaluator.evaluate(board, Player.Player1, GameParams())
        blue = evaluator.evaluate(board, Player.Player2, GameParams())
        self.assertAlmostEqual(red, (25.5 / 35.5 + 1 / 3 + .75) / 3)
        self.assertAlmostEqual(blue, (10 / 35.5 + 1 / 3 + .25) / 3)
        self.assertAlmostEqual(red + blue, 8 / 9)
        self.assertEqual(before, board.model_dump())

    def test_capturing_neutral_planet_increases_ownership_share(self):
        board = state()
        board.planets[2].n_ships = board.planets[2].growth_rate = 0
        evaluator = ThreeFactorAdvantageEvaluator()
        before = evaluator.evaluate(board, Player.Player1, GameParams())
        board.planets[2].owner = Player.Player1
        self.assertAlmostEqual(evaluator.evaluate(board, Player.Player1, GameParams()) - before, 1 / 9)

    def test_zero_totals_empty_board_and_full_ownership(self):
        board = state()
        for planet in board.planets:
            planet.n_ships = planet.growth_rate = 0
        evaluator = ThreeFactorAdvantageEvaluator()
        self.assertAlmostEqual(evaluator.evaluate(board, Player.Player1, GameParams()), (0.5 + 1 / 3 + 0.5) / 3)
        self.assertEqual(evaluator.evaluate(GameState(planets=[]), Player.Player1, GameParams()), .5)
        for planet in board.planets:
            planet.owner = Player.Player1
            planet.n_ships = 1
            planet.growth_rate = .1
        self.assertEqual(evaluator.evaluate(board, Player.Player1, GameParams()), 1)
        self.assertEqual(evaluator.evaluate(board, Player.Player2, GameParams()), 0)

    def test_default_comparison_restoration_export_and_terminal_formula(self):
        comparison = Comparison.load()
        self.assertEqual(comparison.slots, {'A': 'ship_advantage', 'B': 'three_factor_advantage'})
        restored = Comparison(comparison.config, restore=True)
        self.assertEqual(comparison.metadata['configHash'], restored.metadata['configHash'])
        board = state()
        nonterminal = comparison.score(board, GameParams())
        expected = .3 * (2 / 3) + .4 * (1 / 3) + .3 * .5
        self.assertAlmostEqual(nonterminal['scores']['Player1']['B'], expected)
        board.game_tick = 2001
        scores = comparison.score(board, GameParams())
        self.assertEqual(scores['scores']['Player1']['A'], 1)
        self.assertEqual(scores['scores']['Player1']['B'], 1)
        self.assertEqual(scores, restored.score(board, GameParams()))
        rows, _ = export_rows(history(comparison, [board]), rescore_missing=True)
        self.assertEqual(rows[0]['red_B'], 1)
        self.assertEqual(rows[0]['heuristic_B'], 'three_factor_advantage')

    def test_planet_weight_and_legacy_profiles(self):
        board = state()
        board.planets[2].n_ships = board.planets[2].growth_rate = 0
        evaluator = ThreeFactorAdvantageEvaluator(ThreeFactorWeights(ships=.3, planets=.4, growth=.3))
        before = evaluator.evaluate(board, Player.Player1, GameParams())
        board.planets[2].owner = Player.Player1
        self.assertAlmostEqual(evaluator.evaluate(board, Player.Player1, GameParams()) - before, .4 / 3)
        scaled = ThreeFactorAdvantageEvaluator(ThreeFactorWeights(ships=3, planets=4, growth=3))
        self.assertAlmostEqual(scaled.evaluate(board, Player.Player1, GameParams()),
                               evaluator.evaluate(board, Player.Player1, GameParams()))
        settings = config()
        settings['evaluators']['mcts'] = {'type': 'three_factor_advantage'}
        legacy = Comparison(settings)
        restored = Comparison(legacy.config, restore=True)
        self.assertEqual(legacy.metadata['configHash'], restored.metadata['configHash'])
        self.assertAlmostEqual(restored.score(state(), GameParams())['scores']['Player1']['B'], .5)

    def test_invalid_three_factor_weights(self):
        for weights in ({'ships': -1}, {'planets': float('nan')}, {'growth': float('inf')},
                        {'ships': 0, 'planets': 0, 'growth': 0}):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                ThreeFactorWeights(**weights)


class TestHistoryExport(unittest.TestCase):
    def test_missing_scores_are_blank_and_can_be_rescored(self):
        comparison = Comparison(config())
        records = history(comparison, [state()])
        rows, _ = export_rows(records)
        self.assertIsNone(rows[0]['red_A'])
        self.assertEqual(rows[0]['red_total_ships'], 20)
        filled, metadata = export_rows(records, rescore_missing=True)
        self.assertAlmostEqual(filled[0]['red_A'], 2 / 3)
        self.assertEqual(filled[0]['score_status'], 'rescored')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out.csv'
            write_csv(rows, output)
            self.assertIn('missing', output.read_text())
            import importlib.util
            if importlib.util.find_spec('matplotlib'):
                plot_rows(filled, metadata, Path(directory) / 'plot.png')
                self.assertGreater((Path(directory) / 'plot.png').stat().st_size, 1000)

    def test_completed_score_records_are_joined_by_tick(self):
        comparison = Comparison(config())
        first, second = state(), state()
        second.game_tick = 1
        second.planets[0].n_ships = 25
        records = history(comparison, [first, second])
        records.append({"event": "scores", "gameId": "game", "tick": 1,
                        "configHash": comparison.metadata['configHash'],
                        **comparison.score(second, GameParams())})
        rows, _ = export_rows(records)
        self.assertEqual([r['tick'] for r in rows], [0, 1])
        self.assertIsNone(rows[0]['blue_B'])
        self.assertAlmostEqual(rows[1]['red_A'], 25 / 35)
        self.assertEqual(rows[1]['red_total_ships'], 25)

    def test_mixed_games_configs_and_duplicate_ticks_are_rejected(self):
        comparison = Comparison(config())
        records = history(comparison, [state()])
        mixed = copy.deepcopy(records)
        mixed[-1]['gameId'] = 'other'
        with self.assertRaises(ValueError): export_rows(mixed)
        duplicate = records + [records[-1]]
        with self.assertRaises(ValueError): export_rows(duplicate)
        records.append({'event': 'scores', 'gameId': 'game', 'tick': 0, 'configHash': 'wrong'})
        with self.assertRaises(ValueError): export_rows(records)

    def test_unresolved_history_requires_explicit_rescore_config(self):
        records = [r for r in history(Comparison(config()), [state()]) if r['event'] != 'metadata']
        with self.assertRaises(ValueError): export_rows(records, rescore_missing=True)

    def test_truncated_final_line_can_be_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'game.jsonl'
            path.write_text('{"event":"test"}\n{"event":', encoding='utf-8')
            self.assertEqual(read_history(path), [{'event': 'test'}])


class TestScoringService(unittest.IsolatedAsyncioTestCase):
    async def test_real_websocket_requests_and_error_recovery(self):
        comparison = Comparison(config())
        service = ScoringService(comparison)
        async with serve(service.handler, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with connect(f'ws://127.0.0.1:{port}') as socket:
                await socket.send('{bad json')
                self.assertEqual(json.loads(await socket.recv())['status'], 'error')
                await socket.send(json.dumps({'type': 'describe'}))
                self.assertEqual(json.loads(await socket.recv())['metadata']['configHash'], comparison.metadata['configHash'])
                request = {'type': 'score', 'requestId': 'req', 'gameId': 'game', 'tick': 0,
                           'configHash': comparison.metadata['configHash'], 'params': GameParams().model_dump(by_alias=True),
                           'state': state().model_dump(by_alias=True)}
                await socket.send(json.dumps(request))
                result = json.loads(await socket.recv())
                self.assertEqual(result['status'], 'ok')
                self.assertAlmostEqual(result['scores']['Player1']['A'], 2 / 3)
                request['tick'] = 5
                await socket.send(json.dumps(request))
                self.assertEqual(json.loads(await socket.recv())['status'], 'error')
                request['tick'] = 0
                request['configHash'] = 'other'
                await socket.send(json.dumps(request))
                self.assertEqual(json.loads(await socket.recv())['status'], 'error')
