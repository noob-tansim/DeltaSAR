"""Alert sentences. Fixed templates filled with numbers from a rule's `values`: no AI writes any of this.

The Bangla lines are drafts and must be checked by a native reader (see event_kit/05_bangla_copy_sheet.md).
"""
from __future__ import annotations

from typing import Any

from src.alerts.settings import NOT_OFFICIAL_BN, NOT_OFFICIAL_EN
from src.alerts.types import Confidence, RuleName

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
STATION_BN = {"Kazipur": "কাজীপুর", "Sirajganj": "সিরাজগঞ্জ", "Sariakandi": "সারিয়াকান্দি", "Bahadurabad": "বাহাদুরাবাদ"}

REPLY_BN = "নিরাপদ থাকলে ১ চাপুন। সাহায্য লাগলে ২ চাপুন।"
REPLY_EN = "Press 1 if you are safe, 2 if you need help."


def bn(value: Any) -> str:
    """Number (or text holding digits) in Bangla digits."""
    return str(value).translate(_BN_DIGITS)


def _num(v: float, places: int) -> str:
    return f"{v:.{places}f}"


def render(rule: RuleName, values: dict[str, Any], confidence: Confidence, replay: bool = False) -> tuple[str, str]:
    """(Bangla, English) body of one alert, without the closing lines."""
    if rule == RuleName.radar:
        m, d = values["walk_minutes"], values["picture_age_days"]
        b = f"রাডারে আপনার বাড়ি থেকে {bn(m)} মিনিট হাঁটা দূরে নতুন পানি দেখা গেছে। ছবিটি {bn(d)} দিন আগের।"
        e = f"Radar saw new water about {m} minutes' walk from your home. The picture is {d} days old."
        grew = values.get("grew_since_previous_pass")
        if grew is True:
            b += " আগের ছবির তুলনায় পানি আরও কাছে এসেছে।"
            e += " The water is closer than in the previous picture."
        elif grew is False:
            b += " আগের ছবির তুলনায় পানি কাছে আসেনি।"
            e += " The water is not closer than in the previous picture."
        if confidence == Confidence.less_sure:
            b += " রাডার এখানে পুরোপুরি নিশ্চিত নয়।"
            e += " The radar is less sure here."
    elif rule == RuleName.river:
        st = values["station"]
        lvl, dl = _num(values["level_m"], 2), _num(values["danger_level_m"], 2)
        kind_b = "পূর্বাভাস" if values.get("kind") == "forecast" else "মাপা"
        kind_e = "forecast" if values.get("kind") == "forecast" else "measured"
        b = f"যমুনা নদী, {STATION_BN.get(st, st)} পয়েন্ট: পানি {bn(lvl)} মিটার ({kind_b})। বিপদসীমা {bn(dl)} মিটার।"
        e = f"Jamuna at {st}: water level {lvl} m ({kind_e}). Danger level {dl} m."
    else:
        mm, lim = _num(values["rain_mm"], 1), values["limit_mm"]
        b = f"গত ২৪ ঘণ্টায় {bn(mm)} মিমি বৃষ্টি হয়েছে। আপনার সীমা {bn(lim)} মিমি।"
        e = f"{mm} mm of rain in the last 24 hours. Your level is {lim} mm."
    if replay:
        b = "রিপ্লে (আগের তারিখের আসল তথ্য): " + b
        e = "REPLAY (real data from a past date): " + e
    return b, e


def full(body_bn: str, body_en: str) -> tuple[str, str]:
    """Body plus the reply line and the "not official" line: what is spoken, pushed and emailed."""
    return f"{body_bn} {REPLY_BN} {NOT_OFFICIAL_BN}", f"{body_en} {REPLY_EN} {NOT_OFFICIAL_EN}"


def event_summary(rule: RuleName, n: int, sample_values: dict[str, Any], replay: bool) -> tuple[str, str]:
    """One line for the console card (the per-person text is on each recipient)."""
    b, e = render(rule, sample_values, Confidence.sure, replay)
    return f"{bn(n)} জনের জন্য। উদাহরণ: {b}", f"For {n} people. Example: {e}"
