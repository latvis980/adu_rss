# storage/scraping_stats.py
"""
Scraping Statistics Module
Tracks and reports statistics from custom scraper runs.

Statistics tracked:
- Screenshot creation details
- Headlines extracted from vision AI
- Headlines matched to HTML links
- Dates fetched from article pages
- AI filtering results (passed/rejected)

Output: JSON report uploaded to R2 bucket in "scraping" folder
"""

import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class ScrapingStats:
    """Container for scraping statistics."""

    # Source information
    source_id: str
    source_name: str
    base_url: str
    run_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Screenshot stats
    screenshot_created: bool = False
    screenshot_path: Optional[str] = None
    screenshot_size_bytes: Optional[int] = None
    screenshot_r2_path: Optional[str] = None      # <-- ADD THIS
    screenshot_r2_url: Optional[str] = None

    # Vision AI extraction stats
    headlines_extracted_count: int = 0
    headlines_extracted: List[str] = field(default_factory=list)

    # Database filtering stats
    previously_seen_count: int = 0
    new_headlines_count: int = 0
    new_headlines: List[str] = field(default_factory=list)

    # HTML matching stats
    headlines_matched_count: int = 0
    headlines_matched: List[Dict[str, str]] = field(default_factory=list)  # {headline, url}
    headlines_failed_match_count: int = 0
    headlines_failed_match: List[str] = field(default_factory=list)

    # Date extraction stats
    dates_fetched_count: int = 0
    dates_fetched: List[Dict[str, str]] = field(default_factory=list)  # {headline, date, url}
    dates_failed_count: int = 0
    dates_failed: List[str] = field(default_factory=list)

    # AI filtering stats
    articles_passed_filter_count: int = 0
    articles_passed_filter: List[Dict[str, str]] = field(default_factory=list)  # {headline, url, reason}
    articles_rejected_filter_count: int = 0
    articles_rejected_filter: List[Dict[str, str]] = field(default_factory=list)  # {headline, url, reason}

    # Final output stats
    final_articles_count: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def log_screenshot(self, path: str, size_bytes: int, r2_path: Optional[str] = None, r2_url: Optional[str] = None):
        """Log screenshot creation."""
        self.screenshot_created = True
        self.screenshot_path = path
        self.screenshot_size_bytes = size_bytes
        self.screenshot_r2_path = r2_path
        self.screenshot_r2_url = r2_url

    def log_headlines_extracted(self, headlines: List[str]):
        """Log headlines extracted from vision AI."""
        self.headlines_extracted = headlines
        self.headlines_extracted_count = len(headlines)

    def log_new_headlines(self, new_headlines: List[str], total_extracted: int):
        """Log new headlines after database filtering."""
        self.new_headlines = new_headlines
        self.new_headlines_count = len(new_headlines)
        self.previously_seen_count = total_extracted - len(new_headlines)

    def log_headline_matched(self, headline: str, url: str):
        """Log successful headline-to-URL match."""
        self.headlines_matched.append({"headline": headline, "url": url})
        self.headlines_matched_count = len(self.headlines_matched)

    def log_headline_match_failed(self, headline: str):
        """Log failed headline-to-URL match."""
        self.headlines_failed_match.append(headline)
        self.headlines_failed_match_count = len(self.headlines_failed_match)

    def log_date_fetched(self, headline: str, url: str, date: str):
        """Log successful date extraction."""
        self.dates_fetched.append({"headline": headline, "url": url, "date": date})
        self.dates_fetched_count = len(self.dates_fetched)

    def log_date_fetch_failed(self, headline: str):
        """Log failed date extraction."""
        self.dates_failed.append(headline)
        self.dates_failed_count = len(self.dates_failed)

    def log_filter_passed(self, headline: str, url: str, reason: str = "Passed filter"):
        """Log article that passed AI filter."""
        self.articles_passed_filter.append({"headline": headline, "url": url, "reason": reason})
        self.articles_passed_filter_count = len(self.articles_passed_filter)

    def log_filter_rejected(self, headline: str, url: str, reason: str = "Rejected by filter"):
        """Log article that was rejected by AI filter."""
        self.articles_rejected_filter.append({"headline": headline, "url": url, "reason": reason})
        self.articles_rejected_filter_count = len(self.articles_rejected_filter)

    def log_final_count(self, count: int):
        """Log final article count."""
        self.final_articles_count = count

    def log_error(self, error: str):
        """Log an error."""
        self.errors.append(error)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def print_summary(self):
        """Print a human-readable summary."""
        print(f"\n{'='*60}")
        print(f"📊 SCRAPING STATISTICS - {self.source_name}")
        print(f"{'='*60}")
        print(f"🕐 Run: {self.run_timestamp}")
        print(f"🌐 URL: {self.base_url}")
        print()

        if self.screenshot_created:
            size_kb = self.screenshot_size_bytes / 1024 if self.screenshot_size_bytes else 0
            print(f"📸 Screenshot: Created ({size_kb:.1f} KB)")
            if self.screenshot_r2_path:
                print(f"   R2: {self.screenshot_r2_path}")
        else:
            print(f"📸 Screenshot: Not created")

        print("🤖 Vision AI Extraction:")
        print(f"   • Total headlines extracted: {self.headlines_extracted_count}")
        if self.headlines_extracted:
            for i, h in enumerate(self.headlines_extracted[:5], 1):
                print(f"     {i}. {h[:80]}...")
            if len(self.headlines_extracted) > 5:
                print(f"     ... and {len(self.headlines_extracted) - 5} more")
        print()

        print(f"🗄️  Database Filtering:")
        print(f"   • Previously seen: {self.previously_seen_count}")
        print(f"   • New headlines: {self.new_headlines_count}")
        if self.new_headlines:
            for i, h in enumerate(self.new_headlines[:3], 1):
                print(f"     {i}. {h[:80]}...")
        print()

        print(f"🔗 HTML Matching:")
        print(f"   • Successfully matched: {self.headlines_matched_count}")
        print(f"   • Failed to match: {self.headlines_failed_match_count}")
        if self.headlines_matched:
            for match in self.headlines_matched[:3]:
                print(f"     ✅ {match['headline'][:60]}...")
                print(f"        → {match['url']}")
        if self.headlines_failed_match:
            for headline in self.headlines_failed_match[:3]:
                print(f"     ❌ {headline[:60]}...")
        print()

        print(f"📅 Date Extraction:")
        print(f"   • Dates fetched: {self.dates_fetched_count}")
        print(f"   • Date fetch failed: {self.dates_failed_count}")
        if self.dates_fetched:
            for date_info in self.dates_fetched[:3]:
                print(f"     📆 {date_info['date']} - {date_info['headline'][:50]}...")
        print()

        print(f"🎯 AI Filtering:")
        print(f"   • Passed filter: {self.articles_passed_filter_count}")
        print(f"   • Rejected: {self.articles_rejected_filter_count}")
        if self.articles_passed_filter:
            for article in self.articles_passed_filter[:3]:
                print(f"     ✅ {article['headline'][:60]}...")
        if self.articles_rejected_filter:
            for article in self.articles_rejected_filter[:3]:
                print(f"     ❌ {article['headline'][:60]}...")
                print(f"        Reason: {article['reason']}")
        print()

        print(f"📦 Final Output:")
        print(f"   • Articles returned: {self.final_articles_count}")
        print()

        if self.errors:
            print(f"⚠️  Errors:")
            for error in self.errors:
                print(f"   • {error}")
            print()

        print(f"{'='*60}\n")