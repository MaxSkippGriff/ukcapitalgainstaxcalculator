"""UKCapitalGainsTaxCalculator.co.uk Flask application."""
from __future__ import annotations
import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, abort, make_response, redirect, render_template, request, send_from_directory
from flask_limiter import Limiter
from calculator import active_tax_year, TAX_YEAR, calculate_cgt, ANNUAL_EXEMPT_AMOUNT, CGT_LOWER_RATE, CGT_HIGHER_RATE, PERSONAL_ALLOWANCE, BASIC_RATE_LIMIT
from scraper_guard import init_guard

load_dotenv()

_PUBLIC_PATHS = (
    "/sitemap.xml", "/robots.txt", "/ads.txt", "/favicon.ico",
    "/favicon-16x16.png", "/favicon-32x32.png", "/apple-touch-icon.png",
    "/site.webmanifest", "/health",
)
_HONEYPOT_BLOCKED: set = set()

app = Flask(__name__)

CANONICAL_HOST = os.getenv("CANONICAL_HOST", "ukcapitalgainstaxcalculator.co.uk").replace("https://","").replace("http://","")
CANONICAL_HOST = CANONICAL_HOST[4:] if CANONICAL_HOST.startswith("www.") else CANONICAL_HOST
SITE_URL = f"https://{CANONICAL_HOST}"
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "G-DL1LSYHD97").strip()
ADSENSE_CLIENT = os.getenv("ADSENSE_CLIENT", "ca-pub-3932111812673824").strip()

limiter = Limiter(
    app=app,
    key_func=lambda: (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or ""),
    default_limits=["300 per minute"],
    storage_uri="memory://",
    strategy="fixed-window",
)

init_guard(app, _PUBLIC_PATHS, "/trap", _HONEYPOT_BLOCKED)


@app.before_request
def enforce_canonical():
    host = (request.host or "").split(":")[0].lower()
    if host == f"www.{CANONICAL_HOST}":
        t = f"{SITE_URL}{request.full_path if request.query_string else request.path}"
        return redirect(t.rstrip("?"), code=301)
    return None


@app.after_request
def cache_headers(r):
    p = request.path or ""
    if p.startswith("/static/"):
        r.headers["Cache-Control"] = "public, max-age=300"
    elif p in ("/favicon.ico","/site.webmanifest","/apple-touch-icon.png","/favicon-32x32.png","/favicon-16x16.png"):
        r.headers["Cache-Control"] = "public, max-age=86400"
    elif p == "/robots.txt":
        r.headers["Cache-Control"] = "public, max-age=60"
    elif r.mimetype == "text/html":
        r.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
    r.headers.setdefault("X-Content-Type-Options","nosniff")
    r.headers.setdefault("X-Frame-Options","SAMEORIGIN")
    r.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    r.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()")
    return r


def _ctx(**kw):
    return dict(site_url=SITE_URL, tax_year=active_tax_year(), now=datetime.utcnow(),
                ga_measurement_id=GA_MEASUREMENT_ID, adsense_client=ADSENSE_CLIENT, **kw)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/favicon-32x32.png")
def favicon_32():
    return send_from_directory(app.static_folder, "favicon-32x32.png", mimetype="image/png")

@app.route("/favicon-16x16.png")
def favicon_16():
    return send_from_directory(app.static_folder, "favicon-16x16.png", mimetype="image/png")

@app.route("/apple-touch-icon.png")
def apple_touch_icon():
    return send_from_directory(app.static_folder, "apple-touch-icon.png", mimetype="image/png")

@app.route("/site.webmanifest")
def webmanifest():
    return send_from_directory(app.static_folder, "site.webmanifest", mimetype="application/manifest+json")

@app.route("/trap")
def trap():
    xff = request.headers.get("X-Forwarded-For", "")
    _HONEYPOT_BLOCKED.add(xff.split(",")[0].strip() if xff else (request.remote_addr or ""))
    abort(403)

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/robots.txt")
def robots():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /trap",
        "Disallow: /api/",
        "Disallow: /admin/",
        "",
        f"Sitemap: {SITE_URL}/sitemap.xml",
    ])
    r = make_response(body)
    r.content_type = "text/plain"
    return r

