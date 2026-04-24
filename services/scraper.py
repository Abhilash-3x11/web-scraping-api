import re
import asyncio
import base64
import urllib.parse
from datetime import datetime, timezone
from playwright.async_api import async_playwright


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    # 1) Sports / IPL
    if "ipl" in q or ("match" in q and _contains_any(q, SPORT_TERMS)):
        if "yesterday" in q and ("won" in q or "winner" in q):
            return ("IPL yesterday match result winner scorecard", "sports")
        if "today" in q and ("won" in q or "winner" in q):
            return ("IPL today match result winner live score", "sports")
        if "who won" in q:
            return ("IPL match winner score result", "sports")
        return (f"{query} cricket IPL score result", "sports")

    # 2) Time
    if _contains_any(q, TIME_TERMS):
        return ("current local time in India", "time")

    # 3) News
    if _contains_any(q, NEWS_TERMS):
        return (f"{query} latest updates", "news")

    return (query, "general")


def _filter_results_for_intent(results: list[dict], detected_type: str) -> list[dict]:
    if not results:
        return []

    # Always let Google's direct widgets (OneBox) bypass filters
    def passes_filter(item: dict, bad_domains: set, good_hints: set) -> bool:
        if item.get("source") == "google.com":
            return True
        url = item.get("url", "").lower()
        text = f"{item.get('title', '')} {item.get('snippet', '')} {url}".lower()
        if any(domain in url for domain in bad_domains):
            return False
        if any(hint in text for hint in good_hints):
            return True
        return False

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
async def _fetch_page_content(url: str, max_chars: int = 2000) -> str:
    # Do not try to extract text from Google's internal links/widgets
    if "google.com/search" in url:
        return ""

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(
                "wss://chrome.browserless.io?token=YOUR_API_KEY_HERE"
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-IN",
                timezone_id="Asia/Kolkata"
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                await page.evaluate("""
                    const remove = ['script','style','nav','footer',
                                    'header','aside','iframe',
                                    '.ad','[class*="cookie"]',
                                    '[class*="banner"]','[class*="popup"]'];
                    remove.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                """)
                content = ""
                for selector in ["article", "main", "[role='main']",
                                  ".article-body", ".post-content",
                                  ".entry-content", "#content", "body"]:
                    el = await page.query_selector(selector)
                    if el:
                        content = await el.inner_text()
                        content = " ".join(content.split())
                        if len(content) > 200:
                            break
                return content[:max_chars] if content else ""
            except Exception as e:
                print(f"[DEBUG] Content fetch error for {url}: {e}")
                return ""
            finally:
                await browser.close()
    except Exception as e:
        print(f"[DEBUG] Playwright content error: {e}")
        return ""


# ─────────────────────────────────────────────
# GOOGLE SEARCH (Primary & Only Web Engine)
# ─────────────────────────────────────────────
async def _do_google_search(query: str, max_results: int, detected_type: str) -> list:
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded_query}&num={max_results + 5}&hl=en&gl=in"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(
            "wss://chrome.browserless.io?token=YOUR_API_KEY_HERE"
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata", 
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"}
        )
        
        # 🔥 ADVANCED STEALTH
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
        """)

        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000) # Slightly longer wait to let heavy Sports widgets load
            print(f"[DEBUG] Google page title: {await page.title()}")

            # Extract results with Universal Fallback Parser
            results_data = await page.evaluate("""
                (typeStr) => {
                    const items = [];
                    const seenUrls = new Set();
                    
                    // 1) Extract Google's TIME widget ONLY if asked
                    if (typeStr === 'time') {
                        const timeBox = document.querySelector('div[role="heading"][aria-level="3"], .gsrt.vk_bk');
                        const locBox = document.querySelector('span.vk_gy.vk_sh');
                        if (timeBox && timeBox.textContent.match(/\\d/)) {
                            const timeText = timeBox.textContent.trim();
                            const locText = locBox ? locBox.textContent.trim() : "India (IST)";
                            items.push({
                                title: "Current Time: " + timeText + " " + locText,
                                href: "https://www.google.com/search?q=time",
                                snippet: "The exact current time is " + timeText,
                                is_onebox: true
                            });
                        }
                    }

                    // 2) Extract Google's SPORTS SCOREBOARD widget ONLY if asked
                    if (typeStr === 'sports') {
                        const sportsBox = document.querySelector('div.imso_mh__mh-xs, div.imso-loa, div[data-attrid="match_details"]');
                        if (sportsBox) {
                            const text = sportsBox.innerText.replace(/\\n/g, ' | ').replace(/\\s+/g, ' ');
                            items.push({
                                title: "Google Sports Live Status",
                                href: "https://www.google.com/search?q=sports",
                                snippet: text.substring(0, 400),
                                is_onebox: true
                            });
                        }
                    }

                    // 3) Universal Organic/News Parser (Finds ALL a > h3 tags)
                    document.querySelectorAll('a').forEach(a => {
                        const h3 = a.querySelector('h3');
                        if (h3) {
                            const title = h3.textContent.trim();
                            const href = a.getAttribute('href') || '';
                            
                            // Exclude internal Google links (Related searches, etc.)
                            if (title && href.startsWith('http') && !href.includes('google.com/search') && !seenUrls.has(href)) {
                                seenUrls.add(href);
                                
                                let snippet = '';
                                // Try to find the closest paragraph text
                                const container = a.closest('.g, .tF2Cxc, [data-sok]') || a.parentElement.parentElement;
                                if (container) {
                                    const snippetEl = container.querySelector('.VwiC3b, .yXK7lf, .MUxGbd, [style*="-webkit-line-clamp"]');
                                    if (snippetEl) snippet = snippetEl.textContent.trim();
                                }
                                
                                items.push({
                                    title: title,
                                    href: href,
                                    snippet: snippet,
                                    is_onebox: false
                                });
                            }
                        }
                    });
                    
                    return items;
                }
            """, detected_type)

            for item in results_data:
                if len(results) >= max_results:
                    break

                href = item['href']
                source = "google.com" if item.get('is_onebox') else urllib.parse.urlparse(href).netloc
                
                results.append({
                    "title": item['title'],
                    "url": href,
                    "snippet": item['snippet'],
                    "source": source
                })
                prefix = "🌟 OneBox" if item.get('is_onebox') else "✅ Google"
                print(f"[DEBUG] {prefix}: {item['title'][:60]}")

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
        browser = await p.chromium.connect_over_cdp(
            "wss://chrome.browserless.io?token=YOUR_API_KEY_HERE"
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0",
            locale="en-IN"
        )
        
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            print(f"[DEBUG] News page title: {await page.title()}")

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
    print(f"[DEBUG] Original query: {query}")
    
    rewritten_query, detected_type = _rewrite_query(query)
    print(f"[DEBUG] Rewritten query: {rewritten_query}")
    print(f"[DEBUG] Detected type: {detected_type}")
    
    # 1️⃣ Google Search (Primary & Only Web Engine)
    result = await _do_google_search(rewritten_query, max_results + 5, detected_type)
    
    # ✅ Filter results
    result = _filter_results_for_intent(result, detected_type)
    print(f"[DEBUG] Google result count after filter: {len(result)}")

    # Ensure we only return max requested
    result = result[:max_results]
    print(f"[DEBUG] Final result count before enrich: {len(result)}")
    
    if not result:
        return []

    async def enrich(item: dict) -> dict:
        raw_url = item["url"].split("#")[0]
        content = await _fetch_page_content(raw_url, 2000)
        item["content"] = content or item.get("snippet", "")
        item["detected_type"] = detected_type
        print(f"[DEBUG] Content ({len(item['content'])} chars): {item['title'][:50]}")
        return item

    enriched = await asyncio.gather(*[enrich(item) for item in result])
    return [r for r in enriched if r]


async def fetch_news_results(query: str, max_results: int = 5) -> list:
    result = await _do_news_search(query, max_results)
    print(f"[DEBUG] News result count: {len(result)}")
    return result or []


async def fetch_trends_results(query: str, max_results: int = 5) -> list:
    trend_query = f"{query} trends {datetime.now(timezone.utc).year}"
    return await fetch_google_results(trend_query, max_results)