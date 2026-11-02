"""Regla condicional de aproximación. Sin geometría inferida ni comunicaciones externas."""

from datetime import datetime, timezone
import math

RULE_VERSION = "approach-1.0.0"
MAX_AGE_S = 30
MAX_SKEW_S = 10
MAX_TTC_S = 120
MAX_GAP_M = 10_000


def instant(value):
    if not isinstance(value, str):
        raise ValueError("El instante necesita zona horaria explícita")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Instante sin zona horaria")
    return parsed.astimezone(timezone.utc).timestamp()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def available(events, at):
    """Solo eventos ya observados, publicados y recibidos. No interpola."""
    now = instant(at)
    latest = {}
    for item in events:
        try:
            received = instant(item["received_at"])
            published = instant(item["published_at"]) if item.get("published_at") else received
            observed = instant(item["observed_at"]) if item.get("observed_at") else None
            if received > now or published > now or (observed is not None and observed > now):
                continue
            if observed is not None and (observed > received or observed > published):
                continue
            key = item["train_id"]
            rank = (observed if observed is not None else float("-inf"), received)
            if key not in latest or rank > latest[key][0]:
                latest[key] = (rank, dict(item))
        except (KeyError, TypeError, ValueError):
            continue
    return [entry[1] for entry in latest.values()]


def evaluate(events, train_ids, at):
    now = instant(at)
    samples = {e["train_id"]: e for e in available(events, at)}
    result = {"rule_version": RULE_VERSION, "at": at, "status": "not_evaluable",
              "message": "Faltan datos para evaluar", "reasons": [],
              "potential_severity": "No se estima", "data_confidence": "insuficiente"}
    if len(train_ids) != 2 or train_ids[0] == train_ids[1]:
        raise ValueError("Se necesitan dos servicios distintos")
    if any(i not in samples for i in train_ids):
        result["reasons"] = ["Falta al menos un servicio en los datos disponibles"]
        return result
    a, b = (samples[i] for i in train_ids)
    reasons = []
    for item in (a, b):
        label = item["train_id"]
        if not item.get("observed_at"):
            reasons.append(f"{label}: falta tiempo original de observación")
        elif now - instant(item["observed_at"]) > MAX_AGE_S:
            reasons.append(f"{label}: observación de más de {MAX_AGE_S} s")
        if not finite(item.get("speed_m_s")) or item.get("speed_m_s", -1) < 0:
            reasons.append(f"{label}: velocidad desconocida o inválida")
        if not finite(item.get("chainage_m")):
            reasons.append(f"{label}: posición longitudinal desconocida")
        if not item.get("track_id") or item.get("track_basis") not in ("verified", "synthetic"):
            reasons.append(f"{label}: vía física sin verificar")
        if item.get("kind") not in ("observation", "synthetic"):
            reasons.append(f"{label}: una interpolación/predicción no es una observación")
        if item.get("direction") not in (-1, 1) or isinstance(item.get("direction"), bool):
            reasons.append(f"{label}: sentido longitudinal desconocido")
        if not finite(item.get("position_error_m")) or item.get("position_error_m", -1) < 0:
            reasons.append(f"{label}: incertidumbre espacial desconocida")
    if reasons:
        result["reasons"] = reasons
        return result
    if a["track_id"] != b["track_id"]:
        result.update(status="no_candidate", message="Vías distintas: no hay candidato de alcance",
                      data_confidence="vía declarada")
        return result
    if a["direction"] != b["direction"]:
        result["reasons"] = ["Sentidos opuestos: fuera de esta regla de alcance"]
        return result
    skew = abs(instant(a["observed_at"]) - instant(b["observed_at"]))
    if skew > MAX_SKEW_S:
        result["reasons"] = [f"Observaciones separadas más de {MAX_SKEW_S} s"]
        return result
    direction = a["direction"]
    rear, front = sorted((a, b), key=lambda e: e["chainage_m"] * direction)
    gap = (front["chainage_m"] - rear["chainage_m"]) * direction
    # Incertidumbre espacial más desplazamiento potencial durante el desfase.
    uncertainty = a["position_error_m"] + b["position_error_m"] + skew * max(a["speed_m_s"], b["speed_m_s"])
    if gap <= uncertainty:
        result["reasons"] = ["El orden longitudinal no se resuelve con la incertidumbre disponible"]
        return result
    closing = rear["speed_m_s"] - front["speed_m_s"]
    ttc = gap / closing if closing > 0 else None
    candidate = closing > 0 and ttc <= MAX_TTC_S and gap <= MAX_GAP_M
    result.update(status="candidate" if candidate else "no_candidate",
                  message="Posible aproximación para revisión" if candidate else "Sin candidato con esta regla",
                  reasons=["Misma vía declarada, orden longitudinal resuelto y velocidades constantes"],
                  rear=rear["train_id"], front=front["train_id"], gap_m=gap,
                  uncertainty_m=uncertainty, closing_speed_m_s=closing,
                  conditional_reference_reach_s=ttc,
                  potential_severity="Potencialmente grave; sin probabilidad de colisión" if candidate else "No se estima",
                  data_confidence="escenario controlado" if a["kind"] == b["kind"] == "synthetic" else "condicionada a las observaciones")
    return result
