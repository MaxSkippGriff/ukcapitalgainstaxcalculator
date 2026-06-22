"""UKCapitalGainsTaxCalculator.co.uk Flask application."""
from __future__ import annotations
import logging
import os
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory
from flask_limiter import Limiter
from calculator import active_tax_year, TAX_YEAR, calculate_cgt, ANNUAL_EXEMPT_AMOUNT, CGT_LOWER_RATE, CGT_HIGHER_RATE, PERSONAL_ALLOWANCE, BASIC_RATE_LIMIT
from scraper_guard import init_guard

log = logging.getLogger(__name__)

load_dotenv()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CGT_PACK_PRICE_ID = os.getenv("STRIPE_CGT_PACK_PRICE_ID", "")
PACK_AMOUNT_PENCE = int(os.getenv("PACK_AMOUNT_PENCE", "499"))

_stripe = None
if STRIPE_SECRET_KEY and "sk_" in STRIPE_SECRET_KEY:
    import stripe as _stripe
    _stripe.api_key = STRIPE_SECRET_KEY

_PACK_PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "private", "Capital-Gains-Tax-Survival-Pack.pdf")

_PUBLIC_PATHS = (
    "/sitemap.xml", "/robots.txt", "/ads.txt", "/favicon.ico",
    "/favicon-16x16.png", "/favicon-32x32.png", "/apple-touch-icon.png",
    "/site.webmanifest", "/health",
    "/cgt-survival-pack/webhook",
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
                ga_measurement_id=GA_MEASUREMENT_ID, adsense_client=ADSENSE_CLIENT,
                stripe_pub_key=STRIPE_PUBLISHABLE_KEY, **kw)


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
        (f"{SITE_URL}/editorial-standards","0.4","yearly"),
        (f"{SITE_URL}/capital-gains-tax-on-inherited-property","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-on-buy-to-let","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-losses","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-reporting-deadline","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-basic-rate-taxpayer","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-second-home","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-business-sale","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-higher-rate-taxpayer","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-for-higher-rate-taxpayers","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-on-gifts","0.6","monthly"),
        (f"{SITE_URL}/capital-gains-tax-records","0.6","monthly"),
        (f"{SITE_URL}/guides","0.7","monthly"),
        (f"{SITE_URL}/calculators","0.7","monthly"),
        (f"{SITE_URL}/property-cgt-calculator","0.8","monthly"),
        (f"{SITE_URL}/shares-cgt-calculator","0.8","monthly"),
        (f"{SITE_URL}/crypto-cgt-calculator","0.7","monthly"),
        (f"{SITE_URL}/cgt-allowance-calculator","0.7","monthly"),
        # New guide pages
        (f"{SITE_URL}/capital-gains-tax-on-property","0.8","monthly"),
        (f"{SITE_URL}/capital-gains-tax-on-shares","0.8","monthly"),
        (f"{SITE_URL}/capital-gains-tax-allowance-2026-27","0.8","monthly"),
        (f"{SITE_URL}/capital-gains-tax-30-day-rule","0.7","monthly"),
        (f"{SITE_URL}/entrepreneurs-relief-business-asset-disposal","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-scotland","0.7","monthly"),
        (f"{SITE_URL}/capital-gains-tax-rates-2026-27","0.8","monthly"),
        (f"{SITE_URL}/how-to-calculate-capital-gains-tax","0.8","monthly"),
        (f"{SITE_URL}/capital-gains-tax-property-calculator","0.8","monthly"),
        # Blog
        (f"{SITE_URL}/blog","0.7","weekly"),
        *[(f"{SITE_URL}/blog/{p['slug']}","0.6","monthly") for p in BLOG_POSTS],
        # CGT gain pages
        *[(f"{SITE_URL}/cgt/{g}", "0.6", "monthly") for g in CGT_GAIN_AMOUNTS],
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
        title="Capital Gains Tax Calculator UK 2026/27 | Free CGT Tool",
        meta_description="Free UK CGT calculator 2026/27. Enter proceeds, costs & income, instant CGT breakdown at 18%/24%. £3,000 annual exempt amount applied. Property, shares & crypto.",
        canonical_url=SITE_URL+"/",
        calc=calc,
        faq_items=faq,
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"}],
    ))

@app.route("/calculator")
def calculator_page():
    return render_template("calculator.html", **_ctx(
        title="CGT Calculator 2026/27 | UK Capital Gains Tax Breakdown",
        meta_description="Free UK Capital Gains Tax calculator 2026/27. Enter sale proceeds, cost, losses and income, get a full CGT breakdown showing tax at 18% (basic rate) and 24% (higher rate) with £3,000 AEA applied.",
        canonical_url=SITE_URL+"/calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Calculator","url":SITE_URL+"/calculator"}],
    ))

@app.route("/methodology")
def methodology():
    return render_template("methodology.html", **_ctx(
        title="Methodology, How We Calculate UK Capital Gains Tax 2026/27",
        meta_description="How UKCapitalGainsTaxCalculator.co.uk calculates CGT: 2026/27 rates, annual exempt amount, band ordering and what we don't model.",
        canonical_url=SITE_URL+"/methodology",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Methodology","url":SITE_URL+"/methodology"}],
    ))

@app.route("/about")
def about():
    return render_template("about.html", **_ctx(
        title="About UK Capital Gains Tax Calculator, Free CGT Tool",
        meta_description="About UKCapitalGainsTaxCalculator.co.uk, a free, independent tool to estimate CGT on shares, property and other UK assets for 2026/27.",
        canonical_url=SITE_URL+"/about",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"About","url":SITE_URL+"/about"}],
    ))

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", **_ctx(
        title="Privacy Policy, UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Privacy policy for UKCapitalGainsTaxCalculator.co.uk. We don't store your financial data.",
        canonical_url=SITE_URL+"/privacy",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Privacy","url":SITE_URL+"/privacy"}],
    ))

@app.route("/editorial-standards")
def editorial_standards():
    return render_template("editorial_standards.html", **_ctx(
        title="Editorial Standards, UKCapitalGainsTaxCalculator.co.uk",
        meta_description="How UKCapitalGainsTaxCalculator.co.uk writes, reviews and maintains its calculator content and guides on UK capital gains tax.",
        canonical_url=SITE_URL+"/editorial-standards",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Editorial Standards","url":SITE_URL+"/editorial-standards"}],
    ))

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip()[:200]
        message = request.form.get("message", "").strip()[:2000]
        if email and message:
            try:
                db = get_db()
                if db is not None:
                    db.collection("contact_messages").add({
                        "name": name, "email": email, "message": message,
                        "site": SITE_URL, "created_at": server_timestamp(), "read": False,
                    })
            except Exception:
                pass
        return redirect("/contact?sent=1")
    sent = request.args.get("sent") == "1"
    return render_template("contact.html", **_ctx(
        title="Contact, UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Get in touch with UKCapitalGainsTaxCalculator.co.uk.",
        canonical_url=SITE_URL+"/contact",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Contact","url":SITE_URL+"/contact"}],
        sent=sent,
    ))

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", **_ctx(
        title="Disclaimer, UKCapitalGainsTaxCalculator.co.uk",
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
@app.route("/capital-gains-tax-on-a-second-property")
@app.route("/capital-gains-tax-second-property")
@app.route("/capital-gains-tax-residential-property")
@app.route("/cgt-tax-rates-2026-2027-residential")
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
        meta_description="Capital Gains Tax for higher-rate taxpayers 2026/27: 24% on shares and property. Learn how gains stack on top of income, worked examples, and legal ways to reduce your CGT bill.",
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
        meta_description="How CGT works at 24% for higher-rate taxpayers in 2026/27, income interactions, worked example and planning strategies to reduce your bill.",
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
        meta_description="Calculate CGT on property 2026/27: 18% basic rate, 24% higher rate on second homes, buy-to-let and inherited property. £3,000 annual exempt amount. Includes 60-day reporting reminder.",
        canonical_url=SITE_URL + "/property-cgt-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Property CGT Calculator","url":SITE_URL+"/property-cgt-calculator"}],
    ))

@app.route("/shares-cgt-calculator")
def shares_cgt_calculator():
    return render_template("shares-cgt-calculator.html", **_ctx(
        title="Shares CGT Calculator 2026/27 | UKCapitalGainsTaxCalculator.co.uk",
        meta_description="Estimate Capital Gains Tax on shares 2026/27. Rates: 18% basic rate, 24% higher rate. £3,000 annual exempt amount. Enter your share sale details for an instant CGT estimate.",
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

@app.route("/cgt-calculator")
@app.route("/capital-gains-calculator")
@app.route("/cgt-calculator-uk")
def cgt_alias():
    return redirect("/", code=301)

@app.route("/divorce-cgt")
@app.route("/divorce-capital-gains-tax")
def divorce_cgt_alias():
    return redirect("/blog/divorce-capital-gains-tax", code=301)

# ── New guide pages ──────────────────────────────────────────────────────────

@app.route("/capital-gains-tax-on-property")
def guide_cgt_on_property():
    return render_template("capital-gains-tax-on-property.html", **_ctx(
        title="Capital Gains Tax on Property UK 2026/27 | 18% & 24% Rates",
        meta_description="Capital gains tax on UK property 2026/27: 18% (basic rate) or 24% (higher rate) on second homes, buy-to-let & inherited property. £3,000 AEA. Worked examples.",
        canonical_url=SITE_URL+"/capital-gains-tax-on-property",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT on Property","url":SITE_URL+"/capital-gains-tax-on-property"}],
    ))

@app.route("/capital-gains-tax-on-shares")
@app.route("/capital-gains-tax-on-shares-uk")
@app.route("/capital-gains-tax-shares")
def guide_cgt_on_shares():
    return render_template("capital-gains-tax-on-shares.html", **_ctx(
        title="Capital Gains Tax on Shares UK 2026/27 | 18% & 24% Rates",
        meta_description="CGT on shares 2026/27: 18% basic rate, 24% higher rate. Section 104 pooling, bed-and-ISA strategy, the 30-day rule and worked calculation examples.",
        canonical_url=SITE_URL+"/capital-gains-tax-on-shares",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT on Shares","url":SITE_URL+"/capital-gains-tax-on-shares"}],
    ))

@app.route("/capital-gains-tax-allowance-2026-27")
@app.route("/cgt-annual-exemption-2026-27")
@app.route("/capital-gains-tax-exemption-2026-27")
@app.route("/cgt-exemption-2026-27")
@app.route("/cgt-annual-allowance-2026-27")
@app.route("/uk-capital-gains-allowance-2026-27")
@app.route("/capital-gains-exemption-2026-27")
@app.route("/2026-27-capital-gains-exemption-limit")
@app.route("/capital-gains-tax-allowance")
def guide_cgt_allowance():
    return render_template("capital-gains-tax-allowance-2026-27.html", **_ctx(
        title="CGT Allowance 2026/27: £3,000 Annual Exempt Amount | UK Guide",
        meta_description="The capital gains tax allowance for 2026/27 is £3,000. This guide explains how the AEA works, how it has been cut from £12,300, and planning tips to make the most of it.",
        canonical_url=SITE_URL+"/capital-gains-tax-allowance-2026-27",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Allowance 2026/27","url":SITE_URL+"/capital-gains-tax-allowance-2026-27"}],
    ))

@app.route("/capital-gains-tax-30-day-rule")
@app.route("/cgt-30-day-rule")
def guide_30_day_rule():
    return render_template("capital-gains-tax-30-day-rule.html", **_ctx(
        title="CGT 30-Day Rule Explained | Bed & Breakfast Rule UK 2026/27",
        meta_description="The CGT 30-day rule (bed & breakfast rule) prevents you re-buying the same shares within 30 days of selling. Learn how it works and how to plan around it.",
        canonical_url=SITE_URL+"/capital-gains-tax-30-day-rule",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT 30-Day Rule","url":SITE_URL+"/capital-gains-tax-30-day-rule"}],
    ))

@app.route("/entrepreneurs-relief-business-asset-disposal")
@app.route("/business-asset-disposal-relief")
@app.route("/business-asset-disposal-relief-2026")
@app.route("/business-asset-disposal-relief-2026-27")
@app.route("/uk-qualifying-business-asset-2026-27")
@app.route("/entrepreneurs-relief")
def guide_badr():
    return render_template("entrepreneurs-relief-business-asset-disposal.html", **_ctx(
        title="Business Asset Disposal Relief (BADR) 2026/27 | 14% CGT Rate",
        meta_description="Business Asset Disposal Relief 2026/27: 14% CGT on qualifying gains up to £1m lifetime limit. Qualifying conditions, worked examples and planning tips.",
        canonical_url=SITE_URL+"/entrepreneurs-relief-business-asset-disposal",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"BADR / Entrepreneurs' Relief","url":SITE_URL+"/entrepreneurs-relief-business-asset-disposal"}],
    ))

