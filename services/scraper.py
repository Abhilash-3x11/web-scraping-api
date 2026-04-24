import re
import asyncio
import base64
import urllib.parse
from datetime import datetime, timezone
import pytz
from playwright.async_api import async_playwright

# ⚠️ PASTE YOUR BROWSERLESS API KEY HERE ⚠️
BROWSERLESS_URL = "wss://chrome.browserless.io/chromium?token=2UOWCOBFSNBWTTncd4bc93d4394d0b27d022c9d5351201ff1&stealth=true"

def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _get_ist_date_str() -> str:
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%B %d %Y")

def _get_ist_date_numeric() -> str:
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist).strftime("%Y-%m-%d")

# ─────────────────────────────────────────────
# DOMAINS THAT BLOCK HEADLESS BROWSERS
# ─────────────────────────────────────────────
BOT_BLOCKED_DOMAINS = {
    "iplt20.com", "cricbuzz.com", "espncricinfo.com",
    "bcci.tv", "hotstar.com", "jio.com", "cricinfo.com",
    "ndtv.com", "hindustantimes.com", "timesofindia.com"
}

# ─────────────────────────────────────────────
# QUERY NORMALIZATION / INTENT ROUTING
# ─────────────────────────────────────────────
SPORT_TERMS = {
    "ipl", "match", "score", "winner", "won", "cricket", "csk", "mi", "rcb",
    "kkr", "srh", "rr", "dc", "pbks", "gt", "lsg"
}

NEWS_TERMS = {
    "latest", "breaking", "news", "today", "yesterday", "update", "updates"
}

TIME_TERMS = {
    "time", "time now", "current time", "what time"
}

BAD_SPORT_DOMAINS = {"xe.com", "wise.com", "x-rates.com", "themoneyconverter.com", "forbes.com", "oanda.com", "exchangerates.org.uk"}
BAD_TIME_DOMAINS = {"att.com", "forums", "reddit.com", "community", "apple.com"}

GOOD_SPORT_HINTS = {"cricbuzz", "espncricinfo", "iplt20", "sports", "cricket", "score", "ndtv", "hindustantimes", "indianexpress"}
GOOD_TIME_HINTS = {"time.is", "timeanddate", "worldometer", "nist.gov", "worldtimeserver", "clock"}

