import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"


# --- Accounts ---


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class UserCreateIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9_.-]{3,32}$")
    name: str = Field(min_length=1, max_length=80)
    role: Literal["ops", "manager", "admin", "client"]
    password: str = Field(min_length=10, max_length=128)
    client_name: str | None = Field(default=None, max_length=120)  # required for a client account: the client on its contracts

    @model_validator(mode="after")
    def client_has_a_name(self):
        if self.role == "client" and not (self.client_name or "").strip():
            raise ValueError("A client account needs the client name exactly as it appears on the contracts.")
        return self


class UserActiveIn(BaseModel):
    active: bool


# --- Fleet and contracts ---


class CertificateRenewIn(BaseModel):
    issued_on: str = Field(pattern=ISO_DATE)
    expires_on: str = Field(pattern=ISO_DATE)

    @model_validator(mode="after")
    def after_issue(self):
        if self.expires_on <= self.issued_on:
            raise ValueError("The expiry date must be after the issue date.")
        return self


class ContractIn(BaseModel):
    contract_no: str = Field(min_length=3, max_length=40)
    client: str = Field(min_length=2, max_length=120)
    vessel_id: str
    scope: str = Field(min_length=2, max_length=500)
    start_date: str = Field(pattern=ISO_DATE)
    end_date: str = Field(pattern=ISO_DATE)
    operating_rate: float = Field(gt=0)
    standby_rate: float = Field(ge=0)
    breakdown_allowance_hrs: float = Field(ge=0, le=744)
    allowance_accrues: bool = True
    weather_billing: Literal["OPERATING", "STANDBY"] = "STANDBY"
    tax_label: str = Field(default="GST", min_length=1, max_length=30)
    tax_rate: float = Field(default=0.18, ge=0, le=0.5)
    client_signoff_required: bool = False
    mob_fee: float = Field(default=0, ge=0)
    demob_fee: float = Field(default=0, ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=180)
    bg_amount: float = Field(default=0, ge=0)
    bg_expiry: str | None = Field(default=None, pattern=ISO_DATE)

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.end_date < self.start_date:
            raise ValueError("The end date must not be before the start date.")
        if self.standby_rate > self.operating_rate:
            raise ValueError("The standby rate is normally below the operating rate.")
        return self


# --- Daily progress report ---

HOURS = Field(ge=0, le=24)


