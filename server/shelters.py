"""Where to send people once they are out.

Thirty-eight evacuation and gathering points across thirteen Egyptian cities: stadiums,
civic squares, parks and open ground with the room to hold a displaced crowd. The dataset
is the teammates' fieldwork -- it arrived with the merge of nour000304/AFRICA-RESQ, where
it was src/shelter_data.py -- and it is reproduced here record for record.

It is plain Python and the search over it is trigonometry, so this answers with no network
at all. That matters more than it sounds: the board is built to run on a Pi with a radio
link as its only connection, and "nearest shelter" is exactly the question that gets asked
at the moment the uplink is gone.

Capacities are estimates. Coordinates and contacts are not.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config, geo

SHELTERS = [
    # ----------------------------- CAIRO -----------------------------------
    {
        "id": "CAI-01",
        "name": "Cairo International Stadium",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "stadium",
        "lat": 30.069113,
        "lon": 31.312407,
        "capacity": 75000,
        "address": "Nasr City, Cairo",
        "contact": "+20 2 22652555"
    },
    {
        "id": "CAI-02",
        "name": "Cairo Opera House Grounds",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "civic_center",
        "lat": 30.042149,
        "lon": 31.223577,
        "capacity": 5000,
        "address": "Gezira Island, Zamalek, Cairo",
        "contact": "+20 2 27390132"
    },
    {
        "id": "CAI-03",
        "name": "Tahrir Square (Egyptian Museum)",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "open_square",
        "lat": 30.045748,
        "lon": 31.235881,
        "capacity": 50000,
        "address": "Downtown Cairo",
        "contact": "+20 2 25796949"
    },
    {
        "id": "CAI-04",
        "name": "Al-Azhar Park",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "park",
        "lat": 30.041199,
        "lon": 31.260171,
        "capacity": 8000,
        "address": "Ad Darb Al Ahmar, Cairo",
        "contact": "+20 2 25108536"
    },
    {
        "id": "CAI-05",
        "name": "Baron Empain Palace Park (Heliopolis)",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "civic_center",
        "lat": 30.087960,
        "lon": 31.330410,
        "capacity": 6000,
        "address": "Korba, Heliopolis, Cairo",
        "contact": "+20 2 27171100"
    },
    {
        "id": "CAI-06",
        "name": "El-Hussein Square (Al-Azhar)",
        "city": "Cairo",
        "governorate": "Cairo",
        "type": "open_square",
        "lat": 30.046248,
        "lon": 31.262682,
        "capacity": 15000,
        "address": "Al Azhar, Historic Cairo",
        "contact": "+20 2 27716100"
    },

    # ----------------------------- GIZA ------------------------------------
    {
        "id": "GIZ-01",
        "name": "Giza Zoo",
        "city": "Giza",
        "governorate": "Giza",
        "type": "park",
        "lat": 30.020813,
        "lon": 31.213529,
        "capacity": 10000,
        "address": "Giza South, Giza",
        "contact": "+20 2 35700281"
    },
    {
        "id": "GIZ-02",
        "name": "Giza Sporting Club",
        "city": "Giza",
        "governorate": "Giza",
        "type": "sports_club",
        "lat": 30.009700,
        "lon": 31.211000,
        "capacity": 12000,
        "address": "Dokki, Giza",
        "contact": "+20 2 33361424"
    },
    {
        "id": "GIZ-03",
        "name": "Giza Pyramids Plateau",
        "city": "Giza",
        "governorate": "Giza",
        "type": "open_area",
        "lat": 29.978000,
        "lon": 31.134300,
        "capacity": 90000,
        "address": "Haram, Giza",
        "contact": "+20 2 33732233"
    },
    {
        "id": "GIZ-04",
        "name": "Midan El Giza Square",
        "city": "Giza",
        "governorate": "Giza",
        "type": "open_square",
        "lat": 30.014800,
        "lon": 31.207000,
        "capacity": 20000,
        "address": "Midan El Giza, Giza",
        "contact": "+20 2 35736604"
    },

    # --------------------------- ALEXANDRIA --------------------------------
    {
        "id": "ALX-01",
        "name": "Alexandria Stadium",
        "city": "Alexandria",
        "governorate": "Alexandria",
        "type": "stadium",
        "lat": 31.196329,
        "lon": 29.909712,
        "capacity": 20000,
        "address": "Al Azarita, Moharram Bey, Alexandria",
        "contact": "+20 3 4875860"
    },
    {
        "id": "ALX-02",
        "name": "Qaitbay Citadel Seafront",
        "city": "Alexandria",
        "governorate": "Alexandria",
        "type": "open_area",
        "lat": 31.213889,
        "lon": 29.885278,
        "capacity": 12000,
        "address": "Al Manshiyah, Alexandria",
        "contact": "+20 3 4809144"
    },
    {
        "id": "ALX-03",
        "name": "Bibliotheca Alexandrina Plaza",
        "city": "Alexandria",
        "governorate": "Alexandria",
        "type": "civic_center",
        "lat": 31.208900,
        "lon": 29.909200,
        "capacity": 8000,
        "address": "Shatby, Alexandria",
        "contact": "+20 3 4839999"
    },
    {
        "id": "ALX-04",
        "name": "Montaza Palace Gardens",
        "city": "Alexandria",
        "governorate": "Alexandria",
        "type": "park",
        "lat": 31.288600,
        "lon": 30.015000,
        "capacity": 15000,
        "address": "Montaza, Alexandria",
        "contact": "+20 3 5477076"
    },
    {
        "id": "ALX-05",
        "name": "Stanley Bridge Promenade",
        "city": "Alexandria",
        "governorate": "Alexandria",
        "type": "open_area",
        "lat": 31.240700,
        "lon": 29.956500,
        "capacity": 9000,
        "address": "Gleem / Stanley, Alexandria",
        "contact": "+20 3 4809144"
    },

    # ---------------------------- PORT SAID --------------------------------
    {
        "id": "PSD-01",
        "name": "Port Said Stadium",
        "city": "Port Said",
        "governorate": "Port Said",
        "type": "stadium",
        "lat": 31.259500,
        "lon": 32.285000,
        "capacity": 18000,
        "address": "Shohadaa, Port Said",
        "contact": "+20 66 3205111"
    },
    {
        "id": "PSD-02",
        "name": "Martyrs Square (Midan Shohadaa)",
        "city": "Port Said",
        "governorate": "Port Said",
        "type": "open_square",
        "lat": 31.264800,
        "lon": 32.305600,
        "capacity": 12000,
        "address": "Downtown Port Said",
        "contact": "+20 66 3335000"
    },

    # ---------------------------- ISMAILIA ---------------------------------
    {
        "id": "ISM-01",
        "name": "Ismailia Stadium",
        "city": "Ismailia",
        "governorate": "Ismailia",
        "type": "stadium",
        "lat": 30.604600,
        "lon": 32.257500,
        "capacity": 18000,
        "address": "Ismailia El Gedida, Ismailia",
        "contact": "+20 64 3329000"
    },
    {
        "id": "ISM-02",
        "name": "Lake Timsah Waterfront",
        "city": "Ismailia",
        "governorate": "Ismailia",
        "type": "open_area",
        "lat": 30.590000,
        "lon": 32.270000,
        "capacity": 10000,
        "address": "Corniche El Timsah, Ismailia",
        "contact": "+20 64 3201111"
    },

    # ------------------------------- SUEZ ----------------------------------
    {
        "id": "SUZ-01",
        "name": "Suez Stadium",
        "city": "Suez",
        "governorate": "Suez",
        "type": "stadium",
        "lat": 29.989950,
        "lon": 32.510910,
        "capacity": 25000,
        "address": "El Arbeen, Suez",
        "contact": "+20 62 3367000"
    },
    {
        "id": "SUZ-02",
        "name": "Martyrs Square (Midan Al Shohadaa)",
        "city": "Suez",
        "governorate": "Suez",
        "type": "open_square",
        "lat": 29.981000,
        "lon": 32.548000,
        "capacity": 10000,
        "address": "Downtown Suez",
        "contact": "+20 62 3220111"
    },

    # ------------------------------- LUXOR ----------------------------------
    {
        "id": "LXR-01",
        "name": "Karnak Temple Forecourt",
        "city": "Luxor",
        "governorate": "Luxor",
        "type": "open_area",
        "lat": 25.719100,
        "lon": 32.657500,
        "capacity": 20000,
        "address": "El Karnak, Luxor",
        "contact": "+20 95 2372406"
    },
    {
        "id": "LXR-02",
        "name": "Luxor Temple Plaza",
        "city": "Luxor",
        "governorate": "Luxor",
        "type": "open_area",
        "lat": 25.699200,
        "lon": 32.639200,
        "capacity": 10000,
        "address": "Corniche El Nil, East Bank, Luxor",
        "contact": "+20 95 2372406"
    },
    {
        "id": "LXR-03",
        "name": "Luxor Municipality Square",
        "city": "Luxor",
        "governorate": "Luxor",
        "type": "open_square",
        "lat": 25.696000,
        "lon": 32.644000,
        "capacity": 8000,
        "address": "Downtown Luxor",
        "contact": "+20 95 2372406"
    },

    # ------------------------------- ASWAN ---------------------------------
    {
        "id": "ASW-01",
        "name": "Aswan Stadium",
        "city": "Aswan",
        "governorate": "Aswan",
        "type": "stadium",
        "lat": 24.085700,
        "lon": 32.898000,
        "capacity": 20000,
        "address": "El Sadat, Aswan",
        "contact": "+20 97 2304555"
    },
    {
        "id": "ASW-02",
        "name": "Aswan Corniche (Felucca Dock)",
        "city": "Aswan",
        "governorate": "Aswan",
        "type": "open_area",
        "lat": 24.081500,
        "lon": 32.889600,
        "capacity": 12000,
        "address": "Corniche El Nil, Aswan",
        "contact": "+20 97 2304555"
    },
    {
        "id": "ASW-03",
        "name": "Philae Temple Car Park",
        "city": "Aswan",
        "governorate": "Aswan",
        "type": "open_area",
        "lat": 24.024900,
        "lon": 32.884600,
        "capacity": 6000,
        "address": "Agilkia Island, Aswan",
        "contact": "+20 97 2304555"
    },

    # -------------------------- SHARM EL-SHEIKH ----------------------------
    {
        "id": "SSH-01",
        "name": "Naama Bay Promenade",
        "city": "Sharm El-Sheikh",
        "governorate": "South Sinai",
        "type": "open_area",
        "lat": 27.909100,
        "lon": 34.412800,
        "capacity": 15000,
        "address": "Naama Bay, Sharm El-Sheikh",
        "contact": "+20 69 3660111"
    },
    {
        "id": "SSH-02",
        "name": "Peace Square (Midan El Salam)",
        "city": "Sharm El-Sheikh",
        "governorate": "South Sinai",
        "type": "open_square",
        "lat": 27.861500,
        "lon": 34.304000,
        "capacity": 8000,
        "address": "Hadaba, Sharm El-Sheikh",
        "contact": "+20 69 3660111"
    },
    {
        "id": "SSH-03",
        "name": "Sharm El-Sheikh Airport Gathering Point",
        "city": "Sharm El-Sheikh",
        "governorate": "South Sinai",
        "type": "transport_hub",
        "lat": 27.977000,
        "lon": 34.394000,
        "capacity": 12000,
        "address": "Airport Rd, Sharm El-Sheikh",
        "contact": "+20 69 3622620"
    },

    # ----------------------------- HURGHADA --------------------------------
    {
        "id": "HUR-01",
        "name": "Hurghada Marina",
        "city": "Hurghada",
        "governorate": "Red Sea",
        "type": "open_area",
        "lat": 27.235100,
        "lon": 33.833700,
        "capacity": 10000,
        "address": "Sakala, Hurghada",
        "contact": "+20 65 3441570"
    },
    {
        "id": "HUR-02",
        "name": "El Dahar Square (Midan El Dahar)",
        "city": "Hurghada",
        "governorate": "Red Sea",
        "type": "open_square",
        "lat": 27.222900,
        "lon": 33.836600,
        "capacity": 8000,
        "address": "El Dahar, Hurghada",
        "contact": "+20 65 3549000"
    },
    {
        "id": "HUR-03",
        "name": "Hurghada Grand Aquarium Plaza",
        "city": "Hurghada",
        "governorate": "Red Sea",
        "type": "civic_center",
        "lat": 27.182900,
        "lon": 33.809300,
        "capacity": 6000,
        "address": "Hurghada - Safaga Road",
        "contact": "+20 65 3535600"
    },

    # ----------------------------- MANSOURA --------------------------------
    {
        "id": "MAN-01",
        "name": "Mansoura Stadium",
        "city": "Mansoura",
        "governorate": "Dakahlia",
        "type": "stadium",
        "lat": 31.041900,
        "lon": 31.378400,
        "capacity": 23000,
        "address": "Talkha Rd, Mansoura",
        "contact": "+20 50 2200500"
    },
    {
        "id": "MAN-02",
        "name": "Mit Khaleq Square",
        "city": "Mansoura",
        "governorate": "Dakahlia",
        "type": "open_square",
        "lat": 31.041000,
        "lon": 31.366000,
        "capacity": 10000,
        "address": "Universities Bridge, Mansoura",
        "contact": "+20 50 2222222"
    },

    # ------------------------------- TANTA ----------------------------------
    {
        "id": "TAN-01",
        "name": "Tanta Stadium",
        "city": "Tanta",
        "governorate": "Gharbia",
        "type": "stadium",
        "lat": 30.793500,
        "lon": 31.001900,
        "capacity": 20000,
        "address": "Stadium St, Tanta",
        "contact": "+20 40 3312000"
    },
    {
        "id": "TAN-02",
        "name": "Saeed Square (Midan El Saeyed)",
        "city": "Tanta",
        "governorate": "Gharbia",
        "type": "open_square",
        "lat": 30.788500,
        "lon": 31.001400,
        "capacity": 9000,
        "address": "Downtown Tanta",
        "contact": "+20 40 3331000"
    },

    # ----------------------- NEW ADMIN CAPITAL -----------------------------
    {
        "id": "NAC-01",
        "name": "Al Fattah Al Aleem Mosque Plaza",
        "city": "New Administrative Capital",
        "governorate": "Cairo",
        "type": "civic_center",
        "lat": 30.028300,
        "lon": 31.759500,
        "capacity": 30000,
        "address": "New Administrative Capital",
        "contact": "+20 2 22652555"
    }
]

# Every city with at least one shelter, for a picker that should not offer an empty list.
CITIES = sorted({s["city"] for s in SHELTERS})


def all_shelters() -> List[Dict[str, Any]]:
    return list(SHELTERS)


def cities() -> List[str]:
    return list(CITIES)


def by_city(city: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every shelter, or every shelter in one city. Matching is loose on purpose:
    an operator typing "cairo" under pressure should not be told there is no such place."""
    if not city:
        return list(SHELTERS)
    q = city.strip().lower()
    return [s for s in SHELTERS if q in s["city"].lower()]


