package games.planetwars.view

import games.planetwars.core.GameState
import games.planetwars.core.Player
import games.planetwars.core.Transporter
import util.Vec2d
import xkg.gui.XColor
import xkg.gui.XPoly
import xkg.gui.XStyle

/** Rendering and picking use the same rotated arrow geometry. */
object FleetMarker {
    fun shape(fleet: Transporter, color: XColor = XColor.white): XPoly = XPoly(
        fleet.s, arrayListOf(Vec2d(-16.0, 16.0), Vec2d(0.0, 0.0),
            Vec2d(-16.0, -16.0), Vec2d(16.0, 0.0)),
        XStyle(fg = color, fill = true, stroke = false), rotation = fleet.v.angle(),
    )

    fun contains(fleet: Transporter, point: Vec2d, padding: Double): Boolean {
        val shape = shape(fleet)
        if (shape.contains(point)) return true
        // Include edges and the arrow's center notch, with a small screen-space
        // tolerance so clicking the central ship-count label also works.
        val local = (point - fleet.s).rotatedBy(-shape.rotation)
        return shape.points.indices.any { index ->
            val start = shape.points[index]
            val end = shape.points[(index + 1) % shape.points.size]
            val edge = end - start
            val lengthSquared = edge.x * edge.x + edge.y * edge.y
            val offset = local - start
            val t = ((offset.x * edge.x + offset.y * edge.y) / lengthSquared).coerceIn(0.0, 1.0)
            local.distance(start + edge * t) <= padding
        }
    }
}

/** Store stable fleet attributes, not a snapshot's mutable transporter reference. */
class HumanFleetSelection {
    private data class Identity(val source: Int, val destination: Int, val owner: Player, val ships: Double)
    private var selected: Identity? = null

    fun select(fleet: Transporter) {
        selected = Identity(fleet.sourceIndex, fleet.destinationIndex, fleet.owner, fleet.nShips)
    }

    fun clear() { selected = null }

    fun current(state: GameState): Transporter? {
        val identity = selected ?: return null
        val fleet = state.planets.getOrNull(identity.source)?.transporter
        if (fleet == null || fleet.sourceIndex != identity.source ||
            fleet.destinationIndex != identity.destination || fleet.owner != identity.owner ||
            fleet.nShips != identity.ships || fleet.destinationIndex !in state.planets.indices) {
            clear()
            return null
        }
        return fleet
    }
}
