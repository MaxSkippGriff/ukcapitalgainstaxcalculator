"""UK Capital Gains Tax Calculator — 2026/27 tax year constants and logic."""

from __future__ import annotations
import datetime
from dataclasses import dataclass


def active_tax_year() -> str:
    today = datetime.date.today()
    return "2026/27" if today >= datetime.date(2026, 4, 6) else "2025/26"


TAX_YEAR = "2026/27"

# Annual exempt amount (reduced to £3,000 from April 2024)
ANNUAL_EXEMPT_AMOUNT = 3_000

# CGT rates (from 30 October 2024 Autumn Budget)
CGT_LOWER_RATE = 0.18          # 18% — basic-rate taxpayer (all assets)
CGT_HIGHER_RATE = 0.24         # 24% — higher/additional-rate taxpayer (all assets)

# Income tax thresholds 2026/27
PERSONAL_ALLOWANCE = 12_570
BASIC_RATE_LIMIT = 50_270      # Top of basic-rate band
HIGHER_RATE_LIMIT = 125_140
BASIC_RATE_BAND = BASIC_RATE_LIMIT - PERSONAL_ALLOWANCE  # £37,700

# BADR rate from April 2026
BADR_RATE = 0.18


@dataclass(frozen=True)
class CGTResult:
    sale_proceeds_share: float
    purchase_cost_share: float
    allowable_costs: float
    gross_gain: float
    losses_used: float
    gain_after_losses: float
    exempt_amount_used: float
    taxable_gain: float
    basic_rate_gain: float
    higher_rate_gain: float
    cgt_at_basic: float
    cgt_at_higher: float
    total_cgt: float
    net_proceeds_after_cgt: float
    effective_rate: float


def _r(v: float) -> float:
    return round(float(v), 2)


def calculate_cgt(
    sale_proceeds: float,
    purchase_cost: float,
    buying_costs: float = 0.0,
    selling_costs: float = 0.0,
    improvement_costs: float = 0.0,
    losses_brought_forward: float = 0.0,
    exempt_amount_already_used: float = 0.0,
    taxable_income_before_gain: float = 0.0,
    ownership_pct: float = 100.0,
) -> CGTResult:
    """Calculate UK CGT liability for 2026/27."""
    sale_proceeds = float(sale_proceeds)
    purchase_cost = float(purchase_cost)
    buying_costs = max(0.0, float(buying_costs))
    selling_costs = max(0.0, float(selling_costs))
    improvement_costs = max(0.0, float(improvement_costs))
    losses_bfw = max(0.0, float(losses_brought_forward))
    exempt_used_already = max(0.0, min(float(exempt_amount_already_used), ANNUAL_EXEMPT_AMOUNT))
    own_pct = max(0.0, min(100.0, float(ownership_pct))) / 100.0
    taxable_income = max(0.0, float(taxable_income_before_gain))

    # Apply ownership share
    proc_share = sale_proceeds * own_pct
    cost_share = purchase_cost * own_pct
    allowable = (buying_costs + selling_costs + improvement_costs) * own_pct
    cost_base = cost_share + allowable

    gross_gain = max(0.0, proc_share - cost_base)

    # Losses reduce the gain
    losses_used = min(losses_bfw, gross_gain)
    gain_after_losses = gross_gain - losses_used

    # Annual exempt amount (what's left after other disposals this year)
    exempt_remaining = max(0.0, ANNUAL_EXEMPT_AMOUNT - exempt_used_already)
    exempt_used = min(exempt_remaining, gain_after_losses)
    taxable_gain = max(0.0, gain_after_losses - exempt_used)

    # Band split: income fills band first, gain sits on top
    # taxable_income_before_gain = income already taxed (after personal allowance)
    basic_remaining = max(0.0, BASIC_RATE_BAND - taxable_income)
    basic_gain = min(taxable_gain, basic_remaining)
    higher_gain = max(0.0, taxable_gain - basic_gain)

    cgt_basic = basic_gain * CGT_LOWER_RATE
    cgt_higher = higher_gain * CGT_HIGHER_RATE
    total_cgt = cgt_basic + cgt_higher

    net_after_cgt = proc_share - total_cgt
    eff_rate = (total_cgt / gross_gain * 100.0) if gross_gain > 0 else 0.0

    return CGTResult(
        sale_proceeds_share=_r(proc_share),
        purchase_cost_share=_r(cost_share),
        allowable_costs=_r(allowable),
        gross_gain=_r(gross_gain),
        losses_used=_r(losses_used),
        gain_after_losses=_r(gain_after_losses),
        exempt_amount_used=_r(exempt_used),
        taxable_gain=_r(taxable_gain),
        basic_rate_gain=_r(basic_gain),
        higher_rate_gain=_r(higher_gain),
        cgt_at_basic=_r(cgt_basic),
        cgt_at_higher=_r(cgt_higher),
        total_cgt=_r(total_cgt),
        net_proceeds_after_cgt=_r(net_after_cgt),
        effective_rate=_r(eff_rate),
    )
