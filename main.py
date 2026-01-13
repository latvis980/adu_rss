# main.py
"""
ArchNews Monitor - Main Entry Point

Pipeline:
    1. Fetch RSS feed (get article URLs)
    2. Scrape full article content (Browserless)
    3. Download & save hero images to R2
    4. Generate AI summaries (OpenAI)
    5. Save articles to R2 storage (Cloudflare)
    6. Send digest to Telegram

Usage:
    python main.py              # Run full pipeline
    python main.py --rss-only   # Just fetch RSS (no scraping)
"""

import asyncio
import sys
import os
from datetime import datetime

# Import operators
from operators.monitor import fetch_rss_feed, create_llm, summarize_article, ARCHDAILY_RSS_URL, HOURS_LOOKBACK
from operators.scraper import ArticleScraper

# Import storage
from storage.r2 import R2Storage

# Import Telegram
from telegram_bot import TelegramBot

# Import prompts
from prompts.summarize import SUMMARIZE_PROMPT_TEMPLATE


# =============================================================================
# Hero Image Processing
# =============================================================================

async def download_and_save_hero_images(
    articles: list[dict], 
    scraper: ArticleScraper, 
    r2: R2Storage,
    source: str = "archdaily"
) -> list[dict]:
    """Download hero images and save to R2 storage."""
    print("\n🖼️ Step 2b: Downloading hero images...")

    downloaded = 0
    failed = 0

    for i, article in enumerate(articles):
        hero_image = article.get("hero_image")

        if not hero_image or not hero_image.get("url"):
            continue

        title_preview = article.get("title", "")[:40]
        print(f"   [{i+1}/{len(articles)}] {title_preview}...")

        try:
            image_bytes = await scraper.download_hero_image(hero_image)

            if image_bytes:
                updated_hero = r2.save_hero_image(
                    image_bytes=image_bytes,
                    article=article,
                    source=source
                )

                if updated_hero:
                    article["hero_image"] = updated_hero
                    downloaded += 1
            else:
                failed += 1

        except Exception as e:
            print(f"      ⚠️ Error: {e}")
            failed += 1

        await asyncio.sleep(0.3)

    print(f"   ✅ Downloaded {downloaded} hero images ({failed} failed)")
    return articles


# =============================================================================
# Main Pipeline
# =============================================================================

