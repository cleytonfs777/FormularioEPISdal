"""Fuso America/Sao_Paulo: banco guarda UTC, exibição/filtros em horário de Brasília."""
from datetime import date, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    BR_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base tz no host
    BR_TZ = timezone(timedelta(hours=-3), "BRT")


def agora_br() -> datetime:
    return datetime.now(BR_TZ)


def para_br(dt: datetime | None) -> datetime | None:
    """SQLite devolve datetime sem fuso; ele é sempre UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BR_TZ)


def fmt_br(dt: datetime | None) -> str:
    d = para_br(dt)
    return d.strftime("%d/%m/%Y %H:%M") if d else ""


def iso_br(dt: datetime | None) -> str | None:
    d = para_br(dt)
    return d.isoformat() if d else None


def inicio_dia_utc(dia: str) -> datetime:
    """'aaaa-mm-dd' (dia em Brasília) -> início do dia em UTC naive, como gravado no SQLite."""
    local = datetime.combine(date.fromisoformat(dia), time.min, tzinfo=BR_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def fim_dia_utc(dia: str) -> datetime:
    """Início do dia seguinte (limite exclusivo) em UTC naive."""
    return inicio_dia_utc((date.fromisoformat(dia) + timedelta(days=1)).isoformat())
