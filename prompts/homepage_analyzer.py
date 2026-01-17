# prompts/homepage_analyzer.py
"""
Visual Homepage Analysis Prompt
Uses GPT-4o (vision) to analyze homepage screenshots and extract article titles.

This is used by custom scrapers to visually identify article headlines
on homepages where the HTML structure is unclear or inconsistent.
"""

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# System prompt for visual homepage analysis
HOMEPAGE_ANALYZER_SYSTEM_PROMPT = """You are a web scraping assistant that analyzes homepage screenshots to identify article headlines.

Your task is to examine a screenshot of a news/blog homepage and extract the visible article titles/headlines.

Guidelines:
- Look for text that appears to be article headlines (larger font, prominent placement)
- Ignore navigation menus, footer links, sidebar content, ads
- Ignore section labels — they can sometimes appear above the actual headline. The clue is that they are usually smaller and often appear on the page several times. 
- Focus on the main content area where articles are listed
- Each headline should be distinct (not repeated navigation items)
- Return ONLY the headlines, one per line
- Do not change wording, copy the headline EXACLTY as it appears
- Return headlines in the order they appear (top to bottom, left to right)
- Limit to maximum 20 headlines
- Do not include any explanation or commentary
- Do not use emoji in your response"""

# User message template
HOMEPAGE_ANALYZER_USER_TEMPLATE = """Analyze this homepage screenshot and extract all visible article headlines.

Return only the headlines, one per line, in the order they appear.

Example output:
New Museum Opens in Tokyo
Sustainable Architecture Award Winners Announced
Interview: Studio XYZ on Their Latest Project"""

# Combined ChatPromptTemplate for LangChain
HOMEPAGE_ANALYZER_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(HOMEPAGE_ANALYZER_SYSTEM_PROMPT),
    HumanMessagePromptTemplate.from_template(HOMEPAGE_ANALYZER_USER_TEMPLATE)
])


def parse_headlines(response_text: str) -> list[str]:
    """
    Parse AI response into list of headlines.
    
    Args:
        response_text: Raw AI response (headlines separated by newlines)
        
    Returns:
        List of headline strings
    """
    lines = response_text.strip().split('\n')
    
    headlines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines, numbered lists, explanations
        if not line or line.startswith('#') or line.lower().startswith('here'):
            continue
        
        # Remove numbered list markers (1. 2. etc)
        if line[0].isdigit() and '. ' in line[:4]:
            line = line.split('. ', 1)[1].strip()
        
        # Remove bullet points
        if line.startswith('- ') or line.startswith('• '):
            line = line[2:].strip()
        
        if line:
            headlines.append(line)
    
    return headlines[:20]  # Limit to 20