@app.route("/sitemap.xml")
def sitemap():
    now = datetime.utcnow().strftime("%Y-%m-%d")
    entries = [
        (f"{SITE_URL}/","1.0","weekly"),
        (f"{SITE_URL}/calculator","0.9","weekly"),
        (f"{SITE_URL}/methodology","0.7","monthly"),
        (f"{SITE_URL}/about","0.5","monthly"),
        (f"{SITE_URL}/privacy","0.3","yearly"),
        (f"{SITE_URL}/contact","0.3","yearly"),
        (f"{SITE_URL}/disclaimer","0.3","yearly"),
        (f"{SITE_URL}/capital-gains-tax-on-inherited-property","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-on-buy-to-let","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-losses","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-reporting-deadline","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-basic-rate-taxpayer","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-second-home","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-business-sale","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-higher-rate-taxpayer","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-for-higher-rate-taxpayers","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-on-gifts","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-records","0.6","monthly"),
        (f"{SITE_URL}/guides","0.6","monthly"),
        (f"{SITE_URL}/calculators","0.6","monthly"),
        (f"{SITE_URL}/property-cgt-calculator","0.7","monthly"),
        (f"{SITE_URL}/shares-cgt-calculator","0.7","monthly"),
        (f"{SITE_URL}/crypto-cgt-calculator","0.7","monthly"),
        (f"{SITE_URL}/cgt-allowance-calculator","0.7","monthly"),
        # CGT gain pages
        *[(f"{SITE_URL}/cgt/{g}", "0.5", "monthly") for g in CGT_GAIN_AMOUNTS],
    ]
    r = make_response(render_template("sitemap.xml", url_entries=entries, now=now))
    r.content_type = "application/xml"
    return r

@app.route("/")
def landing():
    calc = calculate_cgt(sale_proceeds=80000, purchase_cost=50000, buying_costs=1500, selling_costs=1500, taxable_income_before_gain=37700)
    faq = [
        {"q":"What is the CGT annual exempt amount for 2026/27?","a":"The annual exempt amount is £3,000 for individuals for 2026/27. Gains below this threshold are free from CGT."},
        {"q":"What are the CGT rates for 2026/27?","a":"For most assets (shares, property that is not your main home): 18% for gains that fall within the basic-rate band and 24% for gains in the higher or additional-rate band. These rates have applied since the October 2024 Autumn Budget."},
        {"q":"How does my income affect my CGT rate?","a":"Your other taxable income uses up the basic-rate band first. Any remaining basic-rate band is then available to absorb taxable gains at 18%. Gains that exceed the remaining basic-rate band are charged at 24%."},
        {"q":"Can I use capital losses to reduce my CGT bill?","a":"Yes. Capital losses from the same or previous tax years reduce your gain before the annual exempt amount is applied. Enter any losses in the calculator to see the impact."},
        {"q":"Does the calculator handle my main home?","a":"Not fully. Main homes can qualify for private residence relief, which can significantly reduce or eliminate CGT. This calculator is designed for other assets such as second properties, shares and crypto."},
        {"q":"Are crypto disposals subject to CGT?","a":"Yes, crypto disposals can be subject to CGT in the UK. The rules around pooling and records can be complex, so treat this calculator as a simplified estimate only."},
        {"q":"When do I need to report a property gain?","a":"If you sell a UK residential property and owe CGT, you generally need to report and pay within 60 days of completion. HMRC has a separate online service for this. Non-property gains are usually reported via Self Assessment."},
    ]
    return render_template("landing.html", **_ctx(
        title="Capital Gains Tax Calculator UK 2026/27 | Estimate CGT on Property, Shares & Assets",
        meta_description="Calculate Capital Gains Tax for 2026/27 on property, shares or other assets. Estimate CGT using proceeds, costs, expenses, losses and your income.",
        canonical_url=SITE_URL+"/",
        calc=calc,
        faq_items=faq,
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"}],
    ))

