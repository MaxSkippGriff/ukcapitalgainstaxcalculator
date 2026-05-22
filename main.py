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
        (f"{SITE_URL}/blog","0.7","weekly"),
        *[(f"{SITE_URL}/blog/{p['slug']}","0.6","monthly") for p in BLOG_POSTS],
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

BLOG_POSTS = [
    {
        "slug": "capital-gains-tax-scotland",
        "title": "Capital Gains Tax in Scotland 2026/27: How Scottish Income Tax Affects Your CGT Rate",
        "description": "CGT rates are the same across the UK, but Scottish taxpayers pay different income tax rates — and that affects which CGT rate (18% or 24%) applies to their gains.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "CGT Rates Are Set by Westminster — the Same Across the UK",
                "paragraphs": [
                    "Capital gains tax rates apply identically in England, Scotland, Wales and Northern Ireland. For 2026/27, the rates are 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. These rates apply to most assets, including shares, second properties and crypto. Business Asset Disposal Relief (BADR) has a 14% rate on qualifying gains up to £1,000,000. Scotland has no power to vary CGT rates.",
                    "The annual exempt amount of £3,000 also applies identically across the UK. Gains below £3,000 in a tax year are free from CGT regardless of where the taxpayer lives. These UK-wide rules mean that, for CGT purposes, Scottish taxpayers follow the same rules as English taxpayers — the complication arises only in determining which rate (18% or 24%) applies, because that depends on the taxpayer's total income, and Scottish income tax rates differ from rUK.",
                ],
            },
            {
                "heading": "How Your Income Determines Your CGT Rate",
                "paragraphs": [
                    "CGT rates depend on how much of the basic-rate band remains after your other taxable income. The UK-wide basic-rate band runs from £12,570 (the Personal Allowance) to £50,270. Your salary, pension and other non-CGT income fills this band first. Any remaining space is then available to absorb taxable gains at 18%. Gains that exceed the remaining basic-rate band are charged at 24%.",
                    "For this calculation, HMRC uses the UK-wide basic-rate limit of £50,270, not the Scottish higher-rate threshold. This is important because the Scottish higher-rate band starts lower — at £43,662 for 2026/27. A Scottish taxpayer with £43,000 of salary is already in the Scottish higher-rate band for income tax purposes, but for CGT purposes they still have £7,270 of the UK basic-rate band remaining (£50,270 − £43,000). Gains up to £7,270 would be charged at 18%, and gains above that at 24%.",
                ],
            },
            {
                "heading": "Worked Example: Scottish Higher-Rate Taxpayer",
                "paragraphs": [
                    "Consider a Scottish employee with a salary of £48,000 and a gain of £20,000 from selling shares. For Scottish income tax, the salary puts this person in the Scottish higher-rate band (above £43,662). For CGT, the remaining UK basic-rate band is £50,270 − £48,000 = £2,270. After the annual exempt amount of £3,000, the taxable gain is £17,000.",
                    "The first £2,270 of the taxable gain is within the remaining basic-rate band: taxed at 18% = £409. The remaining £14,730 is in the higher-rate band: taxed at 24% = £3,535. Total CGT: approximately £3,944. If this taxpayer were in England with the same salary and gain, the calculation would be identical — because the UK-wide basic-rate limit of £50,270 applies in both cases.",
                ],
            },
            {
                "heading": "Planning Implications for Scottish Taxpayers",
                "paragraphs": [
                    "Because Scottish higher-rate income tax applies from a lower threshold (£43,662), Scottish higher-rate taxpayers have less basic-rate band available for CGT than English taxpayers at the same income level in the range £43,662–£50,270. A Scottish taxpayer with £46,000 of salary has £4,270 of basic-rate band for CGT, compared to an English taxpayer with the same salary who also has £4,270 — the calculation is the same, showing CGT operates symmetrically.",
                    "Strategies to reduce CGT apply equally to Scottish taxpayers: using the annual exempt amount, matching gains with losses, transferring assets to a lower-income spouse, and holding appreciating assets inside an ISA. Scottish taxpayers considering realising gains should also check whether pension contributions (which reduce adjusted net income) can bring more of their gain into the 18% band.",
                ],
            },
        ],
        "faqs": [
            {"q": "Do Scottish taxpayers pay higher CGT rates?", "a": "No. CGT rates of 18% and 24% apply identically across the UK. Scotland cannot vary CGT rates."},
            {"q": "Which band threshold applies for CGT in Scotland?", "a": "The UK-wide basic-rate limit of £50,270 is used for CGT purposes, not the lower Scottish higher-rate threshold of £43,662."},
            {"q": "Does the annual exempt amount apply in Scotland?", "a": "Yes. The £3,000 annual exempt amount applies to all UK taxpayers including those in Scotland."},
        ],
    },
    {
        "slug": "capital-gains-tax-on-second-home-2026",
        "title": "Capital Gains Tax on a Second Home 2026/27: Rates, Examples and the 60-Day Rule",
        "description": "Selling a second home or holiday property triggers CGT at 18% or 24% in 2026/27. This guide covers the rates, the 60-day reporting rule and how to calculate your bill.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "CGT Rates on Residential Property in 2026/27",
                "paragraphs": [
                    "Since the Autumn Budget of October 2024, residential property gains (other than your main home) are charged at 18% for gains within the basic-rate band and 24% for gains in the higher-rate band. These rates replaced the previous rates of 18% and 28%. The change took effect for disposals on or after 30 October 2024. For 2026/27, all second home disposals use the 18%/24% rate structure.",
                    "The annual exempt amount of £3,000 is available to offset the gain. If you have capital losses from other disposals in the same or earlier tax years, these are applied first to reduce the gain. The net taxable gain is then assessed against your income to determine how much falls into each CGT band.",
                ],
            },
            {
                "heading": "Calculating the Gain",
                "paragraphs": [
                    "The gain is calculated as sale proceeds minus allowable costs. Allowable costs include the purchase price, buying costs (solicitor fees, stamp duty, surveyor fees), any capital improvements (extensions, loft conversions — not maintenance or repairs), and selling costs (estate agent fees, solicitor fees). Costs of maintaining or decorating the property are not allowable for CGT purposes.",
                    "For example: a second home bought for £250,000 with £5,000 of purchase costs, £30,000 spent on an extension, and sold for £380,000 with £7,500 in selling costs. Gain = £380,000 − £250,000 − £5,000 − £30,000 − £7,500 = £87,500. After the £3,000 annual exempt amount: taxable gain = £84,500. For a higher-rate taxpayer (salary of £60,000), all of this would be charged at 24% = £20,280.",
                ],
            },
            {
                "heading": "The 60-Day Reporting Rule",
                "paragraphs": [
                    "If you sell a UK residential property and owe CGT, you must report the gain and pay an estimate of the tax within 60 days of the completion date. This is done through HMRC's online residential property disposal service, separate from the annual Self Assessment process. Failure to report within 60 days can result in a penalty and interest charges.",
                    "The 60-day rule applies to UK residential property only. Non-residential property gains and other asset gains (shares, crypto, etc.) are reported through Self Assessment as normal, by 31 January following the end of the tax year. If you have already paid CGT under the 60-day rule, you will reconcile this against your Self Assessment return, but you do not need to wait until January — the initial payment is due within 60 days of completion.",
                    "The 60-day clock starts from the completion date, not the exchange of contracts date. If you exchange in March and complete in April, the 60-day clock starts in April. A common mistake is assuming that reporting through Self Assessment before 31 January satisfies the obligation — it does not if the 60-day deadline has already passed.",
                ],
            },
            {
                "heading": "Private Residence Relief and Its Limits",
                "paragraphs": [
                    "Private Residence Relief (PRR) exempts the gain on your main home from CGT. If you sell a property that was your main home for part of the ownership period, you may be entitled to partial PRR. The gain is apportioned across the ownership period, and the proportion relating to the time it was your main home is exempt. The final 9 months of ownership always count as main home periods, even if you had moved out.",
                    "For a pure second home that was never your main residence, PRR is not available. The full gain (less costs and the annual exempt amount) is subject to CGT. Furnished holiday lettings used to have specific tax advantages, but significant changes to FHL rules took effect from April 2025, removing the historic CGT and income tax advantages. If you have an FHL property, you should check the current rules carefully.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the CGT rate on a second home in 2026/27?", "a": "18% for gains within the basic-rate band and 24% for gains in the higher-rate band. These rates have applied since October 2024."},
            {"q": "Do I need to report a second home sale within 60 days?", "a": "Yes. UK residential property disposals where CGT is owed must be reported to HMRC within 60 days of completion using HMRC's online service."},
            {"q": "Can I deduct the cost of improvements from my CGT gain?", "a": "Yes. Capital improvements (such as extensions) are allowable costs. Maintenance and repairs are not."},
        ],
    },
    {
        "slug": "capital-gains-tax-crypto-2026",
        "title": "Capital Gains Tax on Crypto 2026/27: HMRC Rules, Rates and Pooling",
        "description": "HMRC treats cryptocurrency as a capital asset. Disposals trigger CGT at 18% or 24% in 2026/27. This guide covers pooling rules, same-day matching and record-keeping.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "7 min read",
        "sections": [
            {
                "heading": "HMRC's Treatment of Crypto as a Capital Asset",
                "paragraphs": [
                    "HMRC's guidance (CRYPTO10100 and onwards) is clear: for most individuals, cryptocurrency is a capital asset, and disposals are subject to capital gains tax. A disposal includes selling crypto for fiat currency, exchanging one cryptocurrency for another, using crypto to pay for goods or services, and gifting crypto (except to a spouse or civil partner). Each disposal creates a separate CGT event.",
                    "The CGT rates for 2026/27 are 18% for gains within the basic-rate band and 24% for gains in the higher-rate band. The annual exempt amount of £3,000 applies in the same way as for shares or property. Income from crypto activities such as staking rewards, mining and airdrops may be treated as income rather than capital gain — HMRC's position is complex and depends on the facts of each case.",
                ],
            },
            {
                "heading": "The Section 104 Pooling Rules",
                "paragraphs": [
                    "HMRC applies the same share pooling rules (Section 104 TCGA 1992) to crypto that apply to shares. Each type of cryptocurrency is treated as a single pool. When you acquire the same type of crypto on different dates at different prices, the total cost is pooled and averaged. When you dispose of some of the pool, you use the averaged cost per unit to calculate the gain.",
                    "For example, if you bought 1 Bitcoin at £20,000 and then another at £30,000, your pool contains 2 Bitcoin at a total cost of £50,000 — an average of £25,000 per Bitcoin. If you then sell 1 Bitcoin for £35,000, your gain is £35,000 − £25,000 = £10,000. The remaining Bitcoin in the pool has a cost of £25,000. Each type of crypto (Bitcoin, Ethereum, etc.) is treated as a separate pool.",
                ],
            },
            {
                "heading": "Same-Day and 30-Day Matching Rules",
                "paragraphs": [
                    "Before the pool is used, HMRC applies priority matching rules. If you buy and sell the same crypto on the same day, the buy and sell are matched against each other (same-day rule). If you sell and then buy the same crypto within 30 days, the purchase is matched against the sale (the 30-day rule, also known as the bed-and-breakfast rule). These rules exist to prevent tax avoidance through rapid recycling of crypto holdings.",
                    "The 30-day rule is particularly important for crypto investors who try to crystallise a loss by selling and immediately repurchasing the same asset. If you sell Bitcoin at a loss and buy it back within 30 days, the loss is matched against the new acquisition rather than the pool, potentially neutralising the tax planning. To crystallise a loss properly, you must wait more than 30 days before repurchasing, or switch to a different but correlated asset in the interim.",
                ],
            },
            {
                "heading": "Record-Keeping Requirements",
                "paragraphs": [
                    "HMRC requires crypto investors to keep detailed records of every transaction: the date, the amount of crypto, the value in sterling at the date of the transaction, the exchange used and the purpose of the transaction. Without complete records, it is impossible to calculate accurate gains and losses, and HMRC can challenge any CGT return.",
                    "Many exchanges provide transaction histories that can be downloaded as CSV files. There are also dedicated crypto tax software tools that connect to exchange APIs and calculate CGT automatically using HMRC's pooling rules. Given the complexity of the rules and the high volume of transactions that active crypto traders can accumulate, using dedicated software is strongly recommended over manual calculation.",
                ],
            },
        ],
        "faqs": [
            {"q": "Is crypto subject to CGT in the UK?", "a": "Yes. HMRC treats most crypto disposals as capital gains events, subject to CGT at 18% or 24% for 2026/27. Each sale, exchange or payment using crypto is a separate disposal."},
            {"q": "Do the share matching rules apply to crypto?", "a": "Yes. HMRC applies the Section 104 pool, same-day rule and 30-day rule to crypto in the same way as shares."},
            {"q": "What records do I need to keep for crypto CGT?", "a": "Date, amount, sterling value at time of transaction, exchange and purpose for every crypto transaction. HMRC requires records to be kept for at least 5 years after the Self Assessment filing deadline."},
        ],
    },
    {
        "slug": "how-to-use-annual-exempt-amount",
        "title": "How to Use the £3,000 Annual Exempt Amount in 2026/27",
        "description": "The CGT annual exempt amount is £3,000 for 2026/27. This guide explains how to use it effectively, including spousal transfers, timing disposals and what use-it-or-lose-it means.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "5 min read",
        "sections": [
            {
                "heading": "What Is the Annual Exempt Amount?",
                "paragraphs": [
                    "The annual exempt amount (AEA) is the amount of net capital gains each individual can make in a tax year without paying any CGT. For 2026/27 it is £3,000. Net gains above £3,000 are subject to CGT at 18% or 24% depending on the taxpayer's income. The AEA has been significantly reduced in recent years: it was £12,300 for 2022/23, then cut to £6,000 for 2023/24 and further to £3,000 for 2024/25 onwards.",
                    "The AEA applies to each individual separately. A married couple each have their own £3,000 AEA, giving a combined £6,000 of tax-free gains per year if both spouses make disposals. The AEA cannot be transferred between spouses — each person must use their own.",
                ],
            },
            {
                "heading": "Use It or Lose It",
                "paragraphs": [
                    "The AEA cannot be carried forward. Any unused AEA at 5 April is permanently lost. This means there is a real benefit in timing disposals to use the AEA each year rather than making all disposals in one year and wasting multiple years' worth of allowances. An investor planning to sell a large shareholding might split the sale across two tax years: sell some in March (before 5 April) and the remainder in April (after 5 April), using two years' worth of AEA.",
                    "Similarly, investors who have not made any gains in a tax year might consider whether to realise some growth before 5 April to use the AEA. This is known as bed and re-ISA, where you sell shares, use the AEA to reduce any gain, and then repurchase inside an ISA. This shelters future growth from CGT entirely. The repurchase inside the ISA can happen immediately — the 30-day rule that applies to direct repurchase in the same account does not apply to repurchases inside an ISA.",
                ],
            },
            {
                "heading": "Transferring Assets Between Spouses",
                "paragraphs": [
                    "Gifts between spouses and civil partners are made at no-gain/no-loss for CGT purposes. This means you can transfer an asset to your spouse without triggering a CGT event. The receiving spouse acquires the asset at your original cost. When they eventually sell the asset, they use their own AEA and pay CGT at their own marginal rate.",
                    "This strategy is most valuable when one spouse has a lower income and therefore pays CGT at 18% rather than 24%, and when one spouse has an unused AEA. If your spouse has made no gains this year and you are about to sell an asset with a £10,000 gain, transferring the asset to your spouse first means the £3,000 AEA shelters part of the gain and the remaining £7,000 may be taxed at 18% rather than 24% — a saving of £420 on that portion alone.",
                ],
            },
            {
                "heading": "Losses and the Annual Exempt Amount",
                "paragraphs": [
                    "Capital losses from the same tax year must be set against capital gains before the AEA is applied. This means if you have both gains and losses in a year, the losses reduce your gain first, and then the AEA applies to the net result. You cannot choose to carry forward current-year losses to preserve the AEA — they must be applied in the year they arise.",
                    "Losses brought forward from previous years behave differently. They are only applied to the extent needed to reduce the net gain to the AEA. So if you have £10,000 of gains, £3,000 of AEA and £8,000 of brought-forward losses, you would only apply £7,000 of the losses (to bring the gain down to £3,000, which is sheltered by the AEA). The remaining £1,000 of losses is carried forward to future years.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the CGT annual exempt amount for 2026/27?", "a": "£3,000. This applies to each individual. Gains below £3,000 in a tax year are free from CGT."},
            {"q": "Can I transfer my annual exempt amount to my spouse?", "a": "No. The annual exempt amount cannot be transferred. However, you can transfer assets between spouses (at no-gain/no-loss) so that your spouse uses their own AEA."},
            {"q": "Can I carry forward an unused annual exempt amount?", "a": "No. The AEA is use-it-or-lose-it. Any unused AEA at 5 April disappears permanently."},
        ],
    },
    {
        "slug": "capital-gains-tax-shares-2026",
        "title": "Capital Gains Tax on Shares 2026/27: Rates, Share Matching and ISA Exemption",
        "description": "How CGT works on shares and funds outside ISAs in 2026/27: 18% basic rate, 24% higher rate, the share matching rules and how ISAs provide a complete exemption.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "7 min read",
        "sections": [
            {
                "heading": "CGT Rates on Shares in 2026/27",
                "paragraphs": [
                    "Gains on shares and investment funds held outside ISAs and pensions are subject to CGT in 2026/27 at 18% for gains within the basic-rate band and 24% for gains in the higher-rate band. These rates apply to most shares, unit trusts, OEICs, ETFs and investment trusts. The rates changed in October 2024: the previous higher-rate rate was 20%, increased to 24% from 30 October 2024.",
                    "The annual exempt amount of £3,000 reduces the taxable gain. A basic-rate taxpayer with £5,000 of share gains pays CGT on £2,000 (£5,000 − £3,000 AEA) at 18% = £360. A higher-rate taxpayer with the same gain pays 24% on £2,000 = £480. The difference underlines why long-term investors should prioritise sheltering high-growth assets inside ISAs.",
                ],
            },
            {
                "heading": "The Share Matching Rules",
                "paragraphs": [
                    "When you sell shares, HMRC applies matching rules to determine which shares are being sold (and therefore what the cost base is). The rules apply in this order: first, shares bought on the same day as the sale (same-day rule); second, shares bought within 30 days after the sale (the bed-and-breakfast rule); third, shares in the Section 104 pool (all other shares of the same type, averaged over time).",
                    "The bed-and-breakfast rule prevents investors from selling shares to crystallise a loss (or use the AEA) and then immediately repurchasing. If you sell 500 shares on 1 March and buy 500 of the same shares on 15 March (within 30 days), HMRC matches the sale against the new purchase — the pool average cost is not used. To avoid this, investors either wait more than 30 days to repurchase, buy the shares back inside an ISA (where the matching rule does not apply to ISA holdings), or switch to a similar but different fund in the interim.",
                ],
            },
            {
                "heading": "How the Section 104 Pool Works",
                "paragraphs": [
                    "The Section 104 pool treats all acquisitions of the same share or fund as one pool. Acquisitions add to the pool, increasing the total cost and the number of shares held. When shares are sold, you use the average cost per share from the pool to calculate the gain. This prevents investors from cherry-picking high-cost lots to minimise gains.",
                    "For example, suppose you buy 1,000 shares in a fund at £2.00 each (cost £2,000), then later buy another 500 at £3.00 each (cost £1,500). Your pool now contains 1,500 shares at a total cost of £3,500 — an average of £2.33 per share. If you sell 500 shares at £4.00 each (proceeds £2,000), the gain is £2,000 − (500 × £2.33) = £2,000 − £1,167 = £833.",
                ],
            },
            {
                "heading": "ISA Exemption: No CGT on Shares Inside an ISA",
                "paragraphs": [
                    "Shares, funds and ETFs held inside a Stocks and Shares ISA are completely exempt from CGT (and dividend tax). The annual ISA subscription limit is £20,000 per person for 2026/27. Once money is inside the ISA wrapper, all future growth and income are tax-free, regardless of how large the gains become. There is no limit on the total ISA pot size — only on annual contributions.",
                    "For long-term investors, the ISA wrapper is the single most powerful tax-efficiency tool available. Holding a high-growth ETF inside an ISA eliminates CGT entirely on what could otherwise be a very large future gain. The bed-and-re-ISA strategy (sell in general account, use AEA, repurchase inside ISA) is the standard method for gradually migrating holdings from taxable accounts to ISA wrappers.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the CGT rate on shares in 2026/27?", "a": "18% for gains within the basic-rate band and 24% for gains in the higher-rate band. These rates have applied since October 2024."},
            {"q": "What are the share matching rules?", "a": "HMRC matches disposals first against same-day purchases, then against purchases within the following 30 days, then against the Section 104 pool average. This prevents selective lot matching and rapid recycling to avoid tax."},
            {"q": "Are shares inside an ISA exempt from CGT?", "a": "Yes. There is no CGT on gains from shares, funds or ETFs held inside a Stocks and Shares ISA."},
        ],
    },
    {
        "slug": "reducing-capital-gains-tax-legally",
        "title": "How to Reduce Capital Gains Tax Legally in 2026/27",
        "description": "Proven legal strategies to reduce your UK CGT bill in 2026/27: annual exempt amount, losses, ISAs, pensions, spouse transfers and Business Asset Disposal Relief.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "Use the Annual Exempt Amount Every Year",
                "paragraphs": [
                    "The £3,000 annual exempt amount is use-it-or-lose-it. Every year you fail to crystallise gains up to £3,000, you lose that year's allowance permanently. Active investors should review their portfolio each year before 5 April and consider whether to realise any gains to use the AEA. Over 10 years, a couple who use both their AEAs every year will have crystallised £60,000 of gains tax-free.",
                    "The bed-and-re-ISA technique (sell in the general account, use the AEA, repurchase inside the ISA) systematically moves holdings into the tax-free ISA environment. Once inside an ISA, future growth and income are permanently sheltered. The immediate repurchase inside the ISA avoids the 30-day same-account rule because the new holding is in a different legal wrapper.",
                ],
            },
            {
                "heading": "Match Gains with Losses",
                "paragraphs": [
                    "Capital losses, whether from the current tax year or carried forward from earlier years, reduce taxable gains. If you have loss-making holdings that you intend to dispose of eventually, selling them in the same tax year as a large gain can significantly reduce or eliminate the CGT bill. Losses must be reported to HMRC (through Self Assessment) to be officially recognised — HMRC will not automatically discover and apply losses.",
                    "Brought-forward losses from previous years are applied to the extent needed to bring the net gain down to the annual exempt amount. Any excess losses are carried forward again. There is no time limit on carrying forward capital losses, so losses from many years ago remain available indefinitely, provided they were reported when they arose.",
                ],
            },
            {
                "heading": "Transfer Assets to a Lower-Rate Spouse",
                "paragraphs": [
                    "Gifts between spouses and civil partners are at no-gain/no-loss for CGT purposes. If you are a higher-rate taxpayer (CGT at 24%) and your spouse is a basic-rate taxpayer (CGT at 18%) or has unused AEA, transferring the asset before disposal can save up to 6% of the gain. On a £50,000 gain, that is a saving of £3,000.",
                    "The transfer is a genuine gift — the asset must belong to the recipient spouse outright, not just temporarily for tax purposes. HMRC's settlements legislation (section 620 ITTOIA 2005) can apply if the arrangement is primarily tax-motivated and the transferring spouse retains benefits from the asset. For straightforward transfers of investment portfolios or property between genuinely jointly-managing spouses, the strategy is well-established and HMRC-compliant.",
                ],
            },
            {
                "heading": "Use ISAs and Pensions to Shelter Future Gains",
                "paragraphs": [
                    "ISAs provide complete CGT (and income tax) exemption. The £20,000 annual subscription limit means it takes time to move large portfolios inside an ISA, but the tax-free compounding effect is substantial over time. Pensions provide a similar shelter — assets inside a pension grow free of CGT. The pension annual allowance is £60,000 for 2026/27 (with carry-forward available for the previous three years), making pensions a powerful tool for those with business sale proceeds or large property gains.",
                    "When selling a business or commercial property, consider whether proceeds can be reinvested into a pension in the same tax year. A contribution of £60,000 to a pension not only shelters those funds from future CGT but also generates income tax relief at the marginal rate, which could partially offset the CGT payable on the sale.",
                ],
            },
            {
                "heading": "Business Asset Disposal Relief",
                "paragraphs": [
                    "Business Asset Disposal Relief (BADR, formerly Entrepreneurs' Relief) provides a 14% CGT rate on qualifying gains up to a lifetime limit of £1,000,000. Qualifying disposals include shares in a personal company (where you hold at least 5% of shares and voting rights, and the company is a trading company, and you have held shares for at least two years) and business assets used in a sole trade or partnership.",
                    "BADR is one of the most valuable reliefs in the CGT system but is complex and easy to lose by failing to meet all the qualifying conditions. The two-year qualifying period for shares must be met before the disposal date. Dilution of a shareholding below 5% through a funding round can potentially eliminate BADR eligibility, so company owners should plan carefully around any investment events that might affect their holding percentage.",
                ],
            },
        ],
        "faqs": [
            {"q": "What are the most effective ways to reduce CGT in 2026/27?", "a": "Using the annual exempt amount every year, matching gains with losses, transferring assets to a lower-rate spouse, and sheltering assets inside ISAs and pensions are the key legal strategies."},
            {"q": "Can I sell at a loss deliberately to reduce CGT?", "a": "Yes. Capital losses from selling assets at a loss can offset gains in the same or future tax years. The losses must be reported to HMRC through Self Assessment."},
            {"q": "What is Business Asset Disposal Relief?", "a": "BADR is a CGT relief that provides a 14% rate on qualifying gains up to a £1,000,000 lifetime limit. It applies to qualifying business disposals such as shares in a personal company or assets used in a sole trade."},
        ],
    },
]

@app.route("/blog")
def blog_index():
    return render_template("blog_index.html", **_ctx(
        title="UK Capital Gains Tax Guides 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="In-depth guides on UK capital gains tax for property, shares, crypto and other assets. Covering 2026/27 rates, exemptions and planning strategies.",
        canonical_url=SITE_URL + "/blog",
        posts=BLOG_POSTS,
    ))

BLOG_BY_SLUG = {p["slug"]: p for p in BLOG_POSTS}

@app.route("/blog/<slug>")
def blog_post(slug):
    post = BLOG_BY_SLUG.get(slug)
    if not post:
        abort(404)
    return render_template("blog_post.html", **_ctx(
        title=post["title"],
        meta_description=post["description"],
        canonical_url=SITE_URL + f"/blog/{slug}",
        post=post,
        examples=[],
        article_faqs=post.get("faqs", []),
        reference_facts=None,
        sources=[
            {"url": "https://www.gov.uk/capital-gains-tax", "label": "HMRC: Capital Gains Tax overview"},
            {"url": "https://www.gov.uk/government/publications/rates-and-allowances-capital-gains-tax", "label": "HMRC: CGT rates and allowances"},
            {"url": "https://www.gov.uk/tax-sell-home", "label": "HMRC: Tax when you sell your home"},
        ],
    ))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