def get(shelter_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """One shelter by id, or None. An unknown id is a 404, not an exception."""
    if not shelter_id:
        return None
    q = shelter_id.strip().lower()
    for s in SHELTERS:
        if s["id"].lower() == q:
            return s
    return None


def _reached(origin_lat: float, origin_lon: float, s: Dict[str, Any]) -> Dict[str, Any]:
    km = geo.haversine_km(origin_lat, origin_lon, s["lat"], s["lon"])
    bearing = geo.bearing_deg(origin_lat, origin_lon, s["lat"], s["lon"])
    return {
        "shelter": s,
        "distance_km": round(km, 2),
        "bearing_deg": round(bearing, 1),
        "direction": geo.compass_point(bearing),
        # Labelled estimates, from a walking pace and a city driving average. Neither is
        # a routed time -- see server/route.py for that, and for what it costs.
        "estimated_walk_minutes": geo.walk_minutes(km),
        "estimated_drive_minutes": geo.drive_minutes(km),
    }


def nearest(latitude: Optional[float] = None, longitude: Optional[float] = None,
            limit: int = 3, city: Optional[str] = None) -> List[Dict[str, Any]]:
    """The closest shelters to a point, nearest first.

    With no coordinate the mission anchor is used, because the question an operator is
    actually asking -- "where do we take them from here" -- is about this incident, and
    the server already knows where this incident is.
    """
    if latitude is None or longitude is None:
        a = geo.anchor()
        latitude, longitude = a["lat"], a["lon"]
    pool = by_city(city)
    out = [_reached(latitude, longitude, s) for s in pool]
    out.sort(key=lambda r: r["distance_km"])
    return out[:max(1, min(int(limit), len(SHELTERS)))]
