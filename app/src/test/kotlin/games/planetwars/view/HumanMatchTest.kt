package games.planetwars.view

import games.planetwars.agents.Action
import games.planetwars.agents.HumanAgent
import games.planetwars.agents.PlanetWarsPlayer
import games.planetwars.core.*
import org.junit.jupiter.api.Test
import util.Vec2d
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.awt.image.BufferedImage
import xkg.jvm.EasyComponent
import xkg.jvm.XGraphicsJVM
import kotlin.test.*

private fun board() = GameState(listOf(
    Planet(Player.Player1, 20.0, Vec2d(100.0, 100.0), 0.5, 10.0, id = 0),
    Planet(Player.Player2, 15.0, Vec2d(300.0, 100.0), 0.25, 10.0, id = 1),
    Planet(Player.Neutral, 4.0, Vec2d(500.0, 100.0), 0.1, 10.0, id = 2),
))

private class TestOpponent(private val action: (GameState) -> Action = { Action.DO_NOTHING }) :
    PlanetWarsPlayer(), AutoCloseable {
    val calls = AtomicInteger()
    val closed = CountDownLatch(1)
    override fun getAgentType() = "Test opponent"
    override fun getAction(gameState: GameState): Action {
        calls.incrementAndGet()
        return action(gameState)
    }
    override fun close() { closed.countDown() }
}

class HumanMatchTest {
    private val params = GameParams(maxTicks = 20)
    private fun CompletableFuture<HumanMatchSnapshot>.await() = get(5, TimeUnit.SECONDS)
    private fun session(ai: () -> TestOpponent, gameParams: GameParams = params) =
        HumanMatchSession(gameParams, ai, ::board, dispatch = { it() })

    @Test
    fun `human agent consumes an order once and resets it between games`() {
        val human = HumanAgent()
        human.prepareToPlayAs(Player.Player1, params)
        val order = Action(Player.Player1, 0, 2, 5.25)
        human.submit(order)
        assertFailsWith<IllegalStateException> { human.submit(order) }
        assertEquals(order, human.getAction(board()))
        assertEquals(Action.DO_NOTHING, human.getAction(board()))
        human.submit(order)
        human.prepareToPlayAs(Player.Player1, params)
        assertEquals(Action.DO_NOTHING, human.getAction(board()))
    }

    @Test
    fun `initialization and idle snapshots never ask for an action or advance ticks`() {
        val ai = TestOpponent()
        session({ ai }).use { match ->
            match.newGame().await()
            repeat(100) { assertEquals(0, match.snapshot.state!!.gameTick) }
            assertEquals(0, ai.calls.get())
        }
    }

    @Test
    fun `inspecting a moving fleet never submits a human decision`() {
        val ai = TestOpponent()
        val initial = board()
        initial.planets[0].transporter = Transporter(Vec2d(200.0, 100.0), Vec2d(3.0, 0.0),
            Player.Player1, 0, 1, 5.5)
        HumanMatchSession(params, { ai }, { initial }, dispatch = { it() }).use { match ->
            match.newGame().await()
            val selection = HumanFleetSelection()
            selection.select(match.snapshot.state!!.planets[0].transporter!!)
            assertEquals(1, selection.current(match.snapshot.state!!)!!.destinationIndex)
            assertEquals(0, match.snapshot.state!!.gameTick)
            assertEquals(0, ai.calls.get())
            val next = match.pass().await().state!!
            assertEquals(203.0, selection.current(next)!!.s.x)
            selection.clear()
            assertEquals(1, match.snapshot.state!!.gameTick)
            assertEquals(1, ai.calls.get())
        }
    }

    @Test
    fun `each pass advances exactly one tick including growth`() {
        val ai = TestOpponent()
        session({ ai }).use { match ->
            match.newGame().await()
            repeat(3) { tick ->
                val state = match.pass().await().state!!
                assertEquals(tick + 1, state.gameTick)
                assertEquals(20.0 + (tick + 1) * 0.5, state.planets[0].nShips)
                assertNull(state.planets[0].transporter)
            }
            assertEquals(3, ai.calls.get())
        }
    }

