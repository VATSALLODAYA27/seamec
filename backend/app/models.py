"""Every table. Phase 1: fleet, contracts, daily progress reports and charter-hire billing.

shortcut: dates are ISO text (YYYY-MM-DD), which sorts correctly; money is float rupees.
Switch to Date and Numeric columns before real money is booked.
"""
import time
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> float:
    """Seconds since 1970, UTC. Stored as a plain number, so no database timezone handling is involved."""
    return time.time()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_dict(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


# --- Accounts and the audit trail ---


class User(Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    role: Mapped[str]  # ops, manager, admin, client (see auth.py)
    password_hash: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)
    # For a client account: the client name on its contracts. A client sees only those contracts.
    client_name: Mapped[str | None] = mapped_column(default=None)


class LoginToken(Base):
    __tablename__ = "login_tokens"
    digest: Mapped[str] = mapped_column(primary_key=True)  # SHA-256 of the cookie value
    username: Mapped[str] = mapped_column(ForeignKey("users.username"))
    expires_at: Mapped[float]


class AuditEntry(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(default=stamp)
    username: Mapped[str]
    role: Mapped[str]
    action: Mapped[str]
    target: Mapped[str]
    detail: Mapped[str]


# --- Fleet ---


class Vessel(Base):
    __tablename__ = "vessels"
    vessel_id: Mapped[str] = mapped_column(primary_key=True)  # "SM-PRINCESS"
    name: Mapped[str]
    vessel_type: Mapped[str]  # DSV, OSV, BARGE, BULK
    imo: Mapped[str]
    mmsi: Mapped[str | None] = mapped_column(default=None)  # 9 digits; what AIS position reports are keyed by
    flag: Mapped[str]
    built_year: Mapped[int | None] = mapped_column(default=None)
    entity: Mapped[str]  # owning company
    daily_opex: Mapped[float]  # running cost per day, for vessel P&L
    # Where the vessel sits when it has no reported position (home port, anchorage or shipyard).
    base_port: Mapped[str] = mapped_column(default="")
    base_lat: Mapped[float | None] = mapped_column(default=None)
    base_lon: Mapped[float | None] = mapped_column(default=None)
    # Last time the outside of the bottom was inspected (dry dock, or an in-water survey accepted by class).
    # HSSC: two such inspections in every 5 years, never more than 36 months apart.
    last_bottom_survey_on: Mapped[str | None] = mapped_column(default=None)
    # AVAILABLE, ON_HIRE, DRY_DOCK. ON_HIRE is set by an active contract.
    status: Mapped[str] = mapped_column(default="AVAILABLE")


class Certificate(Base):
    __tablename__ = "certificates"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    name: Mapped[str]
    authority: Mapped[str]
    issued_on: Mapped[str]
    expires_on: Mapped[str]
    critical: Mapped[bool] = mapped_column(default=True)  # an expired critical certificate stops the vessel going on hire
    # Most statutory certificates (IMO harmonized system, HSSC) run 5 years and need an annual survey within
    # 3 months either side of each anniversary of the expiry date. This is the date of the latest such endorsement.
    annual_survey: Mapped[bool] = mapped_column(default=True)
    endorsed_on: Mapped[str | None] = mapped_column(default=None)


# --- Contracts ---


class Contract(Base):
    __tablename__ = "contracts"
    contract_no: Mapped[str] = mapped_column(primary_key=True)
    client: Mapped[str]
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    scope: Mapped[str]
    start_date: Mapped[str]
    end_date: Mapped[str]
    operating_rate: Mapped[float]  # per day
    standby_rate: Mapped[float]  # per day
    breakdown_allowance_hrs: Mapped[float]  # maintenance allowance per month (SUPPLYTIME 2017: 24 h); above it, off hire
    allowance_accrues: Mapped[bool] = mapped_column(default=True)  # unused allowance carries forward (SUPPLYTIME 2017)
    weather_billing: Mapped[str] = mapped_column(default="STANDBY")  # weather hours paid at OPERATING or STANDBY rate
    tax_label: Mapped[str] = mapped_column(default="GST")  # e.g. "GST", "IGST", "UAE VAT"; the rate depends on how the charter is classified
    tax_rate: Mapped[float] = mapped_column(default=0.18)
    # When true, the client's representative must sign the monthly timesheet before the invoice can be approved.
    client_signoff_required: Mapped[bool] = mapped_column(default=False)
    mob_fee: Mapped[float] = mapped_column(default=0)
    demob_fee: Mapped[float] = mapped_column(default=0)
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    bg_amount: Mapped[float] = mapped_column(default=0)  # performance bank guarantee
    bg_expiry: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="ACTIVE")  # ACTIVE, COMPLETED
    created_by: Mapped[str] = mapped_column(default="")


# --- Operations: the daily progress report ---


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("vessel_id", "on_date"), Index("ix_reports_contract", "contract_no"))
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    contract_no: Mapped[str | None] = mapped_column(ForeignKey("contracts.contract_no"))
    on_date: Mapped[str]
    location: Mapped[str]
    lat: Mapped[float | None] = mapped_column(default=None)  # noon position, decimal degrees
    lon: Mapped[float | None] = mapped_column(default=None)
    # The 24 hours of the day, split by what the vessel was doing. They must add up to 24.
    operating_hrs: Mapped[float]
    standby_hrs: Mapped[float]  # ready, waiting on the client
    weather_hrs: Mapped[float]  # waiting on weather
    breakdown_hrs: Mapped[float]  # vessel's own fault
    transit_hrs: Mapped[float]
    work_done: Mapped[str]
    dive_hrs: Mapped[float] = mapped_column(default=0)
    rov_hrs: Mapped[float] = mapped_column(default=0)
    fuel_rob: Mapped[float] = mapped_column(default=0)  # fuel remaining on board, m3
    fuel_received: Mapped[float] = mapped_column(default=0)
    pob: Mapped[int] = mapped_column(default=0)  # persons on board
    # The equipment that broke down, when there were breakdown hours. Filing the report raises a defect on it.
    breakdown_equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), default=None)
    # Made by the device that filed it. Sending the same report again (a retry after a dropped VSAT link) is
    # recognised by this and accepted once, instead of being refused as a duplicate.
    client_ref: Mapped[str | None] = mapped_column(default=None)
    incidents: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="SUBMITTED")  # SUBMITTED, APPROVED, REJECTED
    submitted_by: Mapped[str] = mapped_column(default="")
    approved_by: Mapped[str | None] = mapped_column(default=None)


