"""Hogar de dos personas: seed y permisos de Telegram."""

from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Household, Person, PersonRole


def _parse_telegram_id(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


async def seed_household() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        household = await session.scalar(select(Household).order_by(Household.id).limit(1))
        if household is None:
            household = Household(
                name=f"Hogar {settings.person_a_name} y {settings.person_b_name}"
            )
            session.add(household)
            await session.flush()

        await _upsert_person(
            session,
            household.id,
            PersonRole.a,
            settings.person_a_name,
            _parse_telegram_id(settings.person_a_telegram_id),
        )
        await _upsert_person(
            session,
            household.id,
            PersonRole.b,
            settings.person_b_name,
            _parse_telegram_id(settings.person_b_telegram_id),
        )
        await session.commit()


async def _upsert_person(
    session,
    household_id: int,
    role: PersonRole,
    name: str,
    telegram_user_id: int | None,
) -> Person:
    person = await session.scalar(
        select(Person).where(Person.household_id == household_id, Person.role == role)
    )
    if person is None:
        person = Person(
            household_id=household_id,
            name=name,
            role=role,
            telegram_user_id=telegram_user_id,
        )
        session.add(person)
        return person

    person.name = name
    if telegram_user_id is not None:
        person.telegram_user_id = telegram_user_id
    return person


async def get_person_by_telegram_id(telegram_user_id: int) -> Person | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Person).where(Person.telegram_user_id == telegram_user_id)
        )


async def is_household_member(telegram_user_id: int) -> bool:
    settings = get_settings()
    if telegram_user_id in settings.allowed_telegram_ids:
        return True
    person = await get_person_by_telegram_id(telegram_user_id)
    return person is not None


async def bind_telegram_user(telegram_user_id: int, requested_name: str) -> str:
    """Vincula un Telegram ID a Mauri o Daysi. Devuelve mensaje para el usuario."""
    settings = get_settings()
    aliases = {
        settings.person_a_name.strip().lower(): PersonRole.a,
        settings.person_b_name.strip().lower(): PersonRole.b,
    }
    role = aliases.get(requested_name.strip().lower())
    if role is None:
        return (
            f"No estás en el hogar.\n\n"
            f"Usa /soy {settings.person_a_name} o /soy {settings.person_b_name}."
        )

    async with SessionLocal() as session:
        already = await session.scalar(
            select(Person).where(Person.telegram_user_id == telegram_user_id)
        )
        if already is not None:
            return f"Ya estás en el hogar como {already.name}."

        person = await session.scalar(select(Person).where(Person.role == role))
        if person is None:
            return "El hogar aún no está creado. Reinicia la app."

        if person.telegram_user_id is not None and person.telegram_user_id != telegram_user_id:
            return f"No estás en el hogar.\n\n{person.name} ya está vinculado a otra cuenta."

        person.telegram_user_id = telegram_user_id
        await session.commit()
        return f"Listo, {person.name}. Ya estás en el hogar."
