import os
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════
# CONFIG — loaded from Render environment
# ══════════════════════════════════════════
GMAIL_FROM      = os.environ.get("GMAIL_FROM",    "mahamkhalid480@gmail.com")
GMAIL_PASSWORD  = os.environ.get("GMAIL_PASSWORD", "")   # App Password
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY",   "")
SUPA_URL        = os.environ.get("SUPA_URL",       "https://aahgqcrcbjddmryqptah.supabase.co")
SUPA_SERVICE_KEY= os.environ.get("SUPA_SERVICE_KEY","")

# Your Render app public URL — set this after first deploy
BACKEND_URL     = os.environ.get("BACKEND_URL",   "https://your-app.onrender.com")

ADMIN_EMAILS = [
    "mahamkhalid480@gmail.com",
    "anasjaved375@gmail.com",
    "anasjaved498@gmail.com",
    "atkajaved@gmail.com",
]

# ══════════════════════════════════════════
# EMAIL HELPER
# ══════════════════════════════════════════
def send_email(to: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_FROM
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_FROM, GMAIL_PASSWORD)
        server.sendmail(GMAIL_FROM, to, msg.as_string())

def send_to_all_admins(subject: str, html_body: str):
    errors = []
    for email in ADMIN_EMAILS:
        try:
            send_email(email, subject, html_body)
        except Exception as e:
            errors.append(f"{email}: {e}")
    return errors

# ══════════════════════════════════════════
# SUPABASE HELPERS
# ══════════════════════════════════════════
def supa_headers():
    return {
        "apikey": SUPA_SERVICE_KEY,
        "Authorization": f"Bearer {SUPA_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

async def supa_insert_review(data: dict):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{SUPA_URL}/rest/v1/reviews",
            headers=supa_headers(),
            json={
                "name":     data.get("name", "Unknown"),
                "role":     data.get("role", None),
                "review":   data.get("review", ""),
                "rating":   int(data.get("rating", 5)),
                "approved": False,
            }
        )
        res.raise_for_status()
        rows = res.json()
        return rows[0] if isinstance(rows, list) else rows

async def supa_approve_review(review_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.patch(
            f"{SUPA_URL}/rest/v1/reviews?id=eq.{review_id}",
            headers={**supa_headers(), "Prefer": "return=minimal"},
            json={"approved": True},
        )
        res.raise_for_status()

async def supa_save_chat(session_id: str, role: str, content: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPA_URL}/rest/v1/academy_chat_memory",
            headers={**supa_headers(), "Prefer": "return=minimal"},
            json={"session_id": session_id, "role": role, "content": content},
        )

async def supa_get_chat_history(session_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{SUPA_URL}/rest/v1/academy_chat_memory"
            f"?session_id=eq.{session_id}&order=created_at.desc&limit=6",
            headers=supa_headers(),
        )
        rows = res.json() if res.status_code == 200 else []
        return list(reversed(rows))

# ══════════════════════════════════════════
# GROQ CHATBOT
# ══════════════════════════════════════════
SYSTEM_PROMPT = """You are the official AI Assistant for National Academy of Science & Arts, Arifwala, Pakistan.

═══════════════════════════════════════
LANGUAGE RULE — MOST IMPORTANT
═══════════════════════════════════════
Detect the user's language from their message:
- English text → reply ONLY in English
- Urdu script (اردو) → reply ONLY in Urdu
- Roman Urdu (urdu in english letters) → reply ONLY in Roman Urdu
NEVER mix languages. NEVER reply in a different language than the user wrote in.

═══════════════════════════════════════
RESPONSE RULES
═══════════════════════════════════════
1. Keep answers SHORT — max 3-4 sentences
2. Always end with exactly ONE follow-up question relevant to what the user asked
3. Islamic greeting rules:
   - User says Salam/Assalamualaikum → reply with "Wa Alaikum Assalam!" ONLY at the START
   - User says Allah Hafiz/goodbye → reply with "Allah Hafiz!" ONLY at the END
   - User says JazakAllah → reply with "JazakAllah Khair!" ONLY at the END
   - Any other message → NO Islamic greeting at all

═══════════════════════════════════════
WHATSAPP RULE
═══════════════════════════════════════
Mention WhatsApp number 03045884090 ONLY when:
- User asks about FEES
- User asks something you do NOT know
In all other cases — DO NOT mention WhatsApp. Just answer the question.

═══════════════════════════════════════
ACADEMY INFORMATION
═══════════════════════════════════════
Name: National Academy of Science & Arts
Location: GIC House 97, Gulshan e Iqbal Colony, Arifwala, Near Savy School
Contact: 03045884090 (Phone & WhatsApp)
Timings: Monday to Saturday, 2:00 PM – 5:00 PM
Online Classes: Available for boys and girls above 9th grade

COURSES:
1. Basic Computer
2. Python Programming
3. AI & Chatbots — build AI tools, ManyChat, automation
4. Nazra Quran + Tajweed-o-Qiarat
5. Basic English — spoken and written
6. Syllabus Revision — board exam prep, Pre-Level to Bachelor's

ADMISSION POLICY:
- Girls: ALL levels welcome (in-person)
- Boys: 9th grade ONLY (in-person)
- Online: Both boys and girls ABOVE 9th grade

TEACHERS:
- Maham Khalid — English (BS Psychology)
- Aatiqa Javed — AI & Chatbots, ManyChat Expert
- Anas Javed — Python, AI Automation Developer, Nazra + Tajweed
- Humaira Javed — Physics & Mathematics

FEES: Never reveal or guess fees. Direct to WhatsApp: 03045884090
ENROLLMENT: Direct users to fill the admission form on the website."""

