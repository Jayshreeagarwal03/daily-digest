from __future__ import annotations

import json
import re
import textwrap
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import feedparser
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "DailyDigestBot/1.0 (+https://github.com/)"

TOPIC_CONFIG = {
    "big-fintech": {
        "label": "Big Fintech (IN/US)",
        "queries": [
            "(Stripe OR Block OR PayPal OR Visa OR Mastercard OR Robinhood OR Klarna) when:2d",
            "(Paytm OR PhonePe OR Razorpay OR CRED OR Pine Labs OR BharatPe) when:2d",
        ],
    },
    "vc-pe": {
        "label": "VC / PE investing",
        "queries": [
            "(venture capital OR private equity OR startup funding OR growth equity) when:2d",
            "(India venture capital OR India private equity OR startup investment India) when:3d",
        ],
    },
    "india-markets": {
        "label": "India markets",
        "queries": [
            "(Sensex OR Nifty OR NSE OR BSE) when:1d",
            "(mutual funds OR SIP OR AMC OR SEBI) when:2d",
        ],
    },
    "ai": {
        "label": "AI",
        "queries": [
            "(artificial intelligence OR OpenAI OR Anthropic OR DeepMind OR Gemini OR Copilot) when:1d",
            "(AI agents OR AI product launch) when:2d",
        ],
    },
    "digital-products": {
        "label": "Digital products",
        "queries": [
            '("digital products" OR "creator economy" OR "indie hacker" OR "micro SaaS") when:7d',
            '("side hustle" OR "Notion template" OR "newsletter monetization") when:7d',
        ],
    },
    "startup-ecosystem": {
        "label": "Startup ecosystem",
        "queries": [
            '("startup ecosystem" OR "startup trends" OR "founder trends" OR "startup India") when:3d',
            '("startup launches" OR "startup market trend" OR "emerging startup sectors") when:4d',
        ],
    },
    "jobs-skills": {
        "label": "Jobs & skills (India)",
        "queries": [
            '("India hiring" OR "job market India" OR "IT jobs India") when:7d',
            '("skills in demand India" OR "AI skills India" OR "upskilling India") when:7d',
        ],
    },
}

FALLBACK_ARTICLES = {
    "big-fintech": [
        {
            "title": "Payments and merchant software remain the big fintech wedge",
            "summary": "Fintech coverage is still clustering around merchant tools, embedded finance, and cross-sell economics. Watch for products that deepen operating workflows rather than just add payment volume.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/big-fintech",
            "published": "Apr 11",
        }
    ],
    "vc-pe": [
        {
            "title": "Capital is flowing, but quality bars remain high",
            "summary": "Investors continue to favor strong unit economics and sharper narratives around durable growth. Expect more emphasis on proof of efficiency than on pure momentum.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/vc-pe",
            "published": "Apr 11",
        }
    ],
    "india-markets": [
        {
            "title": "Retail participation still matters in the India markets story",
            "summary": "Market commentary continues to track domestic flows, mutual fund participation, and sentiment around benchmarks. The key question is how sticky those flows remain through volatility.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/india-markets",
            "published": "Apr 11",
        }
    ],
    "ai": [
        {
            "title": "AI news is increasingly about products, agents, and deployment",
            "summary": "The market is paying more attention to practical launches that change how work gets done. Agentic workflows and vertical applications keep gaining mindshare.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/ai",
            "published": "Apr 11",
        }
    ],
    "digital-products": [
        {
            "title": "Small digital products are leaning into niche audiences and bundles",
            "summary": "Creators and indie builders are combining templates, newsletters, and lightweight software into tighter monetization systems. Repeatable niche demand remains the useful signal.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/digital-products",
            "published": "Apr 11",
        }
    ],
    "startup-ecosystem": [
        {
            "title": "The ecosystem conversation keeps circling back to capital efficiency",
            "summary": "Operators are still balancing faster experimentation with disciplined spending. Distribution, retention, and focused GTM loops remain the recurring themes.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/startup-ecosystem",
            "published": "Apr 11",
        }
    ],
    "jobs-skills": [
        {
            "title": "Applied AI and business-facing technical work stay relevant in India",
            "summary": "Hiring signals continue to favor practical skills that combine technical fluency with execution. Teams are looking for people who can turn tools into outcomes.",
            "source": "Fallback Brief",
            "url": "https://example.com/fallback/jobs-skills",
            "published": "Apr 11",
        }
    ],
}


def main() -> None:
    generated_at = datetime.now(IST)
    articles = build_articles(generated_at)
    build_info = {
        "generatedAtIso": generated_at.isoformat(timespec="seconds"),
        "timezoneLabel": "IST",
    }
    rewrite_index(build_info, articles)
    print(f"Updated {INDEX_PATH} with {len(articles)} articles.")


