"""Every table: fleet, contracts, daily reports, billing, maintenance, crew, tenders, off hire and claims, supply,
port calls, dry docks, insurance, costs and budgets.

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
    # Running cost per day: crew, victualling, lubes, management. Spares, port, dry dock and insurance are costed separately.
    daily_opex: Mapped[float]
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


# --- Commercial: tenders, off hire, charterer performance claims ---


class Tender(Base):
    """A bid for a charter. Its margin is modelled from the bid rates and the vessel's running cost (core/commercial.py)."""

    __tablename__ = "tenders"
    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(unique=True)  # the client's tender number
    client: Mapped[str]
    vessel_type: Mapped[str]  # DSV, OSV, BARGE, BULK
    vessel_id: Mapped[str | None] = mapped_column(ForeignKey("vessels.vessel_id"), default=None)  # the vessel offered
    scope: Mapped[str]
    start_date: Mapped[str]
    end_date: Mapped[str]
    due_on: Mapped[str]  # bid submission deadline
    operating_rate: Mapped[float]
    standby_rate: Mapped[float]
    operating_share: Mapped[float] = mapped_column(default=0.85)  # expected share of days paid at the operating rate
    mob_fee: Mapped[float] = mapped_column(default=0)
    demob_fee: Mapped[float] = mapped_column(default=0)
    mob_cost: Mapped[float] = mapped_column(default=0)  # what mobilizing costs us
    extra_daily_cost: Mapped[float] = mapped_column(default=0)  # project cost per day on top of the vessel's running cost
    probability: Mapped[float] = mapped_column(default=0.3)  # chance of winning, used by the forecast
    status: Mapped[str] = mapped_column(default="DRAFT")  # DRAFT, SUBMITTED, WON, LOST, WITHDRAWN
    winning_rate: Mapped[float | None] = mapped_column(default=None)  # on a lost bid: the operating rate that won, if known
    outcome_note: Mapped[str] = mapped_column(default="")
    contract_no: Mapped[str | None] = mapped_column(default=None)  # the contract made from a won bid
    created_by: Mapped[str] = mapped_column(default="")


