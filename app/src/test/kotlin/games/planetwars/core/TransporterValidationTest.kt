package games.planetwars.core

import kotlinx.serialization.json.*
import org.junit.jupiter.api.Test
import util.Vec2d
import kotlin.test.*

class TransporterValidationTest {
    @Test
    fun `zero negative and nonfinite fleets cannot be constructed`() {
        for (ships in listOf(0.0, -0.0, -1.0, Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)) {
            assertFailsWith<IllegalArgumentException>("Invalid fleet: $ships") {
                Transporter(Vec2d(), Vec2d(3.0, 0.0), Player.Player1, 0, 1, ships)
            }
        }
    }

    @Test
    fun `serialized fleets with zero ships are rejected`() {
        val valid = Transporter(Vec2d(), Vec2d(3.0, 0.0), Player.Player1, 0, 1, 0.5)
        val fields = Json.encodeToJsonElement(Transporter.serializer(), valid).jsonObject.toMutableMap()
        fields["nShips"] = JsonPrimitive(0.0)
        assertFailsWith<IllegalArgumentException> {
            Json.decodeFromJsonElement(Transporter.serializer(), JsonObject(fields))
        }
        assertEquals(0.5, Json.decodeFromJsonElement(Transporter.serializer(),
            Json.encodeToJsonElement(Transporter.serializer(), valid)).nShips)
    }
}