# --- Maintenance (ISM Code 10: maintain the ship; 10.3: identify critical equipment and test it regularly) ---


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    name: Mapped[str]
    system: Mapped[str]  # Diving, DP, Power, Propulsion, Lifting, ROV, Safety
    critical: Mapped[bool] = mapped_column(default=False)  # ISM 10.3: sudden failure may cause a hazardous situation
    running_hours: Mapped[float] = mapped_column(default=0)
    hours_updated_on: Mapped[str | None] = mapped_column(default=None)


class MaintenanceJob(Base):
    """A planned job (repeats by days and/or running hours) or a defect (a breakdown to be fixed once)."""

    __tablename__ = "maintenance_jobs"
    __table_args__ = (Index("ix_jobs_equipment", "equipment_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"))
    kind: Mapped[str]  # PLANNED or DEFECT
    title: Mapped[str]
    interval_days: Mapped[int | None] = mapped_column(default=None)
    interval_hours: Mapped[float | None] = mapped_column(default=None)
    last_done_on: Mapped[str | None] = mapped_column(default=None)
    last_done_hours: Mapped[float | None] = mapped_column(default=None)
    # Defects only
    status: Mapped[str] = mapped_column(default="OPEN")  # OPEN or CLOSED (a planned job stays OPEN: it repeats)
    raised_on: Mapped[str | None] = mapped_column(default=None)
    report_id: Mapped[int | None] = mapped_column(default=None)
    downtime_hrs: Mapped[float] = mapped_column(default=0)
    closed_on: Mapped[str | None] = mapped_column(default=None)
    note: Mapped[str] = mapped_column(default="")