@app.route("/capital-gains-tax-scotland")
@app.route("/cgt-scotland")
def guide_cgt_scotland():
    return render_template("capital-gains-tax-scotland.html", **_ctx(
        title="Capital Gains Tax Scotland 2026/27 | Scottish CGT Guide",
        meta_description="CGT rates are the same across the UK, but Scottish taxpayers' lower higher-rate threshold (£43,662) affects which CGT band applies. Full guide with worked examples.",
        canonical_url=SITE_URL+"/capital-gains-tax-scotland",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT in Scotland","url":SITE_URL+"/capital-gains-tax-scotland"}],
    ))

@app.route("/capital-gains-tax-rates-2026-27")
@app.route("/cgt-rates-2026-27")
@app.route("/cgt-rates-26-27")
@app.route("/cgt-tax-rates-2026-27")
@app.route("/capital-gains-tax-rates-2026")
@app.route("/uk-cgt-rates-2026-27")
@app.route("/capital-gains-tax-rate-2026-uk")
@app.route("/uk-capital-gains-tax-rate-2026")
@app.route("/cgt-rates")
@app.route("/capital-gains-tax-rates")
def guide_cgt_rates():
    return render_template("capital-gains-tax-rates-2026-27.html", **_ctx(
        title="Capital Gains Tax Rates 2026/27 | 18% & 24% UK CGT Rates",
        meta_description="UK CGT rates 2026/27: 18% basic rate, 24% higher rate on all assets. £3,000 annual exempt amount. BADR 14%. How rates changed in October 2024 Budget. Full guide.",
        canonical_url=SITE_URL+"/capital-gains-tax-rates-2026-27",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"CGT Rates 2026/27","url":SITE_URL+"/capital-gains-tax-rates-2026-27"}],
    ))

@app.route("/how-to-calculate-capital-gains-tax")
@app.route("/calculate-capital-gains-tax")
@app.route("/how-to-calculate-cgt")
@app.route("/how-do-you-calculate-cgt-uk")
@app.route("/how-to-work-out-cgt-uk")
def guide_how_to_calculate():
    return render_template("how-to-calculate-capital-gains-tax.html", **_ctx(
        title="How to Calculate Capital Gains Tax UK 2026/27 | Step-by-Step",
        meta_description="How to calculate capital gains tax in the UK 2026/27: step-by-step with worked examples for property and shares. S104 pooling, AEA, income band split explained.",
        canonical_url=SITE_URL+"/how-to-calculate-capital-gains-tax",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"How to Calculate CGT","url":SITE_URL+"/how-to-calculate-capital-gains-tax"}],
    ))

@app.route("/capital-gains-tax-property-calculator")
def guide_property_calculator_landing():
    return render_template("capital-gains-tax-property-calculator.html", **_ctx(
        title="Capital Gains Tax Property Calculator UK 2026/27 | Free Tool",
        meta_description="Free capital gains tax calculator for UK property 2026/27. Enter purchase price, improvements, sale proceeds & income. Instant CGT split at 18%/24%.",
        canonical_url=SITE_URL+"/capital-gains-tax-property-calculator",
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":"Property CGT Calculator","url":SITE_URL+"/capital-gains-tax-property-calculator"}],
    ))

# ── Redirect aliases for common query variants ────────────────────────────────

@app.route("/cgt-allowance-2026-27")
@app.route("/capital-gains-allowance")
@app.route("/cgt-annual-exempt-amount")
def alias_cgt_allowance():
    return redirect("/capital-gains-tax-allowance-2026-27", code=301)

@app.route("/capital-gains-tax-uk-rates")
@app.route("/uk-capital-gains-tax-rate")
@app.route("/cgt-rate-uk")
def alias_cgt_rates():
    return redirect("/capital-gains-tax-rates-2026-27", code=301)

@app.route("/property-capital-gains-tax")
@app.route("/cgt-on-property")
@app.route("/capital-gains-on-property")
def alias_property_cgt():
    return redirect("/capital-gains-tax-on-property", code=301)

@app.route("/capital-gains-tax-on-shares-calculator")
@app.route("/cgt-on-shares")
@app.route("/shares-cgt")
def alias_shares_cgt():
    return redirect("/capital-gains-tax-on-shares", code=301)

@app.route("/hmrc-capital-gains-tax-calculator")
@app.route("/hmrc-cgt-calculator")
def alias_hmrc_cgt():
    return redirect("/calculator", code=301)

@app.route("/cgt-second-home")
@app.route("/second-home-capital-gains-tax")
def alias_second_home():
    return redirect("/capital-gains-tax-second-home", code=301)

@app.route("/cgt-on-inherited-property")
@app.route("/inherited-property-capital-gains-tax")
def alias_inherited():
    return redirect("/capital-gains-tax-on-inherited-property", code=301)

@app.route("/cgt-calculator-uk-2026")
@app.route("/capital-gains-tax-uk-calculator-2026")
def redirect_cgt_calc_2026():
    return redirect("/", code=301)

@app.route("/cgt-on-property-sale")
@app.route("/cgt-on-house-sale")
@app.route("/cgt-on-selling-a-house")
def redirect_cgt_property_sale():
    return redirect("/capital-gains-tax-on-property", code=301)

@app.route("/how-much-cgt-do-i-pay")
@app.route("/how-to-work-out-capital-gains-tax")
def redirect_how_much_cgt():
    return redirect("/", code=301)

@app.route("/private-residence-relief")
@app.route("/private-residence-relief-calculator")
@app.route("/cgt-main-residence-relief")
def redirect_prr():
    return redirect("/capital-gains-tax-second-home", code=301)

@app.route("/cgt-on-crypto")
@app.route("/crypto-capital-gains-tax")
@app.route("/capital-gains-tax-on-crypto")
def redirect_cgt_crypto():
    return redirect("/crypto-cgt-calculator", code=301)

@app.route("/cgt-losses-allowance")
@app.route("/capital-gains-tax-loss-relief")
def redirect_cgt_losses():
    return redirect("/capital-gains-tax-losses", code=301)

CGT_GAIN_AMOUNTS = [5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000, 150000, 200000, 250000, 500000]

@app.route("/cgt/<int:gain>")
def cgt_gain_page(gain: int):
    if gain not in CGT_GAIN_AMOUNTS:
        abort(404)
    calc_basic = calculate_cgt(sale_proceeds=gain, purchase_cost=0, buying_costs=0, selling_costs=0, taxable_income_before_gain=35000)
    calc_higher = calculate_cgt(sale_proceeds=gain, purchase_cost=0, buying_costs=0, selling_costs=0, taxable_income_before_gain=55000)
    nearby = [a for a in CGT_GAIN_AMOUNTS if a != gain]
    neighbours = sorted(nearby, key=lambda x: abs(x - gain))[:4]
    aea = 3000
    taxable = max(0, gain - aea)
    faq_items = [
        {"q": f"How much capital gains tax will I pay on a £{gain:,} gain in 2026/27?",
         "a": f"After deducting the £{aea:,} annual exempt amount, the taxable gain is £{taxable:,}. A basic-rate taxpayer pays about £{calc_basic.total_cgt:,.0f} and a higher-rate taxpayer about £{calc_higher.total_cgt:,.0f}. CGT is charged at 18% within your remaining basic-rate band and 24% above it."},
        {"q": "What is the capital gains tax allowance for 2026/27?",
         "a": f"The annual exempt amount is £{aea:,} for 2026/27 — you pay CGT only on gains above it. Allowable costs (the purchase price plus buying and selling fees) also reduce the taxable gain before CGT applies."},
        {"q": f"Why do basic-rate and higher-rate taxpayers pay different CGT on a £{gain:,} gain?",
         "a": "Capital gains tax rates depend on your total income. Gains that fall within your remaining basic-rate band are taxed at 18%; gains above it at 24%. A higher-rate taxpayer has little or no basic-rate band left, so more of the gain is taxed at 24%."},
        {"q": f"When do I report and pay CGT on a £{gain:,} gain?",
         "a": "For most assets, report and pay through Self Assessment by 31 January after the end of the tax year. For UK residential property you must report and pay within 60 days of completion using a Capital Gains Tax on UK property account."},
    ]
    return render_template("cgt_gain_page.html", **_ctx(
        title=f"Capital Gains Tax on £{gain:,} Gain 2026/27 | CGT Calculator",
        meta_description=f"How much CGT on a £{gain:,} gain in 2026/27? After the £3,000 annual exempt amount, a basic-rate taxpayer pays £{calc_basic.total_cgt:,.0f} and a higher-rate taxpayer pays £{calc_higher.total_cgt:,.0f}.",
        canonical_url=SITE_URL+f"/cgt/{gain}",
        gain=gain,
        calc_basic=calc_basic,
        calc_higher=calc_higher,
        neighbours=neighbours,
        faq_items=faq_items,
        breadcrumbs=[{"name":"Home","url":SITE_URL+"/"},{"name":f"CGT on £{gain:,}","url":SITE_URL+f"/cgt/{gain}"}],
    ))

