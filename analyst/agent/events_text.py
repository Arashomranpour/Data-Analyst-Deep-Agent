def message_text(message) -> str:
    """Plain text of a LangChain message (content may be a string or a list of parts)."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
