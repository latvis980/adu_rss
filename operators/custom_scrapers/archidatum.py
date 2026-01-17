# operators/custom_scrapers/archidatum.py
"""
Archidatum Custom Scraper - Visual AI Approach with Cloudscraper Fallback
Scrapes architecture news from Archidatum (African architecture magazine)

Site: https://www.archidatum.com/
Challenge: Use User-Agent, cloudscraper as fallback

Visual Scraping Strategy:
1. Use proper User-Agent headers
2. Take screenshot of homepage
3. Use GPT-4o vision to extract article headlines
4. On first run: Store all headlines in database as "seen"
5. On subsequent runs: Only process NEW headlines (not in database)
6. Find headline text in HTML coupled with link using AI
7. Click link to get publication date ONLY (hero image extracted by scraper.py)

Usage:
    scraper = ArchidatumScraper()
    articles = await scraper.fetch_articles()
    await scraper.close()
"""

import asyncio
import base64
from typing import Optional, List, cast
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from operators.custom_scraper_base import BaseCustomScraper, custom_scraper_registry
from storage.article_tracker import ArticleTracker
from prompts.homepage_analyzer import HOMEPAGE_ANALYZER_PROMPT_TEMPLATE, parse_headlines


class ArchidatumScraper(BaseCustomScraper):
    """Visual AI-powered custom scraper for Archidatum"""

    source_id = "archidatum"
    source_name = "Archidatum"
    base_url = "https://www.archidatum.com/"
    MAX_ARTICLE_AGE_DAYS = 2

    def __init__(self):
        super().__init__()
        self.tracker: Optional[ArticleTracker] = None
        self.vision_model: Optional[ChatOpenAI] = None

    async def _ensure_tracker(self):
        if not self.tracker:
            self.tracker = ArticleTracker()
            await self.tracker.connect()

    def _ensure_vision_model(self):
        if not self.vision_model:
            import os
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            self.vision_model = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)

    async def _analyze_homepage_screenshot(self, screenshot_path: str) -> List[str]:
        self._ensure_vision_model()
        with open(screenshot_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        message = HumanMessage(content=[
            {"type": "text", "text": HOMEPAGE_ANALYZER_PROMPT_TEMPLATE.format()},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
        ])
        response = await asyncio.to_thread(self.vision_model.invoke, [message])
        response_text = str(response.content if hasattr(response, 'content') else response)
        return parse_headlines(response_text)

    async def _find_headline_in_html_with_ai(self, page, headline: str) -> Optional[dict]:
        self._ensure_vision_model()
        html_context = await page.evaluate("""
            () => {
                const containers = document.querySelectorAll('article, .post, [class*="item"], [class*="card"]');
                const articleData = [];
                containers.forEach((c, i) => {
                    const links = c.querySelectorAll('a[href]');
                    let main = null, text = '';
                    links.forEach(l => {
                        const t = l.textContent.trim();
                        if (t.length > text.length) { main = l; text = t; }
                    });
                    if (main && text.length > 5) {
                        const desc = c.querySelector('p, .excerpt');
                        const img = c.querySelector('img');
                        articleData.push({index: i, link_text: text, href: main.href,
                            description: desc ? desc.textContent.trim().substring(0, 150) : '',
                            image_url: img ? img.src : null});
                    }
                });
                return articleData;
            }
        """)
        if not html_context: return None

        context = f"Looking for: '{headline}'\n\n"
        for item in html_context[:15]:
            context += f"\n[{item['index']}] {item['link_text']}\n    {item['href']}\n"

        prompt = f"{context}\n\nWhich index matches '{headline}'? Respond with ONLY the number or 'NONE'."
        ai_resp = await asyncio.to_thread(self.vision_model.invoke, [HumanMessage(content=prompt)])
        resp_text = str(ai_resp.content if hasattr(ai_resp, 'content') else ai_resp).strip().upper()

        if resp_text == "NONE": return None
        import re
        match = re.search(r'\d+', resp_text)
        if match:
            idx = int(match.group(0))
            for item in html_context:
                if item['index'] == idx:
                    return {'title': item['link_text'], 'link': item['href'],
                            'description': item['description'], 'image_url': item['image_url']}
        return None

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        await self._ensure_tracker()
        try:
            page = await self._create_page()
            # Set extra headers for anti-bot
            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })

            try:
                await page.goto(self.base_url, timeout=self.timeout, wait_until="networkidle")
                await page.wait_for_timeout(2000)

                screenshot_path = f"/tmp/{self.source_id}_homepage.png"
                await page.screenshot(path=screenshot_path, full_page=False)

                current_headlines = await self._analyze_homepage_screenshot(screenshot_path)
                if not current_headlines: return []

                seen_headlines = await self.tracker.get_stored_headlines(self.source_id)
                new_headlines = [h for h in current_headlines if h not in seen_headlines][:10]

                if not new_headlines: return []

                new_articles = []
                for i, headline in enumerate(new_headlines, 1):
                    try:
                        # ============================================
                        # STEP 1: Find headline and link with AI
                        # ============================================
                        data = await self._find_headline_in_html_with_ai(page, headline)
                        if not data or not data.get('link'): 
                            continue

                        url = data['link']
                        print(f"   [{i}/{len(new_headlines)}] {headline[:50]}...")
                        print(f"      🔗 Found link: {url}")

                        # ============================================
                        # STEP 2: Navigate to article to get date ONLY
                        # ============================================
                        await page.goto(url, timeout=self.timeout)
                        await page.wait_for_timeout(1000)

                        # Extract only the date (hero image will be handled by scraper.py)
                        date_text = await page.evaluate("""
                            () => {
                                const dateEl = document.querySelector(
                                    'time[datetime], .date, [class*="date"]'
                                );
                                return dateEl ? 
                                    (dateEl.getAttribute('datetime') || dateEl.textContent.trim()) : 
                                    null;
                            }
                        """)

                        published = self._parse_date(date_text) if date_text else None

                        # Check article age
                        if published:
                            days = (datetime.now(timezone.utc) - datetime.fromisoformat(published.replace('Z', '+00:00'))).days
                            if days > self.MAX_ARTICLE_AGE_DAYS:
                                print(f"      ⏭️ Skipping: too old ({days} days)")
                                continue

                        # ============================================
                        # STEP 3: Create MINIMAL article dict
                        # Hero image and content will be extracted by scraper.py
                        # ============================================
                        article = self._create_minimal_article_dict(
                            title=data['title'],
                            link=url,
                            published=published
                        )

                        if self._validate_article(article):
                            new_articles.append(article)
                            await self.tracker.update_headline_url(self.source_id, headline, url)
                            print(f"      ✅ Date: {published or 'unknown'}")

                        # Small delay between pages
                        await asyncio.sleep(0.5)

                        # Go back to homepage for next headline
                        await page.goto(self.base_url, timeout=self.timeout)
                        await page.wait_for_timeout(1000)

                    except Exception as e:
                        print(f"      ⚠️ Error processing {headline[:30]}: {e}")
                        continue

                # Store all current headlines as seen
                await self.tracker.store_headlines(self.source_id, current_headlines)

                print(f"[{self.source_id}] Returning {len(new_articles)} articles for pipeline processing")
                return new_articles

            finally:
                await page.close()

        except Exception as e:
            print(f"[{self.source_id}] Error: {e}")
            return []

    async def close(self):
        await super().close()
        if self.tracker:
            await self.tracker.close()
            self.tracker = None


custom_scraper_registry.register(ArchidatumScraper)