import logging
import os
import datetime
import threading
import hashlib
import sqlite3
import secrets
import numpy as np
import cv2
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── SQLite DB for receipt tracking ───────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts.db")

def init_db():
    """Create all required tables if they do not exist."""
    conn = sqlite3.connect(DB_PATH)

    # ── Receipt deduplication ─────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanned_receipts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_hash TEXT UNIQUE NOT NULL,
            qr_data      TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            scanned_at   TEXT NOT NULL
        )
    """)

    # ── Monthly tax reports submitted by pharmacies ───────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tax_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pharmacy_name   TEXT NOT NULL,
            user_id         TEXT NOT NULL,
            report_month    TEXT NOT NULL,        -- e.g. '2024-06'
            total_sales_birr REAL NOT NULL,
            units_sold      INTEGER NOT NULL,
            tax_paid_birr   REAL NOT NULL,
            notes           TEXT,
            submitted_at    TEXT NOT NULL,
            status          TEXT DEFAULT 'pending' -- pending / approved / flagged
        )
    """)

    # ── EFDA stock ledger (what was handed to each pharmacy) ──────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS efda_stock (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pharmacy_name   TEXT NOT NULL,
            medicine_name   TEXT NOT NULL,
            units_allocated INTEGER NOT NULL,
            allocated_month TEXT NOT NULL,        -- e.g. '2024-06'
            recorded_at     TEXT NOT NULL
        )
    """)

    # ── Rate limiting ─────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id    TEXT NOT NULL,
            action     TEXT NOT NULL,
            ts         TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rl ON rate_limits(user_id, action, ts)")

    # ── App users (Android login) ─────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phone        TEXT UNIQUE NOT NULL,
            name         TEXT NOT NULL,
            role         TEXT DEFAULT 'user',   -- user / pharmacy / admin
            pharmacy_idx INTEGER DEFAULT -1,    -- which pharmacy they manage (-1 = none)
            created_at   TEXT NOT NULL
        )
    """)

    # ── API tokens (issued on login) ──────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def is_duplicate_receipt(receipt_hash: str) -> bool:
    """Return True if this receipt hash was already scanned before."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id FROM scanned_receipts WHERE receipt_hash = ?", (receipt_hash,)
    ).fetchone()
    conn.close()
    return row is not None

def save_receipt(receipt_hash: str, qr_data: str, user_id: str) -> None:
    """Save a newly scanned receipt to the DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO scanned_receipts (receipt_hash, qr_data, user_id, scanned_at) "
        "VALUES (?, ?, ?, ?)",
        (receipt_hash, qr_data, str(user_id),
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def decode_qr_from_bytes(image_bytes: bytes) -> str | None:
    """
    Decode a QR code from raw image bytes using OpenCV.
    Returns the QR string on success, or None if no valid QR is detected.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data and data.strip():
            return data.strip()
        # Retry with grayscale for low-contrast images
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        data, _, _ = detector.detectAndDecode(gray)
        return data.strip() if data and data.strip() else None
    except Exception as e:
        logger.warning(f"QR decode error: {e}")
        return None

def hash_image(image_bytes: bytes) -> str:
    """SHA-256 hash of raw image bytes — used as the duplicate key."""
    return hashlib.sha256(image_bytes).hexdigest()


# ── Tax report helpers ────────────────────────────────────────────

def save_tax_report(pharmacy_name: str, user_id: str, report_month: str,
                    total_sales: float, units_sold: int, tax_paid: float,
                    notes: str = "") -> int:
    """Insert a tax report and return its new row id."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """INSERT INTO tax_reports
           (pharmacy_name, user_id, report_month, total_sales_birr,
            units_sold, tax_paid_birr, notes, submitted_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (pharmacy_name, str(user_id), report_month, total_sales,
         units_sold, tax_paid, notes,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_tax_reports(pharmacy_name: str | None = None,
                    month: str | None = None) -> list[dict]:
    """Return tax reports, optionally filtered by pharmacy and/or month."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query  = "SELECT * FROM tax_reports WHERE 1=1"
    params: list = []
    if pharmacy_name:
        query += " AND pharmacy_name = ?"
        params.append(pharmacy_name)
    if month:
        query += " AND report_month = ?"
        params.append(month)
    query += " ORDER BY submitted_at DESC"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return rows


# ── Stock reconciliation helpers ──────────────────────────────────

def add_efda_stock(pharmacy_name: str, medicine_name: str,
                   units: int, month: str) -> None:
    """Record units allocated by EFDA to a pharmacy for a given month."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO efda_stock
           (pharmacy_name, medicine_name, units_allocated, allocated_month, recorded_at)
           VALUES (?,?,?,?,?)""",
        (pharmacy_name, medicine_name, units, month,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def reconcile_stock(pharmacy_name: str, month: str) -> dict:
    """
    Compare EFDA allocation vs pharmacy-reported sales for a given month.
    Returns a summary dict with allocated, reported, and discrepancy.
    """
    conn = sqlite3.connect(DB_PATH)

    # Total units EFDA handed to this pharmacy this month
    row = conn.execute(
        """SELECT COALESCE(SUM(units_allocated), 0)
           FROM efda_stock
           WHERE pharmacy_name=? AND allocated_month=?""",
        (pharmacy_name, month),
    ).fetchone()
    allocated = int(row[0]) if row else 0

    # Total units pharmacy claimed to sell this month
    row2 = conn.execute(
        """SELECT COALESCE(SUM(units_sold), 0)
           FROM tax_reports
           WHERE pharmacy_name=? AND report_month=? AND status != 'flagged'""",
        (pharmacy_name, month),
    ).fetchone()
    reported = int(row2[0]) if row2 else 0

    conn.close()
    diff = reported - allocated          # positive → over-reported (fraud risk)
    pct  = round((diff / allocated * 100) if allocated else 0, 1)
    return {
        "pharmacy":  pharmacy_name,
        "month":     month,
        "allocated": allocated,
        "reported":  reported,
        "diff":      diff,
        "pct":       pct,
        "flag":      diff > 0 or pct > 10,   # flag if reported > allocated or >10% gap
    }


def flag_tax_report(report_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tax_reports SET status='flagged' WHERE id=?", (report_id,))
    conn.commit()
    conn.close()


# ── Rate limiting ─────────────────────────────────────────────────
# Limits per action (window_seconds, max_calls)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "qr_scan":     (3600, 10),   # max 10 QR scans per hour
    "report_price":(3600, 20),   # max 20 price reports per hour
    "rate_pharmacy":(86400, 5),  # max 5 ratings per day
    "tax_report":  (86400, 3),   # max 3 tax reports per day
    "search":      (60, 15),     # max 15 searches per minute
}

def check_rate_limit(user_id: str, action: str) -> tuple[bool, int]:
    """
    Returns (allowed: bool, remaining_seconds: int).
    Cleans up old entries and checks whether the user is within limit.
    """
    window_s, max_calls = RATE_LIMITS.get(action, (60, 30))
    now     = datetime.datetime.now()
    cutoff  = (now - datetime.timedelta(seconds=window_s)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    # Purge old entries for this user+action
    conn.execute(
        "DELETE FROM rate_limits WHERE user_id=? AND action=? AND ts < ?",
        (user_id, action, cutoff),
    )
    # Count recent calls
    count = conn.execute(
        "SELECT COUNT(*) FROM rate_limits WHERE user_id=? AND action=?",
        (user_id, action),
    ).fetchone()[0]

    if count >= max_calls:
        # Find when the oldest entry expires
        oldest = conn.execute(
            "SELECT ts FROM rate_limits WHERE user_id=? AND action=? ORDER BY ts ASC LIMIT 1",
            (user_id, action),
        ).fetchone()
        conn.close()
        if oldest:
            oldest_dt = datetime.datetime.strptime(oldest[0], "%Y-%m-%d %H:%M:%S")
            wait = int((oldest_dt + datetime.timedelta(seconds=window_s) - now).total_seconds())
            return False, max(wait, 1)
        return False, window_s

    # Record this call
    conn.execute(
        "INSERT INTO rate_limits (user_id, action, ts) VALUES (?,?,?)",
        (user_id, action, now_str),
    )
    conn.commit()
    conn.close()
    return True, 0


def _fmt_wait(seconds: int) -> str:
    """Format wait seconds into a human-readable string (am/en mixed)."""
    if seconds < 60:
        return f"{seconds} ሰከንድ / {seconds}s"
    elif seconds < 3600:
        m = seconds // 60
        return f"{m} ደቂቃ / {m} min"
    else:
        h = seconds // 3600
        return f"{h} ሰዓት / {h} hr"


# ── Input sanitization ────────────────────────────────────────────
import re as _re

_ALLOWED_PATTERN = _re.compile(
    r"^[\u1200-\u137F\u0020-\u007Ea-zA-Z0-9 "
    r"\u00C0-\u024F.,;:!?()\-\+/'\"@#\n]{1,500}$"
)

def sanitize_text(text: str) -> str | None:
    """
    Return the sanitized text, or None if it contains suspicious content.
    Allows Amharic (Ethiopic), basic ASCII, and common punctuation.
    Rejects SQL/script injection patterns and overly long strings.
    """
    text = text.strip()
    if not text or len(text) > 500:
        return None
    # Block obvious SQL/script injection keywords
    lowered = text.lower()
    for bad in ("drop table", "select *", "insert into", "<script", "javascript:", "--", "/*"):
        if bad in lowered:
            return None
    return text


# ── Self-rating prevention ─────────────────────────────────────────
# Map pharmacy index → Telegram user_id of the owner (set via env var)
# Format: PHARMACY_OWNERS=0:123456789,1:987654321
def _load_pharmacy_owners() -> dict[int, int]:
    raw = os.environ.get("PHARMACY_OWNERS", "")
    owners: dict[int, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if ":" in part:
            try:
                idx, uid = part.split(":", 1)
                owners[int(idx)] = int(uid)
            except ValueError:
                pass
    return owners

PHARMACY_OWNERS: dict[int, int] = _load_pharmacy_owners()

# Initialise DB on startup
init_db()

# ══════════════════════════════════════════════════════════════════
# FastAPI — REST API for Android App
# ══════════════════════════════════════════════════════════════════

api = FastAPI(title="Pharmacy Bot API", version="1.0.0")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic request/response models ─────────────────────────────

class RegisterRequest(BaseModel):
    phone: str
    name: str
    role: str = "user"          # user / pharmacy / admin
    pharmacy_idx: int = -1

class LoginRequest(BaseModel):
    phone: str

class PriceReportRequest(BaseModel):
    pharmacy: str
    medicine: str
    price: str

class RatingRequest(BaseModel):
    pharmacy_idx: int
    stars: int                  # 1-5
    comment: str = "—"

class TaxReportRequest(BaseModel):
    pharmacy_name: str
    report_month: str           # e.g. "2024-06"
    total_sales_birr: float
    units_sold: int

class EfdaStockRequest(BaseModel):
    pharmacy_name: str
    medicine_name: str
    units_allocated: int
    allocated_month: str


# ── Auth helpers ──────────────────────────────────────────────────

def _issue_token(user_id: int) -> str:
    """Create and store a 30-day API token for a user."""
    token     = secrets.token_hex(32)
    now       = datetime.datetime.now()
    expires   = (now + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    now_str   = now.strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO api_tokens (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, now_str, expires),
    )
    conn.commit()
    conn.close()
    return token


def _get_current_user(authorization: str = Header(None)) -> dict:
    """Dependency: validate Bearer token and return user row."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token አልተሰጠም / Missing token")
    token = authorization.split(" ", 1)[1]
    now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn  = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT u.* FROM api_tokens t
           JOIN app_users u ON u.id = t.user_id
           WHERE t.token=? AND t.expires_at > ?""",
        (token, now),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Token ጊዜው አልፏል ወይም ትክክለኛ አይደለም")
    return dict(row)


def _require_admin(user: dict = Depends(_get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin ብቻ ይህን ሊጠቀም ይችላል")
    return user


# ══════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS (no auth needed)
# ══════════════════════════════════════════════════════════════════

@api.get("/")
@api.head("/")
def root():
    """Root endpoint — UptimeRobot root ping."""
    import time as _t
    return {"status": "ok", "service": "MedLink Ethiopia Bot", "timestamp": int(_t.time())}

@api.get("/health")
@api.head("/health")
def health():
    """Render health check."""
    import time as _t
    return {"status": "ok", "service": "MedLink Ethiopia Bot", "timestamp": int(_t.time())}


@api.post("/auth/register")
def register(req: RegisterRequest):
    """Register a new app user and return a token."""
    safe_phone = sanitize_text(req.phone)
    safe_name  = sanitize_text(req.name)
    if not safe_phone or not safe_name:
        raise HTTPException(status_code=400, detail="ትክክለኛ ያልሆነ ግብዓት / Invalid input")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO app_users (phone, name, role, pharmacy_idx, created_at) "
            "VALUES (?,?,?,?,?)",
            (safe_phone, safe_name, req.role, req.pharmacy_idx, now),
        )
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        # Phone already registered — just log in
        row = conn.execute(
            "SELECT id FROM app_users WHERE phone=?", (safe_phone,)
        ).fetchone()
        user_id = row[0]
    finally:
        conn.close()

    token = _issue_token(user_id)
    return {"token": token, "user_id": user_id, "message": "ተመዝግበዋል! / Registered!"}


@api.post("/auth/login")
def login(req: LoginRequest):
    """Log in by phone number and return a fresh token."""
    safe_phone = sanitize_text(req.phone)
    if not safe_phone:
        raise HTTPException(status_code=400, detail="ትክክለኛ ያልሆነ ስልክ ቁጥር")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM app_users WHERE phone=?", (safe_phone,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="ተጠቃሚ አልተገኘም / User not found")
    token = _issue_token(row["id"])
    return {
        "token":    token,
        "user_id":  row["id"],
        "name":     row["name"],
        "role":     row["role"],
    }


# ══════════════════════════════════════════════════════════════════
# PROTECTED ENDPOINTS (Bearer token required)
# ══════════════════════════════════════════════════════════════════

# ── Pharmacies ────────────────────────────────────────────────────

@api.get("/pharmacies")
def get_pharmacies(
    lat: float = 0.0,
    lon: float = 0.0,
    user: dict = Depends(_get_current_user),
):
    """Return all pharmacies with distance from user location."""
    from pharmacies import PHARMACIES, haversine_km, TIER_LABELS
    result = []
    for i, p in enumerate(PHARMACIES):
        dist = round(haversine_km(lat or p["lat"], lon or p["lon"], p["lat"], p["lon"]), 2)
        result.append({
            "idx":      i,
            "name":     p["name"],
            "address":  p["address"],
            "phone":    p["phone"],
            "hours":    p["hours"],
            "tier":     p.get("tier", ""),
            "tier_label": TIER_LABELS.get(p.get("tier", ""), ""),
            "lat":      p["lat"],
            "lon":      p["lon"],
            "distance_km": dist,
        })
    result.sort(key=lambda x: x["distance_km"])
    return {"pharmacies": result}


# ── Price summary ─────────────────────────────────────────────────

@api.get("/prices/summary")
def price_summary(user: dict = Depends(_get_current_user)):
    """Return the latest price summary text."""
    from pharmacies import format_price_summary
    return {"summary": format_price_summary()}


# ── Price reports ─────────────────────────────────────────────────

@api.post("/prices/report")
def report_price(
    req: PriceReportRequest,
    user: dict = Depends(_get_current_user),
):
    """Submit a medicine price report."""
    safe_med   = sanitize_text(req.medicine)
    safe_price = sanitize_text(req.price)
    safe_ph    = sanitize_text(req.pharmacy)
    if not all([safe_med, safe_price, safe_ph]):
        raise HTTPException(status_code=400, detail="ትክክለኛ ያልሆነ ግብዓት")

    # Rate limit
    allowed, wait = check_rate_limit(str(user["id"]), "report_price")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"ብዙ ሪፖርቶች ቀርበዋል። {_fmt_wait(wait)} ቆይተው ይሞክሩ።",
        )

    log_path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"[{timestamp}] user={user['id']} | pharmacy={safe_ph} "
            f"| medicine={safe_med} | price={safe_price} ብር\n"
        )
    return {"ok": True, "points_earned": 20, "message": "ሪፖርት ቀርቧል! / Report submitted!"}


# ── Ratings ───────────────────────────────────────────────────────

@api.get("/ratings")
def get_ratings(user: dict = Depends(_get_current_user)):
    """Return aggregated star ratings per pharmacy."""
    import collections
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ratings.log")
    totals: dict = collections.defaultdict(list)
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    parts = {
                        p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
                        for p in line.split("|")
                    }
                    ph    = parts.get("pharmacy", "").strip()
                    stars = int(parts.get("stars", "0").strip())
                    if ph and stars:
                        totals[ph].append(stars)
                except Exception:
                    continue
    result = []
    for ph, stars_list in totals.items():
        avg = sum(stars_list) / len(stars_list)
        result.append({
            "pharmacy": ph,
            "avg_stars": round(avg, 1),
            "total_reviews": len(stars_list),
        })
    result.sort(key=lambda x: -x["avg_stars"])
    return {"ratings": result}


@api.post("/ratings")
def submit_rating(
    req: RatingRequest,
    user: dict = Depends(_get_current_user),
):
    """Submit a star rating for a pharmacy."""
    if not 1 <= req.stars <= 5:
        raise HTTPException(status_code=400, detail="ኮከብ 1–5 ብቻ ሊሆን ይችላል")

    from pharmacies import PHARMACIES
    if req.pharmacy_idx < 0 or req.pharmacy_idx >= len(PHARMACIES):
        raise HTTPException(status_code=400, detail="ፋርማሲ አልተገኘም")

    pharmacy_name = PHARMACIES[req.pharmacy_idx]["name"]

    # Self-rating check
    owner_id = PHARMACY_OWNERS.get(req.pharmacy_idx)
    if owner_id and user["id"] == owner_id:
        raise HTTPException(status_code=403, detail="ለራስዎ ፋርማሲ ደረጃ መስጠት አይቻልም")

    # Rate limit
    allowed, wait = check_rate_limit(str(user["id"]), "rate_pharmacy")
    if not allowed:
        raise HTTPException(status_code=429, detail=f"{_fmt_wait(wait)} ቆይተው ይሞክሩ።")

    safe_comment = sanitize_text(req.comment) or "—"
    log_path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ratings.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"[{timestamp}] user={user['id']} | pharmacy={pharmacy_name} "
            f"| stars={req.stars} | comment={safe_comment}\n"
        )
    return {"ok": True, "points_earned": 10, "message": "ደረጃ ቀርቧል! / Rating submitted!"}


# ── QR scan (mobile camera) ───────────────────────────────────────

@api.post("/qr/scan")
async def qr_scan(
    file: UploadFile = File(...),
    user: dict = Depends(_get_current_user),
):
    """Upload a receipt photo; returns QR data and awards points if valid."""
    allowed, wait = check_rate_limit(str(user["id"]), "qr_scan")
    if not allowed:
        raise HTTPException(status_code=429, detail=f"{_fmt_wait(wait)} ቆይተው ይሞክሩ።")

    image_bytes = await file.read()
    qr_data = decode_qr_from_bytes(image_bytes)
    if not qr_data:
        raise HTTPException(status_code=422, detail="QR ኮድ አልተገኘም / No QR code found")

    img_hash = hash_image(image_bytes)
    qr_hash  = hashlib.sha256(qr_data.encode()).hexdigest()

    if is_duplicate_receipt(img_hash) or is_duplicate_receipt(qr_hash):
        raise HTTPException(status_code=409, detail="ደረሰኝ ቀደም ሲል ጥቅም ላይ ውሏል / Already used")

    save_receipt(img_hash, qr_data, str(user["id"]))
    save_receipt(qr_hash,  qr_data, str(user["id"]))
    return {"ok": True, "qr_data": qr_data, "points_earned": 5}


# ── Tax reports ───────────────────────────────────────────────────

@api.post("/tax/report")
def submit_tax_report(
    req: TaxReportRequest,
    user: dict = Depends(_get_current_user),
):
    """Pharmacy submits monthly tax report."""
    allowed, wait = check_rate_limit(str(user["id"]), "tax_report")
    if not allowed:
        raise HTTPException(status_code=429, detail=f"{_fmt_wait(wait)} ቆይተው ይሞክሩ።")

    tax_paid  = round(req.total_sales_birr * 0.15, 2)
    report_id = save_tax_report(
        pharmacy_name=req.pharmacy_name,
        user_id=str(user["id"]),
        report_month=req.report_month,
        total_sales=req.total_sales_birr,
        units_sold=req.units_sold,
        tax_paid=tax_paid,
    )
    rec = reconcile_stock(req.pharmacy_name, req.report_month)
    if rec["flag"]:
        flag_tax_report(report_id)

    return {
        "ok":        True,
        "report_id": report_id,
        "tax_paid":  tax_paid,
        "flagged":   rec["flag"],
        "reconciliation": rec,
    }


# ── Admin dashboard ───────────────────────────────────────────────

@api.get("/admin/dashboard")
def admin_dashboard(admin: dict = Depends(_require_admin)):
    """Full stats dashboard — admin only."""
    conn = sqlite3.connect(DB_PATH)
    total_receipts = conn.execute(
        "SELECT COUNT(DISTINCT qr_data) FROM scanned_receipts"
    ).fetchone()[0]
    tr = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_sales_birr),0), "
        "COALESCE(SUM(tax_paid_birr),0), "
        "SUM(CASE WHEN status='flagged' THEN 1 ELSE 0 END) FROM tax_reports"
    ).fetchone()
    flagged_rows = conn.execute(
        "SELECT pharmacy_name, report_month, units_sold, total_sales_birr "
        "FROM tax_reports WHERE status='flagged' ORDER BY submitted_at DESC LIMIT 10"
    ).fetchall()
    top_ph = conn.execute(
        "SELECT pharmacy_name, SUM(total_sales_birr) FROM tax_reports "
        "GROUP BY pharmacy_name ORDER BY 2 DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return {
        "total_receipts_scanned": total_receipts,
        "tax_reports": {
            "count":       tr[0],
            "total_sales": tr[1],
            "total_tax":   tr[2],
            "flagged":     tr[3],
        },
        "flagged_reports": [
            {"pharmacy": r[0], "month": r[1], "units": r[2], "sales": r[3]}
            for r in flagged_rows
        ],
        "top_pharmacies_by_sales": [
            {"pharmacy": r[0], "total_sales": r[1]} for r in top_ph
        ],
    }


@api.post("/admin/efda_stock")
def add_stock(
    req: EfdaStockRequest,
    admin: dict = Depends(_require_admin),
):
    """Admin records EFDA stock allocation for a pharmacy."""
    add_efda_stock(
        req.pharmacy_name,
        req.medicine_name,
        req.units_allocated,
        req.allocated_month,
    )
    return {"ok": True, "message": "ክምችት ተመዝግቧል / Stock recorded"}


# ── FastAPI runner (in background thread) ─────────────────────────

def run_api_server():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="warning")

def run_self_ping():
    """ቦቱ ራሱን ይ-ping ያደርጋል — Render free tier sleep እንዳይተኛ"""
    import urllib.request, time as _t
    port = int(os.environ.get("PORT", 10000))
    url = f"http://localhost:{port}/health"
    _t.sleep(40)  # API server startup ይጠብቅ
    while True:
        try:
            _t.sleep(8 * 60)  # ከ8 ደቂቃ አንዴ
            urllib.request.urlopen(url, timeout=10)
            logger.info("Self-ping OK")
        except Exception as e:
            logger.warning(f"Self-ping failed: {e}")

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from pharmacies import (
    BAHIR_DAR_CENTER,
    PHARMACIES,
    format_all_pharmacies_by_category,
    format_nearest_three,
    format_price_summary,
)
from gemini_vision import extract_medicines_from_image
from medicine_search import smart_medicine_search
from strings import t, with_footer

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

USE_DEFAULT_TEXT_AM = "📍 የባህር ዳር ማዕከልን ተጠቀም (Use Bahir Dar Center)"
USE_DEFAULT_TEXT_EN = "📍 Use Bahir Dar Center"


# ── helpers ──────────────────────────────────────────────────────

def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "am")


def get_user_location(context: ContextTypes.DEFAULT_TYPE) -> tuple[float, float]:
    return (
        context.user_data.get("user_lat", BAHIR_DAR_CENTER[0]),
        context.user_data.get("user_lon", BAHIR_DAR_CENTER[1]),
    )


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_prescription", lang), callback_data="send_prescription")],
        [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
        [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
        [InlineKeyboardButton(t("btn_summary", lang), callback_data="price_summary")],
        [InlineKeyboardButton(t("btn_report", lang), callback_data="report_price")],
        [InlineKeyboardButton(t("btn_rating", lang), callback_data="rate_pharmacy")],
        [InlineKeyboardButton(t("btn_loyalty", lang), callback_data="loyalty_points")],
        [InlineKeyboardButton(t("btn_tax_report", lang), callback_data="tax_report")],
        [InlineKeyboardButton(t("btn_help", lang), callback_data="help")],
        [InlineKeyboardButton(t("btn_language", lang), callback_data="change_language")],
    ])


def report_pharmacy_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for i, ph in enumerate(PHARMACIES):
        pair.append(InlineKeyboardButton(ph["name"], callback_data=f"report_pharm_{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
    ])


def rate_pharmacy_select_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for i, ph in enumerate(PHARMACIES):
        pair.append(InlineKeyboardButton(ph["name"], callback_data=f"rate_pharm_{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def format_ratings_summary() -> str:
    """Read ratings.log and compute average stars per pharmacy."""
    import os, collections
    log_path = os.path.join(os.path.dirname(__file__), "ratings.log")
    if not os.path.exists(log_path):
        return (
            "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*\n\n"
            "_ገና ምንም ደረጃ አልተሰጠም — No ratings yet._"
        )

    totals = collections.defaultdict(list)
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            # format: [timestamp] user=X | pharmacy=Y | stars=N | comment=Z
            try:
                parts = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
                         for p in line.split("|")}
                ph = parts.get("pharmacy", "").strip()
                stars = int(parts.get("stars", "0").strip())
                if ph and stars:
                    totals[ph].append(stars)
            except Exception:
                continue

    if not totals:
        return (
            "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*\n\n"
            "_ገና ምንም ደረጃ አልተሰጠም — No ratings yet._"
        )

    lines = [
        "⭐ *የፋርማሲ ደረጃዎች / Pharmacy Ratings*",
        "_Aggregated from user reviews_\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    sorted_ph = sorted(totals.items(), key=lambda x: -sum(x[1]) / len(x[1]))
    for ph, stars_list in sorted_ph:
        avg = sum(stars_list) / len(stars_list)
        filled = round(avg)
        star_bar = "⭐" * filled + "☆" * (5 - filled)
        lines.append(f"{star_bar} *{ph}*")
        lines.append(f"   📊 _(avg {avg:.1f}/5 · {len(stars_list)} ግምገማዎች)_\n")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


async def _save_rating(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    comment: str,
) -> None:
    lang = get_lang(context)
    data = context.user_data.get("rating_data", {})
    pharmacy = data.get("pharmacy", "—")
    stars = data.get("stars", 0)
    star_display = "⭐" * stars

    log_path = os.path.join(os.path.dirname(__file__), "ratings.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = update.effective_user
    user_info = f"@{user.username}" if user.username else str(user.id)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"[{timestamp}] user={user_info} | pharmacy={pharmacy} "
            f"| stars={stars} | comment={comment}\n"
        )

    context.user_data["mode"] = None
    context.user_data.pop("rating_step", None)
    context.user_data.pop("rating_data", None)

    # +10 points for rating
    total = add_points(context, 10)
    level = get_level(total)

    await update.effective_message.reply_text(
        with_footer(
            f"✅ *ደረጃዎ ደርሷል! / Rating Submitted!*\n\n"
            f"🏥 *{pharmacy}*\n"
            f"⭐ {star_display} ({stars}/5)\n"
            f"💬 _{comment}_\n\n"
            f"🎁 *+10 Points ተጨምሮልዎታል!*\n"
            f"📊 አጠቃላይ: *{total} pts* — {level}\n"
            f"_Thank you for your feedback! +10 loyalty points added._"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 ሁሉም ደረጃዎች (View All Ratings)", callback_data="view_ratings")],
            [InlineKeyboardButton("🎁 የእኔ Points", callback_data="loyalty_points")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


# ── loyalty points helpers ───────────────────────────────────────

def get_points(context: ContextTypes.DEFAULT_TYPE) -> int:
    return context.user_data.get("loyalty_points", 0)


def add_points(context: ContextTypes.DEFAULT_TYPE, pts: int) -> int:
    total = context.user_data.get("loyalty_points", 0) + pts
    context.user_data["loyalty_points"] = total
    return total


def get_level(points: int) -> str:
    if points >= 500:
        return "💎 Platinum"
    elif points >= 300:
        return "🥇 Gold"
    elif points >= 150:
        return "🥈 Silver"
    elif points >= 50:
        return "🥉 Bronze"
    else:
        return "🌱 Starter"


def location_request_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t("btn_share_location", lang), request_location=True)],
            [KeyboardButton(t("btn_use_default", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _ask_for_location(message, context, pending_action: str) -> None:
    lang = get_lang(context)
    context.user_data["pending_action"] = pending_action
    prompt_key = "nearest_prompt" if pending_action == "nearest" else "location_prompt"
    await message.reply_text(
        with_footer(t(prompt_key, lang)),
        parse_mode="Markdown",
        reply_markup=location_request_keyboard(lang),
    )


async def _show_nearby_pharmacies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    lat, lon = get_user_location(context)
    await update.effective_message.reply_text(
        with_footer(format_all_pharmacies_by_category(lat, lon)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _show_nearest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    lat, lon = get_user_location(context)
    await update.effective_message.reply_text(
        with_footer(format_nearest_three(lat, lon)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
            [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _show_filtered_pharmacies(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_key: str) -> None:
    from pharmacies import PHARMACIES, haversine_km, TIER_LABELS
    lang = get_lang(context)
    lat, lon = get_user_location(context)

    TIER_ORDER = {"budget": 1, "standard": 2, "premium": 3}

    all_entries = []
    for p in PHARMACIES:
        dist = haversine_km(lat, lon, p["lat"], p["lon"])
        all_entries.append({**p, "distance_km": round(dist, 2)})

    if filter_key == "pharmacies_nearby":
        group = [e for e in all_entries if e["distance_km"] <= 1.0]
        title = "📍 *በዙሪያህ ያሉ ፋርማሲዎች* — 1 ኪ.ሜ ውስጥ\n_Pharmacies within 1km_"
    elif filter_key == "pharmacies_kebele":
        group = [e for e in all_entries if e["distance_km"] <= 5.0]
        title = "🏘️ *በቀበሌው ያሉ ፋርማሲዎች* — 5 ኪ.ሜ ውስጥ\n_Pharmacies within 5km_"
    else:
        # City-wide — ሁሉም ፋርማሲዎች ይታያሉ
        group = all_entries[:]
        title = "🏙️ *በከተማው ያሉ ሁሉም ፋርማሲዎች*\n_All pharmacies in Bahir Dar_"

    # Sort: ዝቅተኛ (budget) → መካከለኛ (standard) → ከፍተኛ (premium), then by distance
    group.sort(key=lambda x: (TIER_ORDER.get(x.get("tier", ""), 9), x["distance_km"]))

    if not group:
        text = f"{title}\n\n_— ምንም ፋርማሲ አልተገኘም / No pharmacies found in this range._"
    else:
        TIER_EMOJI = {"budget": "🟢", "standard": "🟡", "premium": "🔴"}
        lines = [title, ""]
        for i, e in enumerate(group):
            tier_key = e.get("tier", "")
            tier_icon = TIER_EMOJI.get(tier_key, "")
            tier_label = TIER_LABELS.get(tier_key, "")
            lines.append(
                f"{i+1}. {tier_icon} *{e['name']}* _{tier_label}_\n"
                f"   📍 {e['address']}\n"
                f"   📏 {e['distance_km']} ኪ.ሜ · 📞 {e['phone']}\n"
                f"   🕐 {e['hours']}\n"
            )
        text = "\n".join(lines)

    await update.effective_message.reply_text(
        with_footer(text),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def _resolve_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the action that was waiting for a location."""
    pending = context.user_data.pop("pending_action", None)
    if pending == "pharmacy_filter":
        filter_key = context.user_data.pop("pending_pharmacy_filter", "pharmacies_city")
        await _show_filtered_pharmacies(update, context, filter_key)
    elif pending == "nearby_pharmacies":
        await _show_nearby_pharmacies(update, context)
    elif pending == "nearest":
        await _show_nearest(update, context)
    elif pending == "search_medicine":
        lang = get_lang(context)
        context.user_data["mode"] = "search"
        await update.effective_message.reply_text(
            with_footer(t("search_prompt", lang)),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )


# ── command handlers ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["mode"] = None
    lang = get_lang(context)
    await update.message.reply_text(
        with_footer(t("welcome", lang)),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(lang),
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    context.user_data["mode"] = "report"
    context.user_data["report_step"] = "pharmacy"
    context.user_data["report_data"] = {}
    await update.message.reply_text(
        with_footer(t("report_step1", lang)),
        parse_mode="Markdown",
        reply_markup=report_pharmacy_keyboard(lang),
    )


async def nearest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "user_lat" not in context.user_data:
        await _ask_for_location(update.message, context, "nearest")
    else:
        await _show_nearest(update, context)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    msg = await update.message.reply_text(
        t("summary_generating", lang), parse_mode="Markdown"
    )
    summary_text = format_price_summary()
    await msg.delete()
    await update.message.reply_text(
        with_footer(summary_text),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
            [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
        ]),
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_lang_am", lang), callback_data="set_lang_am")],
        [InlineKeyboardButton(t("btn_lang_en", lang), callback_data="set_lang_en")],
    ])
    await update.message.reply_text(
        with_footer(t("language_choose", lang)),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── callback button handler ───────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.data == "set_lang_am":
        context.user_data["lang"] = "am"
        await query.edit_message_text(
            with_footer(t("language_set_am", "am")), parse_mode="Markdown",
            reply_markup=main_menu_keyboard("am"),
        )

    elif query.data == "set_lang_en":
        context.user_data["lang"] = "en"
        await query.edit_message_text(
            with_footer(t("language_set_en", "en")), parse_mode="Markdown",
            reply_markup=main_menu_keyboard("en"),
        )

    elif query.data == "change_language":
        await query.edit_message_text(
            with_footer(t("language_choose", lang)), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_lang_am", lang), callback_data="set_lang_am")],
                [InlineKeyboardButton(t("btn_lang_en", lang), callback_data="set_lang_en")],
            ]),
        )

    elif query.data == "send_prescription":
        context.user_data["mode"] = "prescription"
        await query.edit_message_text(
            with_footer(t("prescription_prompt", lang)), parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "search_medicine":
        context.user_data["mode"] = "search"
        await query.edit_message_text(
            with_footer(t("search_prompt", lang)), parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "nearby_pharmacies":
        context.user_data["mode"] = None
        await query.edit_message_text(
            with_footer(
                "🏥 *ቅርብ ፋርማሲዎች / Nearby Pharmacies*\n\n"
                "እባክዎ ከታች ካሉት አማራጮች ይምረጡ:\n"
                "_Please choose a filter:_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_pharmacies_nearby", lang), callback_data="pharmacies_nearby")],
                [InlineKeyboardButton(t("btn_pharmacies_kebele", lang), callback_data="pharmacies_kebele")],
                [InlineKeyboardButton(t("btn_pharmacies_city", lang), callback_data="pharmacies_city")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data in ("pharmacies_nearby", "pharmacies_kebele", "pharmacies_city"):
        context.user_data["mode"] = None
        if "user_lat" not in context.user_data:
            context.user_data["pending_action"] = "pharmacy_filter"
            context.user_data["pending_pharmacy_filter"] = query.data
            await query.edit_message_text(
                with_footer(t("location_prompt", lang)), parse_mode="Markdown",
            )
            await query.message.reply_text(
                "👇", reply_markup=location_request_keyboard(lang),
            )
        else:
            await _show_filtered_pharmacies(update, context, query.data)

    elif query.data == "price_summary":
        context.user_data["mode"] = None
        generating_msg = await query.message.reply_text(
            t("summary_generating", lang), parse_mode="Markdown"
        )
        summary_text = format_price_summary()
        await generating_msg.delete()
        await query.message.reply_text(
            with_footer(summary_text),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data == "help":
        context.user_data["mode"] = None
        await query.edit_message_text(
            with_footer(t("help_text", lang)), parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "report_price":
        context.user_data["mode"] = "report"
        context.user_data["report_step"] = "pharmacy"
        context.user_data["report_data"] = {}
        await query.edit_message_text(
            with_footer(t("report_step1", lang)), parse_mode="Markdown",
            reply_markup=report_pharmacy_keyboard(lang),
        )

    elif query.data.startswith("report_pharm_"):
        idx = int(query.data.split("_")[-1])
        pharmacy_name = PHARMACIES[idx]["name"]
        context.user_data["report_data"]["pharmacy"] = pharmacy_name
        context.user_data["report_step"] = "medicine"
        await query.edit_message_text(
            with_footer(t("report_step2", lang)) + f"\n\n🏥 _{pharmacy_name}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_back", lang), callback_data="report_price")],
            ]),
        )

    elif query.data == "back_to_menu":
        context.user_data["mode"] = None
        context.user_data.pop("report_step", None)
        context.user_data.pop("report_data", None)
        context.user_data.pop("rating_step", None)
        context.user_data.pop("rating_data", None)
        context.user_data.pop("tax_step", None)
        context.user_data.pop("tax_data", None)
        await query.edit_message_text(
            with_footer(t("welcome", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )

    elif query.data == "rate_pharmacy":
        context.user_data["mode"] = "rating"
        context.user_data["rating_step"] = "pharmacy"
        context.user_data["rating_data"] = {}
        await query.edit_message_text(
            with_footer(
                "⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                "ደረጃ 1/3 — የትኛውን ፋርማሲ ደረጃ መስጠት ትፈልጋለህ?\n"
                "_Step 1/3 — Which pharmacy would you like to rate?_"
            ),
            parse_mode="Markdown",
            reply_markup=rate_pharmacy_select_keyboard(lang),
        )

    elif query.data.startswith("rate_pharm_"):
        idx = int(query.data.split("_")[-1])
        pharmacy_name = PHARMACIES[idx]["name"]

        # ── Self-rating prevention ──────────────────────────────
        user_id = update.effective_user.id
        owner_id = PHARMACY_OWNERS.get(idx)
        if owner_id and user_id == owner_id:
            await query.answer("🚫 ራስዎ ለሚያስተዳድሩት ፋርማሲ ደረጃ መስጠት አይቻልም!", show_alert=True)
            return

        # ── Rate limit ──────────────────────────────────────────
        allowed, wait = check_rate_limit(str(user_id), "rate_pharmacy")
        if not allowed:
            await query.answer(
                f"⏳ ብዙ ጊዜ ሞክረዋል። {_fmt_wait(wait)} ቆይተው ይሞክሩ።",
                show_alert=True,
            )
            return

        context.user_data["rating_data"]["pharmacy"] = pharmacy_name
        context.user_data["rating_data"]["pharmacy_idx"] = idx
        context.user_data["rating_step"] = "stars"
        await query.edit_message_text(
            with_footer(
                f"⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                f"🏥 _{pharmacy_name}_\n\n"
                f"ደረጃ 2/3 — ምን ያህል ኮከብ ትሰጣለህ?\n"
                f"_Step 2/3 — How many stars do you give?_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐", callback_data="rate_stars_1"),
                    InlineKeyboardButton("⭐⭐", callback_data="rate_stars_2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data="rate_stars_3"),
                ],
                [
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_stars_4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_stars_5"),
                ],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="rate_pharmacy")],
            ]),
        )

    elif query.data.startswith("rate_stars_"):
        stars = int(query.data.split("_")[-1])
        context.user_data["rating_data"]["stars"] = stars
        context.user_data["rating_step"] = "comment"
        star_display = "⭐" * stars
        pharmacy_name = context.user_data["rating_data"].get("pharmacy", "")
        await query.edit_message_text(
            with_footer(
                f"⭐ *ፋርማሲ ደረጃ ስጥ / Rate a Pharmacy*\n\n"
                f"🏥 _{pharmacy_name}_  {star_display}\n\n"
                f"ደረጃ 3/3 — አስተያየትዎን ይጻፉ (አማርኛ ወይም እንግሊዝኛ)\n"
                f"_Step 3/3 — Write a short comment (optional)_\n\n"
                f"ለመዝለል «/skip» ይጻፉ\n"
                f"_Type /skip to skip_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ ዝለል (Skip)", callback_data="rate_skip_comment")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="rate_pharmacy")],
            ]),
        )

    elif query.data == "rate_skip_comment":
        await _save_rating(update, context, comment="—")

    elif query.data == "view_ratings":
        text = format_ratings_summary()
        await query.edit_message_text(
            with_footer(text),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "loyalty_points":
        context.user_data["mode"] = None
        points = get_points(context)
        level = get_level(points)
        await query.edit_message_text(
            with_footer(t("loyalty_intro", lang, points=points, level=level)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📷 QR Scan (+5 pts)", callback_data="qr_scan")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")],
            ]),
        )

    elif query.data == "qr_scan":
        # ── Rate limit ──────────────────────────────────────────
        allowed, wait = check_rate_limit(str(update.effective_user.id), "qr_scan")
        if not allowed:
            await query.answer(
                f"⏳ QR scan ብዙ ጊዜ ሞክረዋል። {_fmt_wait(wait)} ቆይተው ይሞክሩ።",
                show_alert=True,
            )
            return
        context.user_data["mode"] = "qr_scan"
        await query.edit_message_text(
            with_footer(t("qr_scan_prompt", lang)),
            parse_mode="Markdown",
            reply_markup=back_keyboard(lang),
        )

    elif query.data == "tax_report":
        context.user_data["mode"] = "tax_report"
        context.user_data["tax_step"] = "pharmacy"
        context.user_data["tax_data"] = {}
        # Build pharmacy selector keyboard
        rows, pair = [], []
        for i, ph in enumerate(PHARMACIES):
            pair.append(InlineKeyboardButton(ph["name"], callback_data=f"tax_pharm_{i}"))
            if len(pair) == 2:
                rows.append(pair); pair = []
        if pair:
            rows.append(pair)
        rows.append([InlineKeyboardButton(t("btn_back", lang), callback_data="back_to_menu")])
        await query.edit_message_text(
            with_footer(
                "🧾 *የወር ታክስ ሪፖርት / Monthly Tax Report*\n\n"
                "ደረጃ 1/4 — የትኛውን ፋርማሲ ሪፖርት ያቀርባሉ?\n"
                "_Step 1/4 — Which pharmacy are you reporting for?_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    elif query.data.startswith("tax_pharm_"):
        idx = int(query.data.split("_")[-1])
        pharmacy_name = PHARMACIES[idx]["name"]
        context.user_data["tax_data"]["pharmacy"] = pharmacy_name
        context.user_data["tax_step"] = "month"
        # Offer last 3 months automatically
        now = datetime.datetime.now()
        months = [(now - datetime.timedelta(days=30 * i)).strftime("%Y-%m") for i in range(3)]
        month_btns = [[InlineKeyboardButton(m, callback_data=f"tax_month_{m}")] for m in months]
        month_btns.append([InlineKeyboardButton(t("btn_back", lang), callback_data="tax_report")])
        await query.edit_message_text(
            with_footer(
                f"🧾 *የወር ታክስ ሪፖርት*\n\n"
                f"🏥 _{pharmacy_name}_\n\n"
                f"ደረጃ 2/4 — ምን ወር ሪፖርት ያቀርባሉ?\n"
                f"_Step 2/4 — Select the reporting month:_"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(month_btns),
        )

    elif query.data.startswith("tax_month_"):
        month = query.data.replace("tax_month_", "")
        context.user_data["tax_data"]["month"] = month
        context.user_data["tax_step"] = "sales"
        pharmacy_name = context.user_data["tax_data"].get("pharmacy", "")
        await query.edit_message_text(
            with_footer(
                f"🧾 *የወር ታክስ ሪፖርት*\n\n"
                f"🏥 _{pharmacy_name}_ · 📅 {month}\n\n"
                f"ደረጃ 3/4 — ጠቅላላ ሽያጭ (ብር) ይጻፉ\n"
                f"_Step 3/4 — Enter total sales amount in Birr:_\n\n"
                f"ምሳሌ: `25000`"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_back", lang), callback_data="tax_report")],
            ]),
        )


# ── location handler ──────────────────────────────────────────────

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    loc = update.message.location
    context.user_data["user_lat"] = loc.latitude
    context.user_data["user_lon"] = loc.longitude
    await update.message.reply_text(
        with_footer(t("location_updated", lang)), parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _resolve_pending(update, context)


# ── photo handler ─────────────────────────────────────────────────

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)

    if context.user_data.get("mode") == "qr_scan":
        context.user_data["mode"] = None
        processing_msg = await update.message.reply_text(
            "⏳ *QR እየተነበበ ነው...*\n_Reading QR code..._", parse_mode="Markdown"
        )
        try:
            photo      = update.message.photo[-1]
            photo_file = await photo.get_file()
            image_bytes = bytes(await photo_file.download_as_bytearray())

            # ── Step 1: Real QR decode via OpenCV ─────────────────
            qr_data = decode_qr_from_bytes(image_bytes)
            await processing_msg.delete()

            if not qr_data:
                await update.message.reply_text(
                    with_footer(
                        "❌ *QR ኮድ አልተገኘም! / No QR Code Found!*\n\n"
                        "📋 ፎቶው ላይ ትክክለኛ QR ኮድ የለም።\n"
                        "_No valid QR code was detected in this photo._\n\n"
                        "• ፎቶው ግልጽ እና ቀጥተኛ መሆን አለበት\n"
                        "• QR ኮዱ ሙሉ በሙሉ መታየት አለበት\n"
                        "_Make sure the QR is fully visible and in focus._"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 እንደገና ሞክር (Retry)", callback_data="qr_scan")],
                        [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                    ]),
                )
                return

            # ── Step 2: Duplicate check (image-level + QR-content) ─
            img_hash = hash_image(image_bytes)
            qr_hash  = hashlib.sha256(qr_data.encode()).hexdigest()

            if is_duplicate_receipt(img_hash):
                await update.message.reply_text(
                    with_footer(
                        "⚠️ *ደረሰኝ ቀደም ሲል ጥቅም ላይ ውሏል! / Receipt Already Used!*\n\n"
                        "🚫 ይህ ደረሰኝ ቀደም ሲል ተቆርጦ points ተወስዷል።\n"
                        "_This receipt has already been scanned and rewarded._\n\n"
                        "እያንዳንዱ ደረሰኝ አንድ ጊዜ ብቻ ይሰራል።\n"
                        "_Each receipt can only be used once._"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                    ]),
                )
                return

            if is_duplicate_receipt(qr_hash):
                await update.message.reply_text(
                    with_footer(
                        "⚠️ *የዚህ QR ደረሰኝ ቀደም ሲል ጥቅም ላይ ውሏል! / QR Already Redeemed!*\n\n"
                        "🚫 ይህ QR ኮድ ይዘት ቀደም ሲል ጥቅም ላይ ውሏል።\n"
                        "_The content of this QR has already been used._\n\n"
                        "ወደ ፋርማሲ ሄደው አዲስ ደረሰኝ ይጠይቁ።\n"
                        "_Please get a new receipt from the pharmacy._"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                    ]),
                )
                return

            # ── Step 3: Valid & new → save both hashes, award points ─
            user    = update.effective_user
            user_id = str(user.id)
            save_receipt(img_hash, qr_data, user_id)
            save_receipt(qr_hash,  qr_data, user_id)

            # Audit log
            log_path  = os.path.join(os.path.dirname(__file__), "qr_scans.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_info = f"@{user.username}" if user.username else user_id
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{timestamp}] user={user_info} | "
                    f"qr_data={qr_data[:80]} | img_hash={img_hash[:16]}...\n"
                )

            total = add_points(context, 5)
            level = get_level(total)
            await update.message.reply_text(
                with_footer(
                    "✅ *QR ተሰርቷል! / QR Verified!*\n\n"
                    "🧾 ደረሰኝዎ ተረጋግጧል!\n"
                    f"📋 QR: `{qr_data[:40]}{'...' if len(qr_data) > 40 else ''}`\n"
                    "_Your receipt has been verified!_\n\n"
                    f"🎁 *+5 Points ተጨምሮልዎታል!*\n"
                    f"📊 አጠቃላይ: *{total} pts* — {level}"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎁 የእኔ Points", callback_data="loyalty_points")],
                    [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                ]),
            )

        except Exception as e:
            logger.error(f"QR scan error: {e}")
            try:
                await processing_msg.delete()
            except Exception:
                pass
            await update.message.reply_text(
                with_footer(
                    "❌ *ስህተት ተፈጠረ / Error*\n\n"
                    "QR ኮዱን ማንበብ አልተቻለም። እንደገና ይሞክሩ።\n"
                    "_Could not process the image. Please try again._"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 እንደገና ሞክር (Retry)", callback_data="qr_scan")],
                    [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                ]),
            )
        return

    if context.user_data.get("mode") != "prescription":
        await update.message.reply_text(
            with_footer(t("photo_not_expected", lang)), parse_mode="Markdown",
            reply_markup=main_menu_keyboard(lang),
        )
        return

    context.user_data["mode"] = None
    processing_msg = await update.message.reply_text(
        t("analyzing", lang), parse_mode="Markdown",
    )

    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        image_bytes = await photo_file.download_as_bytearray()
        result = extract_medicines_from_image(bytes(image_bytes), "image/jpeg")
        await processing_msg.delete()

        response_text = (
            f"{t('prescription_analyzed', lang)}\n\n"
            f"{result}\n\n"
            f"{t('prescription_result_suffix', lang)}"
        )
        await update.message.reply_text(
            with_footer(response_text), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_search", lang), callback_data="search_medicine")],
                [InlineKeyboardButton(t("btn_pharmacies", lang), callback_data="nearby_pharmacies")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )

    except Exception as e:
        logger.error(f"Error processing prescription photo: {e}")
        err_str = str(e)
        # Show specific error hint
        if "GEMINI_API_KEY" in err_str or "API_KEY" in err_str:
            hint = "⚙️ _GEMINI_API_KEY አልተዋቀረም — Render environment variables ላይ ያስገቡ።_"
        elif "quota" in err_str.lower() or "429" in err_str:
            hint = "⏳ _Gemini API limit ደርሷል — ትንሽ ቆይቶ ይሞክሩ።_"
        elif "invalid" in err_str.lower() or "image" in err_str.lower():
            hint = "🖼️ _ፎቶው ሊነበብ አልቻለም — ፎቶውን በደንብ አንስቶ እንደገና ይሞክሩ።_"
        else:
            hint = f"🔧 _{err_str[:120]}_"
        try:
            await processing_msg.delete()
        except Exception:
            pass
        context.user_data["mode"] = "prescription"  # allow retry
        await update.message.reply_text(
            with_footer(
                f"❌ *ስህተት ተፈጠረ / Error*\n\n"
                f"{hint}\n\n"
                f"እንደገና ፎቶ ላክ ወይም ወደ ዋናው ምናሌ ተመለስ።\n"
                f"_Send the photo again or go back to main menu._"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 እንደገና ሞክር (Retry)", callback_data="send_prescription")],
                [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
            ]),
        )


# ── text handler ──────────────────────────────────────────────────

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = get_lang(context)
    text = update.message.text.strip()

    # Default-location keyboard button
    if text in (USE_DEFAULT_TEXT_AM, USE_DEFAULT_TEXT_EN):
        context.user_data["user_lat"] = BAHIR_DAR_CENTER[0]
        context.user_data["user_lon"] = BAHIR_DAR_CENTER[1]
        await update.message.reply_text(
            with_footer(t("location_updated", lang)), parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _resolve_pending(update, context)
        return

    if context.user_data.get("mode") == "tax_report":
        step = context.user_data.get("tax_step")
        data = context.user_data.setdefault("tax_data", {})

        # Rate limit on tax_report submission (check once at sales step)
        if step == "sales":
            allowed, wait = check_rate_limit(str(update.effective_user.id), "tax_report")
            if not allowed:
                await update.message.reply_text(
                    with_footer(
                        f"⏳ *ብዙ ጊዜ ሞክረዋል / Too Many Reports*\n\n"
                        f"{_fmt_wait(wait)} ቆይተው እንደገና ይሞክሩ።\n"
                        f"_Please wait {_fmt_wait(wait)} before submitting again._"
                    ),
                    parse_mode="Markdown",
                )
                context.user_data["mode"] = None
                context.user_data.pop("tax_step", None)
                context.user_data.pop("tax_data", None)
                return

        if step == "sales":
            try:
                sales = float(text.replace(",", ""))
                assert sales >= 0
            except Exception:
                await update.message.reply_text(
                    with_footer(
                        "⚠️ ትክክለኛ ቁጥር ያስገቡ (ምሳሌ: `25000`)\n"
                        "_Please enter a valid number (e.g. 25000)_"
                    ),
                    parse_mode="Markdown",
                )
                return
            data["sales"] = sales
            context.user_data["tax_step"] = "units"
            await update.message.reply_text(
                with_footer(
                    f"🧾 *የወር ታክስ ሪፖርት*\n\n"
                    f"💰 ሽያጭ: *{sales:,.0f} ብር*\n\n"
                    f"ደረጃ 4/4 — የተሸጠ ክምችት (units) ቁጥር ይጻፉ\n"
                    f"_Step 4/4 — How many units were sold?_\n\n"
                    f"ምሳሌ: `340`"
                ),
                parse_mode="Markdown",
            )
            return

        if step == "units":
            try:
                units = int(text.replace(",", ""))
                assert units >= 0
            except Exception:
                await update.message.reply_text(
                    with_footer(
                        "⚠️ ትክክለኛ ቁጥር ያስገቡ (ምሳሌ: `340`)\n"
                        "_Please enter a valid whole number_"
                    ),
                    parse_mode="Markdown",
                )
                return

            # ── Compute tax (15% VAT assumed) and save ────────────
            pharmacy  = data.get("pharmacy", "—")
            month     = data.get("month", "—")
            sales     = data.get("sales", 0.0)
            tax_paid  = round(sales * 0.15, 2)

            report_id = save_tax_report(
                pharmacy_name=pharmacy,
                user_id=str(update.effective_user.id),
                report_month=month,
                total_sales=sales,
                units_sold=units,
                tax_paid=tax_paid,
            )

            # ── Auto reconciliation against EFDA stock ────────────
            rec = reconcile_stock(pharmacy, month)
            if rec["flag"]:
                flag_tax_report(report_id)
                recon_text = (
                    f"\n\n⚠️ *ማጣጣሚያ ማስጠንቀቂያ / Reconciliation Warning!*\n"
                    f"EFDA የሰጠው: *{rec['allocated']} units*\n"
                    f"ሪፖርት የቀረበው: *{rec['reported']} units*\n"
                    f"ልዩነት: *{rec['diff']:+d} units ({rec['pct']:+.1f}%)*\n"
                    f"_ይህ ሪፖርት ለስልጣን አካሉ ለምርመራ ተልኳል።_\n"
                    f"_This report has been flagged for review._"
                )
            elif rec["allocated"] > 0:
                recon_text = (
                    f"\n\n✅ *ማጣጣሚያ OK / Reconciliation OK*\n"
                    f"EFDA የሰጠው: *{rec['allocated']} units*\n"
                    f"ሪፖርት የቀረበው: *{rec['reported']} units*"
                )
            else:
                recon_text = ""

            context.user_data["mode"] = None
            context.user_data.pop("tax_step", None)
            context.user_data.pop("tax_data", None)

            await update.message.reply_text(
                with_footer(
                    f"✅ *ሪፖርት ቀርቧል! / Report Submitted!*\n\n"
                    f"🏥 *{pharmacy}*\n"
                    f"📅 ወር: {month}\n"
                    f"💰 ሽያጭ: *{sales:,.0f} ብር*\n"
                    f"📦 የተሸጠ: *{units} units*\n"
                    f"🧾 ታክስ (15% VAT): *{tax_paid:,.2f} ብር*"
                    f"{recon_text}"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                ]),
            )
            return

    if context.user_data.get("mode") == "rating":
        step = context.user_data.get("rating_step")
        if step == "comment":
            # Sanitize comment
            safe = sanitize_text(text)
            if safe is None:
                await update.message.reply_text(
                    with_footer(
                        "⚠️ *ትክክለኛ ያልሆነ ጽሑፍ / Invalid Input*\n\n"
                        "አስተያየቱ ተቀባይነት የለውም። ትክክለኛ ጽሑፍ ያስገቡ (500 ቁምፊ ወይም ያነሰ)።\n"
                        "_Comment contains invalid characters. Please try again._"
                    ),
                    parse_mode="Markdown",
                )
                return
            comment = "—" if safe.lower() in ("/skip", "skip") else safe
            await _save_rating(update, context, comment=comment)
            return

    if context.user_data.get("mode") == "report":
        step = context.user_data.get("report_step")
        data = context.user_data.setdefault("report_data", {})

        if step == "medicine":
            safe = sanitize_text(text)
            if safe is None:
                await update.message.reply_text(
                    with_footer(
                        "⚠️ *ትክክለኛ ያልሆነ ጽሑፍ*\n_Invalid medicine name. Please try again._"
                    ),
                    parse_mode="Markdown",
                )
                return
            data["medicine"] = safe
            context.user_data["report_step"] = "price"
            await update.message.reply_text(
                with_footer(t("report_step3", lang)) + f"\n\n💊 _{safe}_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("btn_back", lang), callback_data="report_price")],
                ]),
            )
            return

        if step == "price":
            safe_price = sanitize_text(text)
            if safe_price is None:
                await update.message.reply_text(
                    with_footer(
                        "⚠️ *ትክክለኛ ያልሆነ ዋጋ*\n_Invalid price. Please enter a valid amount._"
                    ),
                    parse_mode="Markdown",
                )
                return

            # Rate limit on price reports
            allowed, wait = check_rate_limit(str(update.effective_user.id), "report_price")
            if not allowed:
                await update.message.reply_text(
                    with_footer(
                        f"⏳ *ብዙ ሪፖርቶች ቀርበዋል / Too Many Reports*\n\n"
                        f"{_fmt_wait(wait)} ቆይተው ይሞክሩ።\n"
                        f"_Wait {_fmt_wait(wait)} before reporting again._"
                    ),
                    parse_mode="Markdown",
                )
                return

            data["price"] = safe_price
            pharmacy = data.get("pharmacy", "—")
            medicine = data.get("medicine", "—")
            price    = data.get("price", "—")

            # Log the report
            log_path = os.path.join(os.path.dirname(__file__), "reports.log")
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user = update.effective_user
            user_info = f"@{user.username}" if user.username else str(user.id)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{timestamp}] user={user_info} | pharmacy={pharmacy} "
                    f"| medicine={medicine} | price={price} ብር\n"
                )

            context.user_data["mode"] = None
            context.user_data.pop("report_step", None)
            context.user_data.pop("report_data", None)

            # +20 points for price report
            total = add_points(context, 20)
            level = get_level(total)

            await update.message.reply_text(
                with_footer(
                    t("report_confirm", lang, pharmacy=pharmacy, medicine=medicine, price=price) +
                    f"\n\n🎁 *+20 Points ተጨምሮልዎታል!*\n"
                    f"📊 አጠቃላይ: *{total} pts* — {level}"
                ),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
            return

    if context.user_data.get("mode") == "search":
        context.user_data["mode"] = None

        # Sanitize input
        safe_q = sanitize_text(text)
        if safe_q is None:
            await update.message.reply_text(
                with_footer(
                    "⚠️ *ትክክለኛ ያልሆነ ጽሑፍ / Invalid Input*\n\n"
                    "የፍለጋ ቃሉ ተቀባይነት የለውም።\n"
                    "_Search query contains invalid characters._"
                ),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
            return

        # Rate limit
        allowed, wait = check_rate_limit(str(update.effective_user.id), "search")
        if not allowed:
            await update.message.reply_text(
                with_footer(
                    f"⏳ *ብዙ ፍለጋ ሞክረዋል / Too Many Searches*\n\n"
                    f"{_fmt_wait(wait)} ቆይተው ይሞክሩ።\n"
                    f"_Wait {_fmt_wait(wait)} before searching again._"
                ),
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
            return

        searching_msg = await update.message.reply_text(
            t("searching", lang, q=safe_q), parse_mode="Markdown",
        )
        try:
            lat, lon = get_user_location(context)
            result_text = smart_medicine_search(safe_q, lat, lon)
            await searching_msg.delete()
            await update.message.reply_text(
                with_footer(result_text), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("btn_search_again", lang), callback_data="search_medicine")],
                    [InlineKeyboardButton(t("btn_main_menu", lang), callback_data="back_to_menu")],
                ]),
            )
        except Exception as e:
            logger.error(f"Medicine search error: {e}")
            await searching_msg.delete()
            await update.message.reply_text(
                with_footer(t("search_error", lang)), parse_mode="Markdown",
                reply_markup=main_menu_keyboard(lang),
            )
        return

    # Fallback for unrecognised input
    await update.message.reply_text(
        with_footer(t("fallback", lang)), parse_mode="Markdown",
        reply_markup=main_menu_keyboard(lang),
    )


