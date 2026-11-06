package games.planetwars.view

import games.planetwars.agents.RemoteAgent
import games.planetwars.core.*
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.Test
import util.Vec2d
import java.util.concurrent.TimeUnit
import kotlin.test.*

/** Opt in with HUMAN_MCTS_TEST_PORT pointing at a running examples.mcts_server. */
class HumanMctsIntegrationTest {
    @Test
    fun `human session interoperates with Python MCTS and can restart the remote agent`() {
        val port = System.getenv("HUMAN_MCTS_TEST_PORT")?.toIntOrNull()
        assumeTrue(port != null, "Set HUMAN_MCTS_TEST_PORT to run the Python MCTS integration test")
        val params = GameParams()
        HumanMatchSession(params,
            { RemoteAgent("MCTSAgent", port!!, requestTimeoutMillis = 30_000, strictResponses = true) },
            { GameState(listOf(
                Planet(Player.Player1, 20.0, Vec2d(100.0, 100.0), 0.5, 10.0, id = 0),
                Planet(Player.Player2, 15.0, Vec2d(300.0, 100.0), 0.25, 10.0, id = 1),
                Planet(Player.Neutral, 4.0, Vec2d(500.0, 100.0), 0.1, 10.0, id = 2),
            )) }, dispatch = { it() }).use { match ->
            val initial = match.newGame().get(40, TimeUnit.SECONDS)
            assertFalse(initial.error, initial.message)
            assertEquals(0, initial.state!!.gameTick)
            val passed = match.pass().get(40, TimeUnit.SECONDS)
            assertFalse(passed.error, passed.message)
            assertEquals(1, passed.state!!.gameTick)
            val launched = match.launch(0, 2, 5.5).get(40, TimeUnit.SECONDS)
            assertFalse(launched.error, launched.message)
            assertEquals(2, launched.state!!.gameTick)
            assertEquals(5.5, launched.state.planets[0].transporter!!.nShips)
            val fresh = match.newGame().get(40, TimeUnit.SECONDS)
            assertFalse(fresh.error, fresh.message)
            assertEquals(0, fresh.state!!.gameTick)
            assertNull(fresh.state.planets[0].transporter)
            assertEquals(1, match.pass().get(40, TimeUnit.SECONDS).state!!.gameTick)
        }
    }
}