def _clean_query(query: str) -> str:
    q = query.strip().lower()
    q = re.sub(r"[^\w\s?]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q

def _contains_any(q: str, terms: set[str]) -> bool:
    return any(term in q for term in terms)

def _rewrite_query(query: str) -> tuple[str, str]:
    q = _clean_query(query)
    today = _get_ist_date_str()

    if "ipl" in q or ("match" in q and _contains_any(q, SPORT_TERMS)):
        if "yesterday" in q and ("won" in q or "winner" in q):
            return (f"IPL match result winner scorecard {today}", "sports")
        if ("today" in q or "now" in q) and ("teams" in q or "playing" in q or "schedule" in q):
            return (f"IPL today match schedule playing teams {today}", "sports")
        if "today" in q and ("won" in q or "winner" in q):
            return (f"IPL today match result winner live score {today}", "sports")
        if "who won" in q:
            return (f"IPL match winner score result {today}", "sports")
        if "live" in q or "score" in q:
            return (f"{query} live score {today}", "sports")
        return (f"{query} IPL cricket {today}", "sports")

    if _contains_any(q, TIME_TERMS):
        return ("current local time in India", "time")

    if _contains_any(q, NEWS_TERMS):
        return (f"{query} {today}", "news")

    return (query, "general")

def _filter_results_for_intent(results: list[dict], detected_type: str) -> list[dict]:
    if not results:
        return []

    def passes_filter(item: dict, bad_domains: set, good_hints: set) -> bool:
        if item.get("source") == "google.com":
            return True
        url = item.get("url", "").lower()
        text = f"{item.get('title', '')} {item.get('snippet', '')} {url}".lower()
        if any(domain in url for domain in bad_domains):
            return False
        return any(hint in text for hint in good_hints)

    if detected_type == "sports":
        filtered = [item for item in results if passes_filter(item, BAD_SPORT_DOMAINS, GOOD_SPORT_HINTS)]
        return filtered or [r for r in results if not any(d in r.get("url", "").lower() for d in BAD_SPORT_DOMAINS)]

    if detected_type == "time":
        filtered = [item for item in results if passes_filter(item, BAD_TIME_DOMAINS, GOOD_TIME_HINTS)]
        return filtered or [r for r in results if not any(d in r.get("url", "").lower() for d in BAD_TIME_DOMAINS)]

    return results

# ─────────────────────────────────────────────
# CONTENT EXTRACTOR
# ─────────────────────────────────────────────
async def _fetch_page_content(url: str, snippet: str = "", max_chars: int = 2000) -> str:
    if "google.com/search" in url:
        return snippet

    parsed_domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
    if any(blocked in parsed_domain for blocked in BOT_BLOCKED_DOMAINS):
        return snippet[:max_chars]

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(BROWSERLESS_URL)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-IN",
                timezone_id="Asia/Kolkata"
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                await page.wait_for_timeout(1000)
                
                await page.evaluate("""
                    const remove = ['script','style','nav','footer',
                                    'header','aside','iframe',
                                    '.ad','[class*="cookie"]',
                                    '[class*="banner"]','[class*="popup"]'];
                    remove.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el?.remove());
                    });
                """)
                content = ""
                for selector in ["article", "main", "[role='main']", ".article-body", ".post-content", ".entry-content", "#content", "body"]:
                    el = await page.query_selector(selector)
                    if el:
                        content = await el.inner_text()
                        content = " ".join(content.split())
                        if len(content) > 200:
                            break
                return content[:max_chars] if content else snippet[:max_chars]
            except Exception:
                return snippet[:max_chars]
            finally:
                await browser.close()
    except Exception:
        return snippet[:max_chars]


# ─────────────────────────────────────────────
# GOOGLE SEARCH (Primary Web Engine)
# ─────────────────────────────────────────────
async def _do_google_search(query: str, max_results: int, detected_type: str) -> list:
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded_query}&num={max_results + 5}&hl=en&gl=in"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BROWSERLESS_URL)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )

        # 🔥 COOKIE BYPASS: Automatically accepts Google's consent screen 
        # so it never blocks the search results
        await context.add_cookies([{
            "name": "CONSENT",
            "value": "YES+cb.20230501-11-p0.en+FX+111",
            "domain": ".google.com",
            "path": "/"
        }])

        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # Ensure the actual search results have loaded
            try:
                await page.wait_for_selector("div#search, div#main", timeout=5000)
            except Exception:
                pass
                
            await page.wait_for_timeout(1000)

            # 🔥 ENHANCED PARSER: Handles Top Stories, News Carousels, and Standard Links
            results_data = await page.evaluate("""
                (typeStr) => {
                    const items = [];
                    const seenUrls = new Set();

                    // 1) Time Extraction
                    if (typeStr === 'time') {
                        const timeBox = document.querySelector('div[role="heading"][aria-level="3"], .gsrt.vk_bk');
                        const locBox = document.querySelector('span.vk_gy.vk_sh');
                        if (timeBox && timeBox.textContent.match(/\\d/)) {
                            items.push({
                                title: "Current Time: " + timeBox.textContent.trim() + (locBox ? " " + locBox.textContent.trim() : ""),
                                href: "https://www.google.com/search?q=time",
                                snippet: "The exact current time is " + timeBox.textContent.trim(),
                                is_onebox: true
                            });
                        }
                    }

                    // 2) Sports Extraction
                    if (typeStr === 'sports') {
                        const sportsBox = document.querySelector('div.imso_mh__mh-xs, div.imso-loa, div[data-attrid="match_details"], .imspo_mt__mt-t');
                        if (sportsBox) {
                            const text = sportsBox.innerText.replace(/\\n/g, ' | ').replace(/\\s+/g, ' ').trim();
                            if (text.length > 20) {
                                items.push({
                                    title: "Google Sports Live: " + text.substring(0, 80),
                                    href: "https://www.google.com/search?q=ipl+match+today",
                                    snippet: text.substring(0, 500),
                                    is_onebox: true
                                });
                            }
                        }
                    }

                    // 3) Universal Organic & News Parser
                    document.querySelectorAll('a').forEach(a => {
                        const href = a.getAttribute('href') || '';
                        
                        // Ignore internal Google links
                        if (!href.startsWith('http') || href.includes('google.com')) return;
                        if (seenUrls.has(href)) return;

                        const h3 = a.querySelector('h3');
                        const heading = a.querySelector('div[role="heading"]');
                        let title = '';

                        // Check for standard titles or Top Story Carousel titles
                        if (h3) title = h3.textContent.trim();
                        else if (heading) title = heading.textContent.trim();
                        else if (a.closest('.g') || a.closest('g-card')) {
                            title = a.textContent.trim().split('\\n')[0];
                        }

                        if (title && title.length > 10) {
                            seenUrls.add(href);
                            let snippet = '';
                            const container = a.closest('.g, g-card, .tF2Cxc, .MjjYud');
                            if (container) {
                                const snippetEl = container.querySelector('.VwiC3b, .yXK7lf, .MUxGbd, .lEBKkf, [style*="-webkit-line-clamp"]');
                                if (snippetEl) snippet = snippetEl.textContent.trim();
                            }
                            items.push({ title, href, snippet, is_onebox: false });
                        }
                    });

                    return items;
                }
            """, detected_type)

            for item in results_data:
                if len(results) >= max_results: break
                href = item['href']
                source = "google.com" if item.get('is_onebox') else urllib.parse.urlparse(href).netloc
                results.append({
                    "title": item['title'],
                    "url": href,
                    "snippet": item['snippet'],
                    "source": source
                })

        except Exception as e:
            print(f"[DEBUG] Google error: {e}")
        finally:
            await browser.close()
    
    return results