async def run_pipeline(skip_scraping: bool = False):
    """Run the complete news monitoring pipeline."""
    print(f"\n{'=' * 60}")
    print("🏛️ ArchNews Monitor")
    print(f"📅 {datetime.now().strftime('%B %d, %Y at %H:%M')}")
    print(f"{'=' * 60}")

    scraper = None
    r2 = None

    try:
        # Initialize R2 storage
        try:
            r2 = R2Storage()
        except Exception as e:
            print(f"⚠️ R2 not configured: {e}")
            r2 = None

        # Step 1: Fetch RSS Feed
        print("\n📡 Step 1: Fetching RSS feed...")
        articles = fetch_rss_feed(ARCHDAILY_RSS_URL, HOURS_LOOKBACK)

        if not articles:
            print("📭 No new articles found. Exiting.")
            return

        print(f"   ✅ Found {len(articles)} articles")

        # Step 2: Scrape Full Content (optional)
        if not skip_scraping and os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT'):
            print("\n🌐 Step 2: Scraping full article content...")

            scraper = ArticleScraper(browser_pool_size=2)

            try:
                articles = await scraper.scrape_articles(articles)

                successful = sum(1 for a in articles if a.get("scrape_success"))
                hero_count = sum(1 for a in articles if a.get("hero_image"))
                print(f"   ✅ Scraped {successful}/{len(articles)} articles")
                print(f"   ✅ Found {hero_count} hero images (og:image)")

                for article in articles:
                    if article.get("scrape_success") and article.get("full_content"):
                        article["description"] = article["full_content"][:2000]

                # Step 2b: Download & Save Hero Images
                if r2 and hero_count > 0:
                    articles = await download_and_save_hero_images(
                        articles=articles,
                        scraper=scraper,
                        r2=r2,
                        source="archdaily"
                    )

            except Exception as e:
                print(f"   ⚠️ Scraping failed: {e}")
                print("   ℹ️ Continuing with RSS descriptions...")
        else:
            if skip_scraping:
                print("\n⏭️ Step 2: Skipping scraping (--rss-only mode)")
            else:
                print("\n⏭️ Step 2: Skipping scraping (Browserless not configured)")

        # Step 3: Generate AI Summaries
        print("\n🤖 Step 3: Generating AI summaries...")

        llm = create_llm()
        summarized_articles = []

        for i, article in enumerate(articles, 1):
            try:
                print(f"   [{i}/{len(articles)}] {article['title'][:50]}...")
                summarized = summarize_article(article, llm, SUMMARIZE_PROMPT_TEMPLATE)
                summarized_articles.append(summarized)
            except Exception as e:
                print(f"   ⚠️ Summary failed: {e}")
                article["ai_summary"] = article.get("description", "")[:200] + "..."
                article["tags"] = []
                summarized_articles.append(article)

        print(f"   ✅ Generated {len(summarized_articles)} summaries")

        # Step 4: Save to R2 Storage
        print("\n☁️ Step 4: Saving to Cloudflare R2...")

        if r2:
            try:
                storage_articles = []
                for article in summarized_articles:
                    hero_image_data = None
                    hero = article.get("hero_image")
                    if hero:
                        hero_image_data = {
                            "url": hero.get("url"),
                            "r2_path": hero.get("r2_path"),
                            "r2_url": hero.get("r2_url"),
                            "width": hero.get("width"),
                            "height": hero.get("height"),
                            "source": hero.get("source"),
                        }

                    storage_article = {
                        "title": article.get("title"),
                        "link": article.get("link"),
                        "published": article.get("published"),
                        "guid": article.get("guid"),
                        "ai_summary": article.get("ai_summary"),
                        "tags": article.get("tags", []),
                        "image_count": article.get("image_count", 0),
                        "hero_image": hero_image_data,
                        "images": article.get("images", [])[:3],
                        "scrape_success": article.get("scrape_success", False),
                    }
                    storage_articles.append(storage_article)

                storage_path = r2.save_articles(storage_articles, source="archdaily")
                print(f"   ✅ Saved to: {storage_path}")

                saved_heroes = sum(1 for a in storage_articles if a.get("hero_image", {}).get("r2_path"))
                if saved_heroes > 0:
                    print(f"   ✅ {saved_heroes} hero images saved to R2")

            except Exception as e:
                print(f"   ⚠️ R2 storage failed: {e}")
        else:
            print("   ⚠️ R2 not configured, skipping storage")

        # Step 5: Send to Telegram
        print("\n📱 Step 5: Sending Telegram digest...")

        try:
            bot = TelegramBot()
            results = await bot.send_digest(summarized_articles, source_name="ArchDaily")
            print(f"   ✅ Sent {results['sent']} messages")
            if results['failed'] > 0:
                print(f"   ⚠️ Failed: {results['failed']} messages")
        except Exception as e:
            print(f"   ❌ Telegram error: {e}")

        # Done
        print(f"\n{'=' * 60}")
        print("✅ Pipeline completed!")
        print(f"   📰 Articles: {len(summarized_articles)}")
        hero_saved = sum(1 for a in summarized_articles if a.get("hero_image", {}).get("r2_path"))
        if hero_saved > 0:
            print(f"   🖼️ Hero images: {hero_saved}")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"\n❌ Pipeline error: {e}")
        try:
            bot = TelegramBot()
            await bot.send_error_notification(f"Pipeline failed: {str(e)}")
        except:
            pass
        raise

    finally:
        if scraper:
            await scraper.close()


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rss-only":
        asyncio.run(run_pipeline(skip_scraping=True))
    else:
        asyncio.run(run_pipeline())