@app.route("/calculator")
def calculator_page():
    return render_template("calculator.html", **_ctx(
        title="CGT Calculator 2026/27 | UK Capital Gains Tax Breakdown",
        meta_description="Free UK capital gains tax calculator for 2026/27. Enter sale proceeds, cost, losses and income to get a full CGT breakdown at 18% or 24%.",
        canonical_url=SITE_URL+"/calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Calculator","url":SITE_URL+"/calculator"}],
    ))

@app.route("/methodology")
def methodology():
    return render_template("methodology.html", **_ctx(
        title="Methodology — How We Calculate UK Capital Gains Tax 2026/27",
        meta_description="How UKCapitalGainsTaxCalculator.co.uk calculates CGT: 2026/27 rates, annual exempt amount, band ordering and what we don't model.",
        canonical_url=SITE_URL+"/methodology",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Methodology","url":SITE_URL+"/methodology"}],
    ))

@app.route("/about")
def about():
    return render_template("about.html", **_ctx(
        title="About UK Capital Gains Tax Calculator — Free CGT Tool",
        meta_description="About UKCapitalGainsTaxCalculator.co.uk — a free, independent tool to estimate CGT on shares, property and other UK assets for 2026/27.",
        canonical_url=SITE_URL+"/about",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"About","url":SITE_URL+"/about"}],
    ))

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", **_ctx(
        title="Privacy Policy — UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Privacy policy for UKCapitalGainsTaxCalculator.co.uk. We don't store your financial data.",
        canonical_url=SITE_URL+"/privacy",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Privacy","url":SITE_URL+"/privacy"}],
    ))

@app.route("/contact")
def contact():
    return render_template("contact.html", **_ctx(
        title="Contact — UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Get in touch with UKCapitalGainsTaxCalculator.co.uk.",
        canonical_url=SITE_URL+"/contact",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Contact","url":SITE_URL+"/contact"}],
    ))

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", **_ctx(
        title="Disclaimer — UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Disclaimer for UKCapitalGainsTaxCalculator.co.uk. Results are estimates only and not tax advice.",
        canonical_url=SITE_URL+"/disclaimer",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Disclaimer","url":SITE_URL+"/disclaimer"}],
    ))

@app.route("/capital-gains-tax-on-inherited-property")
def guide_inherited_property():
    return render_template("capital-gains-tax-on-inherited-property.html", **_ctx(
        title="Capital Gains Tax on Inherited Property 2026/27 | UK Guide",
        meta_description="Learn how UK capital gains tax can apply when selling inherited property, including probate value, allowable costs and 2026/27 CGT rates.",
        canonical_url=SITE_URL+"/capital-gains-tax-on-inherited-property",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Inherited Property CGT","url":SITE_URL+"/capital-gains-tax-on-inherited-property"}],
    ))

@app.route("/capital-gains-tax-on-buy-to-let")
def guide_buy_to_let():
    return render_template("capital-gains-tax-on-buy-to-let.html", **_ctx(
        title="Capital Gains Tax on Buy-to-Let Property 2026/27 | UK Guide",
        meta_description="Understand how capital gains tax can apply when selling a buy-to-let property, including allowable costs, 2026/27 rates and examples.",
        canonical_url=SITE_URL+"/capital-gains-tax-on-buy-to-let",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Buy-to-Let CGT","url":SITE_URL+"/capital-gains-tax-on-buy-to-let"}],
    ))

@app.route("/capital-gains-tax-losses")
def guide_losses():
    return render_template("capital-gains-tax-losses.html", **_ctx(
        title="Capital Gains Tax Losses 2026/27 | UK Guide",
        meta_description="Learn how capital losses can reduce taxable gains, how losses interact with the annual exempt amount and what to watch for.",
        canonical_url=SITE_URL+"/capital-gains-tax-losses",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Losses","url":SITE_URL+"/capital-gains-tax-losses"}],
    ))

@app.route("/capital-gains-tax-reporting-deadline")
def guide_reporting_deadline():
    return render_template("capital-gains-tax-reporting-deadline.html", **_ctx(
        title="Capital Gains Tax Reporting Deadlines 2026/27 | UK Guide",
        meta_description="Understand when UK capital gains tax may need to be reported, including property reporting and Self Assessment considerations.",
        canonical_url=SITE_URL+"/capital-gains-tax-reporting-deadline",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Reporting Deadlines","url":SITE_URL+"/capital-gains-tax-reporting-deadline"}],
    ))

