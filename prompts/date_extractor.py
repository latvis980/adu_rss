# prompts/date_extractor.py
"""
Date Extraction Prompt
Uses AI to extract publication dates from article text in any format.
Handles multiple date formats and languages.
"""

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# System prompt for date extraction
DATE_EXTRACTOR_SYSTEM_PROMPT = """You are a date extraction specialist. Your task is to find and extract the publication date from article text.

Today's date is: {current_date}

Guidelines:
- Look for publication dates, NOT event dates or dates mentioned in article content
- Common locations: near the title, author name, or at the top/bottom of the article
- Dates can be in many formats:
  - "January 15, 2026" or "15 January 2026"
  - "2026-01-15" or "15/01/2026" or "01/15/2026"
  - "Jan 15, 2026" or "15 Jan 2026"
  - Relative: "today", "yesterday", "2 days ago"
  - Non-English: "15 janvier 2026", "15 января 2026", etc.
- If you find a relative date like "yesterday", calculate the actual date based on today's date
- If multiple dates appear, choose the one most likely to be the publication date
- Ignore dates in article content (events, historical dates, future dates)
- Do not use emoji in your response

Response format:
If you find a date, respond with ONLY the date in ISO format: YYYY-MM-DD
If you cannot find a publication date, respond with: NONE"""

# User message template
DATE_EXTRACTOR_USER_TEMPLATE = """Extract the publication date from this article text:

{article_text}

Respond with ONLY the date in ISO format (YYYY-MM-DD) or NONE if no publication date is found."""

# Combined ChatPromptTemplate for LangChain
DATE_EXTRACTOR_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(DATE_EXTRACTOR_SYSTEM_PROMPT),
    HumanMessagePromptTemplate.from_template(DATE_EXTRACTOR_USER_TEMPLATE)
])


def parse_date_response(response_text: str) -> str | None:
    """
    Parse AI date extraction response.

    Args:
        response_text: Raw AI response

    Returns:
        ISO format date string (YYYY-MM-DD) or None
    """
    import re
    from datetime import datetime

    text = response_text.strip().upper()

    # Check for NONE response
    if text == "NONE" or "NONE" in text:
        return None

    # Extract ISO format date using regex
    iso_pattern = r'(\d{4}-\d{2}-\d{2})'
    match = re.search(iso_pattern, response_text)

    if match:
        date_str = match.group(1)
        # Validate it's a real date
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            return None

    return None