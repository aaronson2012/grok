def chunk_text(text: str, chunk_size: int = 2000) -> list[str]:
    """
    Splits text into chunks of maximum `chunk_size` characters, 
    respecting word boundaries where possible.
    """
    if len(text) <= chunk_size:
        return [text]
        
    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break
            
        # Find the nearest space before the limit
        split_index = text.rfind(" ", 0, chunk_size)
        
        # If no space found (giant word), force split
        if split_index == -1:
            split_index = chunk_size
            
        chunks.append(text[:split_index])
        text = text[split_index:].lstrip()
        
    return chunks
