# operators/custom_scrapers/_TEMPLATE.py
"""
[SOURCE NAME] Custom Scraper Template
Copy this file and customize for your new source.

Steps to create a new custom scraper:
1. Copy this file: cp _TEMPLATE.py your_source.py
2. Update class name, source_id, source_name, base_url
3. Customize homepage scraping logic
4. Customize article page extraction (if needed)
5. Register at bottom: custom_scraper_registry.register(YourScraper)
6. Test: python your_source.py
7. Add to main.py pipeline
"""

import re
import asyncio
from typing import Optional, List
from datetime import datetime, timezone

from operators.custom_scraper_base import BaseCustomScraper, custom_scraper_registry
from storage.article_tracker import ArticleTracker


class TemplateSourceScraper(BaseCustomScraper):
    """
    Custom scraper for [SOURCE NAME]
    
    Site characteristics:
    - [Describe the site structure]
    - [Note any anti-bot measures]
    - [Publication date location: homepage/article page]
    
    Uses URL tracking to detect new articles.
    """

    # =========================================================================
    # CUSTOMIZE THESE VALUES
    # =========================================================================
    
    source_id = "template_source"  # Unique ID (lowercase, underscores)
    source_name = "Template Source"  # Display name
    base_url = "https://example.com"  # Homepage URL

    def __init__(self):
        """Initialize scraper with article tracker."""
        super().__init__()
        self.tracker: Optional[ArticleTracker] = None
    
    async def _ensure_tracker(self):
        """Ensure article tracker is connected."""
        if not self.tracker:
            self.tracker = ArticleTracker()
            await self.tracker.connect()

    # =========================================================================
    # MAIN FETCH METHOD - Customize homepage scraping
    # =========================================================================

    async def fetch_articles(self, max_new: int = 10) -> list[dict]:
        """
        Fetch new articles from homepage.
        
        Args:
            max_new: Maximum number of new articles to process
            
        Returns:
            List of article dicts (only new articles)
        """
        print(f"[{self.source_id}] Fetching new articles...")
        
        await self._ensure_tracker()
        
        try:
            page = await self._create_page()

            try:
                # ============================================================
                # STEP 1: SCRAPE HOMEPAGE for article URLs
                # ============================================================
                
                await page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.timeout)
                await page.wait_for_timeout(2000)

                # CUSTOMIZE THIS: Extract article URLs from homepage
                homepage_articles = await page.evaluate(r"""
                    () => {
                        const articles = [];

                        // CUSTOMIZE: Update selectors for your site
                        const selectors = [
                            'article',
                            '.post',
                            '.article-item',
                            '[class*="article"]'
                        ];

                        let articleElements = [];
                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            if (elements.length > 0) {
                                articleElements = Array.from(elements);
                                break;
                            }
                        }

                        articleElements.forEach(article => {
                            // CUSTOMIZE: Update selectors for title, link, etc.
                            const titleEl = article.querySelector('h1, h2, h3, .title');
                            const title = titleEl ? titleEl.textContent.trim() : '';

                            const linkEl = article.querySelector('a[href]');
                            const link = linkEl ? linkEl.href : '';

                            const excerptEl = article.querySelector('p, .excerpt');
                            const description = excerptEl ? excerptEl.textContent.trim() : '';

                            const imgEl = article.querySelector('img');
                            const imageUrl = imgEl ? imgEl.src : null;

                            if (title && link) {
                                articles.push({
                                    title: title,
                                    link: link,
                                    description: description,
                                    image_url: imageUrl,
                                });
                            }
                        });

                        return articles;
                    }
                """)

                print(f"[{self.source_id}] Found {len(homepage_articles)} articles on homepage")

                if not homepage_articles:
                    print(f"[{self.source_id}] No articles found")
                    return []

                # ============================================================
                # STEP 2: FILTER to NEW URLs only (using database)
                # ============================================================
                
                all_urls = [a['link'] for a in homepage_articles]
                new_urls = await self.tracker.filter_new_articles(self.source_id, all_urls)
                
                if not new_urls:
                    print(f"[{self.source_id}] No new articles (all URLs seen before)")
                    return []
                
                if len(new_urls) > max_new:
                    print(f"[{self.source_id}] Limiting to {max_new} articles (found {len(new_urls)})")
                    new_urls = new_urls[:max_new]
                
                print(f"[{self.source_id}] Processing {len(new_urls)} new articles")
                
                # ============================================================
                # STEP 3: EXTRACT DATES from new articles (minimal scraping)
                # ============================================================

                new_articles = []

                for i, url in enumerate(new_urls, 1):
                    homepage_data = next((a for a in homepage_articles if a['link'] == url), None)

                    if not homepage_data:
                        continue

                    print(f"   [{i}/{len(new_urls)}] {homepage_data['title'][:50]}...")

                    try:
                        # Navigate to article ONLY to get publication date
                        await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                        await page.wait_for_timeout(1000)

                        # CUSTOMIZE: Extract ONLY the publication date
                        date_metadata = await page.evaluate("""
                            () => {
                                // Try multiple date selectors
                                const dateEl = document.querySelector(
                                    'time[datetime], ' +
                                    '.date, ' +
                                    '[class*="date"], ' +
                                    '[class*="time"], ' +
                                    'meta[property="article:published_time"]'
                                );

                                if (dateEl) {
                                    // Try datetime attribute first
                                    const datetime = dateEl.getAttribute('datetime');
                                    if (datetime) return datetime;

                                    // Try meta content
                                    const content = dateEl.getAttribute('content');
                                    if (content) return content;

                                    // Fall back to text content
                                    return dateEl.textContent.trim();
                                }

                                return null;
                            }
                        """)

                        # Parse date
                        published = self._parse_date(date_metadata) if date_metadata else None

                        # Create MINIMAL article dict
                        # Hero image and content will be extracted by scraper.py
                        article = self._create_minimal_article_dict(
                            title=homepage_data['title'],
                            link=url,
                            published=published
                        )

                        if self._validate_article(article):
                            new_articles.append(article)
                            print(f"      ✅ Date: {published or 'unknown'}")

                        # Small delay between pages
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        print(f"      ⚠️ Error processing article: {e}")
                        continue

                # ============================================================
                # STEP 4: MARK all new URLs as SEEN in database
                # ============================================================

                await self.tracker.mark_as_seen(self.source_id, new_urls)

                print(f"[{self.source_id}] Returning {len(new_articles)} new articles for pipeline processing")
                return new_articles


