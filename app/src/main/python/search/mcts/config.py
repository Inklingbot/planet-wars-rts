"""Configuration for heuristic MCTS and reserved modern search options."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MCTSConfig:
    iterations: int = 128
    tree_depth: int = 20
    rollout_depth: int = 80
    exploration_constant: float = math.sqrt(2)
    seed: int | None = None
    time_limit_seconds: float | None = None
    selection: str = "uct"
    expansion: str = "standard"
    evaluation: str = "heuristic"
    priors: str = "uniform"
    c_puct: float = 1.5
    inference_batch_size: int = 1
    reuse_tree: bool = False
    root_noise: bool = False
    temperature: float = 0.0
    inference_cache: bool = False

    def __post_init__(self):
        for name, minimum in (("iterations", 1), ("tree_depth", 1),
                              ("rollout_depth", 0), ("inference_batch_size", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        for name in ("exploration_constant", "c_puct", "temperature"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.time_limit_seconds is not None:
            if not math.isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0:
                raise ValueError("time_limit_seconds must be finite and positive")
        choices = {"selection": ("uct", "puct"),
                   "expansion": ("standard", "progressive_widening"),
                   "evaluation": ("heuristic", "network", "hybrid"),
                   "priors": ("uniform", "heuristic", "network")}
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name} must be one of {allowed}")
        unsupported = []
        for name, baseline in (("selection", "uct"), ("expansion", "standard"),
                               ("evaluation", "heuristic"), ("priors", "uniform"),
                               ("inference_batch_size", 1), ("reuse_tree", False),
                               ("root_noise", False), ("temperature", 0.0),
                               ("inference_cache", False)):
            if getattr(self, name) != baseline:
                unsupported.append(name)
        if unsupported:
            raise NotImplementedError("Modern MCTS options are reserved: " + ", ".join(unsupported))
