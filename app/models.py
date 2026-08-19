"""Modelos SQLAlchemy — ver docs/DATA_MODEL.md."""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PersonRole(str, enum.Enum):
    a = "a"
    b = "b"


class SplitType(str, enum.Enum):
    shared = "shared"
    personal = "personal"


class ExpenseKind(str, enum.Enum):
    expense = "expense"
    invoice = "invoice"


class ExpenseStatus(str, enum.Enum):
    pending_confirm = "pending_confirm"
    confirmed = "confirmed"
    rejected = "rejected"


class Category(str, enum.Enum):
    comida = "comida"
    supermercado = "supermercado"
    transporte = "transporte"
    vivienda = "vivienda"
    servicios = "servicios"
    salud = "salud"
    educacion = "educacion"
    entretenimiento = "entretenimiento"
    ropa = "ropa"
    mascotas = "mascotas"
    otros = "otros"


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))

    persons: Mapped[list[Person]] = relationship(back_populates="household")
    expenses: Mapped[list[Expense]] = relationship(back_populates="household")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    role: Mapped[PersonRole] = mapped_column(Enum(PersonRole, native_enum=False, length=8))

    household: Mapped[Household] = relationship(back_populates="persons")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    created_by_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"), nullable=True
    )
    paid_by_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"), nullable=True
    )
    split_type: Mapped[SplitType] = mapped_column(
        Enum(SplitType, native_enum=False, length=16), default=SplitType.shared
    )
    kind: Mapped[ExpenseKind] = mapped_column(
        Enum(ExpenseKind, native_enum=False, length=16), default=ExpenseKind.expense
    )
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(ExpenseStatus, native_enum=False, length=24),
        default=ExpenseStatus.pending_confirm,
        index=True,
    )
    spent_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[Category] = mapped_column(
        Enum(Category, native_enum=False, length=32), default=Category.otros
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    household: Mapped[Household] = relationship(back_populates="expenses")
    invoice: Mapped[InvoiceDetail | None] = relationship(
        back_populates="expense", uselist=False
    )


class InvoiceDetail(Base):
    __tablename__ = "invoice_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id"), unique=True, index=True
    )
    ruc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    authorization_sri: Mapped[str | None] = mapped_column(String(80), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    iva_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    iva_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    items_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    expense: Mapped[Expense] = relationship(back_populates="invoice")
