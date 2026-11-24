"""Game-held-out logistic calibration and reliability bins."""

from __future__ import annotations

import math
import random
from typing import Sequence


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-min(value, 700)))
    scaled = math.exp(max(value, -700))
    return scaled / (1 + scaled)


def _game_weights(rows: Sequence[dict]) -> list[float]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["game_id"]] = counts.get(row["game_id"], 0) + 1
    return [1 / counts[row["game_id"]] for row in rows]


def _loss(scores: Sequence[float], targets: Sequence[float], weights: Sequence[float],
          intercept: float, slope: float, ridge: float) -> float:
    total = ridge * slope * slope / 2
    for score, target, weight in zip(scores, targets, weights):
        probability = min(1 - 1e-12, max(1e-12,
                          _sigmoid(intercept + slope * (2 * score - 1))))
        total -= weight * (target * math.log(probability) +
                           (1 - target) * math.log(1 - probability))
    return total


def _fit_logistic(rows: Sequence[dict], score_key: str) -> tuple[float, float]:
    scores = [float(row[score_key]) for row in rows]
    targets = [float(row["outcome"]) for row in rows]
    weights = _game_weights(rows)
    intercept = slope = 0.0
    ridge = 1e-4
    for _ in range(100):
        g0 = g1 = h00 = h01 = 0.0
        h11 = ridge
        for score, target, weight in zip(scores, targets, weights):
            x = 2 * score - 1
            probability = _sigmoid(intercept + slope * x)
            residual = weight * (probability - target)
            curvature = weight * probability * (1 - probability)
            g0 += residual
            g1 += residual * x
            h00 += curvature
            h01 += curvature * x
            h11 += curvature * x * x
        g1 += ridge * slope
        h00 += 1e-8
        h11 += 1e-8
        determinant = h00 * h11 - h01 * h01
        if determinant <= 1e-18:
            break
        step0 = (h11 * g0 - h01 * g1) / determinant
        step1 = (h00 * g1 - h01 * g0) / determinant
        if max(abs(g0), abs(g1)) / max(sum(weights), 1e-12) < 1e-8:
            break
        old_loss = _loss(scores, targets, weights, intercept, slope, ridge)
        rate = 1.0
        while rate > 1e-8:
            candidate0 = intercept - rate * step0
            candidate1 = slope - rate * step1
            if _loss(scores, targets, weights, candidate0, candidate1, ridge) <= old_loss:
                intercept, slope = candidate0, candidate1
                break
            rate /= 2
        else:
            break
    return intercept, slope


def _reliability_bins(targets: Sequence[float], predictions: Sequence[float],
                      weights: Sequence[float], bins: int) -> list[dict]:
    result = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        selected = [(target, prediction, weight)
                    for target, prediction, weight in zip(targets, predictions, weights)
                    if lower <= prediction < upper or (index == bins - 1 and prediction == 1)]
        mass = sum(weight for _, _, weight in selected)
        result.append({
            "bin": index, "lower": lower, "upper": upper,
            "count": len(selected), "weight": mass,
            "mean_prediction": (sum(prediction * weight for _, prediction, weight in selected) / mass
                                if mass else None),
            "observed_result": (sum(target * weight for target, _, weight in selected) / mass
                                if mass else None),
        })
    return result


def calibrate_scores(rows: Sequence[dict], *, score_key: str,
                     bins: int = 10, test_fraction: float = 0.25,
                     seed: int = 42) -> dict:
    """Fit on whole training games, then bin predictions on held-out games."""
    if not rows or bins < 1 or not 0 < test_fraction < 1:
        raise ValueError("rows, positive bins, and a test fraction in (0, 1) are required")
    games = sorted({row["game_id"] for row in rows})
    random.Random(seed).shuffle(games)
    test_count = (min(len(games) - 1, max(1, round(len(games) * test_fraction)))
                  if len(games) > 1 else 0)
    held_out = set(games[:test_count])
    training = set(games[test_count:])
    train_rows = [row for row in rows if row["game_id"] in training]
    test_rows = [row for row in rows if row["game_id"] in (held_out or training)]
    intercept, slope = _fit_logistic(train_rows, score_key)
    weights = _game_weights(test_rows)
    targets = [float(row["outcome"]) for row in test_rows]
    predictions = [_sigmoid(intercept + slope * (2 * float(row[score_key]) - 1))
                   for row in test_rows]
    reliability = _reliability_bins(targets, predictions, weights, bins)
    total_weight = sum(weights)
    brier = sum(weight * (target - prediction) ** 2
                for target, prediction, weight in zip(targets, predictions, weights)) / total_weight
    ece = sum(bin_row["weight"] * abs(bin_row["mean_prediction"] - bin_row["observed_result"])
              for bin_row in reliability if bin_row["count"]) / total_weight
    return {
        "method": "logistic", "score": score_key,
        "intercept": intercept, "slope": slope,
        "split": "game_holdout" if held_out else "in_sample",
        "train_game_ids": sorted(training), "test_game_ids": sorted(held_out or training),
        "train_positions": len(train_rows), "test_positions": len(test_rows),
        "brier": brier, "ece": ece, "bins": reliability,
    }
