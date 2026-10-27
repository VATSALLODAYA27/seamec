"""Monthly charter-hire invoices, drafted from the approved daily reports."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.billing import add_days, month_hire
from ..db import get_session
from ..models import Contract, DailyReport, HireInvoice, Timesheet, User, Vessel, as_dict
from ..schemas import InvoiceDraftIn, PaymentIn
from .commercial import straight_off
from .fleet import days_left, get_or_404, today

router = APIRouter(prefix="/api/invoices", tags=["billing"], dependencies=[Depends(staff)])


def tax_on(contract: Contract, amount: float) -> float:
    return round(amount * contract.tax_rate, 2)


def calc_for(session: Session, contract: Contract, period: str) -> dict:
    reports = session.scalars(select(DailyReport).where(DailyReport.contract_no == contract.contract_no)).all()
    return month_hire(contract, reports, period, straight_off(session, contract.contract_no))


def invoice_out(inv: HireInvoice, contract: Contract, vessel_name: str, sheet: Timesheet | None) -> dict:
    overdue = inv.status == "APPROVED" and days_left(inv.due_date) < 0
    return {**as_dict(inv), "client": contract.client, "vessel_id": contract.vessel_id, "vessel_name": vessel_name, "overdue": overdue,
            "signoff_required": contract.client_signoff_required,
            "signoff": {"status": sheet.status, "by": sheet.by, "at": sheet.at, "note": sheet.note} if sheet else None}


@router.get("")
def list_invoices(session: Session = Depends(get_session)):
    contracts = {c.contract_no: c for c in session.scalars(select(Contract))}
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    sheets = {(t.contract_no, t.period): t for t in session.scalars(select(Timesheet))}
    rows = session.scalars(select(HireInvoice).order_by(HireInvoice.period.desc(), HireInvoice.inv_no.desc())).all()
    return [invoice_out(i, contracts[i.contract_no], names[contracts[i.contract_no].vessel_id], sheets.get((i.contract_no, i.period))) for i in rows]


@router.get("/preview")
def preview(contract_no: str, period: str, session: Session = Depends(get_session)):
    """What the invoice would say if drafted now. Nothing is saved."""
    body = InvoiceDraftIn(contract_no=contract_no, period=period)
    contract = get_or_404(session, Contract, body.contract_no, "Contract")
    calc = calc_for(session, contract, body.period)
    tax = tax_on(contract, calc["amount"])
    return {"calc": calc, "amount": calc["amount"], "tax_label": contract.tax_label, "tax_rate": contract.tax_rate, "tax": tax, "total": round(calc["amount"] + tax, 2)}


@router.post("", status_code=201)
def draft(body: InvoiceDraftIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    contract = get_or_404(session, Contract, body.contract_no, "Contract")
    if session.scalars(select(HireInvoice).where(HireInvoice.contract_no == contract.contract_no, HireInvoice.period == body.period)).first():
        raise HTTPException(409, f"{contract.contract_no} already has an invoice for {body.period}.")
    if body.period >= today()[:7]:
        raise HTTPException(409, "A month is billed once it has ended.")
    calc = calc_for(session, contract, body.period)
    if not calc["contract_days"]:
        raise HTTPException(409, f"{contract.contract_no} did not run in {body.period}.")
    if calc["pending_dates"]:
        raise HTTPException(409, f"Approve or reject the reports still waiting first: {', '.join(calc['pending_dates'])}.")
    used = [int(n[-3:]) for n in session.scalars(select(HireInvoice.inv_no).where(HireInvoice.period == body.period))]
    tax = tax_on(contract, calc["amount"])
    inv = HireInvoice(
        inv_no=f"INV-{body.period[2:4]}{body.period[5:7]}-{max(used, default=0) + 1:03d}", contract_no=contract.contract_no, period=body.period,
        invoice_date=today(), due_date=add_days(today(), contract.payment_terms_days), calc=calc,
        amount=calc["amount"], tax_label=contract.tax_label, tax_rate=contract.tax_rate, tax=tax,
        total=round(calc["amount"] + tax, 2), created_by=user.username,
    )
    session.add(inv)
    audit(session, user, "invoice.drafted", f"invoice {inv.inv_no}", f"{contract.contract_no} {body.period}")
    session.commit()
    return as_dict(inv)


@router.post("/{inv_no}/approve")
def approve(inv_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    inv = get_or_404(session, HireInvoice, inv_no, "Invoice")
    if inv.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be approved.")
    contract = session.get(Contract, inv.contract_no)
    if contract.client_signoff_required:
        sheet = session.scalars(select(Timesheet).where(Timesheet.contract_no == inv.contract_no, Timesheet.period == inv.period)).first()
        if sheet is None or sheet.status != "SIGNED":
            state = "has disputed it: " + sheet.note if sheet else "has not signed it yet"
            raise HTTPException(409, f"This contract needs the client's timesheet sign-off first; the client {state}.")
    inv.status, inv.approved_by = "APPROVED", user.username
    audit(session, user, "invoice.approved", f"invoice {inv_no}", f"total {inv.total:,.2f}")
    session.commit()
    return as_dict(inv)


@router.post("/{inv_no}/pay")
def record_payment(inv_no: str, body: PaymentIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    inv = get_or_404(session, HireInvoice, inv_no, "Invoice")
    if inv.status != "APPROVED":
        raise HTTPException(409, "Only an approved invoice can be marked paid.")
    inv.status, inv.paid_on = "PAID", body.paid_on
    audit(session, user, "invoice.paid", f"invoice {inv_no}", body.paid_on)
    session.commit()
    return as_dict(inv)


@router.delete("/{inv_no}", status_code=204)
def discard_draft(inv_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    """A draft can be thrown away and drafted again, for example after a late report is approved."""
    inv = get_or_404(session, HireInvoice, inv_no, "Invoice")
    if inv.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be discarded.")
    session.delete(inv)
    audit(session, user, "invoice.discarded", f"invoice {inv_no}")
    session.commit()