ADMIN_IDS_ENV = os.environ.get("ADMIN_TELEGRAM_IDS", "")
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in ADMIN_IDS_ENV.split(",") if x.strip().isdigit()
}


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /admin — summary dashboard for ንግድ ቢሮ / EFDA officers.
    Access is restricted to user IDs listed in the ADMIN_TELEGRAM_IDS env var.
    """
    user = update.effective_user
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "🚫 *ፈቃድ የለዎትም / Access Denied*\n"
            "_This command is for authorised officers only._",
            parse_mode="Markdown",
        )
        return

    conn = sqlite3.connect(DB_PATH)

    # ── 1. Total receipts scanned ─────────────────────────────────
    total_receipts = conn.execute(
        "SELECT COUNT(DISTINCT qr_data) FROM scanned_receipts"
    ).fetchone()[0]

    # ── 2. Tax reports summary ────────────────────────────────────
    tr = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(total_sales_birr),0), "
        "       COALESCE(SUM(tax_paid_birr),0), "
        "       SUM(CASE WHEN status='flagged' THEN 1 ELSE 0 END) "
        "FROM tax_reports"
    ).fetchone()
    rpt_count, total_sales, total_tax, flagged = tr

    # ── 3. Flagged reports detail (last 5) ────────────────────────
    flagged_rows = conn.execute(
        "SELECT pharmacy_name, report_month, units_sold, total_sales_birr "
        "FROM tax_reports WHERE status='flagged' ORDER BY submitted_at DESC LIMIT 5"
    ).fetchall()

    # ── 4. Top pharmacies by sales ────────────────────────────────
    top_ph = conn.execute(
        "SELECT pharmacy_name, SUM(total_sales_birr) as s "
        "FROM tax_reports GROUP BY pharmacy_name ORDER BY s DESC LIMIT 5"
    ).fetchall()

    # ── 5. QR scans per user (top 5, potential abusers) ──────────
    top_users = conn.execute(
        "SELECT user_id, COUNT(*) as c FROM scanned_receipts "
        "GROUP BY user_id ORDER BY c DESC LIMIT 5"
    ).fetchall()

    conn.close()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"🛡️ *Admin Dashboard — {now}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📷 *ደረሰኝ Scans (ጠቅላላ):* {total_receipts}",
        "",
        "🧾 *ታክስ ሪፖርቶች*",
        f"   📋 ጠቅላላ ሪፖርቶች: {rpt_count}",
        f"   💰 ጠቅላላ ሽያጭ: {total_sales:,.0f} ብር",
        f"   🏦 ጠቅላላ ታክስ: {total_tax:,.2f} ብር",
        f"   🚩 ምልክት የተደረገ: {flagged}",
    ]

    if flagged_rows:
        lines += ["", "🚩 *የተጠረጠሩ ሪፖርቶች (Flagged)*"]
        for r in flagged_rows:
            lines.append(f"   • {r[0]} | {r[1]} | {r[2]} units | {r[3]:,.0f} ብር")

    if top_ph:
        lines += ["", "🏆 *ከፍተኛ ሽያጭ ፋርማሲዎች*"]
        for i, (ph, s) in enumerate(top_ph, 1):
            lines.append(f"   {i}. {ph}: {s:,.0f} ብር")

    if top_users:
        lines += ["", "👤 *ከፍተኛ QR ስካን ተጠቃሚዎች*"]
        for uid, c in top_users:
            lines.append(f"   • user {uid}: {c} scans")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]

    await update.message.reply_text(
        with_footer("\n".join(lines)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 አዘምን (Refresh)", callback_data="admin_refresh")],
            [InlineKeyboardButton(t("btn_main_menu", get_lang(context)), callback_data="back_to_menu")],
        ]),
    )


async def admin_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button refresh — re-runs admin_command logic."""
    query = update.callback_query
    await query.answer("🔄 እያዘመነ ነው...")
    await admin_command(update, context)

async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nearest", nearest_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(admin_refresh_handler, pattern="^admin_refresh$"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot is starting...")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        threading.Thread(target=run_api_server, daemon=True).start()
        threading.Thread(target=run_self_ping, daemon=True).start()
        # Run forever
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
