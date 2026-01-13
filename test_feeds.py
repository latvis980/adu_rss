# test_feeds.py
"""
RSS Feed Tester - Standalone Script
Tests all 30 configured RSS feeds without requiring browser or API keys.

Run from Replit:
    python test_feeds.py

Requirements: pip install feedparser
"""

import feedparser
import time
from datetime import datetime


# All 30 sources with RSS feeds
SOURCES_TO_TEST = [
    # Tier 1 - Primary Sources
    ("archdaily", "https://feeds.feedburner.com/Archdaily", "ArchDaily", 1),
    ("dezeen", "http://feeds.feedburner.com/dezeen", "Dezeen", 1),
    ("designboom", "https://www.designboom.com/feed", "Designboom", 1),
    ("archpaper", "https://www.archpaper.com/feed", "The Architect's Newspaper", 1),
    ("architects_journal", "https://www.architectsjournal.co.uk/feed", "The Architects' Journal", 1),
    
    # Tier 2 - North America
    ("architectural_record", "https://www.architecturalrecord.com/rss/headlines", "Architectural Record", 2),
    ("metropolis", "https://metropolismag.com/feed/", "Metropolis", 2),
    ("canadian_architect", "https://www.canadianarchitect.com/feed/", "Canadian Architect", 2),
    ("places_journal", "https://placesjournal.org/feed/", "Places Journal", 2),
    ("design_milk", "http://feeds.feedburner.com/design-milk", "Design Milk", 2),
    ("leibal", "https://leibal.com/feed/", "Leibal", 2),
    
    # Tier 2 - Europe
    ("architectural_review", "https://www.architectural-review.com/feed", "The Architectural Review", 2),
    ("domus", "https://www.domusweb.it/en.rss.xml", "Domus", 2),
    ("metalocus", "https://www.metalocus.es/en/feed", "Metalocus", 2),
    ("landezine", "http://www.landezine.com/feed", "Landezine", 2),
    ("aasarchitecture", "https://aasarchitecture.com/feed/", "A As Architecture", 2),
    ("archiru", "https://archi.ru/rss", "Archi.ru", 2),
    
    # Tier 2 - Asia-Pacific
    ("yellowtrace", "https://www.yellowtrace.com.au/feed", "Yellowtrace", 2),
    ("architectureau", "https://architectureau.com/rss.xml", "ArchitectureAU", 2),
    ("architecture_now", "https://architecturenow.co.nz/rss.xml", "Architecture Now", 2),
    ("architecture_update", "https://architectureupdate.in/feed", "Architecture Update", 2),
    ("spoon_tamago", "https://spoon-tamago.com/feed/", "Spoon & Tamago", 2),
    ("indesignlive_sg", "https://www.indesignlive.sg/feed", "Indesign Live Singapore", 2),
    
    # Tier 2 - Latin America, Africa, Middle East
    ("archdaily_brasil", "https://www.archdaily.com.br/br/feed", "ArchDaily Brasil", 2),
    ("arquine", "https://arquine.com/feed/", "Arquine", 2),
    ("archidatum", "https://www.archidatum.com/feed/", "Archidatum", 2),
    ("parametric_architecture", "https://parametric-architecture.com/feed/", "Parametric Architecture", 2),
    
    # Tier 2 - Urbanism & Technical
    ("planetizen", "https://www.planetizen.com/rss/news", "Planetizen", 2),
    ("next_city", "https://nextcity.org/rss", "Next City", 2),
    ("construction_specifier", "https://www.constructionspecifier.com/feed/", "The Construction Specifier", 2),
]


def test_single_feed(source_id: str, rss_url: str, name: str) -> dict:
    """Test a single RSS feed."""
    result = {
        "source_id": source_id,
        "name": name,
        "url": rss_url,
        "success": False,
        "entries": 0,
        "error": None,
    }
    
    try:
        feed = feedparser.parse(rss_url)
        
        if feed.bozo and not feed.entries:
            result["error"] = str(feed.bozo_exception)[:80]
            return result
        
        result["success"] = True
        result["entries"] = len(feed.entries)
        
        if feed.entries:
            result["sample"] = feed.entries[0].get("title", "")[:50]
        
    except Exception as e:
        result["error"] = str(e)[:80]
    
    return result


def main():
    """Test all RSS feeds."""
    print("=" * 70)
    print("RSS FEED TESTER")
    print(f"Testing {len(SOURCES_TO_TEST)} feeds")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = []
    tier1_ok = 0
    tier1_fail = 0
    tier2_ok = 0
    tier2_fail = 0
    
    print("\n--- TIER 1 (Primary Sources) ---")
    for source_id, rss_url, name, tier in SOURCES_TO_TEST:
        if tier != 1:
            continue
            
        print(f"  {name}...", end=" ", flush=True)
        result = test_single_feed(source_id, rss_url, name)
        result["tier"] = tier
        results.append(result)
        
        if result["success"]:
            tier1_ok += 1
            print(f"OK ({result['entries']} articles)")
        else:
            tier1_fail += 1
            print(f"FAILED: {result['error']}")
        
        time.sleep(0.3)
    
    print("\n--- TIER 2 (Regional/Specialty) ---")
    for source_id, rss_url, name, tier in SOURCES_TO_TEST:
        if tier != 2:
            continue
            
        print(f"  {name}...", end=" ", flush=True)
        result = test_single_feed(source_id, rss_url, name)
        result["tier"] = tier
        results.append(result)
        
        if result["success"]:
            tier2_ok += 1
            print(f"OK ({result['entries']} articles)")
        else:
            tier2_fail += 1
            print(f"FAILED: {result['error']}")
        
        time.sleep(0.3)
    
    # Summary
    total_ok = tier1_ok + tier2_ok
    total_fail = tier1_fail + tier2_fail
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Tier 1: {tier1_ok}/{tier1_ok + tier1_fail} working")
    print(f"Tier 2: {tier2_ok}/{tier2_ok + tier2_fail} working")
    print(f"Total:  {total_ok}/{len(SOURCES_TO_TEST)} feeds working")
    
    print("\n--- WORKING FEEDS ---")
    working = [r for r in results if r["success"]]
    for r in working:
        tier_label = "T1" if r["tier"] == 1 else "T2"
        print(f'  "{r["source_id"]}",  # {r["name"]} [{tier_label}]')
    
    if total_fail > 0:
        print("\n--- FAILED FEEDS ---")
        failed = [r for r in results if not r["success"]]
        for r in failed:
            print(f'  {r["name"]}: {r["error"]}')
    
    return results


if __name__ == "__main__":
    main()
