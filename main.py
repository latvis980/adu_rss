# main.py
"""
ADUmedia RSS Pipeline

Dedicated pipeline for RSS feed sources.
Runs independently from custom scrapers pipeline.

Schedule: 18:45 Lisbon time (17:45 UTC in winter, 16:45 UTC in summer)

Pipeline:
    1. Fetch RSS feeds from configured sources
    2. Scrape full article content (Browserless)
    3. Generate AI summaries (OpenAI)
    4. AI content filtering (articles that don't pass are discarded)
    5. Download hero images
    6. Save articles to R2 storage

Usage:
    python main.py                           # Run all RSS sources
    python main.py --sources archdaily dezeen  # Run specific sources
    python main.py --tier 1                  # Run only Tier 1 sources
    python main.py --no-filter               # Skip AI filtering
    python main.py --rss-only                # Skip content scraping
    python main.py --list-sources            # Show available sources

Environment Variables (set in Railway):
    OPENAI_API_KEY              - OpenAI API key for GPT-4o-mini
    BROWSER_PLAYWRIGHT_ENDPOINT - Railway Browserless endpoint
    R2_ACCOUNT_ID               - Cloudflare R2 account ID
    R2_ACCESS_KEY_ID            - R2 access key
    R2_SECRET_ACCESS_KEY        - R2 secret key
    R2_BUCKET_NAME              - R2 bucket name
"""

import asyncio
import argparse
import aiohttp
from datetime import datetime
from typing import Optional, List

# Import operators
from operators.rss_fetcher import RSSFetcher
from operators.scraper import ArticleScraper
from operators.monitor import create_llm, summarize_article

# Import storage
from storage.r2 import R2Storage

# Import prompts and config
from prompts.summarize import SUMMARIZE_PROMPT_TEMPLATE
from prompts.filter import FILTER_PROMPT_TEMPLATE, parse_filter_response
from config.sources import (
    SOURCES,
    get_source_config,
    get_source_ids_by_tier,
    get_all_source_ids,
)

# Default configuration
DEFAULT_HOURS_LOOKBACK = 24


# =============================================================================
# Command Line Arguments
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ADUmedia RSS Pipeline"
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        help="Specific source IDs to process (e.g., archdaily dezeen)"
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2],
        help="Only process sources from this tier"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS_LOOKBACK,
        help=f"Hours to look back (default: {DEFAULT_HOURS_LOOKBACK})"
    )
    parser.add_argument(
        "--rss-only",
        action="store_true",
        help="Skip Browserless content scraping (use RSS data only)"
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Skip AI content filtering"
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="List all available RSS sources and exit"
    )

    return parser.parse_args()


# =============================================================================
# Helper Functions
# =============================================================================

def generate_summaries(articles: list, llm, prompt_template: str) -> list:
    """Generate AI summaries for articles."""
    print(f"\n📝 Generating AI summaries for {len(articles)} articles...")

    for i, article in enumerate(articles, 1):
        title = article.get("title", "No title")
        source_name = article.get("source_name", article.get("source_id", "Unknown"))
        print(f"   [{i}/{len(articles)}] [{source_name}] {title[:40]}...")

        try:
            # summarize_article expects (article, llm, prompt_template)
            summarized = summarize_article(article, llm, prompt_template)
            article["ai_summary"] = summarized.get("ai_summary", "")
            article["tags"] = summarized.get("tags", [])
        except Exception as e:
            print(f"      ⚠️ Error: {e}")
            article["ai_summary"] = article.get("description", "")[:200] + "..."
            article["tags"] = []

    return articles


def filter_articles(articles: list, llm) -> tuple[list, list]:
    """
    Filter articles using AI.

    Args:
        articles: List of articles with ai_summary
        llm: LLM instance

    Returns:
        Tuple of (included_articles, excluded_articles)
    """
    print(f"\n🔍 AI content filtering {len(articles)} articles...")

    included = []
    excluded = []

    # Create the chain once
    filter_chain = FILTER_PROMPT_TEMPLATE | llm

    for i, article in enumerate(articles, 1):
        title = article.get("title", "No title")
        source_name = article.get("source_name", article.get("source_id", "Unknown"))
        print(f"   [{i}/{len(articles)}] [{source_name}] {title[:40]}...")

        try:
            # Use the summary for filtering (more accurate than raw description)
            content_for_filter = article.get("ai_summary", "") or article.get("description", "")

            # Invoke the chain with proper parameters
            response = filter_chain.invoke({
                "title": title,
                "description": content_for_filter[:500],
                "source": source_name
            })

            result = parse_filter_response(response.content)

            if result.get("include", True):
                included.append(article)
                print(f"      ✅ Included")
            else:
                excluded.append(article)
                print(f"      ❌ Excluded: {result.get('reason', 'N/A')}")

        except Exception as e:
            print(f"      ⚠️ Filter error: {e} - including by default")
            included.append(article)

    return included, excluded


