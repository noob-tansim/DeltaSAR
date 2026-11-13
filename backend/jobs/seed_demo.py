"""Demo participants for rehearsals: a few phones "living" at real union centre points. No real person's data.

  python -m jobs.seed_demo                      # add the demo people if they are missing
  python -m jobs.seed_demo --show 2026-07-27T08:00:00+00:00    # what each rule says for them at that moment

A phone that joins through the app gets its own row; these rows only make the console useful before that.
"""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy import select

from src.alerts import engine, inputs
from src.alerts.db import Person, init_engine, session_scope, utcnow

DEMO_UNIONS = ["Char Girish", "Khas Rajbari", "Kazipur", "Natuar Para", "Mansur Nagar", "Nishchintapur"]


def seed() -> int:
    n = 0
    by_name = {u["name_en"]: u for u in inputs.unions()}
    with session_scope() as s:
        for i, name in enumerate(DEMO_UNIONS, 1):
            u = by_name.get(name)
            if u is None:
                print(f"[seed] union not found: {name}")
                continue
            device = f"demo-phone-{i:02d}"
            if s.scalars(select(Person).where(Person.device_id == device)).first():
                continue
            s.add(Person(device_id=device, display_name=f"Demo phone {i} ({name})", union_id=u["union_id"],
                         home_lat=u["lat"], home_lon=u["lon"], months=[6, 7, 8, 9, 10, 11], rain_on=True, rain_mm=76,
                         river_on=True, radar_on=True, radar_km=1.0, channels=["in_app"], mode={}, is_demo=True,
                         consent_utc=utcnow()))
            n += 1
    print(f"[seed] {n} demo people added")
    return n


def show(as_of: dt.datetime) -> None:
    with session_scope() as s:
        for p in s.scalars(select(Person)):
            res = engine.evaluate_person(s, p, as_of)
            line = "; ".join(f"{r.value}: {'FIRED ' + x.confidence.value if x.fired else x.reason}"
                             + (f" ({x.values.get('distance_m')} m)" if r.value == "radar" and x.values else "")
                             for r, x in res.items())
            print(f"  {p.display_name}: {line}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", help="ISO time with offset; print rule results for every person at that moment")
    a = ap.parse_args()
    init_engine()
    seed()
    if a.show:
        show(dt.datetime.fromisoformat(a.show))
