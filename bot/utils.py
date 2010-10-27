def force_str(text):
    if isinstance(text, unicode):
        return text.encode('utf-8')
    if text is None:
        return text
    return str(text)
