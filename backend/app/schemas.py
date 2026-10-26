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


# --- Automatic positions (VSAT / AIS feed) ---


class FixIn(BaseModel):
    vessel_id: str | None = None
    mmsi: str | None = Field(default=None, pattern=r"^\d{9}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")  # UTC; now when left out
    sog: float | None = Field(default=None, ge=0, le=60)
    cog: float | None = Field(default=None, ge=0, le=360)
    source: Literal["VSAT", "AIS"] = "VSAT"

    @model_validator(mode="after")
    def names_a_vessel(self):
        if not self.vessel_id and not self.mmsi:
            raise ValueError("Give the vessel_id or the MMSI.")
        return self


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
