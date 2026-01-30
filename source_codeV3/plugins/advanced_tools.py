"""
Advanced Plugin Example - Using @tool decorator
"""
from plugin_system import tool
import os

@tool(
    name="Text Counter",
    description="Counts characters and words in a text file",
    icon="...",
    category="Text Tools"
)
def count_text(input_file: str, count_spaces: bool = True):
    """Count characters and words in a file."""
    if not os.path.exists(input_file):
        return f"File not found: {input_file}"
    
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    chars = len(text) if count_spaces else len(text.replace(' ', ''))
    words = len(text.split())
    lines = len(text.splitlines())
    
    return f"Characters: {chars}\nWords: {words}\nLines: {lines}"