async def groq_chat(messages: list) -> str:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama3-8b-8192",
                    "messages": messages,
                    "max_tokens": 400,
                    "temperature": 0.7,
                },
            )
            data = res.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Groq error: {e}")
        return "Please WhatsApp us at 03045884090 for help. 😊"

# ══════════════════════════════════════════
# EMAIL HTML BUILDERS
# ══════════════════════════════════════════
def build_admission_email(d: dict) -> str:
    return f"""
<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#f9f9f9;padding:24px;border-radius:10px;">
  <div style="background:#0d9488;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
    <h1 style="color:white;margin:0;font-size:22px;">New Admission Request</h1>
    <p style="color:#ccfbf1;margin:6px 0 0;">National Academy of Science &amp; Arts 2026</p>
  </div>
  <div style="background:white;padding:24px;border-radius:0 0 8px 8px;border:1px solid #e0e0e0;">
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:10px 8px;color:#666;font-size:14px;width:38%;">Student Name</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('name','N/A')}</td></tr>
      <tr style="background:#fafafa;"><td style="padding:10px 8px;color:#666;font-size:14px;">Age</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('age','N/A')}</td></tr>
      <tr><td style="padding:10px 8px;color:#666;font-size:14px;">Parent</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('parent','N/A')}</td></tr>
      <tr style="background:#fafafa;"><td style="padding:10px 8px;color:#666;font-size:14px;">Phone</td><td style="padding:10px 8px;font-weight:bold;color:#0d9488;font-size:14px;">{d.get('phone','N/A')}</td></tr>
      <tr><td style="padding:10px 8px;color:#666;font-size:14px;">Gender</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('gender','N/A')}</td></tr>
      <tr style="background:#fafafa;"><td style="padding:10px 8px;color:#666;font-size:14px;">Class</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('class','N/A')}</td></tr>
      <tr><td style="padding:10px 8px;color:#666;font-size:14px;">Mode</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('mode','N/A')}</td></tr>
      <tr style="background:#fafafa;"><td style="padding:10px 8px;color:#666;font-size:14px;">Course</td><td style="padding:10px 8px;font-weight:bold;font-size:14px;">{d.get('course','N/A')}</td></tr>
      <tr><td style="padding:10px 8px;color:#666;font-size:14px;">Message</td><td style="padding:10px 8px;font-size:14px;">{d.get('message','None')}</td></tr>
    </table>
    <p style="margin-top:16px;color:#999;font-size:12px;text-align:center;">Sent from National Academy Website</p>
  </div>
</div>"""

def build_review_email(row: dict, approve_url: str) -> str:
    stars = "⭐" * int(row.get("rating", 5))
    return f"""
<div style="font-family:Arial,sans-serif;max-width:580px;margin:0 auto;background:#f8fafc;padding:20px;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#0d9488,#0f766e);padding:24px;border-radius:8px 8px 0 0;text-align:center;">
    <h2 style="color:white;margin:0;font-size:20px;">📝 New Review Submitted</h2>
    <p style="color:#ccfbf1;margin:6px 0 0;font-size:13px;">National Academy — Needs Your Approval</p>
  </div>
  <div style="background:white;padding:24px;border-radius:0 0 8px 8px;border:1px solid #e2e8f0;">
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="padding:10px;color:#64748b;font-size:14px;width:30%;">Name</td><td style="padding:10px;font-weight:bold;font-size:14px;">{row.get('name','')}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:10px;color:#64748b;font-size:14px;">Role</td><td style="padding:10px;font-size:14px;">{row.get('role','Not specified')}</td></tr>
      <tr><td style="padding:10px;color:#64748b;font-size:14px;">Rating</td><td style="padding:10px;font-size:18px;">{stars}</td></tr>
      <tr style="background:#f8fafc;"><td style="padding:10px;color:#64748b;font-size:14px;">Review</td><td style="padding:10px;font-size:14px;color:#1e293b;line-height:1.6;">{row.get('review','')}</td></tr>
    </table>
    <div style="text-align:center;margin-top:28px;padding-top:20px;border-top:1px solid #f1f5f9;">
      <a href="{approve_url}" style="display:inline-block;background:#059669;color:white;padding:16px 40px;border-radius:8px;text-decoration:none;font-size:16px;font-weight:bold;">✅ Approve &amp; Publish Review</a>
      <p style="margin-top:12px;color:#94a3b8;font-size:12px;">Click the button above to approve this review. It will appear on the website immediately.</p>
    </div>
  </div>
</div>"""