def build_articles(generated_at: datetime) -> list[dict]:
    all_articles: list[dict] = []
    global_seen: set[str] = set()

    for topic_id, config in TOPIC_CONFIG.items():
        topic_articles: list[dict] = []
        local_seen: set[str] = set()

        for query in config["queries"]:
            for item in fetch_topic_entries(topic_id, query, generated_at):
                url = item["url"]
                if url in local_seen or url in global_seen:
                    continue
                local_seen.add(url)
                global_seen.add(url)
                topic_articles.append(item)
                if len(topic_articles) >= 4:
                    break
            if len(topic_articles) >= 4:
                break

        if not topic_articles:
            topic_articles = with_added_at(FALLBACK_ARTICLES[topic_id], generated_at)

        all_articles.extend(topic_articles[:4])

    return all_articles


def fetch_topic_entries(topic_id: str, query: str, generated_at: datetime) -> list[dict]:
    url = build_google_news_rss_url(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
    except Exception as exc:
        print(f"Failed to fetch {topic_id} query {query!r}: {exc}")
        return []

    parsed = feedparser.parse(payload)
    entries = []

    for entry in parsed.entries:
        cleaned_title, source = split_title_and_source(entry.get("title", "Untitled"))
        description = entry.get("summary", "") or entry.get("description", "")
        summary = summarize_html(description)
        raw_url = extract_entry_url(entry)
        if not raw_url:
            continue
        url = resolve_direct_url(raw_url)
        if not url:
            continue

        published_dt = parse_entry_datetime(entry) or generated_at
        entries.append(
            {
                "topicId": topic_id,
                "title": cleaned_title,
                "summary": summary,
                "source": source or extract_source(entry) or "Google News",
                "url": url,
                "published": published_dt.astimezone(IST).strftime("%b %d"),
                "addedAt": generated_at.isoformat(timespec="seconds"),
            }
        )

    return entries


def build_google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"


def extract_entry_url(entry: feedparser.FeedParserDict) -> str | None:
    link = entry.get("link")
    if link:
        return link

    for candidate in entry.get("links", []):
        href = candidate.get("href")
        if href:
            return href
    return None


def resolve_direct_url(url: str) -> str:
    if "news.google.com" not in url:
        return url

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            resolved = response.geturl()
    except Exception:
        return url

    return resolved or url


def parse_entry_datetime(entry: feedparser.FeedParserDict) -> datetime | None:
    for key in ("published", "updated"):
        value = entry.get(key)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            return dt.replace(tzinfo=IST)
        return dt
    return None


def split_title_and_source(raw_title: str) -> tuple[str, str]:
    parts = [part.strip() for part in raw_title.rsplit(" - ", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return raw_title.strip(), ""


def extract_source(entry: feedparser.FeedParserDict) -> str:
    source = entry.get("source")
    if isinstance(source, dict):
        return source.get("title", "")
    return ""


def summarize_html(html: str) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^\d+\s+(minutes?|hours?|days?)\s+ago\s+", "", text, flags=re.IGNORECASE)
    text = text.strip(" -|")
    if not text:
        return "Tap through for the latest coverage and why it matters."

    sentences = re.split(r"(?<=[.!?])\s+", text)
    compact = " ".join(sentence.strip() for sentence in sentences[:2] if sentence.strip()).strip()
    if not compact:
        compact = text
    if len(compact) > 240:
        compact = textwrap.shorten(compact, width=237, placeholder="...")
    return compact


def with_added_at(items: Iterable[dict], generated_at: datetime) -> list[dict]:
    return [
        {
            **item,
            "topicId": item.get("topicId") or infer_topic_id_from_url(item.get("url", "")),
            "published": generated_at.strftime("%b %d"),
            "addedAt": generated_at.isoformat(timespec="seconds"),
        }
        for item in items
    ]


def infer_topic_id_from_url(url: str) -> str:
    for topic_id in TOPIC_CONFIG:
        if topic_id in url:
            return topic_id
    return "ai"


def rewrite_index(build_info: dict, articles: list[dict]) -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    build_block = "const BUILD_INFO = " + json.dumps(build_info, indent=2) + ";"
    articles_block = "const ARTICLES = " + json.dumps(articles, indent=2, ensure_ascii=False) + ";"

    html = re.sub(
        r"const BUILD_INFO = \{.*?\};",
        build_block,
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"const ARTICLES = \[.*?\];",
        articles_block,
        html,
        count=1,
        flags=re.DOTALL,
    )

    INDEX_PATH.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
