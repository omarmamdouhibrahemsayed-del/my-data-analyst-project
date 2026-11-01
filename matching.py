"""Matching engine: pairs surplus food with the most suitable charity.

The algorithm is a deterministic, urgency-first greedy matcher:

1. Candidate items (available, not expired, with unallocated portions) are
   processed in order of expiry time (soonest first), so food that is about to
   spoil gets first pick of the charities. Ties favour larger batches.
2. For each item, every charity is checked against hard constraints:
   - it accepts the food category,
   - it still has unmet need,
   - it lies within its own maximum pickup distance, and
   - it can realistically arrive before the food expires
     (travel time at ``avg_speed_kmph`` plus a handling buffer).
3. Feasible charities are scored in ``[0, 1]``::

       proximity = 1 - distance / charity.max_distance
       fit       = min(remaining, need) / max(remaining, need)
       urgency   = 1 - clamp(hours_left / urgency_horizon_hours)
       score     = ((w_prox + w_urg * urgency) * proximity + w_fit * fit)
                   / (w_prox + w_urg + w_fit)

   Urgent food therefore weights proximity more heavily (less transit time
   means less risk), while ``fit`` rewards charities whose need closely matches
   the batch size and avoids fragmenting food into tiny pieces.
4. The best charity receives ``min(remaining, need)`` portions. If the item is
   not exhausted the process repeats, so one large donation can be split across
   several charities.

The function is pure: it never mutates its inputs. Use
``Coordinator.run_matching`` to apply the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .errors import ValidationError
from .geo import estimate_travel_minutes, haversine_km
from .models import Allocation, Charity, FoodItem, ItemStatus, to_utc


@dataclass(frozen=True)
class MatchConfig:
    """Tunable parameters of the matching algorithm."""

    w_proximity: float = 0.5
    w_fit: float = 0.3
    w_urgency: float = 0.2
    avg_speed_kmph: float = 30.0
    handling_buffer_min: float = 15.0
    urgency_horizon_hours: float = 24.0
    min_portions: int = 1

    def __post_init__(self) -> None:
        weights = (self.w_proximity, self.w_fit, self.w_urgency)
        if any(w < 0 for w in weights) or sum(weights) <= 0:
            raise ValidationError("Weights must be non-negative and not all zero.")
        if self.avg_speed_kmph <= 0:
            raise ValidationError("Average speed must be positive.")
        if self.handling_buffer_min < 0:
            raise ValidationError("Handling buffer cannot be negative.")
        if self.urgency_horizon_hours <= 0:
            raise ValidationError("Urgency horizon must be positive.")
        if self.min_portions < 1:
            raise ValidationError("min_portions must be at least 1.")


@dataclass
class MatchResult:
    """Outcome of a matching run."""

    allocations: List[Allocation] = field(default_factory=list)
    unmatched: Dict[str, int] = field(default_factory=dict)  # item_id -> leftover

    @property
    def total_portions(self) -> int:
        return sum(a.quantity for a in self.allocations)


def urgency_factor(time_left_hours: float, horizon_hours: float) -> float:
    """1.0 means about to expire, 0.0 means at least ``horizon_hours`` left."""
    return min(1.0, max(0.0, 1.0 - time_left_hours / horizon_hours))


def score_candidate(
    config: MatchConfig,
    distance_km: float,
    max_distance_km: float,
    item_remaining: int,
    charity_need: int,
    urgency: float,
) -> float:
    """Score a feasible (item, charity) pair in ``[0, 1]``."""
    proximity = min(1.0, max(0.0, 1.0 - distance_km / max_distance_km))
    fit = min(item_remaining, charity_need) / max(item_remaining, charity_need)
    total_weight = config.w_proximity + config.w_urgency + config.w_fit
    raw = (config.w_proximity + config.w_urgency * urgency) * proximity + config.w_fit * fit
    return raw / total_weight


def match(
    items: Iterable[FoodItem],
    charities: Iterable[Charity],
    now: datetime,
    config: Optional[MatchConfig] = None,
) -> MatchResult:
    """Compute allocations of ``items`` to ``charities`` at time ``now``."""
    cfg = config or MatchConfig()
    now = to_utc(now)
    charity_list = sorted(charities, key=lambda c: c.id)
    needs: Dict[str, int] = {c.id: c.needed for c in charity_list}

    pending = sorted(
        (
            i
            for i in items
            if i.status is ItemStatus.AVAILABLE and (i.remaining or 0) > 0 and not i.is_expired(now)
        ),
        key=lambda i: (i.expires_at, -(i.remaining or 0), i.id),
    )

    result = MatchResult()
    for item in pending:
        remaining = item.remaining or 0
        minutes_left = item.time_left(now).total_seconds() / 60.0
        urgency = urgency_factor(minutes_left / 60.0, cfg.urgency_horizon_hours)

        while remaining > 0:
            best: Optional[Tuple[float, float, Charity]] = None
            for charity in charity_list:
                need = needs[charity.id]
                if need < cfg.min_portions or not charity.accepts(item.category):
                    continue
                distance = haversine_km(item.pickup_location, charity.location)
                if distance > charity.max_distance_km:
                    continue
                eta = estimate_travel_minutes(distance, cfg.avg_speed_kmph) + cfg.handling_buffer_min
                if eta > minutes_left:
                    continue
                score = score_candidate(
                    cfg, distance, charity.max_distance_km, remaining, need, urgency
                )
                if best is None or (score, -distance) > (best[0], -best[1]):
                    best = (score, distance, charity)

            if best is None:
                break

            score, distance, charity = best
            quantity = min(remaining, needs[charity.id])
            result.allocations.append(
                Allocation(
                    item_id=item.id,
                    charity_id=charity.id,
                    quantity=quantity,
                    distance_km=round(distance, 3),
                    score=round(score, 4),
                    pickup_by=item.expires_at,
                    created_at=now,
                )
            )
            needs[charity.id] -= quantity
            remaining -= quantity

        if remaining > 0:
            result.unmatched[item.id] = remaining

    return result
