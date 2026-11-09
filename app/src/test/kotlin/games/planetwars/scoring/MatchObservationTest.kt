package games.planetwars.scoring

import games.planetwars.agents.Action
import games.planetwars.agents.PlanetWarsPlayer
import games.planetwars.core.*
import games.planetwars.runners.GameRunner
import games.planetwars.view.HumanMatchSession
import org.junit.jupiter.api.Test
import util.Vec2d
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.*

class MatchObservationTest {
    private class WaitingAgent : PlanetWarsPlayer() {
        override fun getAgentType() = "Waiting"
        override fun getAction(gameState: GameState) = Action.DO_NOTHING
    }
    private class Observer : MatchObserver {
        val events = mutableListOf<String>()
        val closed = CountDownLatch(1)
        override fun started(params: GameParams, player1: String, player2: String, state: GameState) {
            events.add("start:${state.gameTick}")
        }
        override fun advanced(state: GameState) { events.add("tick:${state.gameTick}") }
        override fun ended(state: GameState, aborted: Boolean) { events.add("end:${state.gameTick}:$aborted") }
        override fun close() { closed.countDown() }
    }
    @Test
    fun `human observation records initial ticks terminal and aborted restart without idle events`() {
        val observer = Observer()
        val params = GameParams(maxTicks = 1)
        val state = GameState(listOf(
            Planet(Player.Player1, 20.0, Vec2d(100.0, 100.0), .1, 10.0, id = 0),
            Planet(Player.Player2, 10.0, Vec2d(300.0, 100.0), .1, 10.0, id = 1),
        ))
        val session = HumanMatchSession(params, { WaitingAgent() }, { state }, dispatch = { it() }, observer = observer)
        session.newGame().get(5, TimeUnit.SECONDS)
        session.launch(0, 1, 0.0).get(5, TimeUnit.SECONDS) // Invalid: no tick or observation.
        session.pass().get(5, TimeUnit.SECONDS)
        session.pass().get(5, TimeUnit.SECONDS)
        assertEquals(listOf("start:0", "tick:1", "tick:2", "end:2:false"), observer.events)
        session.newGame().get(5, TimeUnit.SECONDS)
        session.close()
        assertTrue(observer.closed.await(5, TimeUnit.SECONDS))
        assertEquals(listOf("start:0", "tick:1", "tick:2", "end:2:false", "start:0", "end:0:true"), observer.events)
    }

    @Test
    fun `spectator runner emits terminal once and marks replaced games aborted`() {
        val observer = Observer()
        val runner = GameRunner(WaitingAgent(), WaitingAgent(),
            GameParams(numPlanets = 2, initialNeutralRatio = 0.0, maxTicks = 0), matchObserver = observer)
        runner.stepGame()
        runner.stepGame()
        runner.newGame()
        runner.finishObservation()
        assertEquals(listOf("start:0", "tick:1", "end:1:false", "start:0", "end:0:true"), observer.events)
    }
}