async def download_hero_images(articles: list, scraper: Optional[ArticleScraper] = None) -> list:
    """
    Download hero images for articles.

    Args:
        articles: List of articles with hero_image metadata
        scraper: Optional ArticleScraper instance (for browser-based downloads)

    Returns:
        Articles with hero_image.bytes populated
    """
    print(f"\n🖼️ Downloading hero images for {len(articles)} articles...")

    downloaded = 0
    failed = 0

    # Use aiohttp for direct image downloads (faster than browser)
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for i, article in enumerate(articles, 1):
            hero = article.get("hero_image")
            if not hero or not hero.get("url"):
                print(f"   [{i}/{len(articles)}] No hero image URL")
                continue

            image_url = hero["url"]
            title = article.get("title", "No title")[:30]

            try:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()

                        # Store bytes in hero_image dict
                        hero["bytes"] = image_bytes
                        hero["content_type"] = response.headers.get("Content-Type", "image/jpeg")

                        downloaded += 1
                        print(f"   [{i}/{len(articles)}] ✅ {title}... ({len(image_bytes)} bytes)")
                    else:
                        failed += 1
                        print(f"   [{i}/{len(articles)}] ⚠️ HTTP {response.status}: {title}...")

            except asyncio.TimeoutError:
                failed += 1
                print(f"   [{i}/{len(articles)}] ⏱️ Timeout: {title}...")
            except Exception as e:
                failed += 1
                print(f"   [{i}/{len(articles)}] ❌ Error: {title}... - {str(e)[:50]}")

    print(f"\n   📊 Downloaded: {downloaded}, Failed: {failed}")
    return articles


def save_candidates_to_r2(articles: list, r2: R2Storage) -> dict:
    """
    Save articles as editorial candidates to R2 storage.

    Args:
        articles: List of article dicts with ai_summary and hero_image.bytes
        r2: R2Storage instance

    Returns:
        Dict with saved paths
    """
    print("\n💾 Saving candidates to R2 storage...")

    # Reset counters for this batch
    r2.reset_counters()

    saved_count = 0
    image_count = 0
    candidates_info = []

    for article in articles:
        try:
            # Get hero image bytes if available
            image_bytes = None
            hero = article.get("hero_image")
            if hero and hero.get("bytes"):
                image_bytes = hero["bytes"]

            # save_candidate handles both JSON and image
            result = r2.save_candidate(
                article=article,
                image_bytes=image_bytes
            )

            candidates_info.append(result)
            saved_count += 1
            if result.get("has_image"):
                image_count += 1

        except Exception as e:
            print(f"   ❌ Error saving {article.get('title', 'unknown')[:30]}: {e}")

    # Save manifest
    if candidates_info:
        try:
            r2.save_manifest(candidates_info)
        except Exception as e:
            print(f"   ⚠️ Failed to save manifest: {e}")

    print(f"\n   📊 Saved: {saved_count} articles, {image_count} with images")
    return {"saved": saved_count, "with_images": image_count}


# =============================================================================
# Main Pipeline
# =============================================================================

