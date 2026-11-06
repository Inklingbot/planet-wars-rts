package games.planetwars.view

import games.planetwars.core.*
import org.junit.jupiter.api.Test
import util.Vec2d
import javax.swing.SwingUtilities
import kotlin.test.*

class HumanMatchControlsTest {
    private fun state() = GameState(listOf(
        Planet(Player.Player1, 37.92345, Vec2d(100.0, 100.0), 0.1, 10.0, id = 0),
        Planet(Player.Player1, 20.23456, Vec2d(200.0, 100.0), 0.1, 10.0, id = 1),
        Planet(Player.Player2, 15.0, Vec2d(300.0, 100.0), 0.1, 10.0, id = 2),
    ))

    @Test
    fun `playback bar starts at ten ticks per second and readout follows slider`() {
        SwingUtilities.invokeAndWait {
            val bar = HumanPlaybackBar()
            assertEquals(10, bar.speed.value)
            assertEquals("10 ticks/s", bar.speedReadout.text)
            bar.speed.value = 25
            assertEquals("25 ticks/s", bar.speedReadout.text)
            assertEquals("Pass one tick", bar.pass.accessibleContext.accessibleName)
            assertNotNull(bar.pass.icon)
        }
    }

    @Test
    fun `play pause icons and enabled states follow session availability`() {
        SwingUtilities.invokeAndWait {
            val bar = HumanPlaybackBar()
            val ready = HumanMatchSnapshot(state())
            bar.refresh(ready, playing = false)
            assertTrue(bar.playPause.isEnabled)
            assertEquals("Play", bar.playPause.accessibleContext.accessibleName)
            val playIcon = bar.playPause.icon
            bar.refresh(ready.copy(busy = true), playing = true)
            assertTrue(bar.playPause.isEnabled)
            assertEquals("Pause", bar.playPause.accessibleContext.accessibleName)
            assertNotSame(playIcon, bar.playPause.icon)
            assertFalse(bar.pass.isEnabled)
            bar.refresh(ready.copy(busy = true), playing = false)
            assertFalse(bar.playPause.isEnabled)
            bar.refresh(ready.copy(gameOver = true), playing = false)
            assertFalse(bar.pass.isEnabled)
        }
    }

    @Test
    fun `selecting a source never auto fills half its fractional garrison`() {
        SwingUtilities.invokeAndWait {
            val panel = HumanOrderPanel()
            panel.refresh(HumanMatchSnapshot(state()), sourceId = 0, inspected = null)
            assertEquals("", panel.amount.text)
            assertTrue(panel.amount.isEnabled)
            panel.refresh(HumanMatchSnapshot(state()), sourceId = 1, inspected = null)
            assertEquals("", panel.amount.text)
        }
    }

    @Test
    fun `typed ship count survives snapshots source changes and inspection`() {
        SwingUtilities.invokeAndWait {
            val panel = HumanOrderPanel()
            val state = state()
            panel.amount.text = "12.5"
            panel.refresh(HumanMatchSnapshot(state), sourceId = 0, inspected = null)
            state.gameTick++
            state.planets[0].nShips += 0.1
            panel.refresh(HumanMatchSnapshot(state, busy = true), sourceId = 0, inspected = null)
            assertFalse(panel.amount.isEnabled)
            panel.refresh(HumanMatchSnapshot(state), sourceId = 1, inspected = null)
            assertEquals("12.5", panel.amount.text)
            panel.refresh(HumanMatchSnapshot(state), sourceId = null, inspected = null)
            assertEquals("12.5", panel.amount.text)
            val fleet = Transporter(Vec2d(), Vec2d(3.0, 0.0), Player.Player1, 0, 2, 4.0)
            panel.refresh(HumanMatchSnapshot(state), sourceId = null, inspected = fleet)
            assertEquals("12.5", panel.amount.text)
            assertFalse(panel.amount.isEnabled)
            assertTrue(panel.clearSelection.isEnabled)
        }
    }
}