@app.route("/capital-gains-tax-basic-rate-taxpayer")
def guide_basic_rate_taxpayer():
    return render_template("capital-gains-tax-basic-rate-taxpayer.html", **_ctx(
        title="Capital Gains Tax for Basic-Rate Taxpayers 2026/27",
        meta_description="Learn how capital gains tax can be calculated for basic-rate taxpayers and why large gains can still be partly charged at 24%.",
        canonical_url=SITE_URL+"/capital-gains-tax-basic-rate-taxpayer",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Basic-Rate Taxpayers","url":SITE_URL+"/capital-gains-tax-basic-rate-taxpayer"}],
    ))

@app.route("/capital-gains-tax-second-home")
def guide_second_home():
    return render_template("capital-gains-tax-second-home.html", **_ctx(
        title="Capital Gains Tax on a Second Home 2026/27 | UK Guide",
        meta_description="Understand how capital gains tax applies when selling a second home or holiday property in the UK, including 2026/27 rates and the 60-day reporting rule.",
        canonical_url=SITE_URL+"/capital-gains-tax-second-home",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Second Home","url":SITE_URL+"/capital-gains-tax-second-home"}],
    ))

@app.route("/capital-gains-tax-business-sale")
def guide_business_sale():
    return render_template("capital-gains-tax-business-sale.html", **_ctx(
        title="Capital Gains Tax When Selling a Business 2026/27 | UK Guide",
        meta_description="Learn about Business Asset Disposal Relief (BADR), the 14% rate on qualifying gains up to £1,000,000 and standard CGT rates when selling a business in 2026/27.",
        canonical_url=SITE_URL+"/capital-gains-tax-business-sale",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Business Sale","url":SITE_URL+"/capital-gains-tax-business-sale"}],
    ))

@app.route("/capital-gains-tax-higher-rate-taxpayer")
def guide_higher_rate_taxpayer():
    return render_template("capital-gains-tax-higher-rate-taxpayer.html", **_ctx(
        title="Capital Gains Tax for Higher-Rate Taxpayers 2026/27 | UK Guide",
        meta_description="How CGT is calculated at 24% for higher-rate taxpayers in 2026/27, how gains stack on top of income and planning options to reduce the bill.",
        canonical_url=SITE_URL+"/capital-gains-tax-higher-rate-taxpayer",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Higher-Rate Taxpayers","url":SITE_URL+"/capital-gains-tax-higher-rate-taxpayer"}],
    ))

@app.route("/capital-gains-tax-on-gifts")
def guide_gifts():
    return render_template("capital-gains-tax-on-gifts.html", **_ctx(
        title="Capital Gains Tax on Gifts 2026/27 | UK Guide",
        meta_description="Gifting an asset triggers CGT at market value in the UK. Learn the rules for gifts to children, spouses and charities, and when Hold-Over Relief applies.",
        canonical_url=SITE_URL+"/capital-gains-tax-on-gifts",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT on Gifts","url":SITE_URL+"/capital-gains-tax-on-gifts"}],
    ))

@app.route("/capital-gains-tax-for-higher-rate-taxpayers")
def guide_for_higher_rate_taxpayers():
    return render_template("capital-gains-tax-for-higher-rate-taxpayers.html", **_ctx(
        title="Capital Gains Tax for Higher-Rate Taxpayers 2026/27 | UK Guide",
        meta_description="How CGT works at 24% for higher-rate taxpayers in 2026/27 — income interactions, worked example and planning strategies to reduce your bill.",
        canonical_url=SITE_URL+"/capital-gains-tax-for-higher-rate-taxpayers",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT for Higher-Rate Taxpayers","url":SITE_URL+"/capital-gains-tax-for-higher-rate-taxpayers"}],
    ))

