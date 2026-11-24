"""Resolve named offline heuristics through the shared scoring registry."""

from __future__ import annotations

from pathlib import Path

from scoring.evaluators import Comparison, EVALUATOR_FACTORIES


def resolve_heuristic(name: str, config_path: str | Path | None = None):
    """Return (evaluator, provenance) for a configured evaluator profile.

    With a comparison YAML, ``name`` is a profile ID in that file. Without one,
    it may be a built-in evaluator type and receives default weights.
    """
    if config_path is not None:
        comparison = Comparison.load(config_path)
        if name not in comparison.evaluators:
            available = ", ".join(sorted(comparison.evaluators))
            raise ValueError(f"Unknown heuristic profile {name!r}; available: {available}")
        return comparison.evaluators[name], {
            "profile": name, "type": comparison.config["evaluators"][name]["type"],
            "version": comparison.config["evaluators"][name]["version"],
            "metadata": comparison.metadata,
            "config_path": str(Path(config_path).resolve()),
        }
    if name not in EVALUATOR_FACTORIES:
        available = ", ".join(sorted(EVALUATOR_FACTORIES))
        raise ValueError(f"Unknown heuristic {name!r}; built-ins: {available}")
    config = {"comparison": {"A": "selected", "B": "selected"},
              "evaluators": {"selected": {"type": name}}}
    comparison = Comparison(config)
    return comparison.evaluators["selected"], {
        "profile": name, "type": comparison.config["evaluators"]["selected"]["type"],
        "version": comparison.config["evaluators"]["selected"]["version"],
        "metadata": comparison.metadata,
        "config_path": None,
    }
