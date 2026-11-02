"""Escenarios controlados: ningún recorrido sintético se atribuye a Urda."""

from datetime import datetime, timedelta, timezone

BASE = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def iso(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def synthetic(key, title, rear_speed=50, front_speed=10, separate=False, missing=False, stale=False):
    events = []
    for t in range(0, 61, 10):
        for name, start, speed, track in (("SIM-A", 0, rear_speed, "LAB-1"),
                                          ("SIM-B", 4000, front_speed, "LAB-2" if separate else "LAB-1")):
            chainage = start + speed * (0 if stale else t)
            events.append({"train_id": name, "lat": 39.7 - chainage / 111_195,
                           "lon": -3.8 + (0.005 if track == "LAB-2" else 0),
                           "crs": "EPSG:4326", "chainage_m": chainage,
                           "speed_m_s": None if missing else speed,
                           "observed_at": iso(0 if stale else t),
                           "published_at": iso(t), "received_at": iso(t),
                           "direction": 1, "position_error_m": 5,
                           "track_id": track, "track_basis": "synthetic",
                           "kind": "synthetic", "source": "Código BIM · escenario sintético"})
    return {"id": key, "title": title, "kind": "synthetic", "train_ids": ["SIM-A", "SIM-B"],
            "times": [iso(t) for t in range(0, 61, 10)], "events": events,
            "description": "Geometría y trenes inventados. No reconstruye el accidente.",
            "track": [[-3.8,39.7],[-3.8,39.64]], "track_label": "Trayectoria sintética, no cartografía de vía real"}


def all_scenarios():
    return [synthetic("approach", "Aproximación · misma vía sintética"),
            synthetic("separate", "Trenes próximos · vías diferentes", separate=True),
            synthetic("no-speed", "Velocidad ausente", missing=True),
            synthetic("stale", "Posiciones repetidas y antiguas", stale=True),
            synthetic("diverging", "Separación creciente", rear_speed=10, front_speed=50),
            {"id":"urda-coverage", "title":"Urda · cobertura histórica comprobada", "kind":"historical_audit",
             "times":["2026-10-28T07:15:29+00:00","2026-10-28T07:30:45+00:00","2026-10-28T07:45:30+00:00"],
             "events":[], "train_ids":["02080","06076"], "track":[],
             "description":"Archivo analizado: 10.240 filas, 82 capturas, 19 registros de 02080 y ninguno de 6076/06076. No se redistribuye el CSV sin aclarar su licencia de datos. No hay trayectoria de Iryo que reproducir.",
             "track_label":"Sin vía física ni geometría histórica verificadas"}]