@app.route("/capital-gains-tax-records")
def guide_records():
    return render_template("capital-gains-tax-records.html", **_ctx(
        title="Capital Gains Tax Record Keeping 2026/27 | UK Guide",
        meta_description="What CGT records to keep, how long to keep them and what HMRC requires for property, shares and crypto disposals in 2026/27.",
        canonical_url=SITE_URL+"/capital-gains-tax-records",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Records","url":SITE_URL+"/capital-gains-tax-records"}],
    ))

@app.route("/guides")
def guides_index():
    return render_template("guides.html", **_ctx(
        title="CGT Guides 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="In-depth guides to UK capital gains tax rules, rates and allowances for 2026/27.",
        canonical_url=SITE_URL + "/guides",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Guides","url":SITE_URL+"/guides"}],
    ))

@app.route("/calculators")
def calculators_index():
    return render_template("calculators.html", **_ctx(
        title="CGT Calculators 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Free UK capital gains tax calculators for property, shares, crypto and the annual exempt amount.",
        canonical_url=SITE_URL + "/calculators",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Calculators","url":SITE_URL+"/calculators"}],
    ))

@app.route("/property-cgt-calculator")
def property_cgt_calculator():
    return render_template("property-cgt-calculator.html", **_ctx(
        title="Property CGT Calculator 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Estimate capital gains tax on a second home, buy-to-let or other property disposal. 18%/24% rates for 2026/27.",
        canonical_url=SITE_URL + "/property-cgt-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Property CGT Calculator","url":SITE_URL+"/property-cgt-calculator"}],
    ))

@app.route("/shares-cgt-calculator")
def shares_cgt_calculator():
    return render_template("shares-cgt-calculator.html", **_ctx(
        title="Shares CGT Calculator 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Estimate capital gains tax on shares and funds outside an ISA or pension for 2026/27.",
        canonical_url=SITE_URL + "/shares-cgt-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Shares CGT Calculator","url":SITE_URL+"/shares-cgt-calculator"}],
    ))

@app.route("/crypto-cgt-calculator")
def crypto_cgt_calculator():
    return render_template("crypto-cgt-calculator.html", **_ctx(
        title="Crypto CGT Calculator 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Estimate capital gains tax on a cryptocurrency disposal for 2026/27.",
        canonical_url=SITE_URL + "/crypto-cgt-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Crypto CGT Calculator","url":SITE_URL+"/crypto-cgt-calculator"}],
    ))

@app.route("/cgt-allowance-calculator")
def cgt_allowance_calculator():
    return render_template("cgt-allowance-calculator.html", **_ctx(
        title="CGT Allowance Calculator 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Calculate your remaining £3,000 capital gains tax annual exempt amount for 2026/27.",
        canonical_url=SITE_URL + "/cgt-allowance-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Allowance Calculator","url":SITE_URL+"/cgt-allowance-calculator"}],
    ))

CGT_GAIN_AMOUNTS = [5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000, 150000, 200000]

@app.route("/cgt/<int:gain>")
def cgt_gain_page(gain: int):
    if gain not in CGT_GAIN_AMOUNTS:
        abort(404)
    calc_basic = calculate_cgt(sale_proceeds=gain, purchase_cost=0, buying_costs=0, selling_costs=0, taxable_income_before_gain=35000)
    calc_higher = calculate_cgt(sale_proceeds=gain, purchase_cost=0, buying_costs=0, selling_costs=0, taxable_income_before_gain=55000)
    nearby = [a for a in CGT_GAIN_AMOUNTS if a != gain]
    neighbours = sorted(nearby, key=lambda x: abs(x - gain))[:4]
    return render_template("cgt_gain_page.html", **_ctx(
        title=f"Capital Gains Tax on £{gain:,} Gain 2026/27 | CGT Calculator",
        meta_description=f"How much CGT on a £{gain:,} gain in 2026/27? After the £3,000 annual exempt amount, a basic-rate taxpayer pays £{calc_basic.total_cgt:,.0f} and a higher-rate taxpayer pays £{calc_higher.total_cgt:,.0f}.",
        canonical_url=SITE_URL+f"/cgt/{gain}",
        gain=gain,
        calc_basic=calc_basic,
        calc_higher=calc_higher,
        neighbours=neighbours,
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":f"CGT on £{gain:,}","url":SITE_URL+f"/cgt/{gain}"}],
    ))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
