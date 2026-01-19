# operators/custom_scrapers/bauwelt.py
"""
Bauwelt Custom Scraper - Visual AI Approach with Statistics
Scrapes architecture news from Bauwelt (German architecture magazine)

Site: https://www.bauwelt.de/rubriken/bauten/standard_index_2073531.html
Challenge: None - straightforward access

Visual Scraping Strategy:
1. Take screenshot of buildings section page
2. Use GPT-4o vision to extract article headlines
3. On first run: Store all headlines in database as "seen"
4. On subsequent runs: Only process NEW headlines (not in database)
5. Find headline text in HTML coupled with link using AI
6. Click link to get publication date using AI (not regex)
7. AI filtering for content quality
8. Generate statistics report and upload to R2

Usage:
    scraper = BauweltScraper()
    articles = await scraper.fetch_articles()
    await scraper.close()
"""

import asyncio
import base64
import os as os_module
from typing import Optional, List, cast
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from operators.custom_scraper_base import BaseCustomScraper, custom_scraper_registry
from storage.article_tracker import ArticleTracker
from prompts.homepage_analyzer import HOMEPAGE_ANALYZER_PROMPT_TEMPLATE, parse_headlines


class BauweltScraper(BaseCustomScraper):
    """
    Visual AI-powered custom scraper for Bauwelt
    Uses GPT-4o vision to identify articles on buildings section.
    """

    source_id = "bauwelt"
    source_name = "Bauwelt"
    base_url = "https://www.bauwelt.de/rubriken/bauten/standard_index_2073531.html"

    # Configuration: Maximum age of articles to process (in days)
    # 14 days = better for testing to get more results
    MAX_ARTICLE_AGE_DAYS = 14

    def __init__(self):
        """Initialize scraper with article tracker and vision model."""
        super().__init__()
        self.tracker: Optional[ArticleTracker] = None
        self.vision_model: Optional[ChatOpenAI] = None

    async def _ensure_tracker(self):
        """Ensure article tracker is connected."""
        if not self.tracker:
            self.tracker = ArticleTracker()
            await self.tracker.connect()

    def _ensure_vision_model(self):
        """Ensure vision model is initialized."""
        if not self.vision_model:
            import os
            api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")

            api_key_str = cast(str, api_key)

            self.vision_model = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=api_key_str,
                temperature=0.1
            )
            print(f"[{self.source_id}] Vision model initialized")

    async def _analyze_homepage_screenshot(self, screenshot_path: str) -> List[str]:
        """
        Analyze homepage screenshot with GPT-4o vision to extract headlines.

        Args:
            screenshot_path: Path to screenshot PNG

        Returns:
            List of article headlines
        """
        self._ensure_vision_model()

        print(f"[{self.source_id}] 📸 Analyzing screenshot with AI vision...")

        # Read and encode screenshot
        with open(screenshot_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        # Create vision message
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": HOMEPAGE_ANALYZER_PROMPT_TEMPLATE.format()
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_data}"
                    }
                }
            ]
        )

        # Get response
        if not self.vision_model:
            raise RuntimeError("Vision model not initialized")

        response = await asyncio.to_thread(
            self.vision_model.invoke,
            [message]
        )

        # Parse headlines
        response_text = response.content if hasattr(response, 'content') else str(response)
        if not isinstance(response_text, str):
            response_text = str(response_text)

        headlines = parse_headlines(response_text)

        print(f"[{self.source_id}] ✅ Extracted {len(headlines)} headlines from screenshot")
        return headlines

    async def _find_headline_in_html_with_ai(self, page, headline: str) -> Optional[dict]:
        """
        Use AI to find the article link for a headline by analyzing HTML context.

        Args:
            page: Playwright page object
            headline: Headline text to search for

        Returns:
            Dict with title, link, description, image or None
        """
        self._ensure_vision_model()

        # Extract relevant HTML context around potential article links
        html_context = await page.evaluate("""
            (headline) => {
                // Find all article-like containers
                const containers = document.querySelectorAll(
                    'article, .post, [class*="post"], [class*="item"], [class*="card"], [class*="teaser"]'
                );

                const articleData = [];

                containers.forEach((container, index) => {
                    // Get all links in this container
                    const links = container.querySelectorAll('a[href]');

                    if (links.length === 0) return;

                    // Get the main link (usually the first or largest)
                    let mainLink = null;
                    let mainLinkText = '';

                    links.forEach(link => {
                        const text = link.textContent.trim();
                        if (text.length > mainLinkText.length) {
                            mainLink = link;
                            mainLinkText = text;
                        }
                    });

                    if (!mainLink) return;

                    // Extract data
                    const href = mainLink.href;
                    const linkText = mainLinkText;

                    // Get description
                    const descEl = container.querySelector('p, .excerpt, [class*="excerpt"], [class*="desc"], [class*="text"]');
                    const description = descEl ? descEl.textContent.trim().substring(0, 150) : '';

                    // Get image
                    const imgEl = container.querySelector('img');
                    const imageUrl = imgEl ? imgEl.src : null;

                    // Only include if it has meaningful content
                    if (linkText.length > 5) {
                        articleData.push({
                            index: index,
                            link_text: linkText,
                            href: href,
                            description: description,
                            image_url: imageUrl
                        });
                    }
                });

                return articleData;
            }
        """, headline)

        if not html_context or len(html_context) == 0:
            print(f"      ⚠️ No article containers found on page")
            return None

        print(f"      🔍 Found {len(html_context)} article containers")

        # Format for AI
        context_text = "\n\n".join([
            f"[{item['index']}] LINK_TEXT: {item['link_text']}\n"
            f"    URL: {item['href']}\n"
            f"    EXCERPT: {item['description']}"
            for item in html_context
        ])

        # AI prompt for semantic matching
        prompt = f"""You are analyzing article containers from bauwelt.de to find which one matches a target headline.

TARGET HEADLINE: "{headline}"

AVAILABLE ARTICLE CONTAINERS:
{context_text}

Your task: Find which container index best matches the target headline.

Consider:
1. Semantic similarity (meaning, not just exact words)
2. Context clues (description, URL patterns)
3. Partial matches are OK if context is clear

Respond with ONLY the container index number (e.g., "3") or "NONE" if no good match.
Do not include any explanation."""

        if not self.vision_model:
            raise RuntimeError("Vision model not initialized")

        ai_response = await asyncio.to_thread(
            self.vision_model.invoke,
            [HumanMessage(content=prompt)]
        )

        response_text = ai_response.content if hasattr(ai_response, 'content') else str(ai_response)
        if not isinstance(response_text, str):
            response_text = str(response_text)

        response_clean = response_text.strip().upper()

        if response_clean == "NONE":
            return None

        # Extract index number
        import re
        match = re.search(r'\d+', response_clean)
        if not match:
            return None

        selected_index = int(match.group(0))

        # Find the matching container
        for item in html_context:
            if item['index'] == selected_index:
                return {
                    'title': item['link_text'],
                    'link': item['href'],
                    'description': item['description'],
                    'image_url': item['image_url']
                }

        return None

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles using visual AI approach with statistics tracking.

        Workflow:
        1. Initialize statistics tracking
        2. Screenshot buildings section page
        3. Extract headlines with GPT-4o vision
        4. Compare with stored headlines to find NEW ones (database filtering)
        5. For each new headline:
           - Find it in HTML and get the link (AI matching)
           - Click link to get publication date (AI extraction)
           - Filter by date: only keep articles within 14 days
           - Create article dict
        6. Generate and upload statistics report

        Args:
            hours: Ignored (we use database tracking instead)

        Returns:
            List of article dicts (minimal - full scraping done by scraper.py)
        """
        # Initialize statistics tracking
        self._init_stats()

        print(f"[{self.source_id}] 📸 Starting visual AI scraping...")

        await self._ensure_tracker()

        try:
            page = await self._create_page()

            try:
                # ============================================================
                # Step 1: Take Screenshot
                # ============================================================
                print(f"[{self.source_id}] Loading buildings section...")
                await page.goto(self.base_url, timeout=self.timeout, wait_until="networkidle")
                await page.wait_for_timeout(2000)

                import tempfile
                screenshot_path = os_module.path.join(tempfile.gettempdir(), f"{self.source_id}_homepage.png")

                await page.screenshot(path=screenshot_path, full_page=False)
                print(f"[{self.source_id}] 📸 Screenshot saved: {screenshot_path}")

                # Log screenshot stats and upload to R2
                if self.stats and os_module.path.exists(screenshot_path):
                    size = os_module.path.getsize(screenshot_path)

                    # Upload screenshot to R2 for audit
                    r2_path, r2_url = await self._upload_screenshot_to_r2(screenshot_path)

                    # Log with R2 info
                    self.stats.log_screenshot(screenshot_path, size, r2_path, r2_url)

                # ============================================================
                # Step 2: Extract Headlines with AI Vision
                # ============================================================
                current_headlines = await self._analyze_homepage_screenshot(screenshot_path)

                if not current_headlines:
                    print(f"[{self.source_id}] No headlines found in screenshot")
                    if self.stats:
                        self.stats.log_headlines_extracted([])
                        self.stats.log_final_count(0)
                        self.stats.print_summary()
                        await self._upload_stats_to_r2()
                    return []

                # Log extracted headlines
                if self.stats:
                    self.stats.log_headlines_extracted(current_headlines)

                # ============================================================
                # Step 3: Database Filtering - Find NEW Headlines
                # ============================================================
                if not self.tracker:
                    raise RuntimeError("Article tracker not initialized")

                seen_headlines = await self.tracker.get_stored_headlines(self.source_id)
                new_headlines = [h for h in current_headlines if h not in seen_headlines]

                print(f"[{self.source_id}] Headlines breakdown:")
                print(f"   Total extracted: {len(current_headlines)}")
                print(f"   Previously seen: {len(current_headlines) - len(new_headlines)}")
                print(f"   New to process: {len(new_headlines)}")

                # Log database filtering stats
                if self.stats:
                    self.stats.log_new_headlines(new_headlines, len(current_headlines))

                if not new_headlines:
                    print(f"[{self.source_id}] No new headlines - all previously seen")
                    if self.stats:
                        self.stats.log_final_count(0)
                        self.stats.print_summary()
                        await self._upload_stats_to_r2()
                    return []

                # Limit processing
                MAX_NEW = 10
                if len(new_headlines) > MAX_NEW:
                    print(f"[{self.source_id}] Limiting to {MAX_NEW} newest headlines")
                    new_headlines = new_headlines[:MAX_NEW]

                # ============================================================
                # Step 4: Process Each New Headline
                # ============================================================
                new_articles = []
                skipped_old = 0
                skipped_no_link = 0

                for i, headline in enumerate(new_headlines, 1):
                    print(f"\n[{self.source_id}] Processing headline {i}/{len(new_headlines)}")
                    print(f"   Headline: {headline[:60]}...")

                    try:
                        # Use AI to find this headline in HTML
                        homepage_data = await self._find_headline_in_html_with_ai(page, headline)

                        if not homepage_data or not homepage_data.get('link'):
                            print(f"      ⚠️  Could not find article link")
                            if self.stats:
                                self.stats.log_headline_match_failed(headline)
                            skipped_no_link += 1
                            continue

                        url = homepage_data['link']
                        print(f"      🔗 Found link: {url}")

                        # Log successful match
                        if self.stats:
                            self.stats.log_headline_matched(headline, url)

                        # ============================================
                        # Navigate to article to get date with AI
                        # ============================================
                        await page.goto(url, timeout=self.timeout)
                        await page.wait_for_timeout(1000)

                        # Extract article text for AI date extraction
                        article_text = await page.evaluate("""
                            () => {
                                // Get text from common date locations
                                const article = document.querySelector('article, main, .content, .post');
                                if (article) {
                                    return article.textContent.substring(0, 2000);
                                }
                                return document.body.textContent.substring(0, 2000);
                            }
                        """)

                        # Use AI to extract date
                        published = self._parse_date_with_ai(article_text)

                        if not published:
                            print(f"      ⚠️ No date found - including article anyway")
                            if self.stats:
                                self.stats.log_date_fetch_failed(headline)
                        else:
                            if self.stats:
                                self.stats.log_date_fetched(headline, url, published)

                            # DATE FILTERING: Only process articles within 14 days
                            article_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                            current_date = datetime.now(timezone.utc)
                            days_old = (current_date - article_date).days

                            if days_old > self.MAX_ARTICLE_AGE_DAYS:
                                print(f"      ⏭️  Skipping old article ({days_old} days old)")
                                skipped_old += 1
                                continue

                            print(f"      ✅ Fresh article ({days_old} day(s) old)")

                        # ============================================
                        # Create MINIMAL article dict
                        # Hero image and content will be extracted by scraper.py
                        # ============================================
                        article = self._create_minimal_article_dict(
                            title=homepage_data['title'],
                            link=url,
                            published=published
                        )

                        if self._validate_article(article):
                            new_articles.append(article)

                            # Update database with URL
                            await self.tracker.update_headline_url(
                                self.source_id,
                                headline,
                                url
                            )

                        # Small delay
                        await asyncio.sleep(0.5)

                        # Go back to buildings section for next headline
                        await page.goto(self.base_url, timeout=self.timeout)
                        await page.wait_for_timeout(1000)

                    except Exception as e:
                        print(f"      ⚠️ Error processing headline: {e}")
                        if self.stats:
                            self.stats.log_error(f"Error processing '{headline[:50]}': {str(e)}")
                        continue

                # ============================================================
                # Step 5: Store All Headlines and Generate Stats
                # ============================================================
                await self.tracker.store_headlines(self.source_id, current_headlines)

                # Final Summary
                print(f"\n[{self.source_id}] 📊 Processing Summary:")
                print(f"   Headlines extracted: {len(current_headlines)}")
                print(f"   New headlines: {len(new_headlines)}")
                print(f"   Skipped (too old): {skipped_old}")
                print(f"   Skipped (no link): {skipped_no_link}")
                print(f"   ✅ Successfully scraped: {len(new_articles)}")

                # Log final count and upload stats
                if self.stats:
                    self.stats.log_final_count(len(new_articles))
                    self.stats.print_summary()
                    await self._upload_stats_to_r2()

                return new_articles

            finally:
                await page.close()

        except Exception as e:
            print(f"[{self.source_id}] Error in visual scraping: {e}")
            if self.stats:
                self.stats.log_error(f"Critical error: {str(e)}")
                self.stats.print_summary()
                await self._upload_stats_to_r2()
            import traceback
            traceback.print_exc()
            return []

    async def close(self):
        """Close browser and tracker connections."""
        await super().close()

        if self.tracker:
            await self.tracker.close()
            self.tracker = None


# Register this scraper
custom_scraper_registry.register(BauweltScraper)


# =============================================================================
# Standalone Test
# =============================================================================

async def test_bauwelt_scraper():
    """Test the visual AI scraper with statistics."""
    print("=" * 60)
    print("Testing Bauwelt Visual AI Scraper")
    print("=" * 60)

    scraper = BauweltScraper()

    try:
        # Test connection
        print("\n1. Testing connection...")
        connected = await scraper.test_connection()

        if not connected:
            print("   ❌ Connection failed")
            return

        # Show tracker stats
        print("\n2. Checking tracker stats...")
        await scraper._ensure_tracker()

        if not scraper.tracker:
            print("   ⚠️ Tracker not initialized")
            return

        stats = await scraper.tracker.get_stats(source_id="bauwelt")

        print(f"   Total articles in database: {stats['total_articles']}")
        if stats['oldest_seen']:
            print(f"   Oldest: {stats['oldest_seen']}")
        if stats['newest_seen']:
            print(f"   Newest: {stats['newest_seen']}")

        # Fetch new articles
        print("\n3. Running visual AI scraping (max 10 new articles)...")
        articles = await scraper.fetch_articles(hours=24)

        print(f"\n   ✅ Found {len(articles)} NEW articles")

        # Display articles
        if articles:
            print("\n4. New articles:")
            for i, article in enumerate(articles, 1):
                print(f"\n   --- Article {i} ---")
                print(f"   Title: {article['title'][:60]}...")
                print(f"   Link: {article['link']}")
                print(f"   Published: {article.get('published', 'No date')}")
        else:
            print("\n4. No new articles (all previously seen)")

        print("\n" + "=" * 60)
        print("Test complete! Statistics uploaded to R2.")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_bauwelt_scraper())