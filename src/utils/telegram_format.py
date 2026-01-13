"""
Converts standard Markdown to Telegram-compatible HTML.
"""
import re
import html


def _fix_tag_nesting(text: str) -> str:
    """Fix improperly nested HTML tags (e.g. <b><i></b></i> -> <b><i></i></b><i></i>)."""
    tag_pattern = re.compile(r'<(/?)([biusa]|code|pre)(?:\s[^>]*)?>|(<a\s+href="[^"]*">)', re.IGNORECASE)
    
    result = []
    open_tags_stack = []
    last_end = 0
    
    for match in tag_pattern.finditer(text):
        result.append(text[last_end:match.start()])
        last_end = match.end()
        
        full_tag = match.group(0)
        is_close = match.group(1) == '/'
        tag_name = 'a' if match.group(3) else match.group(2).lower()
        if match.group(3):
            is_close = False
        
        if not is_close:
            open_tags_stack.append(tag_name)
            result.append(full_tag)
        else:
            if not open_tags_stack:
                continue
            
            matching_idx = next(
                (i for i in range(len(open_tags_stack) - 1, -1, -1) if open_tags_stack[i] == tag_name),
                None
            )
            
            if matching_idx is None:
                continue
            
            tags_to_reopen = []
            while len(open_tags_stack) > matching_idx + 1:
                inner_tag = open_tags_stack.pop()
                result.append(f'</{inner_tag}>')
                tags_to_reopen.append(inner_tag)
            
            open_tags_stack.pop()
            result.append(f'</{tag_name}>')
            
            for inner_tag in reversed(tags_to_reopen):
                open_tags_stack.append(inner_tag)
                result.append(f'<{inner_tag}>')
    
    result.append(text[last_end:])
    
    while open_tags_stack:
        result.append(f'</{open_tags_stack.pop()}>')
    
    return ''.join(result)


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
    
    # Fix any improperly nested tags
    text = _fix_tag_nesting(text)
    
    return text
