"""Field plausibility — the layer that refuses to turn sensor artifacts into soil data.

WHY THIS EXISTS ALONGSIDE ValidationEngine, NOT INSTEAD OF IT
-------------------------------------------------------------
`fieldsense.intelligence.ValidationEngine` checks engineering sanity: is every
channel numeric, finite, and inside its physical range. It is frozen, it is
correct, and it is not the check being made here — because a probe held in open
air reports moisture 0.0 %, EC 0, N/P/K 0, and every one of those is inside its
sanity range. A bench run recorded five such samples and every one came back
VALID. Nothing was wrong with the validator. It was answering a different
question.

This layer answers the field question: does this reading look like a
measurement of soil at all. It is strictly additive — it never overrides a
REJECTED verdict from the validator, only narrows a VALID one.

WHAT IT WILL AND WILL NOT CLAIM
-------------------------------
Every detector below keys on an INSTRUMENT signature, not an agronomic one:

  * all primary channels reading exactly zero is what a JXBS probe does when it
    is not in contact with soil, or when no Modbus frame decoded. It is not a
    statement that zero nitrogen is agronomically implausible.
  * a reading identical to the previous one across every channel, to full
    sensor precision, is what a stale frame or an unmoved probe looks like. Real
    soil does not repeat to three decimals at a different place.
  * moisture falling to a tenth of the previous sample's between two insertions
    minutes apart is the probe losing contact, not the field drying out. The
    test is purely relative and makes no claim about what moisture is plausible.
  * every contact channel sitting at the bottom of its range SIMULTANEOUSLY is
    what this probe reports when it is resting on the surface rather than seated
    in soil.

There is deliberately NO detector of the form "pH below X is unlikely" or
"moisture under Y means dry soil". Those are agronomic thresholds, this project
has no evidence for them, and inventing them would be exactly the failure mode
the four-valued verdict was introduced to avoid.

The near-floor check is the one place where that line is thin, and it is drawn
deliberately: it fires only on the CONJUNCTION of four independent channels at
once, never on any single one, and its four numbers are configuration rather
than literals precisely so a region whose real soil trips them can raise them.
Read the note on PlausibilityConfig before touching them.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .states import SampleQuality

#: Channels a JXBS-style probe drives to exactly zero when it is out of soil or
#: when no valid Modbus response was decoded. Temperature is excluded on
#: purpose: it reads a real ambient value in air, so it carries no information
#: about soil contact. pH is excluded because the probe reports a mid-scale
#: default rather than zero when it has nothing to measure.
CONTACT_CHANNELS = ("moisture", "ec", "nitrogen", "phosphorus", "potassium")

#: Channels compared when deciding whether two readings are the same reading.
IDENTITY_CHANNELS = ("moisture", "ec", "ph", "temperature",
                     "nitrogen", "phosphorus", "potassium")


@dataclass(frozen=True)
class PlausibilityConfig:
    """Tunables for the field plausibility layer. All are instrument-facing."""

    #: Consecutive RETRY verdicts on one sample index before the workflow gives
    #: up and stores the reading as SUSPICIOUS instead. Without a bound, a
    #: genuinely dead probe would ask the operator to re-seat forever.
    max_retries: int = 2

    #: Below this the frozen validator already warns; carried here so the field
    #: verdict can mirror it rather than contradict it.
    quality_warning_threshold: float = 0.70

    #: Require a satellite fix before a sample counts as located. A sample
    #: without one is not a point on a map, whatever else it measured.
    require_gps_fix: bool = True

    # ---- near-floor detection --------------------------------------------
    #
    # THESE FOUR ARE THE ONLY NUMBERS IN THIS MODULE THAT COULD BE MISTAKEN FOR
    # AGRONOMIC THRESHOLDS, SO READ THIS BEFORE CHANGING THEM.
    #
    # The exact-zero check cannot catch a probe resting on the surface rather
    # than fully out of the ground. A real session recorded this:
    #
    #     idx  moisture   pH     EC      N   P   K
    #     1    14.2%      5.67   0.014   1   1   3
    #     2    14.1%      5.67   0.014   1   1   2
    #     3     0.2%      5.86   0.021   1   2   4     <- contact lost here
    #     4     0.2%      5.49   0.024   1   2   4
    #     5     0.2%      5.38   0.025   1   2   5
    #
    # Every one of those was stored VALID, because 0.2 is not 0.0.
    #
    # What makes the check below defensible is the CONJUNCTION. No single one of
    # these values is being called implausible: dry soil really can read low
    # moisture, and poor soil really can read low nutrients. The signature is
    # every independent channel sitting at the bottom of its range AT THE SAME
    # TIME, which is what this probe does when it is not in contact with
    # anything. SUSPICIOUS is also not a rejection - the reading is stored,
    # marked, and kept out of the map.
    #
    # If a genuine soil in your region reads under all four of these at once,
    # raise them. That is the honest failure mode of this check, and it is why
    # they are parameters rather than literals.
    near_floor_moisture_pct: float = 1.0
    near_floor_ec: float = 0.05
    near_floor_npk_sum: float = 15.0

    #: A reading counts as a collapse when moisture falls to this fraction of
    #: the previous stored sample's. Purely relative - it makes no claim about
    #: what moisture level is plausible, only that a tenfold drop between two
    #: consecutive insertions is a change in the probe, not in the field.
    moisture_collapse_ratio: float = 0.10


@dataclass(frozen=True)
class PlausibilityVerdict:
    """The field verdict on one reading, with every reason kept."""

    quality: SampleQuality
    reasons: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def storable(self) -> bool:
        """True when this reading should be written to the session record."""
        return self.quality is not SampleQuality.RETRY

    @property
    def map_eligible(self) -> bool:
        """True when this reading's values may feed the interpolated map."""
        return self.quality is SampleQuality.VALID

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the durable sample record."""
        return {
            "quality": self.quality.value,
            "reasons": list(self.reasons),
            "detail": self.detail,
        }


def _numeric(value: Any) -> Optional[float]:
    """Return value as a float, or None when it is not a usable number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def channels_all_zero(reading: Dict[str, Any], channels: Sequence[str] = CONTACT_CHANNELS) -> bool:
    """True when every named channel is present and reads exactly zero.

    Exactly zero, not "near zero": a threshold here would be an agronomic claim
    about how dry soil can get, and this function is only allowed to recognise
    the instrument's own out-of-contact signature.
    """
    seen = 0
    for name in channels:
        number = _numeric(reading.get(name))
        if number is None:
            continue
        if number != 0.0:
            return False
        seen += 1
    return seen == len(channels)


