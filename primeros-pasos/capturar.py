"""Primera entrega: conservar una respuesta e inspeccionarla sin completar ausencias."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import urllib.request
from uuid import uuid4

SOURCE_URL = "https://gtfsrt.renfe.com/vehicle_positions_LD.json"
MAX_BYTES = 15_000_000


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def field_state(mapping, key, valid):
    if key not in mapping or mapping[key] is None:
        return "ausente"
    return "valido" if valid(mapping[key]) else "invalido"


def summarize(original):
    feed = json.loads(original)
    if not isinstance(feed, dict):
        raise ValueError("Se esperaba un objeto JSON con header y entity")
    header = feed.get("header")
    entities = feed.get("entity", [])
    if not isinstance(header, dict) or not isinstance(entities, list):
        raise ValueError("header debe ser un objeto y entity una lista")
    result = {
        "entities": len(entities), "vehicles": 0, "other_entities": 0,
        "malformed_entities": 0, "feed_timestamp": header.get("timestamp"),
        "feed_version": header.get("gtfsRealtimeVersion", header.get("gtfs_realtime_version")),
        "position": {"valido": 0, "ausente": 0, "invalido": 0},
        "observed_at": {"valido": 0, "ausente": 0, "invalido": 0},
        "speed_m_s": {"valido": 0, "ausente": 0, "invalido": 0},
    }
    for entity in entities:
        if not isinstance(entity, dict):
            result["malformed_entities"] += 1
            continue
        if "vehicle" not in entity:
            result["other_entities"] += 1
            continue
        vehicle = entity["vehicle"]
        if not isinstance(vehicle, dict):
            result["malformed_entities"] += 1
            continue
        result["vehicles"] += 1
        position = vehicle.get("position")
        if position is None:
            position_state = "ausente"
            position = {}
        elif not isinstance(position, dict):
            position_state = "invalido"
            position = {}
        elif "latitude" not in position or "longitude" not in position:
            position_state = "ausente"
        else:
            lat, lon = position["latitude"], position["longitude"]
            position_state = "valido" if (number(lat) and number(lon)
                             and -90 <= lat <= 90 and -180 <= lon <= 180) else "invalido"
        result["position"][position_state] += 1
        # GTFS JSON puede representar uint64 como cadena decimal.
        time_state = field_state(vehicle, "timestamp", lambda value:
            (type(value) is int and value >= 0) or
            (isinstance(value, str) and value.isascii() and value.isdecimal()))
        speed_state = field_state(position, "speed", lambda value: number(value) and value >= 0)
        result["observed_at"][time_state] += 1
        result["speed_m_s"][speed_state] += 1
    return result


def capture(output, *, url=None, file=None):
    run = Path(output) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    record = {"schema_version": "leer-datos-trenes-1", "attempted_at": utc_now(),
              "source": url if url else str(Path(file).resolve()),
              "mode": "http" if url else "archivo", "status": "error"}
    try:
        if url:
            request = urllib.request.Request(url, headers={"User-Agent": "CodigoBIM-LecturaTrenes/1.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                original = response.read(MAX_BYTES + 1)
                record["http_status"] = response.status
                record["final_url"] = response.url
                record["headers"] = {key: value for key, value in response.headers.items()
                                     if key.lower() in ("content-type", "date", "last-modified", "etag")}
        else:
            with Path(file).open("rb") as stream:
                original = stream.read(MAX_BYTES + 1)
        record["received_at"] = utc_now()
        if len(original) > MAX_BYTES:
            raise ValueError("La respuesta supera el límite de 15 MB; no se conserva como captura completa")
        (run / "original.json").write_bytes(original)
        record.update(bytes=len(original), sha256=hashlib.sha256(original).hexdigest())
        record["summary"] = summarize(original)
        record["status"] = "ok"
    except (OSError, ValueError, TypeError) as error:
        record["error"] = str(error)
    (run / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return run, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="Sin opción se consulta una vez la fuente pública de Renfe")
    source.add_argument("--archivo", type=Path, help="Inspeccionar un archivo sin consultar la red")
    parser.add_argument("--salida", type=Path, default=Path("data/raw/lecturas"))
    args = parser.parse_args()
    run, record = capture(args.salida, url=None if args.archivo else args.url or SOURCE_URL, file=args.archivo)
    print(json.dumps({"capture": str(run), **record}, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