# --- Crew (STCW certificates, MLC service limits, IMCA diver medicals) ---


class CrewMember(Base):
    __tablename__ = "crew"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    rank: Mapped[str]  # Master, Chief Officer, DPO, Chief Engineer, Second Engineer, Diving Superintendent, Diving Supervisor, Diver, LST
    active: Mapped[bool] = mapped_column(default=True)


class CrewCertificate(Base):
    __tablename__ = "crew_certificates"
    id: Mapped[int] = mapped_column(primary_key=True)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crew.id"))
    name: Mapped[str]
    expires_on: Mapped[str]


class Assignment(Base):
    """A trip on board: signed on, planned relief, and the actual sign-off once it happens."""

    __tablename__ = "assignments"
    __table_args__ = (Index("ix_assign_vessel", "vessel_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crew.id"))
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    sign_on: Mapped[str]
    relief_due: Mapped[str]  # planned sign-off
    signed_off: Mapped[str | None] = mapped_column(default=None)


class ManningRequirement(Base):
    """The minimum crew by rank a vessel must carry: from its Minimum Safe Manning Document (flag state) and,
    for diving, the client's / IMCA dive team requirement."""

    __tablename__ = "manning"
    __table_args__ = (UniqueConstraint("vessel_id", "rank"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    rank: Mapped[str]
    count: Mapped[int]


# --- Client sign-off ---


class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (UniqueConstraint("contract_no", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_no: Mapped[str] = mapped_column(ForeignKey("contracts.contract_no"))
    period: Mapped[str]
    status: Mapped[str]  # SIGNED or DISPUTED
    by: Mapped[str]
    at: Mapped[str]
    note: Mapped[str] = mapped_column(default="")


# --- Automatic positions ---


class PositionFix(Base):
    """A position sent automatically: from the vessel's own GPS over VSAT, or picked up from AIS."""

    __tablename__ = "position_fixes"
    __table_args__ = (Index("ix_fixes_vessel_at", "vessel_id", "at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    at: Mapped[str]  # UTC, ISO 8601 "YYYY-MM-DDTHH:MM:SSZ", so it sorts as text
    lat: Mapped[float]
    lon: Mapped[float]
    sog: Mapped[float | None] = mapped_column(default=None)  # speed over ground, knots
    cog: Mapped[float | None] = mapped_column(default=None)  # course over ground, degrees
    source: Mapped[str]  # VSAT or AIS


# --- Billing ---


class HireInvoice(Base):
    __tablename__ = "hire_invoices"
    __table_args__ = (UniqueConstraint("contract_no", "period"),)
    inv_no: Mapped[str] = mapped_column(primary_key=True)  # "INV-2610-001"
    contract_no: Mapped[str] = mapped_column(ForeignKey("contracts.contract_no"))
    period: Mapped[str]  # "2026-10"
    invoice_date: Mapped[str]
    due_date: Mapped[str]
    calc: Mapped[dict] = mapped_column(JSON)  # the full breakdown from core.billing, kept as it was when drafted
    amount: Mapped[float]
    tax_label: Mapped[str] = mapped_column(default="GST")
    tax_rate: Mapped[float] = mapped_column(default=0.18)
    tax: Mapped[float]
    total: Mapped[float]
    status: Mapped[str] = mapped_column(default="DRAFT")  # DRAFT, APPROVED, PAID
    created_by: Mapped[str] = mapped_column(default="")
    approved_by: Mapped[str | None] = mapped_column(default=None)
    paid_on: Mapped[str | None] = mapped_column(default=None)
