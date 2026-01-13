# main.py - Central entry point for the application

import asyncio
import sys

from operators.monitor import run_monitor
from storage.r2 import R2Storage
from operators.scraper import ArticleScraper

async def main():
    """Main entry point - orchestrates all operations."""
    print("🏛️ ArchNews Monitor Starting...")

    # For now, just run the monitor
    await run_monitor()

    # Later you'll add:
    # - Scheduled tasks
    # - R2 storage operations
    # - Multiple news sources
    # - Digest compilation

if __name__ == "__main__":
    asyncio.run(main())