class OffHireEvent(Base):
    """A period the vessel is off hire by its own fault. Breakdown and maintenance use the contract's maintenance
    allowance first (SUPPLYTIME 2017 cl. 13); any other reason (crew, documents, deficiency) is straight off hire."""

    __tablename__ = "off_hire_events"
    __table_args__ = (Index("ix_offhire_contract", "contract_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    contract_no: Mapped[str | None] = mapped_column(ForeignKey("contracts.contract_no"), default=None)
    start_at: Mapped[str]  # "YYYY-MM-DDTHH:MM", vessel time
    end_at: Mapped[str | None] = mapped_column(default=None)  # None while still off hire
    reason: Mapped[str]  # BREAKDOWN, MAINTENANCE, CREW, DOCUMENTS, OTHER
    description: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")  # OPEN, ENDED (statement sent), AGREED (charterer accepted)
    logged_by: Mapped[str] = mapped_column(default="")
    agreed_by: Mapped[str | None] = mapped_column(default=None)


class PerformanceClaim(Base):
    """A charterer's claim against the vessel's performance (speed, fuel, DP, equipment, off hire). An accepted
    amount is a credit to the charterer and comes off the contract's revenue."""

    __tablename__ = "performance_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_no: Mapped[str] = mapped_column(ForeignKey("contracts.contract_no"))
    kind: Mapped[str]  # SPEED, FUEL, DP, EQUIPMENT, DIVING, OFF_HIRE, OTHER
    period: Mapped[str]  # the hire month it concerns, "YYYY-MM"
    description: Mapped[str]
    amount_claimed: Mapped[float]
    status: Mapped[str] = mapped_column(default="OPEN")  # OPEN, ACCEPTED, REJECTED
    amount_agreed: Mapped[float | None] = mapped_column(default=None)
    raised_by: Mapped[str] = mapped_column(default="")
    raised_on: Mapped[str] = mapped_column(default="")
    response_due: Mapped[str] = mapped_column(default="")
    decided_by: Mapped[str | None] = mapped_column(default=None)
    decision_note: Mapped[str] = mapped_column(default="")


# --- Documents (charter parties, quotes, policies, agency accounts ...) ---


class Document(Base):
    """A file kept against a record. Uploading the same title again adds a version; nothing is overwritten."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_entity", "entity", "entity_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str]  # contract, tender, drydock, policy, port_call, po
    entity_key: Mapped[str]
    kind: Mapped[str]  # CHARTER_PARTY, ADDENDUM, BANK_GUARANTEE, QUOTE, POLICY, INVOICE, OTHER
    title: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    filename: Mapped[str]
    content_type: Mapped[str]
    size: Mapped[int]
    sha256: Mapped[str]  # the stored file's name under var/documents
    note: Mapped[str] = mapped_column(default="")
    uploaded_by: Mapped[str] = mapped_column(default="")
    at: Mapped[str] = mapped_column(default=stamp)


# --- Supply: vendors, spares, stock, purchase orders ---


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]  # SPARES, STORES, SERVICE, AGENT, YARD
    country: Mapped[str] = mapped_column(default="")
    contact: Mapped[str] = mapped_column(default="")
    email: Mapped[str] = mapped_column(default="")
    phone: Mapped[str] = mapped_column(default="")
    tax_id: Mapped[str] = mapped_column(default="")  # GSTIN or equivalent
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    approved: Mapped[bool] = mapped_column(default=True)  # only approved vendors get purchase orders
    rating: Mapped[int | None] = mapped_column(default=None)  # 1 to 5, from the last evaluation


class Part(Base):
    """A spare or store item in the catalogue."""

    __tablename__ = "parts"
    id: Mapped[int] = mapped_column(primary_key=True)
    part_no: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    maker: Mapped[str] = mapped_column(default="")
    unit: Mapped[str] = mapped_column(default="pc")
    unit_cost: Mapped[float] = mapped_column(default=0)  # last purchase price
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None)  # preferred supplier
    lead_days: Mapped[int] = mapped_column(default=14)


SHORE = "SHORE"  # the shore warehouse; every other stock location is a vessel_id


class StockItem(Base):
    """How many of a part are at one place. A spare held for critical equipment (ISM 10.3) names that equipment;
    its minimum level then counts for hire readiness."""

    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("part_id", "location"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    location: Mapped[str]  # a vessel_id, or SHORE
    qty: Mapped[float] = mapped_column(default=0)
    min_qty: Mapped[float] = mapped_column(default=0)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), default=None)
    bin: Mapped[str] = mapped_column(default="")


class StockMove(Base):
    """Every change to stock, so any quantity can be traced."""

    __tablename__ = "stock_moves"
    __table_args__ = (Index("ix_moves_part", "part_id", "location"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    location: Mapped[str]
    qty: Mapped[float]  # + in, - out
    kind: Mapped[str]  # RECEIPT, ISSUE, TRANSFER, ADJUST
    ref: Mapped[str] = mapped_column(default="")
    by: Mapped[str] = mapped_column(default="")
    at: Mapped[str] = mapped_column(default=stamp)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    po_no: Mapped[str] = mapped_column(primary_key=True)  # "PO-2610-001"
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    deliver_to: Mapped[str]  # a vessel_id, or SHORE
    status: Mapped[str] = mapped_column(default="DRAFT")  # DRAFT, APPROVED, ORDERED, PART_RECEIVED, RECEIVED, CANCELLED
    total: Mapped[float] = mapped_column(default=0)
    needed_by: Mapped[str | None] = mapped_column(default=None)
    note: Mapped[str] = mapped_column(default="")
    raised_by: Mapped[str] = mapped_column(default="")
    raised_on: Mapped[str] = mapped_column(default="")
    approved_by: Mapped[str | None] = mapped_column(default=None)
    ordered_on: Mapped[str | None] = mapped_column(default=None)


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    po_no: Mapped[str] = mapped_column(ForeignKey("purchase_orders.po_no"), index=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"), default=None)  # None for a service or one-off item
    description: Mapped[str]
    qty: Mapped[float]
    unit_price: Mapped[float]
    received_qty: Mapped[float] = mapped_column(default=0)


class SpareRequest(Base):
    """A maintenance job needs a spare. While it is WAITING the job is blocked, awaiting the spare."""

    __tablename__ = "spare_requests"
    __table_args__ = (Index("ix_spare_requests_job", "job_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("maintenance_jobs.id"))
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    qty: Mapped[float]
    status: Mapped[str] = mapped_column(default="WAITING")  # WAITING, ISSUED, CANCELLED
    po_no: Mapped[str | None] = mapped_column(default=None)
    requested_on: Mapped[str] = mapped_column(default="")
    issued_on: Mapped[str | None] = mapped_column(default=None)


# --- Port calls and disbursements ---


class PortCall(Base):
    __tablename__ = "port_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    port: Mapped[str]
    purpose: Mapped[str]  # crew change, bunkers, stores, repairs ...
    eta: Mapped[str]
    etd: Mapped[str]
    ata: Mapped[str | None] = mapped_column(default=None)
    atd: Mapped[str | None] = mapped_column(default=None)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None)
    appointed_on: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="PLANNED")  # PLANNED, ARRIVED, SAILED, CLOSED
    advance_paid: Mapped[float] = mapped_column(default=0)  # paid to the agent against the PDA
    created_by: Mapped[str] = mapped_column(default="")


class DisbursementLine(Base):
    """One line of the agent's account: estimated in the PDA, final in the FDA."""

    __tablename__ = "disbursement_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    port_call_id: Mapped[int] = mapped_column(ForeignKey("port_calls.id"), index=True)
    item: Mapped[str]
    pda: Mapped[float] = mapped_column(default=0)
    fda: Mapped[float | None] = mapped_column(default=None)


# --- Dry dock projects ---


class DryDockProject(Base):
    __tablename__ = "drydock_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="PLANNING")  # PLANNING, CONTRACTED, IN_DOCK, COMPLETED
    planned_start: Mapped[str]
    planned_end: Mapped[str]
    actual_start: Mapped[str | None] = mapped_column(default=None)
    actual_end: Mapped[str | None] = mapped_column(default=None)
    yard_quote_id: Mapped[int | None] = mapped_column(default=None)  # the chosen yard
    bottom_survey: Mapped[bool] = mapped_column(default=True)  # completing it records the bottom survey
    created_by: Mapped[str] = mapped_column(default="")


class DryDockItem(Base):
    __tablename__ = "drydock_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("drydock_projects.id"), index=True)
    category: Mapped[str]  # HULL, MACHINERY, CLASS, ELECTRICAL, SAFETY, DIVING, OTHER
    description: Mapped[str]
    budget: Mapped[float] = mapped_column(default=0)
    actual: Mapped[float] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="OPEN")  # OPEN, DONE, DEFERRED


class YardQuote(Base):
    __tablename__ = "yard_quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("drydock_projects.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    price: Mapped[float]
    days: Mapped[int]  # days in dock
    deviation_cost: Mapped[float] = mapped_column(default=0)  # steaming there and back, fuel, extra port costs
    note: Mapped[str] = mapped_column(default="")


# --- Insurance ---


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # HM (hull and machinery), PI (P&I club), CREW, LOH (loss of hire), OTHER
    insurer: Mapped[str]
    policy_no: Mapped[str]
    vessel_id: Mapped[str | None] = mapped_column(ForeignKey("vessels.vessel_id"), default=None)  # None: covers the whole fleet
    sum_insured: Mapped[float] = mapped_column(default=0)
    deductible: Mapped[float] = mapped_column(default=0)
    premium: Mapped[float] = mapped_column(default=0)  # for the whole policy period
    start_date: Mapped[str]
    end_date: Mapped[str]


class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("insurance_policies.id"))
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    incident_on: Mapped[str]
    description: Mapped[str]
    amount: Mapped[float]  # the loss claimed
    status: Mapped[str] = mapped_column(default="NOTIFIED")  # NOTIFIED, SUBMITTED, SETTLED, REJECTED
    recovered: Mapped[float | None] = mapped_column(default=None)
    settled_on: Mapped[str | None] = mapped_column(default=None)
    created_by: Mapped[str] = mapped_column(default="")


