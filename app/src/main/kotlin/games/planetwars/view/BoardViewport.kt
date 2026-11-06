package games.planetwars.view

import games.planetwars.core.GameState
import games.planetwars.core.Planet
import games.planetwars.core.Transporter
import util.Vec2d
import xkg.gui.XGraphics

/** Visual scale only; never modify Planet.radius, which controls game physics. */
const val DEFAULT_PLANET_RADIUS_SCALE = 1.5

/** One transform for drawing and mouse hit testing, in component coordinates. */
data class BoardViewport(
    val scale: Double,
    val offsetX: Double,
    val offsetY: Double,
    val worldWidth: Double,
    val worldHeight: Double,
) {
    fun apply(xg: XGraphics) {
        xg.setScale(scale, scale)
        xg.setTranslate(offsetX, offsetY)
    }

    fun screenToWorld(point: Vec2d): Vec2d? {
        val world = Vec2d(point.x / scale - offsetX, point.y / scale - offsetY)
        return world.takeIf { it.x in 0.0..worldWidth && it.y in 0.0..worldHeight }
    }

    fun planetAt(state: GameState, point: Vec2d,
                 radiusScale: Double = DEFAULT_PLANET_RADIUS_SCALE): Planet? {
        val world = screenToWorld(point) ?: return null
        // Enlarged markers can overlap; prefer the closest planet center.
        return state.planets.filter { it.position.distance(world) <= it.radius * radiusScale }
            .minByOrNull { it.position.distance(world) }
    }

    fun fleetAt(state: GameState, point: Vec2d): Transporter? {
        val world = screenToWorld(point) ?: return null
        return state.planets.asReversed().mapNotNull { it.transporter }
            .filter { FleetMarker.contains(it, world, padding = 3.0 / scale) }
            .minByOrNull { it.s.distance(world) }
    }

    companion object {
        fun fit(worldWidth: Double, worldHeight: Double, width: Double, height: Double): BoardViewport? {
            if (width <= 0 || height <= 0 || worldWidth <= 0 || worldHeight <= 0) return null
            val scale = minOf(width / worldWidth, height / worldHeight)
            return BoardViewport(scale, (width / scale - worldWidth) / 2,
                (height / scale - worldHeight) / 2, worldWidth, worldHeight)
        }
    }
}
