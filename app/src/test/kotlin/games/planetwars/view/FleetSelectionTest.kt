package games.planetwars.view

import games.planetwars.core.*
import org.junit.jupiter.api.Test
import util.Vec2d
import kotlin.test.*

class FleetSelectionTest {
    private fun board(): GameState = GameState(listOf(
        Planet(Player.Player1, 20.0, Vec2d(100.0, 100.0), 0.5, 10.0,
            Transporter(Vec2d(200.0, 200.0), Vec2d(0.0, 3.0), Player.Player1, 0, 1, 5.5), 0),
        Planet(Player.Player2, 15.0, Vec2d(500.0, 100.0), 0.25, 10.0,
            Transporter(Vec2d(400.0, 200.0), Vec2d(-3.0, 0.0), Player.Player2, 1, 0, 7.0), 1),
    ))

    @Test
    fun `fleet picking follows rotated arrows at native scaled and letterboxed sizes`() {
        val state = board()
        for ((width, height) in listOf(640.0 to 480.0, 320.0 to 240.0,
                                      1280.0 to 960.0, 1000.0 to 480.0, 640.0 to 900.0)) {
            val viewport = BoardViewport.fit(640.0, 480.0, width, height)!!
            fun screen(x: Double, y: Double) = Vec2d(
                (x + viewport.offsetX) * viewport.scale, (y + viewport.offsetY) * viewport.scale)
            // First fleet faces down. Its center notch/label and front interior are clickable.
            assertEquals(0, viewport.fleetAt(state, screen(200.0, 200.0))!!.sourceIndex)
            assertEquals(0, viewport.fleetAt(state, screen(200.0, 208.0))!!.sourceIndex)
            assertNull(viewport.fleetAt(state, screen(220.0, 220.0)))
            assertNull(viewport.fleetAt(state, Vec2d(-1.0, -1.0)))
        }
    }

    @Test
    fun `click tolerance stays three screen pixels around arrow edges`() {
        val state = board()
        for (size in listOf(0.5, 1.0, 2.0)) {
            val viewport = BoardViewport.fit(640.0, 480.0, 640 * size, 480 * size)!!
            // Arrow tip is at y=216; two extra pixels hit, four do not.
            assertNotNull(viewport.fleetAt(state, Vec2d(200 * size, 216 * size + 2)))
            assertNull(viewport.fleetAt(state, Vec2d(200 * size, 216 * size + 4)))
        }
    }

    @Test
    fun `enemy fleets can be inspected without changing the board`() {
        val state = board()
        val viewport = BoardViewport.fit(640.0, 480.0, 640.0, 480.0)!!
        val fleet = viewport.fleetAt(state, Vec2d(400.0, 200.0))!!
        val selection = HumanFleetSelection()
        selection.select(fleet)
        assertEquals(Player.Player2, selection.current(state)!!.owner)
        assertEquals(0, selection.current(state)!!.destinationIndex)
        assertEquals(0, state.gameTick)
        assertEquals(15.0, state.planets[1].nShips)
        assertEquals(400.0, fleet.s.x)
        selection.clear()
        assertNull(selection.current(state))
    }

    @Test
    fun `selection follows snapshots and remains valid if source ownership changes`() {
        val original = board()
        val selection = HumanFleetSelection()
        selection.select(original.planets[0].transporter!!)
        val next = original.deepCopy()
        next.gameTick++
        next.planets[0].owner = Player.Player2
        val fleet = next.planets[0].transporter!!
        fleet.s += fleet.v
        assertEquals(203.0, selection.current(next)!!.s.y)
        assertEquals(Player.Player1, selection.current(next)!!.owner)
        assertEquals(1, selection.current(next)!!.destinationIndex)
    }

    @Test
    fun `arrival clears selection and does not select a subsequent launch`() {
        val state = board()
        val selection = HumanFleetSelection()
        val oldFleet = state.planets[0].transporter!!
        selection.select(oldFleet)
        state.planets[0].transporter = null
        assertNull(selection.current(state))
        state.planets[0].transporter = oldFleet.copy(s = Vec2d(100.0, 100.0))
        assertNull(selection.current(state))
    }

    @Test
    fun `replacement or invalid destination clears selection safely`() {
        for (replacement in listOf(
            board().planets[0].transporter!!.copy(nShips = 6.0),
            board().planets[0].transporter!!.copy(owner = Player.Player2),
            board().planets[0].transporter!!.copy(destinationIndex = 999),
        )) {
            val state = board()
            val selection = HumanFleetSelection()
            selection.select(state.planets[0].transporter!!)
            state.planets[0].transporter = replacement
            assertNull(selection.current(state))
        }
    }

    @Test
    fun `when arrows overlap the closest fleet is picked`() {
        val state = board()
        state.planets[1].transporter = state.planets[1].transporter!!.copy(s = Vec2d(201.0, 200.0))
        val viewport = BoardViewport.fit(640.0, 480.0, 640.0, 480.0)!!
        assertEquals(1, viewport.fleetAt(state, Vec2d(201.0, 200.0))!!.sourceIndex)
        assertEquals(0, viewport.fleetAt(state, Vec2d(200.0, 200.0))!!.sourceIndex)
    }
}