    @Test
    fun `playback starts paused and returns to single step after pause`() {
        val ai = TestOpponent()
        session({ ai }).use { match ->
            val playback = HumanMatchPlayback(match)
            playback.play()
            assertFalse(playback.playing) // Cannot play before initialization.
            match.newGame().await()
            assertEquals(0, playback.tick().await().state!!.gameTick)
            assertEquals(0, ai.calls.get())
            playback.play()
            assertTrue(playback.playing)
            assertEquals(1, playback.tick().await().state!!.gameTick)
            assertEquals(2, playback.tick().await().state!!.gameTick)
            playback.pause()
            assertEquals(2, playback.tick().await().state!!.gameTick)
            assertEquals(3, match.pass().await().state!!.gameTick)
            assertEquals(4, match.launch(0, 2, 5.0).await().state!!.gameTick)
            assertEquals(4, playback.tick().await().state!!.gameTick)
            assertFalse(playback.playing)
        }
    }

    @Test
    fun `tick speed defaults to ten and can change without starting playback`() {
        session({ TestOpponent() }).use { match ->
            match.newGame().await()
            val playback = HumanMatchPlayback(match)
            assertEquals(10, playback.ticksPerSecond)
            assertEquals(100, playback.delayMillis)
            playback.setSpeed(20)
            assertEquals(50, playback.delayMillis)
            assertFalse(playback.playing)
            assertEquals(0, playback.tick().await().state!!.gameTick)
            playback.play()
            playback.setSpeed(5)
            assertEquals(200, playback.delayMillis)
            assertTrue(playback.playing)
            assertEquals(1, playback.tick().await().state!!.gameTick)
            assertFailsWith<IllegalArgumentException> { playback.setSpeed(0) }
            assertFailsWith<IllegalArgumentException> { playback.setSpeed(31) }
            assertEquals(5, playback.ticksPerSecond)
        }
    }

    @Test
    fun `playback stays active after manual launches and passes`() {
        session({ TestOpponent() }).use { match ->
            match.newGame().await()
            val playback = HumanMatchPlayback(match)
            playback.play()
            playback.observe(match.launch(0, 2, 5.0).await())
            assertTrue(playback.playing)
            playback.observe(match.pass().await())
            assertTrue(playback.playing)
            assertEquals(3, playback.tick().await().state!!.gameTick)
        }
    }