def nutrients_all_zero(reading: Dict[str, Any]) -> bool:
    """True when N, P and K all read exactly zero while moisture does not.

    The signature of a probe that is in soil but whose nutrient channels are
    not responding — a different fault from no soil contact, and one that still
    leaves moisture, pH and temperature worth keeping.
    """
    if not channels_all_zero(reading, ("nitrogen", "phosphorus", "potassium")):
        return False
    moisture = _numeric(reading.get("moisture"))
    return moisture is not None and moisture != 0.0


def channels_near_floor(
    reading: Dict[str, Any], config: Optional["PlausibilityConfig"] = None
) -> bool:
    """True when every contact channel sits at the bottom of its range at once.

    The softer companion to `channels_all_zero`, for a probe resting on the
    surface rather than held in the air. See PlausibilityConfig for why the
    conjunction is what makes this an instrument signature rather than an
    agronomic claim, and for the session that motivated it.
    """
    cfg = config or PlausibilityConfig()
    moisture = _numeric(reading.get("moisture"))
    ec = _numeric(reading.get("ec"))
    nutrients = [_numeric(reading.get(name))
                 for name in ("nitrogen", "phosphorus", "potassium")]
    if moisture is None or ec is None or any(v is None for v in nutrients):
        return False
    return (moisture < cfg.near_floor_moisture_pct
            and ec < cfg.near_floor_ec
            and sum(nutrients) < cfg.near_floor_npk_sum)


def moisture_collapsed(
    reading: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
    config: Optional["PlausibilityConfig"] = None,
) -> bool:
    """True when moisture fell off a cliff since the previous stored sample.

    Relative only. Soil dries out across a field, but not by an order of
    magnitude between two insertions minutes apart - that is the probe losing
    contact, and it is exactly what separated sample 2 from sample 3 in the
    session recorded in PlausibilityConfig.
    """
    cfg = config or PlausibilityConfig()
    if not previous:
        return False
    current = _numeric(reading.get("moisture"))
    prior = _numeric(previous.get("moisture"))
    if current is None or prior is None or prior <= 0.0:
        return False
    return current <= prior * cfg.moisture_collapse_ratio


def readings_identical(
    reading: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
    channels: Sequence[str] = IDENTITY_CHANNELS,
) -> bool:
    """True when two readings match on every channel to full precision."""
    if not previous:
        return False
    matched = 0
    for name in channels:
        current = _numeric(reading.get(name))
        prior = _numeric(previous.get(name))
        if current is None or prior is None:
            return False
        if current != prior:
            return False
        matched += 1
    return matched == len(channels)