class DailyReportIn(BaseModel):
    vessel_id: str
    on_date: str = Field(pattern=ISO_DATE)
    location: str = Field(min_length=1, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    operating_hrs: float = HOURS
    standby_hrs: float = HOURS
    weather_hrs: float = HOURS
    breakdown_hrs: float = HOURS
    transit_hrs: float = HOURS
    work_done: str = Field(min_length=1, max_length=2000)
    dive_hrs: float = Field(default=0, ge=0, le=500)
    rov_hrs: float = Field(default=0, ge=0, le=100)
    fuel_rob: float = Field(default=0, ge=0)
    fuel_received: float = Field(default=0, ge=0)
    pob: int = Field(default=0, ge=0, le=500)
    breakdown_equipment_id: int | None = None
    client_ref: str | None = Field(default=None, max_length=64)
    incidents: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def whole_day(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("Give both latitude and longitude, or neither.")
        total = self.operating_hrs + self.standby_hrs + self.weather_hrs + self.breakdown_hrs + self.transit_hrs
        if abs(total - 24) > 0.01:
            raise ValueError(f"The hours must add up to 24; they add up to {total:g}.")
        return self


class EndorseIn(BaseModel):
    on: str = Field(pattern=ISO_DATE)


# --- Automatic positions (the VSAT feed) ---


class FixIn(BaseModel):
    # The feed key says which vessel is posting; vessel_id or MMSI, when given, must be that vessel.
    vessel_id: str | None = None
    mmsi: str | None = Field(default=None, pattern=r"^\d{9}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")  # UTC; now when left out
    sog: float | None = Field(default=None, ge=0, le=60)
    cog: float | None = Field(default=None, ge=0, le=360)
    source: Literal["VSAT"] = "VSAT"  # AIS positions come only from the AIS listener, never through the feed


class FeedIn(BaseModel):
    fixes: list[FixIn] = Field(min_length=1, max_length=500)


class HoursIn(BaseModel):
    hours: float = Field(ge=0, le=500_000)


class JobDoneIn(BaseModel):
    on: str = Field(pattern=ISO_DATE)
    hours: float | None = Field(default=None, ge=0)


class CloseDefectIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)  # what was found and done


class AssignIn(BaseModel):
    crew_id: int
    vessel_id: str
    sign_on: str = Field(pattern=ISO_DATE)
    relief_due: str = Field(pattern=ISO_DATE)


class SignOffIn(BaseModel):
    on: str = Field(pattern=ISO_DATE)


class TimesheetDecisionIn(BaseModel):
    contract_no: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    decision: Literal["SIGNED", "DISPUTED"]
    note: str = Field(default="", max_length=1000)


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


# --- Billing ---


class InvoiceDraftIn(BaseModel):
    contract_no: str
    period: str

    @field_validator("period")
    @classmethod
    def month(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("The period is a month, like 2026-10.")
        return v


class PaymentIn(BaseModel):
    paid_on: str = Field(pattern=ISO_DATE)


# --- Tenders, off hire, claims ---

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"
MINUTE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"


def money(default: float = 0):
    return Field(default=default, ge=0, le=1e11)


class TenderIn(BaseModel):
    ref: str = Field(min_length=2, max_length=60)
    client: str = Field(min_length=2, max_length=120)
    vessel_type: Literal["DSV", "OSV", "BARGE", "BULK"]
    vessel_id: str | None = None
    scope: str = Field(min_length=2, max_length=500)
    start_date: str = Field(pattern=ISO_DATE)
    end_date: str = Field(pattern=ISO_DATE)
    due_on: str = Field(pattern=ISO_DATE)
    operating_rate: float = Field(gt=0, le=1e9)
    standby_rate: float = Field(ge=0, le=1e9)
    operating_share: float = Field(default=0.85, ge=0, le=1)
    mob_fee: float = money()
    demob_fee: float = money()
    mob_cost: float = money()
    extra_daily_cost: float = money()
    probability: float = Field(default=0.3, ge=0, le=1)

    @model_validator(mode="after")
    def sensible(self):
        if self.end_date < self.start_date:
            raise ValueError("The end date must not be before the start date.")
        if self.standby_rate > self.operating_rate:
            raise ValueError("The standby rate is normally below the operating rate.")
        return self


class TenderOutcomeIn(BaseModel):
    status: Literal["SUBMITTED", "WON", "LOST", "WITHDRAWN"]
    winning_rate: float | None = Field(default=None, gt=0)
    note: str = Field(default="", max_length=1000)


class TenderToContractIn(BaseModel):
    contract_no: str = Field(min_length=3, max_length=40)
    vessel_id: str | None = None  # defaults to the vessel offered


class OffHireIn(BaseModel):
    vessel_id: str
    start_at: str = Field(pattern=MINUTE)
    end_at: str | None = Field(default=None, pattern=MINUTE)
    reason: Literal["BREAKDOWN", "MAINTENANCE", "CREW", "DOCUMENTS", "OTHER"]
    description: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def in_order(self):
        if self.end_at and self.end_at <= self.start_at:
            raise ValueError("The end must be after the start.")
        return self


class OffHireEndIn(BaseModel):
    end_at: str = Field(pattern=MINUTE)


class ClaimIn(BaseModel):
    contract_no: str
    kind: Literal["SPEED", "FUEL", "DP", "EQUIPMENT", "DIVING", "OFF_HIRE", "OTHER"]
    period: str = Field(pattern=MONTH)
    description: str = Field(min_length=5, max_length=2000)
    amount_claimed: float = Field(gt=0, le=1e11)


class ClaimDecisionIn(BaseModel):
    status: Literal["ACCEPTED", "REJECTED"]
    amount_agreed: float | None = Field(default=None, ge=0)
    note: str = Field(min_length=3, max_length=1000)


# --- Documents ---


class DocumentIn(BaseModel):
    entity: Literal["contract", "tender", "drydock", "policy", "port_call", "po"]
    entity_key: str = Field(min_length=1, max_length=60)
    kind: Literal["CHARTER_PARTY", "ADDENDUM", "BANK_GUARANTEE", "QUOTE", "POLICY", "INVOICE", "REPORT", "OTHER"]
    title: str = Field(min_length=2, max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=4, max_length=14_000_000)  # about 10 MB once decoded
    note: str = Field(default="", max_length=500)


# --- Supply ---


class VendorIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: Literal["SPARES", "STORES", "SERVICE", "AGENT", "YARD"]
    country: str = Field(default="", max_length=60)
    contact: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=120, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(default="", max_length=40)
    tax_id: str = Field(default="", max_length=40)
    payment_terms_days: int = Field(default=30, ge=0, le=180)
    approved: bool = True
    rating: int | None = Field(default=None, ge=1, le=5)


class PartIn(BaseModel):
    part_no: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    maker: str = Field(default="", max_length=80)
    unit: str = Field(default="pc", min_length=1, max_length=12)
    unit_cost: float = money()
    vendor_id: int | None = None
    lead_days: int = Field(default=14, ge=0, le=365)


class StockLevelIn(BaseModel):
    part_id: int
    location: str = Field(min_length=1, max_length=40)
    min_qty: float = Field(ge=0, le=1e6)
    equipment_id: int | None = None
    bin: str = Field(default="", max_length=40)


class StockAdjustIn(BaseModel):
    part_id: int
    location: str
    qty: float = Field(ge=0, le=1e6)  # the counted quantity
    reason: str = Field(min_length=3, max_length=300)


class TransferIn(BaseModel):
    part_id: int
    from_location: str
    to_location: str
    qty: float = Field(gt=0, le=1e6)


class POLineIn(BaseModel):
    part_id: int | None = None
    description: str = Field(default="", max_length=200)
    qty: float = Field(gt=0, le=1e6)
    unit_price: float = Field(ge=0, le=1e10)

    @model_validator(mode="after")
    def named(self):
        if self.part_id is None and not self.description.strip():
            raise ValueError("Each line needs a part or a description.")
        return self


class POIn(BaseModel):
    vendor_id: int
    deliver_to: str
    needed_by: str | None = Field(default=None, pattern=ISO_DATE)
    note: str = Field(default="", max_length=500)
    lines: list[POLineIn] = Field(min_length=1, max_length=100)


class ReceiveIn(BaseModel):
    lines: dict[int, float]  # PO line id -> quantity received now


class SpareRequestIn(BaseModel):
    part_id: int
    qty: float = Field(gt=0, le=1e5)


class ReorderIn(BaseModel):
    location: str


# --- Port calls ---


class DaLineIn(BaseModel):
    id: int | None = None
    item: str = Field(min_length=1, max_length=120)
    pda: float = money()
    fda: float | None = Field(default=None, ge=0, le=1e11)


class PortCallIn(BaseModel):
    vessel_id: str
    port: str = Field(min_length=2, max_length=80)
    purpose: str = Field(min_length=2, max_length=200)
    eta: str = Field(pattern=ISO_DATE)
    etd: str = Field(pattern=ISO_DATE)
    agent_id: int | None = None
    lines: list[DaLineIn] = Field(default_factory=list, max_length=60)  # the PDA

    @model_validator(mode="after")
    def in_order(self):
        if self.etd < self.eta:
            raise ValueError("Departure cannot be before arrival.")
        return self


class PortStatusIn(BaseModel):
    on: str = Field(pattern=ISO_DATE)


class AccountIn(BaseModel):
    lines: list[DaLineIn] = Field(min_length=1, max_length=60)
    advance_paid: float = money()


# --- Dry dock ---


class DryDockIn(BaseModel):
    vessel_id: str
    title: str = Field(min_length=3, max_length=120)
    planned_start: str = Field(pattern=ISO_DATE)
    planned_end: str = Field(pattern=ISO_DATE)
    bottom_survey: bool = True

    @model_validator(mode="after")
    def in_order(self):
        if self.planned_end < self.planned_start:
            raise ValueError("The end must not be before the start.")
        return self


class DryDockItemIn(BaseModel):
    category: Literal["HULL", "MACHINERY", "CLASS", "ELECTRICAL", "SAFETY", "DIVING", "OTHER"]
    description: str = Field(min_length=2, max_length=300)
    budget: float = money()
    actual: float = money()
    status: Literal["OPEN", "DONE", "DEFERRED"] = "OPEN"


class YardQuoteIn(BaseModel):
    vendor_id: int
    price: float = Field(gt=0, le=1e11)
    days: int = Field(gt=0, le=365)
    deviation_cost: float = money()
    note: str = Field(default="", max_length=500)


# --- Insurance ---


class PolicyIn(BaseModel):
    kind: Literal["HM", "PI", "CREW", "LOH", "OTHER"]
    insurer: str = Field(min_length=2, max_length=120)
    policy_no: str = Field(min_length=2, max_length=60)
    vessel_id: str | None = None
    sum_insured: float = money()
    deductible: float = money()
    premium: float = money()
    start_date: str = Field(pattern=ISO_DATE)
    end_date: str = Field(pattern=ISO_DATE)

    @model_validator(mode="after")
    def in_order(self):
        if self.end_date <= self.start_date:
            raise ValueError("The policy must end after it starts.")
        return self


class InsuranceClaimIn(BaseModel):
    policy_id: int
    vessel_id: str
    incident_on: str = Field(pattern=ISO_DATE)
    description: str = Field(min_length=5, max_length=2000)
    amount: float = Field(gt=0, le=1e11)


class InsuranceClaimUpdateIn(BaseModel):
    status: Literal["SUBMITTED", "SETTLED", "REJECTED"]
    recovered: float | None = Field(default=None, ge=0)
    on: str = Field(pattern=ISO_DATE)


# --- Finance ---


class CostIn(BaseModel):
    vessel_id: str
    on_date: str = Field(pattern=ISO_DATE)
    category: Literal["SPARES", "PORT", "DRYDOCK", "INSURANCE", "OTHER"]
    amount: float = Field(ge=-1e10, le=1e10)
    description: str = Field(min_length=3, max_length=300)


class BudgetIn(BaseModel):
    vessel_id: str
    period: str = Field(pattern=MONTH)
    category: Literal["REVENUE", "RUNNING", "INSURANCE", "SPARES", "PORT", "DRYDOCK", "OTHER"]
    amount: float = Field(ge=0, le=1e11)


class BudgetBatchIn(BaseModel):
    rows: list[BudgetIn] = Field(min_length=1, max_length=2000)
