"""Resend email delivery for CGT pack downloads."""
from __future__ import annotations
import logging
import os

import requests

log = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_ADDRESS = "UKCapitalGainsTaxCalculator <hello@ukcapitalgainstaxcalculator.co.uk>"


def send_pack_download(to: str, link: str) -> bool:
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email")
        return False
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": FROM_ADDRESS,
                "to": [to],
                "subject": "Your Capital Gains Tax Survival Pack",
                "html": f"""
<p>Thanks for your purchase.</p>
<p><a href="{link}">Download your Capital Gains Tax Survival Pack (PDF)</a></p>
<p>Your link is valid for 7 days and can be used up to 5 times.</p>
<p>Not what you needed? Reply to this email for a full refund.</p>
<p style="color:#666;font-size:0.85em;">UKCapitalGainsTaxCalculator.co.uk &middot; £4.99 one-off purchase</p>
""",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.error("Resend failed: %s", exc)
        return False
