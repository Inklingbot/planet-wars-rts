package games.planetwars.view

import games.planetwars.scoring.ScoreDisplay
import kotlinx.serialization.json.*
import java.awt.BorderLayout
import java.awt.Color
import java.awt.GridLayout
import java.util.Locale
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.border.EmptyBorder

/** Shared by the human window and MCTS spectator launcher. */
class HeuristicScorePanel : JPanel(BorderLayout(0, 4)) {
    private val headerA = JLabel("A", JLabel.RIGHT)
    private val headerB = JLabel("B", JLabel.RIGHT)
    val footer = JLabel("Waiting for scoring service")
    val values = listOf("Player1", "Player2").associateWith {
        listOf("A", "B").associateWith { JLabel("—", JLabel.RIGHT) }
    }

    init {
        border = EmptyBorder(8, 12, 8, 12)
        add(JPanel(GridLayout(3, 3, 12, 4)).apply {
            add(JLabel("Team / heuristic")); add(headerA); add(headerB)
            for ((team, text, color) in listOf(Triple("Player1", "Red", Color(180, 35, 35)),
                                               Triple("Player2", "Blue", Color(35, 75, 180)))) {
                add(JLabel(text).apply { foreground = color })
                add(values[team]!!["A"]); add(values[team]!!["B"])
            }
        }, BorderLayout.CENTER)
        add(footer, BorderLayout.SOUTH)
    }

    fun refresh(display: ScoreDisplay) {
        val definitions = display.metadata?.get("evaluators")?.jsonObject
        headerA.text = "A: " + (definitions?.get("A")?.jsonObject?.get("label")?.jsonPrimitive?.content ?: "—")
        headerB.text = "B: " + (definitions?.get("B")?.jsonObject?.get("label")?.jsonPrimitive?.content ?: "—")
        for ((player, slots) in values) for ((slot, label) in slots) {
            val value = display.scores?.get(player)?.jsonObject?.get(slot)?.jsonPrimitive?.double
            label.text = value?.let { String.format(Locale.ROOT, "%.3f", it) } ?: "—"
        }
        val tick = display.scoredTick?.toString() ?: "—"
        footer.text = "Scores: tick $tick / board: ${display.boardTick} · ${display.status}"
        footer.toolTipText = display.logPath?.let { "History: $it" }
    }
}
