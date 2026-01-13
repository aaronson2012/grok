"""
Converts standard Markdown to Telegram-compatible HTML.
"""
import re
import html


def markdown_to_telegram_html(text: str) -> str:
    """
    Converts common Markdown syntax to Telegram HTML.
    Handles: bold, italic, code blocks, inline code, headers, links.
    """
    # Escape HTML entities first (before we add our own tags)
    text = html.escape(text)
    
    # Code blocks (```...```) -> <pre>...</pre>
    text = re.sub(
        r'```(\w*)\n?(.*?)```',
        lambda m: f'<pre>{m.group(2)}</pre>',
        text,
        flags=re.DOTALL
    )
    
    # Inline code (`...`) -> <code>...</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Bold (**...**) -> <b>...</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    
    # Italic (*...*) -> <i>...</i>  (but not **)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
    
    # Strikethrough (~~...~~) -> <s>...</s>
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # Headers (### text) -> <b>text</b> (Telegram doesn't have headers)
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    # Links [text](url) -> <a href="url">text</a>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    return text