APPROVED_PAGE = """<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#f0fdf4,#dcfce7);min-height:100vh;display:flex;align-items:center;justify-content:center;}
.card{background:white;border-radius:16px;padding:48px 40px;text-align:center;box-shadow:0 8px 32px rgba(5,150,105,0.15);max-width:440px;width:90%;}
.icon{font-size:56px;margin-bottom:16px;}
.title{color:#059669;font-size:24px;font-weight:bold;margin-bottom:10px;}
.sub{color:#6b7280;font-size:15px;line-height:1.6;}
.note{margin-top:24px;color:#9ca3af;font-size:12px;}
</style></head>
<body><div class='card'>
  <div class='icon'>✅</div>
  <h2 class='title'>Review Approved!</h2>
  <p class='sub'>The review is now <strong>live on the website</strong>.<br>Visitors can see it immediately.</p>
  <p class='note'>You can close this tab. JazakAllah Khair 🌿</p>
</div></body></html>"""

# ══════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "National Academy Backend Running ✅"}


@app.get("/webhook/academy-chatbot", response_class=HTMLResponse)
async def approve_review(reviewId: str = ""):
    """Admin clicks approve link in email → approves review in Supabase."""
    if not reviewId:
        return HTMLResponse("<h3>Missing reviewId</h3>", status_code=400)
    try:
        await supa_approve_review(reviewId)
        return HTMLResponse(APPROVED_PAGE)
    except Exception as e:
        return HTMLResponse(f"<h3>Error: {e}</h3>", status_code=500)


@app.post("/webhook/academy-chatbot")
async def handle_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    msg_type   = body.get("type", "chat_message")
    session_id = body.get("sessionId", f"s_{uuid.uuid4().hex[:8]}")
    data       = body.get("data", {})
    message    = body.get("message", "")

    # ─── 1. ADMISSION FORM ───────────────────────────────────
    if msg_type == "admission_form":
        student_name = data.get("name", "New Student")
        html = build_admission_email(data)
        subject = f"New Admission — {student_name} | National Academy 2026"
        errors = send_to_all_admins(subject, html)
        if errors:
            print(f"Email errors: {errors}")
        return JSONResponse({
            "status": "ok",
            "message": "Admission emails sent."
        }, headers={"Access-Control-Allow-Origin": "*"})

    # ─── 2. NEW REVIEW ───────────────────────────────────────
    if msg_type == "new_review":
        try:
            row = await supa_insert_review(data)
            review_id   = row.get("id", "")
            approve_url = f"{BACKEND_URL}/webhook/academy-chatbot?reviewId={review_id}"
            html        = build_review_email(row, approve_url)
            subject     = f"✅ Approve Review — {row.get('name','')} | National Academy"
            errors = send_to_all_admins(subject, html)
            if errors:
                print(f"Review email errors: {errors}")
            return JSONResponse(
                {"status": "ok", "message": "Review received. Approval email sent."},
                headers={"Access-Control-Allow-Origin": "*"}
            )
        except Exception as e:
            print(f"Review error: {e}")
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    # ─── 3. CHAT MESSAGE ─────────────────────────────────────
    # Save user message
    await supa_save_chat(session_id, "user", message)

    # Get history
    history = await supa_get_chat_history(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for row in history[:-1]:   # exclude the message we just saved (already in prompt)
        messages.append({"role": row["role"], "content": row["content"]})
    messages.append({"role": "user", "content": message})

    reply = await groq_chat(messages)

    # Save reply
    await supa_save_chat(session_id, "assistant", reply)

    return JSONResponse(
        {"reply": reply},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


@app.options("/webhook/academy-chatbot")
async def options_handler():
    return JSONResponse(
        {},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )
