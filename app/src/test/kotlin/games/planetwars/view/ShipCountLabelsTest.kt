package games.planetwars.view

import org.junit.jupiter.api.Test
import kotlin.test.*

class ShipCountLabelsTest {
    @Test
    fun `positive fractions are never displayed as zero`() {
        assertEquals("0", formatShipCount(0.0))
        assertEquals("0.5", formatShipCount(0.5))
        assertEquals("0.01", formatShipCount(0.01))
        assertEquals("<0.01", formatShipCount(0.005))
        assertEquals("<0.01", formatShipCount(Double.MIN_VALUE))
        assertEquals("<0.0001", formatShipCount(0.00001, 4))
        assertEquals("1", formatShipCount(1.0))
        assertEquals("12.35", formatShipCount(12.345))
    }
}
