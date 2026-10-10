"""Negotiate gzip without overriding clients that explicitly disable it."""
def accepts_gzip(header):
    for option in (header or '').split(','):
        parts = option.strip().split(';')
        if parts[0].strip().lower() != 'gzip':
            continue
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.strip().startswith('q='):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        return quality > 0
    return False
