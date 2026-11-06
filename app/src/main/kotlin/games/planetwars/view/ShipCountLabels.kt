package games.planetwars.view

import java.math.BigDecimal
import java.math.RoundingMode

/** Never label a positive fraction as zero, even below the displayed precision. */
fun formatShipCount(ships: Double, decimalPlaces: Int = 2): String {
    require(ships.isFinite() && ships >= 0)
    require(decimalPlaces in 0..6)
    if (ships == 0.0) return "0"
    val count = BigDecimal.valueOf(ships)
    val smallest = BigDecimal.ONE.movePointLeft(decimalPlaces)
    if (count < smallest) return "<${smallest.toPlainString()}"
    return count.setScale(decimalPlaces, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
}
