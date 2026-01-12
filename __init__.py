"""
Prompts Package
All AI prompts stored as Python constants for easy importing.

Usage:
    from prompts import SUMMARIZE_PROMPT
    from prompts.summarize import SYSTEM_PROMPT, USER_TEMPLATE
"""

from prompts.summarize import (
    SUMMARIZE_SYSTEM_PROMPT,
    SUMMARIZE_USER_TEMPLATE,
    SUMMARIZE_PROMPT_TEMPLATE,
)

__all__ = [
    "SUMMARIZE_SYSTEM_PROMPT",
    "SUMMARIZE_USER_TEMPLATE", 
    "SUMMARIZE_PROMPT_TEMPLATE",
]