async def run_pipeline(
    source_ids: Optional[list[str]] = None,
    hours: int = DEFAULT_HOURS_LOOKBACK,
    skip_scraping: bool = False,
    skip_filter: bool = False,
    tier: Optional[int] = None,
):
    """
    Run the RSS feeds pipeline.

    Args:
        source_ids: List of RSS source IDs to process (None = all)
        hours: How many hours back to look for articles
        skip_scraping: Skip Browserless content scraping
        skip_filter: Skip AI content filtering
        tier: If specified, only process sources from this tier
    """
    # Determine which sources to run
    if source_ids:
        all_sources = source_ids
    elif tier:
        all_sources = get_source_ids_by_tier(tier)
    else:
        all_sources = get_all_source_ids()

    # Validate sources exist
    valid_sources = []
    for sid in all_sources:
        config = get_source_config(sid)
        if config:
            valid_sources.append(sid)
        else:
            print(f"⚠️ Skipping {sid}: not found in config")

    if not valid_sources:
        print("❌ No valid RSS sources to run. Exiting.")
        return

    # Log pipeline start
    print(f"\n{'=' * 60}")
    print("🏛️ ADUmedia RSS Pipeline")
    print(f"{'=' * 60}")
    print(f"📅 {datetime.now().strftime('%B %d, %Y at %H:%M')}")
    print(f"📡 Sources: {len(valid_sources)}")
    if len(valid_sources) <= 10:
        print(f"   {', '.join(valid_sources)}")
    else:
        print(f"   {', '.join(valid_sources[:5])}... and {len(valid_sources)-5} more")
    print(f"⏰ Looking back: {hours} hours")
    print(f"🔍 Content filter: {'disabled' if skip_filter else 'enabled'}")
    print(f"🌐 Content scraping: {'disabled' if skip_scraping else 'enabled'}")
    print(f"{'=' * 60}")

    scraper = None
    r2 = None
    excluded_articles = []

    try:
        # Initialize R2 storage
        try:
            r2 = R2Storage()
            print("✅ R2 storage connected")
        except Exception as e:
            print(f"⚠️ R2 not configured: {e}")
            r2 = None

        # =================================================================
        # Step 1: Fetch RSS Feeds
        # =================================================================
        print("\n📡 Step 1: Fetching RSS feeds...")

        fetcher = RSSFetcher()
        articles = fetcher.fetch_all_sources(
            hours=hours,
            source_ids=valid_sources
        )

        print(f"\n📰 Total articles from RSS: {len(articles)}")

        if not articles:
            print("\n📭 No new articles found. Exiting.")
            return

        # =================================================================
        # Step 2: Scrape Full Content (includes hero image URL extraction)
        # =================================================================
        if not skip_scraping and articles:
            print("\n🌐 Step 2: Scraping full article content...")
            try:
                scraper = ArticleScraper()
                articles = await scraper.scrape_articles(articles)

                # Count articles with hero images
                hero_count = sum(1 for a in articles if a.get("hero_image"))
                print(f"   📊 Scraped {len(articles)} articles, {hero_count} with hero images")
            except Exception as e:
                print(f"   ❌ Scraping failed: {e}")
                print("   Continuing with RSS data only...")
        else:
            print("\n⏭️ Step 2: Skipping content scraping (--rss-only)")

        # =================================================================
        # Step 3: Generate AI Summaries
        # =================================================================
        print("\n📝 Step 3: Generating AI summaries...")

        try:
            llm = create_llm()
            articles = generate_summaries(articles, llm, SUMMARIZE_PROMPT_TEMPLATE)
        except Exception as e:
            print(f"   ❌ AI summarization failed: {e}")
            for article in articles:
                if not article.get("ai_summary"):
                    article["ai_summary"] = article.get("description", "")[:200] + "..."
                    article["tags"] = []

        # =================================================================
        # Step 4: AI Content Filtering (AFTER summaries)
        # =================================================================
        if not skip_filter and articles:
            print("\n🔍 Step 4: AI content filtering...")
            try:
                llm = create_llm()
                articles, excluded_articles = filter_articles(articles, llm)

                print(f"\n   📊 Filtered: {len(articles)} included, {len(excluded_articles)} excluded")

                if not articles:
                    print("\n❌ All articles filtered out. Exiting.")
                    return

            except Exception as e:
                print(f"   ❌ AI filtering failed: {e}")
                print("   Continuing with all articles...")
        else:
            print("\n⏭️ Step 4: Skipping AI filter (--no-filter)")

        # =================================================================
        # Step 5: Download Hero Images
        # =================================================================
        print("\n🖼️ Step 5: Downloading hero images...")

        try:
            articles = await download_hero_images(articles, scraper)
        except Exception as e:
            print(f"   ❌ Image download failed: {e}")
            print("   Continuing without images...")

        # =================================================================
        # Step 6: Save to R2 Storage
        # =================================================================
        if r2:
            print("\n💾 Step 6: Saving to R2 storage...")
            save_candidates_to_r2(articles, r2)
        else:
            print("\n⏭️ Step 6: Skipping R2 storage (not configured)")

        # =================================================================
        # Done
        # =================================================================
        print(f"\n{'=' * 60}")
        print("✅ Pipeline completed!")
        print(f"   📰 Articles processed: {len(articles)}")
        print(f"   🚫 Articles excluded: {len(excluded_articles)}")
        print(f"{'=' * 60}")

    finally:
        if scraper:
            await scraper.close()


# =============================================================================
# Utility Functions
# =============================================================================

def list_available_sources():
    """List all available RSS sources."""
    print("\n📋 Available RSS Sources")
    print("=" * 60)

    tier1 = get_source_ids_by_tier(1)
    tier2 = get_source_ids_by_tier(2)

    print(f"\n🥇 TIER 1 - Primary Sources ({len(tier1)}):")
    print(f"{'Source ID':<25} {'Name':<30} {'Region':<15}")
    print("-" * 70)
    for source_id in tier1:
        config = SOURCES.get(source_id, {})
        name = config.get("name", source_id)
        region = config.get("region", "global")
        print(f"{source_id:<25} {name:<30} {region:<15}")

    print(f"\n🥈 TIER 2 - Regional Sources ({len(tier2)}):")
    print(f"{'Source ID':<25} {'Name':<30} {'Region':<15}")
    print("-" * 70)
    for source_id in tier2:
        config = SOURCES.get(source_id, {})
        name = config.get("name", source_id)
        region = config.get("region", "global")
        print(f"{source_id:<25} {name:<30} {region:<15}")

    print(f"\n📊 Total: {len(tier1) + len(tier2)} RSS sources")
    print()


if __name__ == "__main__":
    args = parse_args()

    if args.list_sources:
        list_available_sources()
    else:
        asyncio.run(run_pipeline(
            source_ids=args.sources,
            hours=args.hours,
            skip_scraping=args.rss_only,
            skip_filter=args.no_filter,
            tier=args.tier,
        ))