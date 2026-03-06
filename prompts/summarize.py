# prompts/summarize.py
"""
Summarization Prompts
Prompts for generating article summaries and tags.
"""

import re
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# System prompt for the AI summarizer
SUMMARIZE_SYSTEM_PROMPT = """You are an architecture news editor for a professional digest. 
Your task is to create concise, informative summaries of architecture and design articles.

Today's date is {current_date}. Use this for temporal context when describing projects.

Guidelines:
- Header line 1: PROJECT NAME / ARCHITECT OR BUREAU (e.g., "Cloud 11 Office Complex / Snøhetta"). If the architect or bureau is unknown, don't write anything, just the name of the project. DO NOT write Unknown in the title
- Header line 2: TYPOLOGY / CITY, COUNTRY (e.g., "Commercial / Tokyo, Japan"). If any part is unavailable, simply skip that part. Never write "Unknown" or "Various". If the entire line would be empty, skip it entirely.
- For news articles about projects, write a two-sentence summary in a professional British editorial style. Sentence 1: state project name, location, architect/studio (if explicitely mentioned), typology, scale (if mentioned) and key design features (if mentioned). Sentence 2: state key details about the project — status, significance, planning context, or professional response. 
- If the news article is not about a project, but about another related topic, write a 2-sentence summary of the article for professional audience.
- Add appropriate tag from this list: #residential, #hospitality, #office, #culture, #education, #public, #infrastructure, #landscape, #retail, #interior, #masterplan, #reuse, #mixeduse
- If the project name is in the language that doesn't match the country language (for example, in ArchDaily Brasil a project in China is named in Portuguese), translate the name of the project to English
- Keep tone neutral and factual, avoid generic praise and subjective adjectives
- Write for a specialist professional audience. 
- Use professional architectural terminology where appropriate
- Keep the tone informative but engaging
- If the article is an opinion piece, note that it's an opinion piece, but still mention the project discussed
- If it's an interview, note that it's an interview, but still mention the project discussed
- CRITICAL: Do not use emojis anywhere in your response
- CRITICAL: Keep the title clean and professional - just the project name and architect/bureau separated by a forward slash

EXAMPLES OF SUMMARIES ABOUT PROJECTS:

1. Bradfield City / Hassel and SOM
Masterplan / Western Sydney, Australia
Hassell and SOM's masterplan for Bradfield City's first precinct in Western Sydney sets out a sustainable, mixed-use gateway shaped by Country, community and long-term urban ambition. Designed as a 24/7 neighbourhood with homes, workplaces and public space organised around a central green spine, the scheme positions the project as the foundation for Australia's first new city in more than a century.
#masterplan
australia


2. Waves of Water: Future Academy / Scenic Architecture Office
Education / Shanghai, China
Scenic Architecture Office explores the idea of the "wave" as both a cultural symbol and a scientific principle, translating its sense of motion, transmission and rhythm into architectural form for the Future Academy in Shanghai. The project reimagines static building as a dynamic spatial experience, drawing on landscapes, cellular growth and waterfront context to create architecture that feels continuous, fluid and alive.
#education
china

"""

# User message template
SUMMARIZE_USER_TEMPLATE = """Summarize this architecture article:

Title: {title}
Description: {description}
Source: {url}

Respond with ONLY these lines (no blank lines between them):
1. Title in format: PROJECT NAME / ARCHITECT OR BUREAU or just PROJECT NAME if author unknown or irrelevant. DO NOT write Unknown in the title
2. TYPOLOGY / CITY, COUNTRY (e.g., "Culture / Šeduva, Lithuania"). Skip any unavailable parts. If all parts are unknown, skip this line entirely. Never write "Unknown" or "Various".
3. A 2-sentence summary
4. 1 relevant tag from this exact list: #residential, #hospitality, #office, #culture, #education, #public, #infrastructure, #landscape, #retail, #interior, #masterplan, #reuse, #mixeduse
5. Country tag: the country name in English, lowercase, no spaces — use common short forms like "uk" not "unitedkingdom". If the country is unclear, skip this line entirely.

EXAMPLE FORMAT:

Nobel Center / David Chipperfield
Culture / Stockholm, Sweden
David Chipperfield's Nobel Center in Stockholm is designed to celebrate the legacy of the Nobel Prize through a blend of exhibition spaces and public areas. The building's striking architectural form and sustainable features aim to foster dialogue and engagement with the ideals of the Nobel laureates.
#culture
sweden"""

# Combined ChatPromptTemplate for LangChain
SUMMARIZE_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(SUMMARIZE_SYSTEM_PROMPT),
    HumanMessagePromptTemplate.from_template(SUMMARIZE_USER_TEMPLATE)
])


