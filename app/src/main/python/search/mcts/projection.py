"""Compatibility imports; shared fleet prediction lives in ``core.fleet_projection``."""

from core.fleet_projection import (Arrival, PlanetProjection, arrival_tick, incoming_fleets,
                                  project_board, project_planet, remaining_ticks)

__all__ = ["Arrival", "PlanetProjection", "arrival_tick", "incoming_fleets",
           "project_board", "project_planet", "remaining_ticks"]