def assess_reading(
    reading: Dict[str, Any],
    previous_reading: Optional[Dict[str, Any]] = None,
    gps_fix_valid: bool = True,
    validation_state: Optional[str] = None,
    measurement_quality: Optional[float] = None,
    retry_count: int = 0,
    config: Optional[PlausibilityConfig] = None,
) -> PlausibilityVerdict:
    """Judge one probe reading as a field measurement.

    Args:
        reading: Channel name -> value, as acquired from the probe.
        previous_reading: The last reading stored in this session, for the
            frozen-reading check. None for the first sample.
        gps_fix_valid: Whether the receiver had a fix when this was taken.
        validation_state: The frozen ValidationEngine's verdict. A REJECTED
            state is never softened here.
        measurement_quality: The adapter's own 0..1 confidence, if it reports one.
        retry_count: How many times this sample index has already been retried.
            Bounds the RETRY verdict so a dead probe cannot loop forever.
        config: Overrides for the tunables.

    Returns:
        A PlausibilityVerdict. Never raises: an unreadable input yields
        SUSPICIOUS with a reason, because refusing to answer would strand the
        operator mid-session.
    """
    cfg = config or PlausibilityConfig()
    reasons: List[str] = []
    exhausted = retry_count >= cfg.max_retries

    # The frozen validator outranks everything. If it rejected the sample, the
    # field layer records that and stops — it may narrow VALID, never widen
    # REJECTED.
    if validation_state and str(validation_state).upper() == "REJECTED":
        return PlausibilityVerdict(
            SampleQuality.REJECTED,
            ["VALIDATION_REJECTED"],
            "the frozen validation engine rejected this reading",
        )

    # No fix means no location. Ask for a retry while there is still budget,
    # because a fix usually arrives by simply waiting.
    if cfg.require_gps_fix and not gps_fix_valid:
        reasons.append("NO_GPS_FIX")
        if not exhausted:
            return PlausibilityVerdict(
                SampleQuality.RETRY, reasons,
                "no satellite fix; a sample with no position is not a point on a map",
            )
        return PlausibilityVerdict(
            SampleQuality.REJECTED, reasons,
            "no satellite fix after {} retries; stored as evidence, not as a "
            "located sample".format(retry_count),
        )

    # No soil contact. Retriable — re-seating the probe is exactly the fix.
    if channels_all_zero(reading):
        reasons.append("NO_SOIL_CONTACT")
        if not exhausted:
            return PlausibilityVerdict(
                SampleQuality.RETRY, reasons,
                "every contact channel reads exactly zero, which is what this "
                "probe reports in air; re-seat it and measure again",
            )
        return PlausibilityVerdict(
            SampleQuality.SUSPICIOUS, reasons,
            "every contact channel still reads zero after {} retries; stored "
            "and marked, kept out of the map".format(retry_count),
        )

    # Contact lost rather than absent: the probe is touching something, but
    # every channel is at the bottom of its range. Same handling as no contact
    # at all, because the fix is the same - push the probe properly in.
    if channels_near_floor(reading, cfg):
        reasons.append("CONTACT_CHANNELS_AT_FLOOR")
        if not exhausted:
            return PlausibilityVerdict(
                SampleQuality.RETRY, reasons,
                "moisture, EC and all three nutrients are simultaneously at the "
                "bottom of their ranges, which is what this probe reports when "
                "it is not properly seated; push it in and measure again",
            )
        return PlausibilityVerdict(
            SampleQuality.SUSPICIOUS, reasons,
            "every contact channel still sits at its floor after {} retries; "
            "stored and marked, kept out of the map".format(retry_count),
        )

    if moisture_collapsed(reading, previous_reading, cfg):
        reasons.append("MOISTURE_COLLAPSE")

    if nutrients_all_zero(reading):
        reasons.append("NUTRIENT_CHANNELS_ZERO")

    if readings_identical(reading, previous_reading):
        reasons.append("IDENTICAL_TO_PREVIOUS")

    quality = _numeric(measurement_quality)
    if quality is not None and quality < cfg.quality_warning_threshold:
        reasons.append("LOW_MEASUREMENT_QUALITY")

    if validation_state and str(validation_state).upper() == "VALID_WITH_WARNING":
        reasons.append("VALIDATION_WARNING")

    if reasons:
        return PlausibilityVerdict(
            SampleQuality.SUSPICIOUS, reasons,
            "stored and marked: " + ", ".join(reasons),
        )
    return PlausibilityVerdict(SampleQuality.VALID, [], "accepted as a field measurement")