# Typologies used in the second header line (for parser detection)
_KNOWN_TYPOLOGIES = {
    'residential', 'hospitality', 'office', 'culture', 'education',
    'public', 'infrastructure', 'landscape', 'retail', 'interior',
    'masterplan', 'reuse', 'mixeduse',
    # Common variants the AI might produce
    'commercial', 'mixed-use', 'civic', 'religious', 'industrial',
    'museum', 'library', 'sports', 'healthcare', 'housing',
    'renovation', 'pavilion', 'tower', 'bridge', 'memorial',
    'installation', 'adaptive', 'airport', 'urbanism',
}


def _is_typology_location_line(line: str) -> bool:
    """
    Check if a line looks like a typology/location header 
    (e.g., "Culture / Šeduva, Lithuania" or "Residential").

    These lines:
    - Start with a known typology word
    - Are short (not a full summary sentence)
    - Don't end with a period
    """
    stripped = line.strip()
    if not stripped or stripped.endswith('.'):
        return False

    # Get the first word (before any "/" separator), lowercased, no hyphens
    first_part = stripped.split('/')[0].strip().lower()
    words = first_part.split()
    if not words:
        return False

    first_word = words[0].replace('-', '')

    # Check against known typologies
    if first_word in _KNOWN_TYPOLOGIES:
        return True

    # Handle "mixed use" as two words
    if len(words) >= 2 and ''.join(words[:2]) in _KNOWN_TYPOLOGIES:
        return True

    return False


def parse_summary_response(response_text: str) -> dict:
    """
    Parse AI response into headline (two-liner), summary, and tags.

    The AI returns consecutive lines (no blank lines):
        Line 1: Project Name / Architect
        Line 2: Typology / City, Country  (optional — may be skipped)
        Line 3: 2-sentence summary
        Line 4: typology tag (e.g., #culture)
        Line 5: country tag (e.g., sweden)  (optional)

    The parser detects whether line 2 is a typology/location header or already the summary,
    then assembles a two-line headline joined by a blank line for display:

        "Project Name / Architect\\n\\nTypology / City, Country"

    Returns:
        Dict with:
        - 'headline': two-line string (parts joined by \\n\\n), or single line if no second part
        - 'summary': the 2-sentence summary
        - 'tag': first tag as string (typology, for backward compatibility)
        - 'tags': list of tags [typology_tag, country_tag], filtering out empty values
    """
    lines = [line.strip() for line in response_text.strip().split('\n') if line.strip()]

    headline = ""
    summary = ""
    tag = ""
    tags = []

    if len(lines) >= 2:
        header_line1 = lines[0]

        # Check if line 2 is a typology/location header or the summary
        if _is_typology_location_line(lines[1]):
            # Line 2 is the second header line
            header_line2 = lines[1]
            headline = f"{header_line1}\n\n{header_line2}"

            # Summary is the next line
            summary = lines[2] if len(lines) >= 3 else ""

            # Tags start at line 4
            if len(lines) >= 4:
                tag_val = lines[3].lower().strip().lstrip('#')
                if tag_val and tag_val not in ("unknown", "various", "none", "n/a"):
                    tags.append(f"#{tag_val}")
            if len(lines) >= 5:
                country_val = lines[4].lower().strip().lstrip('#')
                if country_val and country_val not in ("unknown", "various", "none", "n/a"):
                    tags.append(country_val)
        else:
            # No typology/location line — line 2 is the summary
            headline = header_line1
            summary = lines[1]

            # Tags start at line 3
            if len(lines) >= 3:
                tag_val = lines[2].lower().strip().lstrip('#')
                if tag_val and tag_val not in ("unknown", "various", "none", "n/a"):
                    tags.append(f"#{tag_val}")
            if len(lines) >= 4:
                country_val = lines[3].lower().strip().lstrip('#')
                if country_val and country_val not in ("unknown", "various", "none", "n/a"):
                    tags.append(country_val)

    elif len(lines) == 1:
        headline = ""
        summary = lines[0]
    else:
        headline = ""
        summary = ""

    # First tag (typology) as string for backward compatibility
    tag = tags[0] if tags else ""

    # Safety net: strip "Unknown" variants from headline
    if headline:
        headline = re.sub(r'\s*/\s*Unknown\s*$', '', headline, flags=re.IGNORECASE)
        headline = re.sub(r'\s*/\s*Unknown\s+Architect(s)?\s*$', '', headline, flags=re.IGNORECASE)
        headline = re.sub(r'\s*/\s*Unknown\s+Bureau\s*$', '', headline, flags=re.IGNORECASE)
        headline = re.sub(r'\s*/\s*Unknown\s+Studio\s*$', '', headline, flags=re.IGNORECASE)
        headline = re.sub(r'\bVarious\b', '', headline, flags=re.IGNORECASE)
        # Clean up leftover empty second line
        headline = re.sub(r'\n\n\s*$', '', headline)
        headline = re.sub(r'  +', ' ', headline).strip()

    return {
        "headline": headline,
        "summary": summary,
        "tag": tag,     # backward compat: first tag as string (e.g., "#culture")
        "tags": tags     # new: list of tags (e.g., ["#culture", "sweden"])
    }