    @Test
    fun `playback skips busy pulses and pausing does not queue another tick`() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val ai = TestOpponent {
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            Action.DO_NOTHING
        }
        session({ ai }).use { match ->
            match.newGame().await()
            val playback = HumanMatchPlayback(match)
            playback.play()
            val first = playback.tick()
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            try {
                repeat(5) {
                    assertTrue(playback.tick().await().busy)
                    assertEquals(0, match.snapshot.state!!.gameTick)
                }
                playback.pause()
            } finally { release.countDown() }
            assertEquals(1, first.await().state!!.gameTick)
            assertEquals(1, playback.tick().await().state!!.gameTick)
            assertEquals(1, ai.calls.get())
        }
    }

    @Test
    fun `playback stops on opponent failure and can be explicitly retried`() {
        lateinit var playback: HumanMatchPlayback
        val attempts = AtomicInteger()
        HumanMatchSession(params,
            { TestOpponent { if (attempts.getAndIncrement() == 0) error("Server offline") else Action.DO_NOTHING } },
            ::board, dispatch = { it() }, onUpdate = { playback.observe(it) }).use { match ->
            playback = HumanMatchPlayback(match)
            match.newGame().await()
            playback.play()
            assertTrue(playback.tick().await().error)
            assertFalse(playback.playing)
            assertEquals(0, playback.tick().await().state!!.gameTick)
            playback.play()
            assertEquals(1, playback.tick().await().state!!.gameTick)
            assertTrue(playback.playing)
        }
    }

    @Test
    fun `playback stops at game end and a new game remains paused`() {
        lateinit var playback: HumanMatchPlayback
        HumanMatchSession(GameParams(maxTicks = 0), { TestOpponent() }, ::board,
            dispatch = { it() }, onUpdate = { playback.observe(it) }).use { match ->
            playback = HumanMatchPlayback(match)
            match.newGame().await()
            playback.play()
            assertTrue(playback.tick().await().gameOver)
            assertFalse(playback.playing)
            playback.play()
            assertFalse(playback.playing)
            assertEquals(1, playback.tick().await().state!!.gameTick)
            match.newGame().await()
            assertFalse(playback.playing)
            assertEquals(0, playback.tick().await().state!!.gameTick)
        }
    }

    @Test
    fun `launch uses exact count and opponent sees the pre-tick board`() {
        val ai = TestOpponent { state ->
            assertEquals(0, state.gameTick)
            assertEquals(20.0, state.planets[0].nShips)
            assertNull(state.planets[0].transporter)
            Action(Player.Player2, 1, 0, 3.0)
        }
        session({ ai }).use { match ->
            match.newGame().await()
            val state = match.launch(0, 2, 5.25).await().state!!
            assertEquals(1, state.gameTick)
            assertEquals(15.25, state.planets[0].nShips)
            assertEquals(5.25, state.planets[0].transporter!!.nShips)
            assertEquals(3.0, state.planets[1].transporter!!.nShips)
            assertEquals(1, ai.calls.get())
        }
    }

    @Test
    fun `invalid launches do not ask the opponent or advance time`() {
        val ai = TestOpponent()
        session({ ai }).use { match ->
            match.newGame().await()
            val invalid = listOf(Triple(0, 2, 0.0), Triple(0, 2, -1.0),
                Triple(0, 2, Double.NaN), Triple(0, 2, Double.POSITIVE_INFINITY),
                Triple(0, 2, 21.0), Triple(0, 0, 1.0), Triple(1, 0, 1.0),
                Triple(0, -1, 1.0), Triple(-1, 2, 1.0))
            invalid.forEach { (source, destination, amount) ->
                val result = match.launch(source, destination, amount).await()
                assertTrue(result.error)
                assertEquals(0, result.state!!.gameTick)
                assertEquals(20.0, result.state.planets[0].nShips)
            }
            assertEquals(0, ai.calls.get())
            assertEquals(1, match.pass().await().state!!.gameTick)
        }
    }

    @Test
    fun `busy source cannot launch again but can still pass`() {
        session({ TestOpponent() }).use { match ->
            match.newGame().await()
            match.launch(0, 2, 5.0).await()
            val rejected = match.launch(0, 1, 2.0).await()
            assertTrue(rejected.error)
            assertEquals(1, rejected.state!!.gameTick)
            assertEquals(2, match.pass().await().state!!.gameTick)
        }
    }

    @Test
    fun `friendly reinforcement is allowed`() {
        val state = board()
        state.planets[2].owner = Player.Player1
        HumanMatchSession(params, { TestOpponent() }, { state }, dispatch = { it() }).use { match ->
            match.newGame().await()
            val result = match.launch(0, 2, 3.0).await()
            assertFalse(result.error)
            assertEquals(2, result.state!!.planets[0].transporter!!.destinationIndex)
        }
    }

    @Test
    fun `duplicate input while opponent is thinking does not queue additional ticks`() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val ai = TestOpponent {
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            Action.DO_NOTHING
        }
        session({ ai }).use { match ->
            match.newGame().await()
            val first = match.pass()
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            try {
                assertTrue(match.snapshot.busy)
                assertTrue(match.pass().await().busy)
                assertTrue(match.launch(0, 2, 5.0).await().busy)
                assertEquals(0, match.snapshot.state!!.gameTick)
            } finally { release.countDown() }
            assertEquals(1, first.await().state!!.gameTick)
            assertEquals(1, ai.calls.get())
        }
    }

    @Test
    fun `opponent error preserves board clears pending order and allows retry`() {
        val created = AtomicInteger()
        val broken = TestOpponent { error("Test connection lost") }
        session({ if (created.getAndIncrement() == 0) broken else TestOpponent() }).use { match ->
            match.newGame().await()
            val failed = match.launch(0, 2, 5.0).await()
            assertTrue(failed.error)
            assertEquals(0, failed.state!!.gameTick)
            assertEquals(20.0, failed.state.planets[0].nShips)
            assertNull(failed.state.planets[0].transporter)
            assertTrue(broken.closed.await(5, TimeUnit.SECONDS))
            val retried = match.pass().await()
            assertFalse(retried.error)
            assertEquals(1, retried.state!!.gameTick)
            assertNull(retried.state.planets[0].transporter)
        }
    }

    @Test
    fun `terminal board stays frozen until new game and agents are recreated`() {
        val created = AtomicInteger()
        session({ created.incrementAndGet(); TestOpponent() }, GameParams(maxTicks = 0)).use { match ->
            match.newGame().await()
            val finished = match.pass().await()
            assertTrue(finished.gameOver)
            assertEquals("You win!", finished.result)
            assertEquals(1, match.pass().await().state!!.gameTick)
            assertEquals(1, match.launch(0, 2, 5.0).await().state!!.gameTick)
            val fresh = match.newGame().await()
            assertEquals(0, fresh.state!!.gameTick)
            assertFalse(fresh.gameOver)
            assertEquals(2, created.get())
        }
    }

    @Test
    fun `closing is idempotent and releases the opponent`() {
        val ai = TestOpponent()
        val match = session({ ai })
        match.newGame().await()
        match.close()
        match.close()
        assertTrue(ai.closed.await(5, TimeUnit.SECONDS))
        assertEquals(0, match.pass().await().state!!.gameTick)
    }

    @Test
    fun `closing during an opponent request cancels the decision without advancing time`() {
        val entered = CountDownLatch(1)
        val ai = TestOpponent {
            entered.countDown()
            CountDownLatch(1).await()
            Action.DO_NOTHING
        }
        val match = session({ ai })
        try {
            match.newGame().await()
            val pending = match.pass()
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            match.close()
            assertTrue(pending.isCancelled)
            assertTrue(ai.closed.await(5, TimeUnit.SECONDS))
            assertEquals(0, match.snapshot.state!!.gameTick)
        } finally { match.close() }
    }

    @Test
    fun `failed initialization can be retried with new game`() {
        val attempts = AtomicInteger()
        HumanMatchSession(params,
            { if (attempts.getAndIncrement() == 0) error("Server offline") else TestOpponent() },
            ::board, dispatch = { it() }).use { match ->
            val failed = match.newGame().await()
            assertTrue(failed.error)
            assertNull(failed.state)
            assertFalse(failed.busy)
            val retried = match.newGame().await()
            assertFalse(retried.error)
            assertEquals(0, retried.state!!.gameTick)
            assertEquals(1, match.pass().await().state!!.gameTick)
        }
    }

    @Test
    fun `selection clears only when source becomes busy or changes owner`() {
        val selection = HumanPlanetSelection()
        val state = board()
        assertNotNull(selection.select(state, 1))
        assertNull(selection.sourceId)
        assertNull(selection.select(state, 0))
        selection.reconcile(state)
        assertEquals(0, selection.sourceId)
        state.planets[0].transporter = Transporter(Vec2d(), Vec2d(), Player.Player1, 0, 2, 1.0)
        selection.reconcile(state)
        assertNull(selection.sourceId)
        assertNotNull(selection.select(state, 0))
        state.planets[0].transporter = null
        selection.select(state, 0)
        state.planets[0].owner = Player.Player2
        selection.reconcile(state)
        assertNull(selection.sourceId)
        state.planets[0].owner = Player.Player1
        selection.select(state, 0)
        selection.clear()
        assertNull(selection.sourceId)
        assertEquals(0, state.gameTick)
    }

    @Test
    fun `viewport hit testing matches native scaled and letterboxed drawing`() {
        val state = board()
        for ((width, height) in listOf(640.0 to 480.0, 1280.0 to 960.0,
                                      960.0 to 640.0, 1000.0 to 480.0, 640.0 to 900.0)) {
            val viewport = BoardViewport.fit(640.0, 480.0, width, height)!!
            val point = Vec2d((100.0 + viewport.offsetX) * viewport.scale,
                (100.0 + viewport.offsetY) * viewport.scale)
            assertEquals(0, viewport.planetAt(state, point)!!.id)
            val world = viewport.screenToWorld(point)!!
            assertEquals(100.0, world.x, 1e-8)
            assertEquals(100.0, world.y, 1e-8)
            assertNull(viewport.planetAt(state, Vec2d(-1.0, -1.0)))
        }
        assertNull(BoardViewport.fit(640.0, 480.0, 0.0, 480.0))
        assertNull(BoardViewport.fit(640.0, 480.0, 1000.0, 480.0)!!.screenToWorld(Vec2d(10.0, 100.0)))
        assertNull(BoardViewport.fit(640.0, 480.0, 640.0, 900.0)!!.screenToWorld(Vec2d(100.0, 10.0)))
    }

    @Test
    fun `enlarged markers are clickable outside physical radius at every window scale`() {
        val state = board()
        for ((width, height) in listOf(640.0 to 480.0, 1280.0 to 960.0,
                                      960.0 to 640.0, 1000.0 to 480.0, 640.0 to 900.0)) {
            val viewport = BoardViewport.fit(640.0, 480.0, width, height)!!
            val edge = Vec2d((114.0 + viewport.offsetX) * viewport.scale,
                (100.0 + viewport.offsetY) * viewport.scale)
            assertEquals(0, viewport.planetAt(state, edge)!!.id)
            assertNull(viewport.planetAt(state, edge, radiusScale = 1.0))
            val outside = Vec2d((116.0 + viewport.offsetX) * viewport.scale, edge.y)
            assertNull(viewport.planetAt(state, outside))
        }
        assertEquals(10.0, state.planets[0].radius)
    }

    @Test
    fun `overlapping visual markers select the closest center`() {
        val state = GameState(listOf(
            Planet(Player.Player1, 20.0, Vec2d(100.0, 100.0), 0.5, 10.0, id = 0),
            Planet(Player.Player2, 15.0, Vec2d(125.0, 100.0), 0.25, 10.0, id = 1),
        ))
        val viewport = BoardViewport.fit(640.0, 480.0, 640.0, 480.0)!!
        assertEquals(0, viewport.planetAt(state, Vec2d(111.0, 100.0))!!.id)
        assertEquals(1, viewport.planetAt(state, Vec2d(114.0, 100.0))!!.id)
    }

    @Test
    fun `rendering and resizing a paused board never advance the session`() {
        val ai = TestOpponent()
        session({ ai }).use { match ->
            match.newGame().await()
            val view = GameView(match.snapshot.state!!, params, paused = true)
            val component = EasyComponent()
            val graphics = XGraphicsJVM(component)
            val image = BufferedImage(1000, 900, BufferedImage.TYPE_INT_RGB)
            graphics.graphics2D = image.createGraphics()
            try {
                for ((width, height) in listOf(640 to 480, 1000 to 480, 640 to 900)) {
                    component.setSize(width, height)
                    repeat(5) { view.paint(graphics) }
                }
            } finally { graphics.graphics2D!!.dispose() }
            assertEquals(0, view.gameState.gameTick)
            assertEquals(15.0, view.displayRadius(view.gameState.planets[0]))
            assertEquals(10.0, view.gameState.planets[0].radius)
            assertEquals(0, match.snapshot.state!!.gameTick)
            assertEquals(0, ai.calls.get())
        }
    }
}