# ─────────────────────────────────────────────
# NEWS SEARCH
# ─────────────────────────────────────────────
async def _do_news_search(query: str, max_results: int) -> list:
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BROWSERLESS_URL)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
            locale="en-IN"
        )
        
        await context.add_cookies([{
            "name": "CONSENT",
            "value": "YES+cb.20230501-11-p0.en+FX+111",
            "domain": ".google.com",
            "path": "/"
        }])
        
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            articles = await page.query_selector_all("article")
            for article in articles:
                if len(results) >= max_results: break
                try:
                    title_el  = await article.query_selector("a.gPFEn, h3, h4")
                    link_el   = await article.query_selector("a")
                    source_el = await article.query_selector("div.vr1PYe, a.wEwyrc")

                    title_text = await title_el.text_content() if title_el else ""
                    href       = await link_el.get_attribute("href") if link_el else ""
                    source     = await source_el.text_content() if source_el else ""

                    if href and href.startswith("./"):
                        href = f"https://news.google.com/{href[2:]}"

                    if title_text and href:
                        results.append({
                            "title": title_text.strip(),
                            "url": href.strip(),
                            "source": source.strip(),
                            "snippet": ""
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"[DEBUG] News error: {e}")
        finally:
            await browser.close()
    return results

# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
async def fetch_google_results(query: str, max_results: int = 5) -> list:
    rewritten_query, detected_type = _rewrite_query(query)
    
    result = await _do_google_search(rewritten_query, max_results + 5, detected_type)
    result = _filter_results_for_intent(result, detected_type)
    result = result[:max_results]

    if not result:
        return []

    async def enrich(item: dict) -> dict:
        raw_url = item["url"].split("#")[0]
        snippet = item.get("snippet", "")
        content = await _fetch_page_content(raw_url, snippet, 2000)
        item["content"] = content or snippet
        item["detected_type"] = detected_type
        return item

    enriched = await asyncio.gather(*[enrich(item) for item in result])
    return [r for r in enriched if r]

async def fetch_news_results(query: str, max_results: int = 5) -> list:
    result = await _do_news_search(query, max_results)
    return result or []

async def fetch_trends_results(query: str, max_results: int = 5) -> list:
    trend_query = f"{query} trends {_get_ist_date_str()}"
    return await fetch_google_results(trend_query, max_results)