BLOG_POSTS = [
    {
        "slug": "capital-gains-tax-scotland",
        "title": "Capital Gains Tax in Scotland 2026/27: How Scottish Income Tax Affects Your CGT Rate",
        "description": "CGT rates are the same across the UK, but Scottish taxpayers pay different income tax rates, and that affects which CGT rate (18% or 24%) applies to their gains.",
        "date_iso": "2026-05-01",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "CGT Rates Are Set by Westminster, the Same Across the UK",
                "paragraphs": [
                    "Capital gains tax rates apply identically in England, Scotland, Wales and Northern Ireland. For 2026/27, the rates are 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. These rates apply to most assets, including shares, second properties and crypto. Business Asset Disposal Relief (BADR) has a 14% rate on qualifying gains up to £1,000,000. Scotland has no power to vary CGT rates.",
                    "The annual exempt amount of £3,000 also applies identically across the UK. Gains below £3,000 in a tax year are free from CGT regardless of where the taxpayer lives. These UK-wide rules mean that, for CGT purposes, Scottish taxpayers follow the same rules as English taxpayers, the complication arises only in determining which rate (18% or 24%) applies, because that depends on the taxpayer's total income, and Scottish income tax rates differ from rUK.",
                ],
            },
            {
                "heading": "How Your Income Determines Your CGT Rate",
                "paragraphs": [
                    "CGT rates depend on how much of the basic-rate band remains after your other taxable income. The UK-wide basic-rate band runs from £12,570 (the Personal Allowance) to £50,270. Your salary, pension and other non-CGT income fills this band first. Any remaining space is then available to absorb taxable gains at 18%. Gains that exceed the remaining basic-rate band are charged at 24%.",
                    "For this calculation, HMRC uses the UK-wide basic-rate limit of £50,270, not the Scottish higher-rate threshold. This is important because the Scottish higher-rate band starts lower, at £43,662 for 2026/27. A Scottish taxpayer with £43,000 of salary is already in the Scottish higher-rate band for income tax purposes, but for CGT purposes they still have £7,270 of the UK basic-rate band remaining (£50,270 − £43,000). Gains up to £7,270 would be charged at 18%, and gains above that at 24%.",
                ],
            },
            {
                "heading": "Worked Example: Scottish Higher-Rate Taxpayer",
                "paragraphs": [
                    "Consider a Scottish employee with a salary of £48,000 and a gain of £20,000 from selling shares. For Scottish income tax, the salary puts this person in the Scottish higher-rate band (above £43,662). For CGT, the remaining UK basic-rate band is £50,270 − £48,000 = £2,270. After the annual exempt amount of £3,000, the taxable gain is £17,000.",
                    "The first £2,270 of the taxable gain is within the remaining basic-rate band: taxed at 18% = £409. The remaining £14,730 is in the higher-rate band: taxed at 24% = £3,535. Total CGT: approximately £3,944. If this taxpayer were in England with the same salary and gain, the calculation would be identical, because the UK-wide basic-rate limit of £50,270 applies in both cases.",
                ],
            },
            {
                "heading": "Planning Implications for Scottish Taxpayers",
                "paragraphs": [
                    "Because Scottish higher-rate income tax applies from a lower threshold (£43,662), Scottish higher-rate taxpayers have less basic-rate band available for CGT than English taxpayers at the same income level in the range £43,662–£50,270. A Scottish taxpayer with £46,000 of salary has £4,270 of basic-rate band for CGT, compared to an English taxpayer with the same salary who also has £4,270, the calculation is the same, showing CGT operates symmetrically.",
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
                    "The gain is calculated as sale proceeds minus allowable costs. Allowable costs include the purchase price, buying costs (solicitor fees, stamp duty, surveyor fees), any capital improvements (extensions, loft conversions, not maintenance or repairs), and selling costs (estate agent fees, solicitor fees). Costs of maintaining or decorating the property are not allowable for CGT purposes.",
                    "For example: a second home bought for £250,000 with £5,000 of purchase costs, £30,000 spent on an extension, and sold for £380,000 with £7,500 in selling costs. Gain = £380,000 − £250,000 − £5,000 − £30,000 − £7,500 = £87,500. After the £3,000 annual exempt amount: taxable gain = £84,500. For a higher-rate taxpayer (salary of £60,000), all of this would be charged at 24% = £20,280.",
                ],
            },
            {
                "heading": "The 60-Day Reporting Rule",
                "paragraphs": [
                    "If you sell a UK residential property and owe CGT, you must report the gain and pay an estimate of the tax within 60 days of the completion date. This is done through HMRC's online residential property disposal service, separate from the annual Self Assessment process. Failure to report within 60 days can result in a penalty and interest charges.",
                    "The 60-day rule applies to UK residential property only. Non-residential property gains and other asset gains (shares, crypto, etc.) are reported through Self Assessment as normal, by 31 January following the end of the tax year. If you have already paid CGT under the 60-day rule, you will reconcile this against your Self Assessment return, but you do not need to wait until January, the initial payment is due within 60 days of completion.",
                    "The 60-day clock starts from the completion date, not the exchange of contracts date. If you exchange in March and complete in April, the 60-day clock starts in April. A common mistake is assuming that reporting through Self Assessment before 31 January satisfies the obligation, it does not if the 60-day deadline has already passed.",
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
                    "The CGT rates for 2026/27 are 18% for gains within the basic-rate band and 24% for gains in the higher-rate band. The annual exempt amount of £3,000 applies in the same way as for shares or property. Income from crypto activities such as staking rewards, mining and airdrops may be treated as income rather than capital gain, HMRC's position is complex and depends on the facts of each case.",
                ],
            },
            {
                "heading": "The Section 104 Pooling Rules",
                "paragraphs": [
                    "HMRC applies the same share pooling rules (Section 104 TCGA 1992) to crypto that apply to shares. Each type of cryptocurrency is treated as a single pool. When you acquire the same type of crypto on different dates at different prices, the total cost is pooled and averaged. When you dispose of some of the pool, you use the averaged cost per unit to calculate the gain.",
                    "For example, if you bought 1 Bitcoin at £20,000 and then another at £30,000, your pool contains 2 Bitcoin at a total cost of £50,000, an average of £25,000 per Bitcoin. If you then sell 1 Bitcoin for £35,000, your gain is £35,000 − £25,000 = £10,000. The remaining Bitcoin in the pool has a cost of £25,000. Each type of crypto (Bitcoin, Ethereum, etc.) is treated as a separate pool.",
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
                    "The AEA applies to each individual separately. A married couple each have their own £3,000 AEA, giving a combined £6,000 of tax-free gains per year if both spouses make disposals. The AEA cannot be transferred between spouses, each person must use their own.",
                ],
            },
            {
                "heading": "Use It or Lose It",
                "paragraphs": [
                    "The AEA cannot be carried forward. Any unused AEA at 5 April is permanently lost. This means there is a real benefit in timing disposals to use the AEA each year rather than making all disposals in one year and wasting multiple years' worth of allowances. An investor planning to sell a large shareholding might split the sale across two tax years: sell some in March (before 5 April) and the remainder in April (after 5 April), using two years' worth of AEA.",
                    "Similarly, investors who have not made any gains in a tax year might consider whether to realise some growth before 5 April to use the AEA. This is known as bed and re-ISA, where you sell shares, use the AEA to reduce any gain, and then repurchase inside an ISA. This shelters future growth from CGT entirely. The repurchase inside the ISA can happen immediately, the 30-day rule that applies to direct repurchase in the same account does not apply to repurchases inside an ISA.",
                ],
            },
            {
                "heading": "Transferring Assets Between Spouses",
                "paragraphs": [
                    "Gifts between spouses and civil partners are made at no-gain/no-loss for CGT purposes. This means you can transfer an asset to your spouse without triggering a CGT event. The receiving spouse acquires the asset at your original cost. When they eventually sell the asset, they use their own AEA and pay CGT at their own marginal rate.",
                    "This strategy is most valuable when one spouse has a lower income and therefore pays CGT at 18% rather than 24%, and when one spouse has an unused AEA. If your spouse has made no gains this year and you are about to sell an asset with a £10,000 gain, transferring the asset to your spouse first means the £3,000 AEA shelters part of the gain and the remaining £7,000 may be taxed at 18% rather than 24%, a saving of £420 on that portion alone.",
                ],
            },
            {
                "heading": "Losses and the Annual Exempt Amount",
                "paragraphs": [
                    "Capital losses from the same tax year must be set against capital gains before the AEA is applied. This means if you have both gains and losses in a year, the losses reduce your gain first, and then the AEA applies to the net result. You cannot choose to carry forward current-year losses to preserve the AEA, they must be applied in the year they arise.",
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
                    "The bed-and-breakfast rule prevents investors from selling shares to crystallise a loss (or use the AEA) and then immediately repurchasing. If you sell 500 shares on 1 March and buy 500 of the same shares on 15 March (within 30 days), HMRC matches the sale against the new purchase, the pool average cost is not used. To avoid this, investors either wait more than 30 days to repurchase, buy the shares back inside an ISA (where the matching rule does not apply to ISA holdings), or switch to a similar but different fund in the interim.",
                ],
            },
            {
                "heading": "How the Section 104 Pool Works",
                "paragraphs": [
                    "The Section 104 pool treats all acquisitions of the same share or fund as one pool. Acquisitions add to the pool, increasing the total cost and the number of shares held. When shares are sold, you use the average cost per share from the pool to calculate the gain. This prevents investors from cherry-picking high-cost lots to minimise gains.",
                    "For example, suppose you buy 1,000 shares in a fund at £2.00 each (cost £2,000), then later buy another 500 at £3.00 each (cost £1,500). Your pool now contains 1,500 shares at a total cost of £3,500, an average of £2.33 per share. If you sell 500 shares at £4.00 each (proceeds £2,000), the gain is £2,000 − (500 × £2.33) = £2,000 − £1,167 = £833.",
                ],
            },
            {
                "heading": "ISA Exemption: No CGT on Shares Inside an ISA",
                "paragraphs": [
                    "Shares, funds and ETFs held inside a Stocks and Shares ISA are completely exempt from CGT (and dividend tax). The annual ISA subscription limit is £20,000 per person for 2026/27. Once money is inside the ISA wrapper, all future growth and income are tax-free, regardless of how large the gains become. There is no limit on the total ISA pot size, only on annual contributions.",
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
        "title": "Capital Gains Tax Rates 2026/27, Full Guide",
        "description": "A complete guide to CGT rates for 2026/27: all assets (shares, property, crypto) at 18% basic rate / 24% higher rate, £3,000 annual exempt amount, 60-day reporting rule and Business Asset Disposal Relief.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "The Two CGT Rate Structures",
                "paragraphs": [
                    "CGT in 2026/27 applies a single rate structure across all asset types. Residential property (second homes, buy-to-let, inherited property) and other assets (shares, funds, crypto, commercial property) are all taxed at 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. These unified rates have applied since the October 2024 Autumn Budget, when the previous lower rates for shares (10%/20%) were aligned with property. Business Asset Disposal Relief has its own reduced rate of 14% for qualifying gains up to £1,000,000 lifetime.",
                    "The rate that applies is determined by your income tax position, not a separate CGT calculation. Your other taxable income (salary, pension, rental income) fills the basic-rate band first, up to the £50,270 threshold. Any remaining basic-rate band space is then available to absorb your taxable gains at the lower rate. Gains above that remaining space are charged at the higher rate. This means a basic-rate taxpayer with a large gain will often find part of it taxed at the higher rate, gains stack on top of income.",
                    "The residential property rates of 18%/24% replaced the previous 18%/28% structure from 30 October 2024 onwards. For the 2026/27 tax year, all qualifying residential property disposals use the current 18%/24% rates throughout.",
                ],
            },
            {
                "heading": "The Annual Exempt Amount, £3,000",
                "paragraphs": [
                    "Every individual has an annual exempt amount (AEA) of £3,000 for 2026/27. Net gains below this threshold in a tax year are completely free from CGT. The AEA is applied after losses, so if you have £8,000 of gains and £3,000 of losses, your net gain is £5,000, and the £3,000 AEA reduces the taxable gain to £2,000.",
                    "The AEA cannot be carried forward to the next tax year. If you do not make any gains in 2026/27, the £3,000 allowance is simply lost. It also cannot be transferred to a spouse, each individual has their own separate allowance. However, married couples should consider whose name an asset is held in before selling, since whichever spouse makes the disposal uses their own AEA and pays CGT at their own rate. A lower-income spouse with unused AEA and a lower CGT rate can reduce the household's total tax bill significantly.",
                ],
            },
            {
                "heading": "The 60-Day Reporting Requirement for Residential Property",
                "paragraphs": [
                    "If you sell a UK residential property (not your main home, or one with only partial main home relief) and a CGT liability arises, you must report the gain and pay an estimate of the tax within 60 days of the completion date. This is done through HMRC's online UK property reporting service, it is separate from the annual Self Assessment process. The 60-day clock starts on the completion date, not the exchange date.",
                    "Failing to report within 60 days triggers a late filing penalty of £100 immediately, rising to £300 (or 5% of the tax due if higher) after 6 months, and a further £300 (or 5%) after 12 months. Daily penalties of £10 per day also apply after 3 months. If there is no CGT to pay, for example if the gain is within the AEA or fully covered by losses, no report is required. Non-UK resident individuals must report all UK residential property disposals through the same service, whether or not CGT is owed.",
                ],
            },
            {
                "heading": "Business Asset Disposal Relief",
                "paragraphs": [
                    "Business Asset Disposal Relief (BADR), previously known as Entrepreneurs' Relief, provides a reduced CGT rate of 10% on qualifying gains up to a lifetime limit of £1,000,000. For qualifying disposals on or after 6 April 2025, the BADR rate is 14% (it increased from 10% as announced in the October 2024 Budget). Check the applicable rate for your disposal date carefully.",
                    "To qualify for BADR, the most common route is shares in your personal trading company: you must hold at least 5% of the ordinary share capital and voting rights, the company must be a trading company (or the holding company of a trading group), and you must have held the shares for at least two years immediately before disposal. You must also have been an officer or employee of the company throughout that two-year period. The £1,000,000 lifetime limit is cumulative across all qualifying disposals throughout your life. Once used up, it is gone, there is no annual reset.",
                ],
            },
        ],
        "faqs": [
            {"q": "What are the CGT rates for 2026/27?", "a": "All assets (residential property, shares, crypto, etc.): 18% basic rate, 24% higher rate. Business Asset Disposal Relief: 14% on qualifying gains up to £1m lifetime limit. These rates have applied since the October 2024 Autumn Budget."},
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
                    "Private Residence Relief exempts the gain on your only or main residence from CGT. If you own one property and it has been your main home throughout your entire period of ownership, the full gain is exempt. You do not need to claim the relief, it applies automatically, and you are not required to report the disposal on a Self Assessment return.",
                    "The relief also covers the final 9 months of ownership, regardless of whether you are still living in the property. This grace period exists to help people who have moved out before completing the sale, for example after buying a new home and needing time to sell the old one. If you moved out 6 months before completion, those 6 months are still counted as a period of main residence. If you moved out 18 months before completion, only the last 9 months of that gap are covered; the other 9 months are potentially chargeable.",
                ],
            },
            {
                "heading": "Partial PRR, Let Property and Periods of Deemed Occupation",
                "paragraphs": [
                    "If you lived in the property for only part of your ownership period, PRR is apportioned. The exempt fraction is the proportion of time the property was your main residence (plus the final 9 months), divided by the total ownership period. Periods of absence can be treated as periods of occupation in certain circumstances, these are called deemed occupation periods. They include the last 9 months, any period working abroad for any length of time, and any period working elsewhere in the UK (up to 4 years), provided the property was your main residence before and after the absence.",
                    "Let Property Relief used to provide a further exemption for periods when the property was let while you were absent, but the rules changed significantly from April 2020. The relief now only applies in situations where the owner is in shared occupation with the tenant, a narrow set of circumstances that does not cover standard buy-to-let periods. For most people who have let their former main home, Let Property Relief is no longer available.",
                ],
            },
            {
                "heading": "When PRR Goes Wrong",
                "paragraphs": [
                    "Several situations can unexpectedly reduce or eliminate PRR. Using part of your home exclusively for business, a room used only as an office, not as a room that doubles as an office, means that portion of the gain does not qualify for PRR. The key word is exclusively: a room used sometimes for work and sometimes as a bedroom retains PRR, but a dedicated office that was never used as living space does not. This is a common trap for the self-employed.",
                    "Development land is another area where PRR can be challenged. If you sell your garden or grounds separately, or if the sale price reflects development potential rather than residential use, HMRC may argue that part of the gain relates to the development value rather than the residence itself. The interaction between PRR and development gains requires careful analysis. Similarly, converting a property from a main home to a buy-to-let before selling it creates a period of non-residence that is fully chargeable.",
                ],
            },
            {
                "heading": "PRR and Marriage, One Main Residence Per Couple",
                "paragraphs": [
                    "Married couples and civil partners can only nominate one property as their main residence for PRR purposes at any given time. If both spouses own separate properties, only one can be the couple's main residence, the same property applies to both of them. There is no ability for each spouse to separately claim PRR on different properties simultaneously.",
                    "The election process allows couples who own more than one property to nominate which one is treated as the main residence. The election must be made within two years of acquiring the second property. If no election is made, HMRC looks at the facts of occupation. For couples buying a second property, a holiday home, a property for a child, understanding this election and making it promptly is essential to preserve PRR on the intended main home.",
                ],
            },
        ],
        "faqs": [
            {"q": "Is my main home exempt from CGT?", "a": "Yes, in most cases. Private Residence Relief exempts the gain on your only or main home. The relief covers the period of occupation plus the final 9 months of ownership even after moving out."},
            {"q": "Do I get PRR if I let my home out?", "a": "Only for the period it was your actual main residence. Periods when it was let rather than occupied by you do not qualify for PRR (with narrow exceptions). Let Property Relief no longer applies to standard letting periods since April 2020."},
            {"q": "Can a married couple each claim PRR on different properties?", "a": "No. Married couples and civil partners share one main residence election, both spouses are bound by the same nominated main home."},
        ],
    },
    {
        "slug": "bed-and-isa-strategy",
        "title": "Bed and ISA, CGT Tax Planning Strategy",
        "description": "Bed and ISA is the strategy of selling investments outside an ISA and immediately rebuying them inside one. Future growth is then tax-free, and the sale uses your annual exempt amount.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "What Bed and ISA Means",
                "paragraphs": [
                    "Bed and ISA refers to selling shares or funds held in a general investment account (GIA) and immediately repurchasing the same or equivalent investments inside a Stocks and Shares ISA. The effect is to move holdings from a taxable environment into a tax-free wrapper. Once inside the ISA, all future growth, dividends and capital gains are permanently free from tax, there is no CGT on gains within an ISA, however large they become.",
                    "The term derives from the older 'bed and breakfast' strategy, where investors sold and repurchased outside any wrapper to crystallise a gain or loss. Bed and ISA is its successor, instead of repurchasing in the same account, the new holding goes into the ISA. This distinction is crucial for understanding how the tax rules apply.",
                ],
            },
            {
                "heading": "The CGT Implication of the 'Bed' Part",
                "paragraphs": [
                    "The sale itself, the 'bed', is a disposal for CGT purposes. If the investment has grown in value, you crystallise a capital gain at the point of sale. That gain uses up your annual exempt amount (£3,000 for 2026/27). If the gain exceeds £3,000, CGT is payable on the excess. If the investment has fallen in value, you crystallise a capital loss, which can offset gains elsewhere.",
                    "Ideally, bed and ISA is timed so that gains fall within the annual exempt amount, meaning no CGT arises. An investor with unrealised gains of £3,000 or less can execute the full transfer tax-free each year. Those with larger unrealised gains might split the bed and ISA across two tax years, selling some before 5 April and the rest after 6 April, to use two years' worth of the annual exempt amount.",
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
                    "The optimal time to execute is when your unrealised gain is close to (but does not exceed) your remaining annual exempt amount for the year, and when your ISA allowance has not yet been fully used. For a couple, both partners can execute bed and ISA in the same tax year, using their individual AEAs and ISA allowances, up to £40,000 combined can move into ISAs in a single year this way. Anyone with substantial GIA holdings should run the bed and ISA calculation every April as part of year-end tax planning.",
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
        "title": "Capital Losses, How to Offset Against Gains",
        "description": "Capital losses reduce your CGT bill, but the offset rules are not straightforward. Same-year losses, carried-forward losses, reporting requirements and the rules on connected-person sales, all covered here.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "7 min read",
        "sections": [
            {
                "heading": "The Offset Rules",
                "paragraphs": [
                    "Capital losses from the same tax year must be set against capital gains from that same year first, before the annual exempt amount is applied. You cannot choose to defer current-year losses, they must be deducted. If your losses exceed your gains in a year, the net loss is carried forward to future years.",
                    "Losses brought forward from earlier years are treated differently. They are only applied to the extent necessary to reduce the net gain to the annual exempt amount (£3,000 for 2026/27). So if you have £15,000 of gains and £20,000 of brought-forward losses, you do not apply all £20,000, you apply only £12,000 (to bring the net gain down to £3,000, which is then fully covered by the AEA and bears no CGT). The remaining £8,000 of brought-forward losses is preserved and carried forward again. This rule prevents losses from being wasted by being applied against gains that would have been exempt anyway.",
                ],
            },
            {
                "heading": "Reporting Losses",
                "paragraphs": [
                    "Capital losses are not automatically identified by HMRC. You must claim them, either on a Self Assessment tax return or by writing to HMRC if you are not within Self Assessment. The claim must be made within four years of the end of the tax year in which the loss arose. For a loss in 2022/23, the deadline to claim is 31 January 2027. Losses that are not claimed within the four-year window are permanently lost.",
                    "On a Self Assessment return, capital losses are reported in the Capital Gains pages (SA108). You enter both gains and losses for the year, and HMRC's calculation applies them in the correct order. Carried-forward losses from previous years must also be entered on the return each year they are used, even partially. Keep a running log of your brought-forward losses, it is easy to lose track across multiple tax years.",
                ],
            },
            {
                "heading": "Negligible Value Claims",
                "paragraphs": [
                    "If an asset has become effectively worthless, for example shares in a company that has gone into liquidation, but you have not yet formally disposed of them, you may be able to make a negligible value claim. This allows you to treat the asset as having been sold and immediately reacquired at the negligible value, crystallising a loss even though no actual sale has occurred. You can specify a date in the past (going back up to two prior tax years) for the deemed disposal, provided the asset was of negligible value at that date.",
                    "The claim is useful for extracting a loss from an investment that is stuck, either because the shares are in a suspended company, the asset has no buyer, or disposal is otherwise impractical. HMRC maintains a list of companies where negligible value claims have been accepted, which speeds up the process. For assets outside that list, you must demonstrate that the asset has no, or negligible, value at the claimed date.",
                ],
            },
            {
                "heading": "Selling at a Loss to a Connected Person",
                "paragraphs": [
                    "Sales to connected persons, which includes your spouse, civil partner, children, siblings, parents and companies you control, do not create allowable CGT losses. If you sell an asset to a connected person at a loss (whether at arm's length or at an undervalue), that loss is not deductible against other gains. It is a 'clogged' loss, which can only be set against gains arising on later transactions with the same connected person.",
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
        "title": "Transferring Assets Between Spouses, CGT Rules",
        "description": "Married couples and civil partners can transfer assets between themselves with no CGT charge. This guide covers the no-gain no-loss rule, its use in pre-sale planning, the year-of-separation trap and gifts to others.",
        "date_iso": "2026-05-26",
        "date": "May 2026",
        "reading_time": "6 min read",
        "sections": [
            {
                "heading": "No-Gain No-Loss Transfers",
                "paragraphs": [
                    "Transfers of assets between spouses and civil partners who are living together are treated as no-gain no-loss transactions for CGT purposes under TCGA 1992 s58. This means no CGT arises at the point of transfer, regardless of the asset's current market value. The receiving spouse acquires the asset at the transferring spouse's original acquisition cost (plus any capital improvements), not at its current value. The base cost carries over.",
                    "This rule applies automatically to all transfers between cohabiting spouses and civil partners, there is no election required and no form to file. It applies to all assets: shares, property, crypto, business interests. The rule does not apply to couples who are separated or who have permanently ceased living together, see the year-of-separation trap below.",
                ],
            },
            {
                "heading": "Why This Matters for Planning",
                "paragraphs": [
                    "The no-gain no-loss rule enables a straightforward and HMRC-compliant strategy: transfer an asset to the lower-income spouse before sale, so that the eventual gain is taxed at their lower CGT rate. A higher-rate taxpayer with a £50,000 gain on shares would pay CGT at 20%, giving a liability of approximately £9,400 after the AEA. If the same asset is transferred to a basic-rate taxpayer spouse before disposal, the same gain is taxed at 10%, a liability of approximately £4,700, a saving of £4,700.",
                    "The strategy works for the annual exempt amount too. If one spouse has already used their £3,000 AEA and the other has not, transferring an asset with a £3,000 gain to the unused-AEA spouse before sale means the gain is entirely tax-free. Over a lifetime of investing, using both spouses' AEAs systematically generates meaningful tax savings. The transfer must be a genuine and unconditional gift to the other spouse, it cannot be conditional on the sale proceeds being returned.",
                ],
            },
            {
                "heading": "The Year-of-Separation Trap",
                "paragraphs": [
                    "The no-gain no-loss rule only applies while spouses or civil partners are living together. For CGT purposes, 'living together' means not separated under a court order or separation agreement, and not in circumstances where the separation is likely to be permanent. Once a couple separates permanently, the rule ceases to apply, even if the divorce has not yet been finalised.",
                    "For tax years from 2023/24 onwards, there is an extended window: separating couples have until the end of the third tax year following the year of separation to transfer assets between themselves on a no-gain no-loss basis. This extended window was introduced to give divorcing couples more time to sort out financial settlements without tax charges arising. Before this change, the window closed at the end of the tax year of separation, often only weeks or months, creating urgent and poorly-timed disposals. The extended window significantly reduces pressure on separating couples to rush asset transfers.",
                ],
            },
            {
                "heading": "Gifts to Others, Deemed Proceeds Rule",
                "paragraphs": [
                    "The no-gain no-loss treatment is exclusive to spouses and civil partners. Gifts to anyone else, children, siblings, friends, cohabitees, trigger CGT at the asset's market value at the date of the gift, regardless of whether any money changes hands. This is the deemed proceeds rule: HMRC treats the gift as if you had sold the asset at open market value.",
                    "For example, gifting shares currently worth £30,000 that you originally bought for £10,000 creates a taxable gain of £20,000. The fact that you received nothing for them is irrelevant, CGT is calculated on the market value. Hold-Over Relief is available in limited circumstances for gifts of business assets, meaning the gain can be deferred until the recipient eventually sells. But for most assets, shares in listed companies, investment property, crypto, no hold-over is available, and the gift triggers an immediate CGT charge at market value.",
                ],
            },
        ],
        "faqs": [
            {"q": "Does transferring assets to my spouse trigger CGT?", "a": "No. Transfers between spouses and civil partners who are living together are no-gain no-loss, no CGT arises at the transfer. The receiving spouse takes the asset at the original acquisition cost."},
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
                    "Capital losses, whether from the current tax year or carried forward from earlier years, reduce taxable gains. If you have loss-making holdings that you intend to dispose of eventually, selling them in the same tax year as a large gain can significantly reduce or eliminate the CGT bill. Losses must be reported to HMRC (through Self Assessment) to be officially recognised, HMRC will not automatically discover and apply losses.",
                    "Brought-forward losses from previous years are applied to the extent needed to bring the net gain down to the annual exempt amount. Any excess losses are carried forward again. There is no time limit on carrying forward capital losses, so losses from many years ago remain available indefinitely, provided they were reported when they arose.",
                ],
            },
            {
                "heading": "Transfer Assets to a Lower-Rate Spouse",
                "paragraphs": [
                    "Gifts between spouses and civil partners are at no-gain/no-loss for CGT purposes. If you are a higher-rate taxpayer (CGT at 24%) and your spouse is a basic-rate taxpayer (CGT at 18%) or has unused AEA, transferring the asset before disposal can save up to 6% of the gain. On a £50,000 gain, that is a saving of £3,000.",
                    "The transfer is a genuine gift, the asset must belong to the recipient spouse outright, not just temporarily for tax purposes. HMRC's settlements legislation (section 620 ITTOIA 2005) can apply if the arrangement is primarily tax-motivated and the transferring spouse retains benefits from the asset. For straightforward transfers of investment portfolios or property between genuinely jointly-managing spouses, the strategy is well-established and HMRC-compliant.",
                ],
            },
            {
                "heading": "Use ISAs and Pensions to Shelter Future Gains",
                "paragraphs": [
                    "ISAs provide complete CGT (and income tax) exemption. The £20,000 annual subscription limit means it takes time to move large portfolios inside an ISA, but the tax-free compounding effect is substantial over time. Pensions provide a similar shelter, assets inside a pension grow free of CGT. The pension annual allowance is £60,000 for 2026/27 (with carry-forward available for the previous three years), making pensions a powerful tool for those with business sale proceeds or large property gains.",
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
    {
        "slug": "divorce-capital-gains-tax",
        "title": "Capital Gains Tax and Divorce UK 2026/27 | CGT on Marital Assets",
        "description": "CGT rules change significantly on separation and divorce. Spousal transfers are exempt, but gains on assets sold or transferred after the tax year of separation can trigger CGT at 18% or 24%. This guide explains what to watch for.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "The Key Rule: Tax Year of Separation",
                "paragraphs": [
                    "The CGT treatment of asset transfers between spouses and civil partners depends critically on timing. While a couple are living together (treated as living together for tax purposes), any transfer of assets between them happens at no gain and no loss, effectively at the original cost, so no CGT arises. This exemption continues until the end of the tax year (5 April) in which the couple permanently separated.",
                    "From 6 April of the tax year after separation, the no-gain no-loss rule no longer applies to new transfers. Any asset transferred from one spouse to the other from that point is treated as a disposal at market value for CGT purposes. If the asset has risen in value since it was acquired, the transferring spouse may have a CGT liability. This rule creates a time pressure: couples who separate late in a tax year have very little time to complete asset transfers under the old beneficial rules.",
                    "For divorces completing from 6 April 2023 onwards, the rules changed significantly. Under the Divorce, Dissolution and Separation Act 2020 reforms to CGT (effective April 2023), the no-gain no-loss window was extended. Separating spouses now have up to three years from the end of the tax year of separation to transfer assets under no-gain no-loss. For assets transferred as part of a formal divorce settlement (court order), there is no time limit, the no-gain no-loss treatment applies regardless of how long after separation the transfer occurs.",
                ],
            },
            {
                "heading": "The Former Marital Home, Private Residence Relief",
                "paragraphs": [
                    "The former matrimonial home is often the most valuable asset in a divorce. If the property was the main residence of both spouses throughout ownership, Private Residence Relief (PRR) normally exempts the gain in full. The final 9 months of ownership also count as a period of main residence, even if the departing spouse has already moved out.",
                    "Problems arise when the gap between leaving the property and completing the sale exceeds 9 months. If you moved out 18 months before the sale completed, only the last 9 months are protected by the final-period rule, the 9-month gap before that is potentially chargeable. For divorces involving a lengthy sale process, this can create unexpected CGT for the departing spouse.",
                    "From April 2020, a specific PRR extension applies to divorcing couples: if one spouse transfers their share of the home to the other as part of the divorce settlement, the departing spouse retains eligibility for PRR on their share as long as the receiving spouse continues to use it as their main home. This is called a deferred disposal election and must be made formally. Without it, the departing spouse's PRR ends at the time of transfer.",
                ],
            },
            {
                "heading": "Calculating CGT on a Jointly Owned Property Sale After Divorce",
                "paragraphs": [
                    "When the matrimonial home is sold after divorce (rather than transferred to one spouse), each party computes their own CGT based on their share of the gain. The gain is split 50/50 for jointly owned property unless ownership is documented differently. Each person applies their own annual exempt amount (£3,000 for 2026/27) and their own income to determine the rate.",
                    "For example: a couple bought a second property in 2015 for £200,000 and sell it in 2026/27 for £320,000. After selling costs of £5,000, the total gain is £115,000. Each spouse has a £57,500 share of the gain. After the £3,000 annual exempt amount, each has a taxable gain of £54,500. A higher-rate taxpayer would owe 24% × £54,500 = £13,080. A basic-rate taxpayer with £40,000 of salary has £10,270 of remaining basic-rate band (£50,270 − £40,000). The first £10,270 is taxed at 18% = £1,849; the remaining £44,230 at 24% = £10,615, total £12,464.",
                ],
            },
            {
                "heading": "Shares and Other Investments in Divorce Settlements",
                "paragraphs": [
                    "Share portfolios and other investments transferred as part of a divorce settlement benefit from the same extended no-gain no-loss window (three years from the end of the year of separation, or indefinitely if under a court order). The receiving spouse takes over the original cost base, they inherit the history of the asset.",
                    "This means the receiving spouse could face a significant latent CGT liability on assets transferred to them. A share portfolio worth £80,000 that cost £30,000 carries an embedded gain of £50,000. If transferred at no gain/no loss, the receiving spouse takes over the £30,000 cost, they will pay CGT on the full £50,000 (plus any further growth) when they eventually sell. Both parties should consider this embedded liability when negotiating the division of assets.",
                    "Rates for 2026/27: shares and most other assets are taxed at 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. The same rates apply to residential property (other than your main home).",
                ],
            },
        ],
        "faqs": [
            {"q": "Is there CGT when transferring assets to my spouse during divorce?", "a": "If the transfer is made in the tax year of separation or within three years of separation (or under a court order, indefinitely), it happens at no gain no loss, no CGT arises. After that window, the transfer is at market value and may trigger CGT."},
            {"q": "What happens to CGT on the family home when we divorce?", "a": "If the home was your main residence throughout, Private Residence Relief (PRR) normally exempts the full gain. If you moved out more than 9 months before the sale, you may have a partial CGT liability on your share. A deferred disposal election can preserve your PRR if your spouse stays in the property."},
            {"q": "What CGT rate applies to divorce asset transfers in 2026/27?", "a": "For shares and property (other than main home): 18% if the gain falls in the basic-rate band, 24% in the higher-rate band. Annual exempt amount is £3,000 per person."},
        ],
    },
    {
        "slug": "capital-gains-tax-on-property-uk-2026",
        "title": "Capital Gains Tax on Property UK 2026/27: The Complete Guide",
        "description": "Second homes, buy-to-let and inherited property are all subject to CGT at 18% or 24% in 2026/27. This guide covers the rates, allowable costs, the 60-day reporting rule, Private Residence Relief and planning strategies.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "12 min read",
        "sections": [
            {
                "heading": "Which Properties Are Subject to CGT?",
                "paragraphs": [
                    "Capital gains tax applies when you dispose of a UK property that is not your only or main home. This includes second homes and holiday properties, buy-to-let properties, inherited properties (where the gain is measured from the probate value), commercial property, land, and any property where only partial Private Residence Relief (PRR) applies. The disposal does not have to be a sale, gifting a property, transferring it to a company, or exchanging it can all trigger a CGT event.",
                    "Your main home is normally exempt from CGT through Private Residence Relief, which covers the full gain where you have lived in the property throughout your ownership. The final 9 months of ownership always count as a period of main residence, even if you have moved out. PRR can apply partially where the property was your main home for only part of the ownership period. A property that was never your main home, a pure investment property, has no PRR available.",
                    "Non-UK resident individuals who own UK residential property must report all disposals through HMRC's non-resident CGT service, whether or not tax is owed. This applies regardless of whether the property was their main residence.",
                ],
            },
            {
                "heading": "CGT Rates on Residential Property 2026/27",
                "paragraphs": [
                    "Since the Autumn Budget of 30 October 2024, all residential property gains use the same rate structure as other assets: 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. Before October 2024, the higher-rate on property was 28%, the reduction to 24% was a significant change that applies to all disposals from 30 October 2024 onwards.",
                    "The rate that applies to your gain depends on how much of the basic-rate band remains after your other taxable income is accounted for. The basic-rate band runs from £12,570 (the personal allowance) to £50,270 (the higher-rate threshold). Your salary, pension and rental income fill this band first. Whatever gap remains up to £50,270 is available to absorb your property gain at 18%. Any gain that pushes beyond £50,270 is taxed at 24%.",
                    "Example: you have a salary of £38,000 and a property gain (after annual exempt amount) of £60,000. Your taxable income is £25,430 (£38,000 minus £12,570). The remaining basic-rate band is £37,700 minus £25,430 = £12,270. The first £12,270 of the property gain is taxed at 18% (£2,209). The remaining £47,730 is taxed at 24% (£11,455). Total CGT: £13,664.",
                ],
            },
            {
                "heading": "Calculating the Gain: Allowable Costs",
                "paragraphs": [
                    "The CGT gain is the sale proceeds minus the allowable costs. Allowable costs include the original purchase price, buying costs (stamp duty land tax, solicitor fees, surveyor fees), improvement expenditure (capital works such as extensions, loft conversions, new kitchens that enhance the property, not repairs or maintenance), and selling costs (estate agent commission, solicitor fees, advertising costs). These costs must be evidenced with receipts or invoices.",
                    "Repairs and decoration are not allowable costs. Replacing a kitchen like-for-like is generally a repair; upgrading to a higher-specification kitchen may qualify as improvement expenditure. The distinction matters: every £1,000 of improvement correctly included reduces the gain by £1,000 and saves up to £240 in CGT. Many landlords and second homeowners underestimate their allowable improvement costs, overpaying CGT as a result.",
                    "For an inherited property, the purchase price is replaced by the probate value, the open market value of the property at the date of death. If the property has fallen in value since the date of death (which is possible in a falling market), you may have a capital loss rather than a gain. If it has risen, the gain is measured from the probate value, not what the deceased paid for it originally.",
                ],
            },
            {
                "heading": "The Annual Exempt Amount",
                "paragraphs": [
                    "The annual exempt amount for 2026/27 is £3,000 per individual. This means the first £3,000 of net gains in the tax year is free from CGT. The AEA is applied after losses. If you have already used part of the AEA on other disposals earlier in the year, only the remaining balance is available against the property gain.",
                    "A married couple each have their own £3,000 AEA. If a property is jointly owned 50/50, each spouse's share of the gain can be reduced by their individual AEA, a combined £6,000 tax-free. For properties held in unequal shares, the gain is apportioned accordingly. Transferring a share of the property to a spouse before sale (no-gain/no-loss transfer) can optimise the use of both allowances and potentially access a lower rate if one spouse has lower income.",
                ],
            },
            {
                "heading": "The 60-Day Reporting Rule",
                "paragraphs": [
                    "If you sell a UK residential property and a CGT liability arises, you must report the gain and pay an estimate of the CGT within 60 days of the completion date. This is done through HMRC's online UK property reporting service (https://www.gov.uk/report-and-pay-your-capital-gains-tax). This is separate from Self Assessment and must be done regardless of whether you complete a Self Assessment return. The 60-day clock starts on the completion date, not exchange of contracts.",
                    "If there is no CGT to pay (because the gain is within the AEA, covered by losses, or fully relieved by PRR), no 60-day report is required. If CGT is owed and you fail to report within 60 days, you face an automatic £100 penalty. This rises to £300 after 6 months and a further £300 after 12 months, plus interest on the unpaid tax. Late reporting is one of HMRC's most common CGT enforcement areas for property.",
                    "When you complete your Self Assessment return for the year, you reconcile the provisional 60-day payment against your final CGT calculation. If your provisional payment was too much (because you estimated income incorrectly), HMRC will repay the difference. If it was too little, you pay the shortfall through Self Assessment.",
                ],
            },
            {
                "heading": "Private Residence Relief, When Your Home Is Also an Investment",
                "paragraphs": [
                    "Where a property has been both your main home and an investment property at different points during ownership, PRR applies proportionately. The exempt fraction is the number of months the property was your main home (plus any final 9-month period), divided by the total months of ownership. The gain attributable to the non-main-home period is fully chargeable to CGT.",
                    "Deemed occupation periods can also increase the PRR fraction. If you worked abroad or worked elsewhere in the UK (up to 4 years in the UK) and used the property as your main home before and after those periods, those absences may count as deemed occupation. The rules are detailed, HMRC's residence relief guidance in CG64300 onwards covers the conditions.",
                    "From April 2020, Lettings Relief, which previously reduced the gain on a former main home that had been let, was significantly restricted. It now only applies when the owner is in shared occupation with the tenant. For most landlords who used to live in a property before renting it out, Lettings Relief no longer applies.",
                ],
            },
            {
                "heading": "Planning Strategies Before Sale",
                "paragraphs": [
                    "Transfer to a lower-income spouse before sale: If you own a property solely and your spouse or civil partner has a lower income (meaning more basic-rate band remains), transferring the property to them before sale is a no-gain/no-loss transaction. The gain is then assessed at their lower CGT rate. On a £100,000 gain, the difference between 18% and 24% is £6,000, a material saving. The transfer must be a genuine gift, and the property must actually belong to the receiving spouse.",
                    "Spread gain across tax years: If the property can be sold in tranches (unusual for residential property but possible for land), spreading the disposal across 5 April can use two years of annual exempt amounts. More commonly, if you have other assets with gains or losses, timing their disposal in the same year as the property sale can optimise the overall CGT position.",
                    "Pension contributions: Additional pension contributions in the year of sale reduce your taxable income, which creates more basic-rate band headroom for the property gain to fall at 18% rather than 24%. A £10,000 additional pension contribution by a higher-rate taxpayer saves £400 in income tax relief and can shift £10,000 of property gain from 24% to 18%, saving another £600 in CGT, for a combined saving of £1,000.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the CGT rate on property in 2026/27?", "a": "18% for gains within the basic-rate band and 24% for gains above it. These rates apply to second homes, buy-to-let and inherited property. They have applied since October 2024, replacing the previous 28% higher rate."},
            {"q": "Do I pay CGT when selling my main home?", "a": "Usually no. Private Residence Relief exempts the full gain if the property was your only or main home throughout ownership. PRR is proportionate if you only lived there for part of the ownership period."},
            {"q": "How long do I have to report a property gain to HMRC?", "a": "60 days from the completion date. Use HMRC's online UK property reporting service. Failure to report within 60 days results in an automatic £100 penalty and interest on the tax owed."},
            {"q": "Can I deduct stamp duty from my CGT gain?", "a": "Yes. Stamp duty paid on purchase is an allowable acquisition cost and reduces your CGT gain."},
            {"q": "What counts as improvement expenditure?", "a": "Capital works that enhance the property: extensions, loft conversions, adding a bathroom, a new garage. Normal maintenance and redecoration are not allowable improvement costs."},
        ],
    },
    {
        "slug": "capital-gains-tax-allowance-explained",
        "title": "The £3,000 CGT Allowance 2026/27: What It Is and How to Use It",
        "description": "The capital gains tax annual exempt amount was cut from £12,300 to £3,000 in 2024. This guide explains what it means, how it has changed, and the planning strategies to make the most of your remaining allowance.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "8 min read",
        "sections": [
            {
                "heading": "What Is the Annual Exempt Amount?",
                "paragraphs": [
                    "The annual exempt amount (AEA), also called the CGT allowance, annual CGT allowance or personal CGT exemption, is the amount of capital gains an individual can make in a tax year without paying any capital gains tax. For 2026/27, the AEA is £3,000. Net capital gains below this threshold in a tax year are completely free from CGT. The AEA applies after capital losses have been deducted from gains.",
                    "The AEA applies to each individual separately. A married couple or civil partnership has a combined AEA of £6,000 if both spouses make disposals (two lots of £3,000). Trusts typically receive a lower AEA of £1,500 for 2026/27, except for certain trusts for disabled persons which receive the full £3,000.",
                    "The AEA is use-it-or-lose-it within a tax year. Any unused AEA at 5 April is permanently lost, it cannot be carried forward to the next year or transferred to a spouse. This makes annual CGT planning important for anyone with investments or properties that have grown in value.",
                ],
            },
            {
                "heading": "The History of the AEA Cuts",
                "paragraphs": [
                    "The dramatic reduction in the AEA is one of the most significant CGT changes in decades. The AEA stood at £12,300 for 2022/23 and had been at broadly that level (rising with inflation) for many years. In the Autumn Statement of November 2022, the government announced it would be cut to £6,000 for 2023/24 and £3,000 from 2024/25 onwards, a 76% reduction in just two years.",
                    "This means that millions of investors, landlords and business owners who previously owed no CGT (because their annual gains were within the allowance) now face CGT bills for the first time. An investor with £10,000 of gains annually would have paid no CGT in 2022/23, but now pays CGT on £7,000 of that gain, £1,260 at 18% or £1,680 at 24%.",
                    "The stated rationale was to increase tax revenue and reduce the incentive for income to be structured as capital gains (which historically were taxed more lightly than income). The practical effect is that more people are now caught by CGT for the first time, and existing CGT payers face substantially higher bills.",
                ],
            },
            {
                "heading": "How the AEA Interacts with Losses",
                "paragraphs": [
                    "Current-year losses must be deducted from current-year gains before the AEA is applied. You cannot choose to carry forward a current-year loss to preserve the AEA, losses are applied compulsorily in the year they arise. If you have gains of £8,000 and losses of £4,000 in the same year, the net gain is £4,000, and the £3,000 AEA reduces the taxable gain to £1,000.",
                    "Brought-forward losses from earlier years are applied differently. They are only applied to the extent necessary to bring the net gain down to the AEA. So if you have £10,000 of gains and £20,000 of brought-forward losses, you only apply £7,000 of the losses (to reduce the gain to £3,000, which is sheltered by the AEA). The remaining £13,000 of losses is preserved and carried forward again. This rule is important: it prevents brought-forward losses from being wasted against gains that would have been exempt anyway.",
                ],
            },
            {
                "heading": "Strategies to Make the Most of the £3,000 AEA",
                "paragraphs": [
                    "Annual crystallisation, review your portfolio before 5 April each year and consider realising gains up to £3,000. Even if you intend to keep holding the investment, you can sell and immediately repurchase inside an ISA (bed-and-ISA), which upgrades the holding to tax-free status without triggering the 30-day same-account rule. Over many years, this systematic migration of GIA holdings into the ISA wrapper is highly valuable.",
                    "Spousal use, if one spouse has not used their AEA and the other has already used theirs, transferring an asset with a gain to the unused-AEA spouse and having them sell it allows both AEAs to be used in the same year. Transfers between spouses are no-gain/no-loss, so no CGT arises on the transfer itself. Over a lifetime, this can shelter an additional £3,000 of gains per year per couple.",
                    "Timing disposals around the year-end, if you are planning to sell assets with total gains of, say, £8,000, selling half before 5 April and half after 6 April uses two years' worth of AEA (£6,000) instead of one. This simple timing adjustment saves £900 for a basic-rate taxpayer (£3,000 × 18% × 2 transactions) or £1,440 for a higher-rate taxpayer.",
                ],
            },
            {
                "heading": "The AEA and ISAs",
                "paragraphs": [
                    "Assets inside a Stocks and Shares ISA are completely exempt from CGT, there is no annual limit on the gains they can make. This makes ISAs the most powerful long-term tool for eliminating CGT entirely. The annual ISA subscription limit is £20,000 for 2026/27. The key strategy is to prioritise holding your highest-growth assets inside an ISA, where future gains will never be taxed.",
                    "The bed-and-ISA technique (selling in a general account, using the AEA to shelter the gain, and immediately repurchasing inside the ISA) progressively transfers holdings from a taxable environment to a tax-free one. The repurchase can happen on the same day because the ISA holding is legally distinct, the 30-day anti-avoidance rule does not apply to purchases inside an ISA. HMRC confirms this in the Capital Gains manual at CG42562.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the capital gains tax allowance for 2026/27?", "a": "£3,000 per individual. This is the net amount of capital gains you can make in a tax year before any CGT is owed. It applies after losses are deducted."},
            {"q": "Has the CGT allowance been reduced?", "a": "Yes, significantly. The AEA was £12,300 in 2022/23, cut to £6,000 in 2023/24, and reduced to £3,000 from 2024/25, a 76% cut. It remains at £3,000 for 2026/27."},
            {"q": "Can I carry forward an unused CGT allowance?", "a": "No. The annual exempt amount is use-it-or-lose-it. Any unused allowance at 5 April is permanently lost."},
            {"q": "Does each spouse have a separate CGT allowance?", "a": "Yes. Each individual has their own £3,000 AEA, giving a couple £6,000 combined if both make disposals."},
        ],
    },
    {
        "slug": "how-to-calculate-capital-gains-tax-on-shares",
        "title": "How to Calculate Capital Gains Tax on Shares UK 2026/27",
        "description": "Step-by-step guide to calculating CGT on shares in 2026/27, including S104 pool averaging, worked examples for basic and higher-rate taxpayers, bed-and-breakfast rules and ISA exemptions.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "9 min read",
        "sections": [
            {
                "heading": "The 2026/27 Rates: 18% and 24%",
                "paragraphs": [
                    "Capital gains on shares held outside an ISA or pension are subject to CGT in 2026/27 at 18% for gains within the basic-rate band and 24% for gains in the higher or additional-rate band. These rates changed in October 2024 (Autumn Budget): the previous rates for shares were 10% and 20%. Both shares and residential property now use the same 18%/24% rate structure.",
                    "The annual exempt amount is £3,000 for 2026/27. You subtract this from your total net gains before applying the CGT rate. Gains below £3,000 in the tax year are completely free from CGT. The rate you pay depends on how much of the basic-rate band (up to £50,270) remains after your salary and other income.",
                ],
            },
            {
                "heading": "Step 1: Calculate the Gain Using the S104 Pool",
                "paragraphs": [
                    "When you sell shares, you cannot pick which specific shares you are selling. HMRC uses the Section 104 (S104) pool rule: all acquisitions of the same share are pooled together, and you use the average cost per share when calculating the gain.",
                    "Example: You bought 1,000 shares in a company at £2.00 each in 2019 (cost: £2,000), then bought another 500 shares at £3.50 each in 2022 (cost: £1,750). Your S104 pool now contains 1,500 shares with a total cost of £3,750, an average of £2.50 per share. In 2026/27, you sell all 1,500 shares at £5.00 each (proceeds: £7,500). Your gain is £7,500 minus £3,750 = £3,750. After the £3,000 annual exempt amount, your taxable gain is £750.",
                ],
            },
            {
                "heading": "Step 2: Apply the Annual Exempt Amount",
                "paragraphs": [
                    "Continuing the example above: taxable gain = £3,750 − £3,000 = £750. If you have capital losses from other disposals in the same tax year, these are applied first (before the annual exempt amount). If you have carried-forward losses from previous years, they reduce the gain only to the extent needed to bring it down to the annual exempt amount, so carried-forward losses do not 'waste' the AEA.",
                ],
            },
            {
                "heading": "Step 3: Work Out Your CGT Rate",
                "paragraphs": [
                    "Your CGT rate depends on how much basic-rate band remains after your other income. The basic-rate band runs from £12,570 (personal allowance) to £50,270. Your salary, pension and other taxable income fills this band first. Whatever gap remains up to £50,270 is available to absorb your taxable gains at 18%; gains above that are taxed at 24%.",
                    "Worked example, basic-rate taxpayer: Taxable income (salary) = £30,000. Remaining basic-rate band = £50,270 − £30,000 = £20,270. Taxable gain (from above) = £750. Since £750 < £20,270, the entire gain is within the basic-rate band: CGT = £750 × 18% = £135.",
                    "Worked example, higher-rate taxpayer: Same gain of £750, but salary = £60,000 (above the basic-rate threshold). No basic-rate band remains. CGT = £750 × 24% = £180.",
                ],
            },
            {
                "heading": "Worked Example: Larger Gain Straddling Both Rates",
                "paragraphs": [
                    "Buy 1,000 shares at £2.00 (cost £2,000). Sell all 1,000 at £30.00 (proceeds £30,000). No other disposals in the year. Gain = £30,000 − £2,000 = £28,000. After AEA: taxable gain = £28,000 − £3,000 = £25,000.",
                    "Taxpayer has salary of £40,000. Remaining basic-rate band = £50,270 − £40,000 = £10,270. First £10,270 of gain at 18% = £1,849. Remaining £14,730 at 24% = £3,535. Total CGT = £5,384.",
                    "For a higher-rate taxpayer (salary £60,000), the full £25,000 taxable gain would be at 24%: CGT = £6,000. The difference illustrates why income level matters, the same gain costs significantly more for a higher-rate taxpayer.",
                ],
            },
            {
                "heading": "The Bed-and-Breakfast Rule, 30-Day Matching",
                "paragraphs": [
                    "HMRC's bed-and-breakfast rule (Section 106A TCGA 1992) exists to prevent investors from selling shares to crystallise a gain or loss, then immediately repurchasing the same shares. If you sell shares and buy the same shares within 30 days, HMRC matches the sale against the new purchase, the S104 pool average is not used. The gain or loss is calculated using the cost of the shares repurchased, not the pool average.",
                    "To crystallise a real gain or loss, you either: wait more than 30 days to repurchase; buy back inside an ISA (where the rule does not apply to the ISA holding); or switch to a similar but legally different investment (e.g. a different fund tracking the same index) in the interim.",
                ],
            },
            {
                "heading": "ISA Exemption, No CGT on Shares Inside an ISA",
                "paragraphs": [
                    "Shares, funds and ETFs held inside a Stocks and Shares ISA are completely exempt from CGT. The annual ISA subscription limit is £20,000 per person for 2026/27. Once assets are inside the ISA wrapper, all future gains are permanently free from CGT, however large they grow.",
                    "The bed-and-ISA strategy (sell in the general account, use the annual exempt amount, repurchase inside the ISA) is the standard method for migrating existing holdings into the tax-free wrapper. Because the repurchase is inside an ISA, the 30-day same-account rule does not apply, you can sell and rebuy in the same day.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the CGT rate on shares in 2026/27?", "a": "18% for gains within the basic-rate band (income up to £50,270) and 24% for gains in the higher-rate band (income above £50,270). These rates changed from 10%/20% in October 2024."},
            {"q": "How do I calculate CGT if I bought shares at different prices?", "a": "You use the Section 104 pool: add up all acquisitions of the same share to get a total cost and total number of shares. Divide to get the average cost per share. Your gain = proceeds minus (shares sold × average cost)."},
            {"q": "Do I pay CGT on shares inside an ISA?", "a": "No. There is no CGT on any gains inside a Stocks and Shares ISA, regardless of how large the gains become."},
            {"q": "What is the annual exempt amount for shares CGT in 2026/27?", "a": "£3,000 per individual. Gains below £3,000 in the tax year are free from CGT. It cannot be carried forward or transferred to a spouse."},
        ],
    },
    {
        "slug": "entrepreneurs-relief-badr-2026",
        "title": "Business Asset Disposal Relief 2026/27: Qualifying Conditions, 14% Rate and Planning",
        "description": "BADR (formerly Entrepreneurs' Relief) provides a 14% CGT rate on qualifying business gains up to £1m lifetime. This guide covers the qualifying conditions, what can go wrong and planning for business owners.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "10 min read",
        "sections": [
            {
                "heading": "What Is Business Asset Disposal Relief?",
                "paragraphs": [
                    "Business Asset Disposal Relief (BADR), previously known as Entrepreneurs' Relief until April 2020, is a CGT relief that reduces the rate of tax on qualifying gains from business disposals. For disposals on or after 6 April 2025, the BADR rate is 14%, it was 10% from 2020 to October 2024, increased to 14% from 30 October 2024 onwards. Without BADR, a higher-rate taxpayer would pay 24% on the same gain. On a £500,000 qualifying gain, BADR saves £50,000 in CGT.",
                    "BADR applies to a lifetime limit of £1,000,000 of qualifying gains per individual. This limit applies across all qualifying disposals throughout your entire life, it is not reset annually. Once the £1 million limit is exhausted, any further gains from business disposals are taxed at the standard rates of 18% or 24%. The limit was reduced from £10 million to £1 million in April 2020.",
                    "The relief applies to disposals of shares in a qualifying personal company, business assets used in a sole trade or partnership, and the disposal of a business or part of a business. The most common route in practice is the disposal of shares in a company that the individual works in and owns at least 5% of.",
                ],
            },
            {
                "heading": "Qualifying Conditions for Shares in a Personal Company",
                "paragraphs": [
                    "To claim BADR on shares in a personal trading company, all of the following conditions must be met throughout the two years immediately before the date of disposal: you must hold at least 5% of the ordinary share capital of the company; those shares must carry at least 5% of the voting rights; you must be an officer (director) or employee of the company; the company must be a trading company or the holding company of a trading group (not an investment company); and you must be entitled to at least 5% of the company's distributable profits and assets on winding up.",
                    "The two-year qualifying period is strict. If you set up a company and sell it 18 months later, BADR is not available on the sale. If the company was set up more than two years ago but you only became a director 18 months ago, BADR may not be available. The qualifying period is measured up to the date of disposal, if you sell your shares by agreement and they are purchased on completion, the qualifying period must run up to completion.",
                    "The trading condition requires the company's activities to be substantially trading, broadly, at least 80% of the company's activities (by reference to assets, income and time) should be trading rather than investment activities. A company that holds significant investment property or large cash balances may fail the trading test, even if it also has active trading operations. This is an area where professional advice is essential before disposal.",
                ],
            },
            {
                "heading": "Dilution Risk, Protecting the 5% Threshold",
                "paragraphs": [
                    "One of the most significant risks to BADR eligibility is dilution below the 5% shareholding threshold. This commonly arises when a company raises external investment, an employee share scheme, a SEIS/EIS funding round, or a strategic investor taking shares. If a new share issue dilutes your holding from 7% to 4%, you immediately lose BADR eligibility on any future gain.",
                    "HMRC provides a valuable anti-dilution protection: where your shares were diluted below 5% due to a qualifying share issue (broadly, a commercial share issue not designed to dilute CGT reliefs), you can make an election to treat your shares as disposed of and immediately reacquired at market value at the point your holding fell below 5%. This crystallises a gain while BADR still applies, at the pre-dilution value. The election must be made within the normal Self Assessment time limits. Planning ahead of a funding round, quantifying the gain and making the election promptly, is essential for business owners facing dilution.",
                ],
            },
            {
                "heading": "Worked Example: BADR vs Standard CGT Rates",
                "paragraphs": [
                    "James founded a technology consultancy in 2018, owning 60% of the shares throughout. In 2026/27 he sells his shares for £800,000. His acquisition cost was £10,000. Gain = £790,000. He has used £200,000 of BADR lifetime limit previously. Remaining BADR limit: £800,000. But the gain is only £790,000, so all of it qualifies for BADR (it does not exceed the remaining £800,000 limit).",
                    "CGT with BADR: £790,000 × 14% = £110,600. His income for the year is £80,000, putting him in the higher-rate band. Without BADR, the CGT would be £790,000 − £3,000 (AEA) = £787,000 × 24% = £188,880. The BADR saving: £188,880 − £110,600 = £78,280. Note that BADR gains are not reduced by the AEA, the AEA is not applied against BADR gains separately.",
                    "Important: BADR is claimed through Self Assessment, in the year the disposal occurs. You make the claim on the Capital Gains pages (SA108). If you fail to make the claim in the relevant tax year's return (within the amendment window, usually four years), the relief is permanently lost.",
                ],
            },
            {
                "heading": "Investor's Relief, BADR for External Investors",
                "paragraphs": [
                    "A related relief called Investors' Relief provides a 14% CGT rate on gains from shares in unlisted trading companies for external investors who are not employees or directors of the company. The conditions are different from BADR: the shares must have been subscribed for (not acquired from another shareholder), held for at least three years from 6 April 2016, and must be in an unlisted trading company. The lifetime limit for Investors' Relief is separate from BADR, also £1,000,000.",
                    "Investors' Relief is less commonly used than BADR but valuable for angel investors and seed investors who have held qualifying shares since 2016 or later. The three-year minimum holding period and the requirement that shares were originally subscribed for (not purchased) limits the scope, but for those who qualify, the rate saving versus the standard 24% is substantial.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the BADR rate for 2026/27?", "a": "14%. This rate applies to qualifying gains up to the £1 million lifetime limit. It increased from 10% in October 2024."},
            {"q": "What is the lifetime limit for BADR?", "a": "£1 million per individual, cumulative across all qualifying disposals in your lifetime. Once used up, there is no reset, further business gains are taxed at standard rates."},
            {"q": "Do I automatically get BADR when I sell my company?", "a": "No. BADR must be actively claimed on your Self Assessment return. You also need to meet all qualifying conditions (5% shareholding, employee/director, trading company, two-year holding period). Failure to meet any condition denies the relief."},
            {"q": "What happens if my shareholding drops below 5%?", "a": "You lose BADR eligibility from the point your holding falls below 5%. If the dilution arises from a qualifying commercial share issue, you can elect to crystallise the gain at the pre-dilution value and claim BADR on that amount."},
        ],
    },
    {
        "slug": "capital-gains-tax-on-inherited-property-uk",
        "title": "Capital Gains Tax on Inherited Property UK 2026/27 | Full Guide",
        "description": "When you sell inherited property in the UK, CGT is calculated from the probate value, not what the deceased paid. This guide covers the rules, rates, allowable costs, PRR implications and worked examples.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "9 min read",
        "sections": [
            {
                "heading": "How the Base Cost Works for Inherited Property",
                "paragraphs": [
                    "When you inherit a property, your base cost for CGT purposes is the market value of the property at the date of death, the probate value. This is the figure used in the inheritance tax valuation. You do not use what the deceased originally paid for the property. This 'uplift to market value on death' is one of the most valuable tax benefits in the CGT system: all the gains that accrued during the deceased's lifetime are permanently wiped out, they never become taxable in the hands of the heir.",
                    "The practical consequence is that if you inherit a property with a probate value of £350,000 and sell it 18 months later for £360,000, your CGT gain is only £10,000, not the full increase in value since the deceased bought it decades ago. If the property falls in value between probate and sale (possible in a falling market), you may have a capital loss, which can be offset against other gains.",
                    "The probate value must be HMRC-accepted, that is, the value agreed with HMRC's Valuation Office Agency as part of the estate's IHT reporting. If the property was undervalued for probate, HMRC can challenge the CGT base cost. Professional valuations from a qualified surveyor at the date of death are important both for IHT and to establish the CGT base cost accurately.",
                ],
            },
            {
                "heading": "CGT Rates on Inherited Property 2026/27",
                "paragraphs": [
                    "Inherited property that is sold is taxed as a residential property gain at the standard 2026/27 rates: 18% for gains within the basic-rate band and 24% for gains in the higher-rate band. The same annual exempt amount of £3,000 applies. These rates replaced the previous higher-rate of 28% in October 2024.",
                    "The 60-day reporting rule applies: if you sell an inherited UK residential property and CGT is owed, you must report and pay within 60 days of completion through HMRC's online property reporting service. If you are executors dealing with an estate, the estate may have its own CGT position, estates have a separate annual exempt amount (£3,000 for 2026/27 in the years of administration) and pay CGT at 24% (as there is no basic-rate element for estates).",
                ],
            },
            {
                "heading": "Allowable Costs When Selling Inherited Property",
                "paragraphs": [
                    "From the probate value base, you can deduct allowable costs to arrive at the CGT gain. These include: solicitor fees and estate agent costs on the eventual sale; any capital improvements made by you after inheriting the property (extensions, new roof, new kitchen of improved specification, not repairs or decoration); and the cost of the probate valuation itself if incurred in connection with establishing the CGT base cost.",
                    "You cannot deduct administration costs of the estate, funeral costs, or IHT paid on the property. The estate's administration costs are matters for the estate accounts, not the individual's CGT calculation. Similarly, any mortgage costs or letting expenses do not reduce the CGT gain, they may be relevant for income tax but not for CGT.",
                ],
            },
            {
                "heading": "Inheritance and Private Residence Relief",
                "paragraphs": [
                    "If an inherited property subsequently becomes your main residence, you may be entitled to partial Private Residence Relief when you eventually sell it. The PRR fraction is calculated as the proportion of your ownership period (from the date you inherited, not the deceased's original purchase) during which it was your main home, plus the final 9 months of ownership. If you move into the inherited property immediately and later sell it, having lived there the whole time, the full gain is likely to be PRR-exempt.",
                    "If you never move into the inherited property, you sell it as an investment or rental property, PRR is not available. The full gain (from probate value to sale price, less allowable costs) is subject to CGT. Multiple beneficiaries who inherit jointly each have their own CGT position, each person's share of the gain is taxed separately, with each beneficiary using their own AEA and income level to determine the rate.",
                ],
            },
            {
                "heading": "Worked Example: Selling an Inherited Property",
                "paragraphs": [
                    "Sarah inherits her mother's buy-to-let property in July 2025. Probate value: £280,000. She does not move in. Over the following year, she spends £8,000 on a new boiler and bathroom (capital improvements). She sells in August 2026 for £305,000. Selling costs: £6,000 (estate agent and solicitor).",
                    "Gain calculation: £305,000 proceeds − £280,000 probate value − £8,000 improvements − £6,000 selling costs = £11,000 gross gain. After the £3,000 annual exempt amount: taxable gain = £8,000. Sarah's salary is £55,000, placing her fully in the higher-rate band. CGT = £8,000 × 24% = £1,920. She must report and pay within 60 days of the August 2026 completion.",
                    "If Sarah had a lower income, say £32,000, her taxable income would be £19,430. Remaining basic-rate band = £37,700 − £19,430 = £18,270. The full £8,000 gain fits within the remaining band: CGT = £8,000 × 18% = £1,440. The same gain costs £480 less simply because of Sarah's lower income.",
                ],
            },
        ],
        "faqs": [
            {"q": "What is the base cost for CGT on inherited property?", "a": "The market value at the date of death (probate value), not what the deceased originally paid. All pre-death gains are wiped out, they never become taxable to the inheritor."},
            {"q": "Do I pay CGT if I sell an inherited property immediately?", "a": "Only if the value has increased between the probate valuation and the sale. If you sell immediately after probate for exactly the probate value, there is no gain and no CGT."},
            {"q": "What if the property falls in value after I inherit it?", "a": "If you sell for less than the probate value, you have a capital loss. This can be offset against other capital gains in the same or future tax years."},
            {"q": "Does PRR apply to inherited property?", "a": "Not automatically. If you move into the inherited property and it becomes your main home, PRR will apply for the period you live there. If you never occupy it, PRR is not available."},
        ],
    },
    {
        "slug": "work-out-capital-gains-tax-uk",
        "title": "How to Work Out Capital Gains Tax UK 2026/27 | Step-by-Step",
        "description": "A practical step-by-step guide to working out UK capital gains tax for 2026/27. Covers property, shares and other assets with two full worked examples and a free calculator.",
        "date_iso": "2026-05-27",
        "date": "May 2026",
        "reading_time": "10 min read",
        "sections": [
            {
                "heading": "The Five Steps to Calculate UK CGT",
                "paragraphs": [
                    "Working out capital gains tax in the UK involves five distinct steps, applied in a specific order. Get the order wrong and you will either overpay or underpay. The five steps are: (1) Calculate the gross gain; (2) Deduct current-year losses; (3) Deduct the annual exempt amount; (4) Work out how much basic-rate band remains; (5) Apply the correct rates. This guide walks through each step in detail with worked examples.",
                ],
            },
            {
                "heading": "Step 1: Calculate the Gross Gain",
                "paragraphs": [
                    "The gross gain is the proceeds from the disposal minus the allowable costs. Proceeds means the cash received, or, if the asset is gifted or disposed of below market value to a connected person, the market value at the date of disposal. Allowable costs for most assets are: acquisition cost, incidental acquisition costs (solicitor fees, stamp duty, broker commissions), improvement costs (for property), and incidental disposal costs (estate agent fees, solicitor fees on sale, broker commissions on share sales).",
                    "For shares, you cannot choose which shares you are selling, HMRC applies the Section 104 pool rule. All acquisitions of the same share are pooled and averaged. The average cost per share from the pool is used as the acquisition cost per share sold. Check also for same-day and 30-day matching rules before using the pool cost.",
                    "For property, the gross gain is straightforward: sale price minus purchase price minus stamp duty on purchase minus capital improvements minus selling costs. If the property is jointly owned (e.g. 50/50 with a spouse), split the proceeds and costs proportionately before calculating each owner's individual gain.",
                ],
            },
            {
                "heading": "Step 2: Deduct Current-Year Capital Losses",
                "paragraphs": [
                    "If you have realised capital losses from other disposals in the same tax year, these are deducted from the gross gain. You cannot choose to defer a current-year loss, it must be used in the year it arises. If your losses exceed your gains in a year, the net loss is carried forward to future years.",
                    "Losses from previous years (brought-forward losses) are treated differently, see Step 3.",
                ],
            },
            {
                "heading": "Step 3: Apply the Annual Exempt Amount and Brought-Forward Losses",
                "paragraphs": [
                    "The annual exempt amount for 2026/27 is £3,000. This is applied after current-year losses. Brought-forward losses from previous years are also applied at this stage, but only to the extent needed to reduce the net gain to the annual exempt amount. You do not waste brought-forward losses against gains that would have been exempt anyway.",
                    "Example: Gain after current-year losses = £12,000. Brought-forward losses = £15,000. You apply £9,000 of the brought-forward losses (to bring the gain down to £3,000, which is sheltered by the AEA). Taxable gain = £0. The remaining £6,000 of brought-forward losses is carried forward again.",
                ],
            },
            {
                "heading": "Step 4: Work Out Your Remaining Basic-Rate Band",
                "paragraphs": [
                    "The CGT rate depends on how much of the basic-rate band remains after your other taxable income. The UK basic-rate band runs from £12,570 (the personal allowance) to £50,270 (the higher-rate threshold). For CGT purposes, you calculate: £50,270 minus your gross income (or more precisely, £37,700 minus your taxable income after the personal allowance). The result is the amount of gain that can be taxed at 18%.",
                    "If your income already fills the basic-rate band (gross income over £50,270), the remaining band is zero, all of the taxable gain is at 24%. If your income is £30,000, your taxable income is £17,430 (£30,000 − £12,570), and the remaining basic-rate band is £37,700 − £17,430 = £20,270. Up to £20,270 of gain is at 18%, and any gain above that is at 24%.",
                ],
            },
            {
                "heading": "Step 5: Apply the Rates",
                "paragraphs": [
                    "Apply 18% to the amount of the taxable gain within the remaining basic-rate band, and 24% to the amount above. Add the two figures together to get the total CGT due.",
                    "Full worked example, property gain: Jane has a salary of £42,000. She sells a buy-to-let property with a gross gain of £38,000. She has capital losses brought forward of £5,000.",
                    "Step 1: Gross gain = £38,000. Step 2: No current-year losses. Step 3: Apply brought-forward losses, need to bring gain down to AEA of £3,000, so apply £35,000 of losses. Taxable gain after AEA = £0. Remaining brought-forward losses = £5,000 − £35,000 ... wait. Losses are only £5,000, so apply all £5,000. Gain after losses = £33,000. AEA reduces to £30,000 taxable gain. Step 4: Jane's taxable income = £42,000 − £12,570 = £29,430. Remaining basic-rate band = £37,700 − £29,430 = £8,270. Step 5: First £8,270 at 18% = £1,489. Remaining £21,730 (£30,000 − £8,270) at 24% = £5,215. Total CGT = £6,704.",
                ],
            },
            {
                "heading": "Reporting and Paying CGT",
                "paragraphs": [
                    "Property gains: report and pay within 60 days of completion using HMRC's online property reporting service. Other gains: report through Self Assessment, with the tax due by 31 January following the end of the tax year. For 2026/27 gains, the Self Assessment deadline is 31 January 2028.",
                    "You must report all disposals where the total proceeds exceeded four times the AEA (£12,000 for 2026/27), even if there is no tax to pay. This means selling a small shareholding for £13,000 with no gain still requires reporting if you are within Self Assessment. HMRC receives share disposal data from brokers and will investigate mismatches.",
                ],
            },
        ],
        "faqs": [
            {"q": "What order do I apply losses and the annual exempt amount?", "a": "Current-year losses first (compulsory), then apply the AEA, then brought-forward losses, but only enough brought-forward losses to bring the gain to the AEA level."},
            {"q": "Do I have to report a disposal if there is no CGT to pay?", "a": "If you are in Self Assessment and total proceeds exceed four times the AEA (£12,000 for 2026/27), you must still report the disposal even if no tax is owed."},
            {"q": "What rate of CGT applies in 2026/27?", "a": "18% for gains within the basic-rate band and 24% for gains above it. The rate depends on how much basic-rate band (up to £50,270) remains after your other income."},
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


@app.route("/cgt-survival-pack")
def cgt_pack_landing():
    return render_template("cgt_pack_landing.html", **_ctx(
        title="Capital Gains Tax Survival Pack 2026/27 | PDF Guide — £4.99",
        meta_description="Work out what you owe, claim every relief, and never miss the 60-day deadline. 11-section PDF guide covering 2026/27 rates, property, shares, crypto and more.",
        canonical_url=SITE_URL + "/cgt-survival-pack",
    ))


@app.route("/cgt-survival-pack/checkout", methods=["POST"])
@limiter.limit("10 per minute")
def cgt_pack_checkout():
    if not _stripe:
        return jsonify({"error": "Payments not configured"}), 503
    try:
        session_kwargs = dict(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "unit_amount": PACK_AMOUNT_PENCE,
                    "product_data": {
                        "name": "Capital Gains Tax Survival Pack",
                        "description": "2026/27 PDF guide — rates, reliefs, 60-day rule, shares, crypto and property.",
                    },
                },
                "quantity": 1,
            }],
            success_url=f"{SITE_URL}/cgt-survival-pack/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{SITE_URL}/cgt-survival-pack",
            payment_intent_data={
                "metadata": {"product": "cgt_survival_pack"},
                "statement_descriptor_suffix": "CGTTAXPACK",
            },
        )
        if STRIPE_CGT_PACK_PRICE_ID:
            session_kwargs["line_items"] = [{"price": STRIPE_CGT_PACK_PRICE_ID, "quantity": 1}]
        session = _stripe.checkout.Session.create(**session_kwargs)
        return jsonify({"url": session.url})
    except Exception as exc:
        log.error("CGT pack checkout error: %s", exc)
        return jsonify({"error": "Checkout failed"}), 500


@app.route("/cgt-survival-pack/webhook", methods=["POST"])
def cgt_pack_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET or not _stripe:
        abort(400)
    try:
        event = _stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        abort(400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = (session.get("payment_intent_data") or {}).get("metadata") or session.get("metadata") or {}
        if meta.get("product") != "cgt_survival_pack":
            intent_id = session.get("payment_intent")
            if intent_id and _stripe:
                try:
                    pi = _stripe.PaymentIntent.retrieve(intent_id)
                    if pi.get("metadata", {}).get("product") != "cgt_survival_pack":
                        return "", 200
                except Exception:
                    pass

        from firestore_client import get_db, server_timestamp
        db = get_db()
        if db:
            event_ref = db.collection("webhook_events").document(event["id"])
            if event_ref.get().exists:
                return "", 200
            event_ref.set({"processed_at": server_timestamp()})

        token = secrets.token_urlsafe(32)
        email = session.get("customer_details", {}).get("email") or session.get("customer_email") or ""
        expires = datetime.utcnow() + timedelta(days=7)

        if db:
            db.collection("pack_downloads").document(token).set({
                "product": "cgt_survival_pack",
                "session_id": session.get("id", ""),
                "email": email,
                "created_at": server_timestamp(),
                "expires_at": expires,
                "download_count": 0,
                "max_downloads": 5,
            })

    return "", 200


@app.route("/cgt-survival-pack/success")
def cgt_pack_success():
    session_id = request.args.get("session_id", "")
    token = None
    email = ""
    if session_id and _stripe:
        try:
            session = _stripe.checkout.Session.retrieve(session_id)
            email = session.get("customer_details", {}).get("email") or session.get("customer_email") or ""
            from firestore_client import get_db
            db = get_db()
            if db:
                docs = db.collection("pack_downloads").where("session_id", "==", session_id).limit(1).get()
                for doc in docs:
                    token = doc.id
                    break
        except Exception as exc:
            log.error("Success page lookup error: %s", exc)
    return render_template("cgt_pack_success.html", **_ctx(
        title="Download Your Capital Gains Tax Survival Pack",
        meta_description="Your Capital Gains Tax Survival Pack is ready to download.",
        canonical_url=SITE_URL + "/cgt-survival-pack/success",
        token=token,
        email=email,
        session_id=session_id,
    ))


@app.route("/cgt-survival-pack/download/<token>")
def cgt_pack_download(token):
    from firestore_client import get_db, server_timestamp
    db = get_db()
    if not db:
        abort(404)
    ref = db.collection("pack_downloads").document(token)
    doc = ref.get()
    if not doc.exists:
        abort(404)
    data = doc.to_dict()
    if data.get("product") != "cgt_survival_pack":
        abort(404)
    expires = data.get("expires_at")
    if expires:
        exp_dt = expires if isinstance(expires, datetime) else expires
        try:
            if hasattr(exp_dt, "replace"):
                exp_dt = exp_dt.replace(tzinfo=None)
            if exp_dt < datetime.utcnow():
                abort(410)
        except Exception:
            pass
    if data.get("download_count", 0) >= data.get("max_downloads", 5):
        abort(410)
    ref.update({"download_count": data.get("download_count", 0) + 1, "last_downloaded_at": server_timestamp()})
    return send_file(_PACK_PDF, as_attachment=True, download_name="Capital-Gains-Tax-Survival-Pack.pdf", mimetype="application/pdf")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