# --- Finance: costs and budgets ---


class CostEntry(Base):
    """A cost booked to a vessel, and to the contract it was on that day. Posted by purchase receipts on board,
    spares sent on board, closed port calls, completed dry docks and insurance recoveries, or entered by hand.
    The vessel's daily running cost (crew, victualling, management) and insurance premiums are worked out, not booked."""

    __tablename__ = "cost_entries"
    __table_args__ = (Index("ix_costs_vessel_date", "vessel_id", "on_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    contract_no: Mapped[str | None] = mapped_column(default=None)
    on_date: Mapped[str]
    category: Mapped[str]  # SPARES, PORT, DRYDOCK, INSURANCE, OTHER
    amount: Mapped[float]  # a recovery is negative
    description: Mapped[str]
    source: Mapped[str] = mapped_column(default="MANUAL")  # PO, TRANSFER, PORT_CALL, DRYDOCK, INSURANCE, MANUAL
    ref: Mapped[str] = mapped_column(default="")
    created_by: Mapped[str] = mapped_column(default="")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("vessel_id", "period", "category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_id: Mapped[str] = mapped_column(ForeignKey("vessels.vessel_id"))
    period: Mapped[str]  # "YYYY-MM"
    category: Mapped[str]  # REVENUE, RUNNING, INSURANCE, SPARES, PORT, DRYDOCK, OTHER
    amount: Mapped[float]
