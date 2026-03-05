import os, ssl, smtplib, textwrap, datetime, sys
from email.message import EmailMessage

import certifi
import requests
from dotenv import load_dotenv
load_dotenv()

import feedparser

USE_AI = True  # set False for $0 version (headlines only)
DEBUG = "--debug" in sys.argv or os.getenv("DEBUG", "").lower() == "true"

# -------- RSS FEEDS: Global + US news (reliable, no auth required) --------
FEEDS = [
    # Global
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.cnn.com/rss/cnn_topstories.rss",
    "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    # US-specific
    "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "https://www.npr.org/rss/rss.php?id=1001",
]

MAX_ITEMS_PER_FEED = 5
TOTAL_MAX_ITEMS = 12

# -------- Email settings --------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # Gmail SSL port
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_TO = os.environ["EMAIL_TO"]
SMTP_USER = os.environ["SMTP_USER"]          # usually same as EMAIL_FROM
SMTP_PASS = os.environ["SMTP_PASS"]          # Gmail App Password recommended

# -------- Optional OpenAI summarization --------
# Requires: pip install openai
# Set OPENAI_API_KEY in environment (never commit your key!)
SCRIPT_MODE = os.getenv("SCRIPT_MODE", "true").lower() == "true"  # ~5-min script vs 6-8 bullets

def summarize_with_openai(items):
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required. Add it to .env or export it.")
    client = OpenAI(api_key=api_key)

    # Build grounded input (no web browsing by the model; only these items)
    bullets = "\n".join(
        [f"- {it['title']} ({it['source']}): {it['summary']} | {it['link']}" for it in items]
    )

    format_instruction = (
        "Write a ~5-minute spoken script (readable aloud) that covers the biggest stories."
        if SCRIPT_MODE else
        "Write ~6–8 concise story bullets for the biggest stories."
    )

    prompt = f"""
You are writing a morning news briefing email. Use ONLY the items provided. Do not add facts.

{format_instruction}
Then add a "Sources" section listing the links.

Items:
{bullets}
""".strip()

    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content or "No summary generated."

def fetch_rss_items():
    items = []
    session = requests.Session()
    session.verify = certifi.where()
    session.headers["User-Agent"] = "NewsBot/1.0 (RSS reader)"

    for url in FEEDS:
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            if DEBUG:
                print(f"  [SKIP] {url}: {e}", file=sys.stderr)
            continue

        source = feed.feed.get("title", "Unknown source")
        count = 0
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            link = entry.get("link", "") or ""
            if not link and getattr(entry, "links", None):
                link = getattr(entry.links[0], "href", "")
            link = link.strip()

            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            summary = " ".join(str(summary).split())
            summary = summary[:280] + ("..." if len(summary) > 280 else "")

            if title and link:
                items.append({"title": title, "link": link, "summary": summary, "source": source})
                count += 1

        if DEBUG:
            print(f"  [OK] {source}: {count} items", file=sys.stderr)

    if DEBUG and not items:
        print("  No items from any feed.", file=sys.stderr)

    return items[:TOTAL_MAX_ITEMS]

def format_headlines_email(items):
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it['title']} — {it['source']}\n   {it['link']}")
    body = "Today’s headlines:\n\n" + "\n\n".join(lines)
    body += "\n\nTip: Use your phone’s “Read Aloud / Speak Screen” to listen."
    return body

def send_email(subject, body):
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context(cafile=certifi.where())
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def run_briefing():
    """Fetch news, summarize (if AI enabled), send email. Returns (success, message)."""
    items = fetch_rss_items()
    today = datetime.date.today().strftime("%Y-%m-%d")
    subject = f"Morning News Briefing — {today}"

    if not items:
        send_email(subject, "No items found from RSS feeds today.")
        return True, "Email sent (no stories found)."

    if USE_AI:
        try:
            body = summarize_with_openai(items)
        except Exception as e:
            if DEBUG:
                print(f"  [FALLBACK] OpenAI failed ({e}), sending headlines instead.", file=sys.stderr)
            body = format_headlines_email(items)
    else:
        body = format_headlines_email(items)

    send_email(subject, body)
    if DEBUG:
        print(f"  [DONE] Email sent ({len(items)} stories)", file=sys.stderr)
    return True, f"Email sent to {os.environ.get('EMAIL_TO', 'you')} ({len(items)} stories)."

def main():
    ok, msg = run_briefing()
    if DEBUG:
        print(f"  {msg}", file=sys.stderr)
    return ok, msg

if __name__ == "__main__":
    main()