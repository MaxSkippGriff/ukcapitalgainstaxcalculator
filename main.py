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


@app.route("/ads.txt")
def ads_txt():
    pub_id = ADSENSE_CLIENT.replace("ca-pub-", "").strip()
    body = f"google.com, pub-{pub_id}, DIRECT, f08c47fec0942fa0\n" if pub_id else ""
    resp = make_response(body)
    resp.mimetype = "text/plain"
    return resp


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

CGT_GAIN_AMOUNTS = [5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000, 150000, 200000, 250000, 500000]

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
        "slug": "cgt-rates-2026-27",
        "title": "Capital Gains Tax Rates 2026/27 — Full Guide",
        "description": "A complete guide to CGT rates for 2026/27: residential property at 18%/24%, other assets at 10%/20%, the £3,000 annual exempt amount, the 60-day reporting rule and Business Asset Disposal Relief.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "The Two CGT Rate Structures",
                "paragraphs": [
                    "CGT in 2026/27 operates on two separate rate structures depending on the type of asset. Residential property that is not your main home — second homes, buy-to-let properties, inherited property — is taxed at 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. Most other assets — shares, funds, crypto, commercial property, business assets — are taxed at 10% basic rate and 20% higher rate.",
                    "The rate that applies is determined by your income tax position, not a separate CGT calculation. Your other taxable income (salary, pension, rental income) fills the basic-rate band first, up to the £50,270 threshold. Any remaining basic-rate band space is then available to absorb your taxable gains at the lower rate. Gains above that remaining space are charged at the higher rate. This means a basic-rate taxpayer with a large gain will often find part of it taxed at the higher rate — gains stack on top of income.",
                    "The residential property rates of 18%/24% replaced the previous 18%/28% structure from 30 October 2024 onwards. For the 2026/27 tax year, all qualifying residential property disposals use the current 18%/24% rates throughout.",
                ],
            },
            {
                "heading": "The Annual Exempt Amount — £3,000",
                "paragraphs": [
                    "Every individual has an annual exempt amount (AEA) of £3,000 for 2026/27. Net gains below this threshold in a tax year are completely free from CGT. The AEA is applied after losses — so if you have £8,000 of gains and £3,000 of losses, your net gain is £5,000, and the £3,000 AEA reduces the taxable gain to £2,000.",
                    "The AEA cannot be carried forward to the next tax year. If you do not make any gains in 2026/27, the £3,000 allowance is simply lost. It also cannot be transferred to a spouse — each individual has their own separate allowance. However, married couples should consider whose name an asset is held in before selling, since whichever spouse makes the disposal uses their own AEA and pays CGT at their own rate. A lower-income spouse with unused AEA and a lower CGT rate can reduce the household's total tax bill significantly.",
                ],
            },
            {
                "heading": "The 60-Day Reporting Requirement for Residential Property",
                "paragraphs": [
                    "If you sell a UK residential property (not your main home, or one with only partial main home relief) and a CGT liability arises, you must report the gain and pay an estimate of the tax within 60 days of the completion date. This is done through HMRC's online UK property reporting service — it is separate from the annual Self Assessment process. The 60-day clock starts on the completion date, not the exchange date.",
                    "Failing to report within 60 days triggers a late filing penalty of £100 immediately, rising to £300 (or 5% of the tax due if higher) after 6 months, and a further £300 (or 5%) after 12 months. Daily penalties of £10 per day also apply after 3 months. If there is no CGT to pay — for example if the gain is within the AEA or fully covered by losses — no report is required. Non-UK resident individuals must report all UK residential property disposals through the same service, whether or not CGT is owed.",
                ],
            },
            {
                "heading": "Business Asset Disposal Relief",
                "paragraphs": [
                    "Business Asset Disposal Relief (BADR), previously known as Entrepreneurs' Relief, provides a reduced CGT rate of 10% on qualifying gains up to a lifetime limit of £1,000,000. For qualifying disposals on or after 6 April 2025, the BADR rate is 14% (it increased from 10% as announced in the October 2024 Budget). Check the applicable rate for your disposal date carefully.",
                    "To qualify for BADR, the most common route is shares in your personal trading company: you must hold at least 5% of the ordinary share capital and voting rights, the company must be a trading company (or the holding company of a trading group), and you must have held the shares for at least two years immediately before disposal. You must also have been an officer or employee of the company throughout that two-year period. The £1,000,000 lifetime limit is cumulative across all qualifying disposals throughout your life. Once used up, it is gone — there is no annual reset.",
                ],
            },
        ],
        "faqs": [
            {"q": "What are the CGT rates for 2026/27?", "a": "Residential property: 18% basic rate, 24% higher rate. Other assets (shares, crypto, etc.): 10% basic rate, 20% higher rate. Business Asset Disposal Relief: 14% on qualifying gains up to £1m lifetime limit."},
            {"q": "How does my income affect my CGT rate?", "a": "Your salary and other income fill the basic-rate band first. Whatever space remains up to £50,270 is available for gains at the lower CGT rate. Gains above that threshold are at the higher rate. A large gain will often straddle both rates."},
            {"q": "Do I have to report a property sale within 60 days?", "a": "Yes, if CGT is owed on the disposal of a UK residential property. The report and payment are due within 60 days of completion through HMRC's online property reporting service."},
        ],
    },
    {
        "slug": "private-residence-relief-explained",
        "title": "Private Residence Relief Explained",
        "description": "Private Residence Relief (PRR) exempts your main home from CGT. This guide covers the final 9 months rule, partial PRR for let periods, when PRR goes wrong and the rules for married couples.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "7 min read",
        "sections": [
            {
                "heading": "What PRR Covers",
                "paragraphs": [
                    "Private Residence Relief exempts the gain on your only or main residence from CGT. If you own one property and it has been your main home throughout your entire period of ownership, the full gain is exempt. You do not need to claim the relief — it applies automatically, and you are not required to report the disposal on a Self Assessment return.",
                    "The relief also covers the final 9 months of ownership, regardless of whether you are still living in the property. This grace period exists to help people who have moved out before completing the sale — for example after buying a new home and needing time to sell the old one. If you moved out 6 months before completion, those 6 months are still counted as a period of main residence. If you moved out 18 months before completion, only the last 9 months of that gap are covered; the other 9 months are potentially chargeable.",
                ],
            },
            {
                "heading": "Partial PRR — Let Property and Periods of Deemed Occupation",
                "paragraphs": [
                    "If you lived in the property for only part of your ownership period, PRR is apportioned. The exempt fraction is the proportion of time the property was your main residence (plus the final 9 months), divided by the total ownership period. Periods of absence can be treated as periods of occupation in certain circumstances — these are called deemed occupation periods. They include the last 9 months, any period working abroad for any length of time, and any period working elsewhere in the UK (up to 4 years), provided the property was your main residence before and after the absence.",
                    "Let Property Relief used to provide a further exemption for periods when the property was let while you were absent, but the rules changed significantly from April 2020. The relief now only applies in situations where the owner is in shared occupation with the tenant — a narrow set of circumstances that does not cover standard buy-to-let periods. For most people who have let their former main home, Let Property Relief is no longer available.",
                ],
            },
            {
                "heading": "When PRR Goes Wrong",
                "paragraphs": [
                    "Several situations can unexpectedly reduce or eliminate PRR. Using part of your home exclusively for business — a room used only as an office, not as a room that doubles as an office — means that portion of the gain does not qualify for PRR. The key word is exclusively: a room used sometimes for work and sometimes as a bedroom retains PRR, but a dedicated office that was never used as living space does not. This is a common trap for the self-employed.",
                    "Development land is another area where PRR can be challenged. If you sell your garden or grounds separately, or if the sale price reflects development potential rather than residential use, HMRC may argue that part of the gain relates to the development value rather than the residence itself. The interaction between PRR and development gains requires careful analysis. Similarly, converting a property from a main home to a buy-to-let before selling it creates a period of non-residence that is fully chargeable.",
                ],
            },
            {
                "heading": "PRR and Marriage — One Main Residence Per Couple",
                "paragraphs": [
                    "Married couples and civil partners can only nominate one property as their main residence for PRR purposes at any given time. If both spouses own separate properties, only one can be the couple's main residence — the same property applies to both of them. There is no ability for each spouse to separately claim PRR on different properties simultaneously.",
                    "The election process allows couples who own more than one property to nominate which one is treated as the main residence. The election must be made within two years of acquiring the second property. If no election is made, HMRC looks at the facts of occupation. For couples buying a second property — a holiday home, a property for a child — understanding this election and making it promptly is essential to preserve PRR on the intended main home.",
                ],
            },
        ],
        "faqs": [
            {"q": "Is my main home exempt from CGT?", "a": "Yes, in most cases. Private Residence Relief exempts the gain on your only or main home. The relief covers the period of occupation plus the final 9 months of ownership even after moving out."},
            {"q": "Do I get PRR if I let my home out?", "a": "Only for the period it was your actual main residence. Periods when it was let rather than occupied by you do not qualify for PRR (with narrow exceptions). Let Property Relief no longer applies to standard letting periods since April 2020."},
            {"q": "Can a married couple each claim PRR on different properties?", "a": "No. Married couples and civil partners share one main residence election — both spouses are bound by the same nominated main home."},
        ],
    },
    {
        "slug": "bed-and-isa-strategy",
        "title": "Bed and ISA — CGT Tax Planning Strategy",
        "description": "Bed and ISA is the strategy of selling investments outside an ISA and immediately rebuying them inside one. Future growth is then tax-free, and the sale uses your annual exempt amount.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "What Bed and ISA Means",
                "paragraphs": [
                    "Bed and ISA refers to selling shares or funds held in a general investment account (GIA) and immediately repurchasing the same or equivalent investments inside a Stocks and Shares ISA. The effect is to move holdings from a taxable environment into a tax-free wrapper. Once inside the ISA, all future growth, dividends and capital gains are permanently free from tax — there is no CGT on gains within an ISA, however large they become.",
                    "The term derives from the older 'bed and breakfast' strategy, where investors sold and repurchased outside any wrapper to crystallise a gain or loss. Bed and ISA is its successor — instead of repurchasing in the same account, the new holding goes into the ISA. This distinction is crucial for understanding how the tax rules apply.",
                ],
            },
            {
                "heading": "The CGT Implication of the 'Bed' Part",
                "paragraphs": [
                    "The sale itself — the 'bed' — is a disposal for CGT purposes. If the investment has grown in value, you crystallise a capital gain at the point of sale. That gain uses up your annual exempt amount (£3,000 for 2026/27). If the gain exceeds £3,000, CGT is payable on the excess. If the investment has fallen in value, you crystallise a capital loss, which can offset gains elsewhere.",
                    "Ideally, bed and ISA is timed so that gains fall within the annual exempt amount — meaning no CGT arises. An investor with unrealised gains of £3,000 or less can execute the full transfer tax-free each year. Those with larger unrealised gains might split the bed and ISA across two tax years — selling some before 5 April and the rest after 6 April — to use two years' worth of the annual exempt amount.",
                ],
            },
            {
                "heading": "The 30-Day Rule Does Not Apply to ISA Rebuys",
                "paragraphs": [
                    "The bed-and-breakfast rule (Section 106A TCGA 1992) matches a sale with any purchase of the same shares within 30 days, neutralising the intended gain or loss crystallisation. This rule is specifically designed to prevent investors from selling and immediately repurchasing in the same account to manipulate their tax position.",
                    "Crucially, the 30-day rule does not apply to purchases made inside an ISA. HMRC's position is that an ISA holding is a different legal entity from a direct holding, so the two are not 'the same' investment for matching purposes. You can sell shares in your GIA at 9am and buy the identical shares inside your ISA at 9.05am, and the 30-day rule does not apply. The gain (or loss) on the GIA sale stands in full. This is confirmed in HMRC's Capital Gains manual at CG42562.",
                ],
            },
            {
                "heading": "When Bed and ISA Makes Sense",
                "paragraphs": [
                    "Bed and ISA is most valuable for investments with significant unrealised growth that you intend to hold for a long time. The longer you hold, the more future gains accumulate inside the tax-free wrapper, and the greater the CGT saving compared to eventually selling from a GIA. For short-term holdings where you plan to sell within a year or two, the benefit may not justify the transaction costs.",
                    "The optimal time to execute is when your unrealised gain is close to (but does not exceed) your remaining annual exempt amount for the year, and when your ISA allowance has not yet been fully used. For a couple, both partners can execute bed and ISA in the same tax year, using their individual AEAs and ISA allowances — up to £40,000 combined can move into ISAs in a single year this way. Anyone with substantial GIA holdings should run the bed and ISA calculation every April as part of year-end tax planning.",
                ],
            },
        ],
        "faqs": [
            {"q": "Does the 30-day rule apply when rebuying inside an ISA?", "a": "No. The bed-and-breakfast 30-day matching rule only applies to repurchases in the same type of account. Repurchasing inside an ISA is not caught by the rule, so you can sell in a GIA and immediately rebuy in an ISA without the gain being neutralised."},
            {"q": "Will I owe CGT on a bed and ISA transaction?", "a": "Only if the gain on the GIA sale exceeds your annual exempt amount (£3,000 for 2026/27). If the unrealised gain is within the AEA, no CGT arises."},
            {"q": "Can I sell and immediately rebuy the same fund inside an ISA?", "a": "Yes. The sale and repurchase can happen on the same day. Your ISA subscription must be within your remaining annual allowance (£20,000 for 2026/27)."},
        ],
    },
    {
        "slug": "cgt-capital-losses",
        "title": "Capital Losses — How to Offset Against Gains",
        "description": "Capital losses reduce your CGT bill, but the offset rules are not straightforward. Same-year losses, carried-forward losses, reporting requirements and the rules on connected-person sales — all covered here.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "7 min read",
        "sections": [
            {
                "heading": "The Offset Rules",
                "paragraphs": [
                    "Capital losses from the same tax year must be set against capital gains from that same year first, before the annual exempt amount is applied. You cannot choose to defer current-year losses — they must be deducted. If your losses exceed your gains in a year, the net loss is carried forward to future years.",
                    "Losses brought forward from earlier years are treated differently. They are only applied to the extent necessary to reduce the net gain to the annual exempt amount (£3,000 for 2026/27). So if you have £15,000 of gains and £20,000 of brought-forward losses, you do not apply all £20,000 — you apply only £12,000 (to bring the net gain down to £3,000, which is then fully covered by the AEA and bears no CGT). The remaining £8,000 of brought-forward losses is preserved and carried forward again. This rule prevents losses from being wasted by being applied against gains that would have been exempt anyway.",
                ],
            },
            {
                "heading": "Reporting Losses",
                "paragraphs": [
                    "Capital losses are not automatically identified by HMRC. You must claim them, either on a Self Assessment tax return or by writing to HMRC if you are not within Self Assessment. The claim must be made within four years of the end of the tax year in which the loss arose. For a loss in 2022/23, the deadline to claim is 31 January 2027. Losses that are not claimed within the four-year window are permanently lost.",
                    "On a Self Assessment return, capital losses are reported in the Capital Gains pages (SA108). You enter both gains and losses for the year, and HMRC's calculation applies them in the correct order. Carried-forward losses from previous years must also be entered on the return each year they are used, even partially. Keep a running log of your brought-forward losses — it is easy to lose track across multiple tax years.",
                ],
            },
            {
                "heading": "Negligible Value Claims",
                "paragraphs": [
                    "If an asset has become effectively worthless — for example shares in a company that has gone into liquidation — but you have not yet formally disposed of them, you may be able to make a negligible value claim. This allows you to treat the asset as having been sold and immediately reacquired at the negligible value, crystallising a loss even though no actual sale has occurred. You can specify a date in the past (going back up to two prior tax years) for the deemed disposal, provided the asset was of negligible value at that date.",
                    "The claim is useful for extracting a loss from an investment that is stuck — either because the shares are in a suspended company, the asset has no buyer, or disposal is otherwise impractical. HMRC maintains a list of companies where negligible value claims have been accepted, which speeds up the process. For assets outside that list, you must demonstrate that the asset has no, or negligible, value at the claimed date.",
                ],
            },
            {
                "heading": "Selling at a Loss to a Connected Person",
                "paragraphs": [
                    "Sales to connected persons — which includes your spouse, civil partner, children, siblings, parents and companies you control — do not create allowable CGT losses. If you sell an asset to a connected person at a loss (whether at arm's length or at an undervalue), that loss is not deductible against other gains. It is a 'clogged' loss, which can only be set against gains arising on later transactions with the same connected person.",
                    "This rule exists to prevent artificial loss creation within families. The no-gain/no-loss rule for spousal transfers means you cannot give an asset to your spouse, have them sell at a loss, and use that loss against your own gains. The connected-person rules also mean that selling a loss-making investment to your adult child at market value still produces a clogged loss if they are a connected person. Genuine arm's-length sales to unrelated third parties are not affected.",
                ],
            },
        ],
        "faqs": [
            {"q": "Do I have to use losses against gains in the same year?", "a": "Yes, current-year losses must be set against current-year gains first. You cannot choose to carry them forward if there are gains available to offset in the same year."},
            {"q": "How long can I carry forward capital losses?", "a": "Indefinitely, provided they were claimed within 4 years of the end of the tax year when they arose. There is no time limit on using losses once correctly claimed."},
            {"q": "Can I claim a loss if my shares are worthless but I haven't sold them?", "a": "Yes, through a negligible value claim. You can treat the shares as sold and immediately reacquired at nil value, creating a capital loss. The claim can be backdated up to two prior tax years if the shares were worthless then."},
        ],
    },
    {
        "slug": "cgt-gifted-property",
        "title": "Transferring Assets Between Spouses — CGT Rules",
        "description": "Married couples and civil partners can transfer assets between themselves with no CGT charge. This guide covers the no-gain no-loss rule, its use in pre-sale planning, the year-of-separation trap and gifts to others.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "No-Gain No-Loss Transfers",
                "paragraphs": [
                    "Transfers of assets between spouses and civil partners who are living together are treated as no-gain no-loss transactions for CGT purposes under TCGA 1992 s58. This means no CGT arises at the point of transfer, regardless of the asset's current market value. The receiving spouse acquires the asset at the transferring spouse's original acquisition cost (plus any capital improvements), not at its current value. The base cost carries over.",
                    "This rule applies automatically to all transfers between cohabiting spouses and civil partners — there is no election required and no form to file. It applies to all assets: shares, property, crypto, business interests. The rule does not apply to couples who are separated or who have permanently ceased living together — see the year-of-separation trap below.",
                ],
            },
            {
                "heading": "Why This Matters for Planning",
                "paragraphs": [
                    "The no-gain no-loss rule enables a straightforward and HMRC-compliant strategy: transfer an asset to the lower-income spouse before sale, so that the eventual gain is taxed at their lower CGT rate. A higher-rate taxpayer with a £50,000 gain on shares would pay CGT at 20%, giving a liability of approximately £9,400 after the AEA. If the same asset is transferred to a basic-rate taxpayer spouse before disposal, the same gain is taxed at 10%, a liability of approximately £4,700 — a saving of £4,700.",
                    "The strategy works for the annual exempt amount too. If one spouse has already used their £3,000 AEA and the other has not, transferring an asset with a £3,000 gain to the unused-AEA spouse before sale means the gain is entirely tax-free. Over a lifetime of investing, using both spouses' AEAs systematically generates meaningful tax savings. The transfer must be a genuine and unconditional gift to the other spouse — it cannot be conditional on the sale proceeds being returned.",
                ],
            },
            {
                "heading": "The Year-of-Separation Trap",
                "paragraphs": [
                    "The no-gain no-loss rule only applies while spouses or civil partners are living together. For CGT purposes, 'living together' means not separated under a court order or separation agreement, and not in circumstances where the separation is likely to be permanent. Once a couple separates permanently, the rule ceases to apply — even if the divorce has not yet been finalised.",
                    "For tax years from 2023/24 onwards, there is an extended window: separating couples have until the end of the third tax year following the year of separation to transfer assets between themselves on a no-gain no-loss basis. This extended window was introduced to give divorcing couples more time to sort out financial settlements without tax charges arising. Before this change, the window closed at the end of the tax year of separation — often only weeks or months — creating urgent and poorly-timed disposals. The extended window significantly reduces pressure on separating couples to rush asset transfers.",
                ],
            },
            {
                "heading": "Gifts to Others — Deemed Proceeds Rule",
                "paragraphs": [
                    "The no-gain no-loss treatment is exclusive to spouses and civil partners. Gifts to anyone else — children, siblings, friends, cohabitees — trigger CGT at the asset's market value at the date of the gift, regardless of whether any money changes hands. This is the deemed proceeds rule: HMRC treats the gift as if you had sold the asset at open market value.",
                    "For example, gifting shares currently worth £30,000 that you originally bought for £10,000 creates a taxable gain of £20,000. The fact that you received nothing for them is irrelevant — CGT is calculated on the market value. Hold-Over Relief is available in limited circumstances for gifts of business assets, meaning the gain can be deferred until the recipient eventually sells. But for most assets — shares in listed companies, investment property, crypto — no hold-over is available, and the gift triggers an immediate CGT charge at market value.",
                ],
            },
        ],
        "faqs": [
            {"q": "Does transferring assets to my spouse trigger CGT?", "a": "No. Transfers between spouses and civil partners who are living together are no-gain no-loss — no CGT arises at the transfer. The receiving spouse takes the asset at the original acquisition cost."},
            {"q": "When does the year-of-separation rule apply?", "a": "Once spouses permanently separate, the no-gain no-loss rule ends. From 2023/24, separating couples have three additional tax years to make no-gain no-loss transfers, giving more time for divorce financial settlements."},
            {"q": "What CGT applies if I give shares to my adult child?", "a": "The gift is treated as a disposal at market value. CGT is calculated on the difference between market value and your acquisition cost. No hold-over relief is available for shares in listed companies."},
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