# =========================================================================
# REGISTER SCRAPER - Uncomment when ready
# =========================================================================

# custom_scraper_registry.register(TemplateSourceScraper)


# =========================================================================
# STANDALONE TEST
# =========================================================================

async def test_scraper():
    """Test the custom scraper."""
    print("=" * 60)
    print(f"Testing {TemplateSourceScraper.source_name} Custom Scraper")
    print("=" * 60)

    scraper = TemplateSourceScraper()

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
        stats = await scraper.tracker.get_stats(source_id=scraper.source_id)
        
        print(f"   Total articles in database: {stats['total_articles']}")
        if stats['oldest_seen']:
            print(f"   Oldest: {stats['oldest_seen']}")
        if stats['newest_seen']:
            print(f"   Newest: {stats['newest_seen']}")

        # Fetch new articles
        print("\n3. Fetching new articles (max 5)...")
        articles = await scraper.fetch_articles(max_new=5)

        print(f"\n   ✅ Found {len(articles)} NEW articles")

        if articles:
            print("\n4. New articles:")
            for i, article in enumerate(articles, 1):
                print(f"\n   --- Article {i} ---")
                print(f"   Title: {article['title'][:60]}...")
                print(f"   Link: {article['link']}")
                print(f"   Published: {article.get('published', 'No date')}")
                print(f"   Hero Image: {'Yes' if article.get('hero_image') else 'No'}")
                print(f"   Description: {article.get('description', '')[:100]}...")
        else:
            print("\n4. No new articles (all previously seen)")

        # Show updated stats
        print("\n5. Updated tracker stats...")
        stats = await scraper.tracker.get_stats(source_id=scraper.source_id)
        print(f"   Total articles in database: {stats['total_articles']}")

        print("\n" + "=" * 60)
        print("Test complete!")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_scraper())
