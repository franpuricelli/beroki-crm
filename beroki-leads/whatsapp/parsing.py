class ParseError(ValueError):
    pass


def obj(value, where):
    if not isinstance(value, dict):
        raise ParseError(f"{where}: expected an object")
    return value


def items(value, where):
    if not isinstance(value, list):
        raise ParseError(f"{where}: expected a list")
    return value


def text(value, where):
    if not isinstance(value, str):
        raise ParseError(f"{where}: expected a string")
    return value


def text_or_none(value, where):
    if value is None:
        return None
    return text(value, where)


def flag(value, where):
    if not isinstance(value, bool):
        raise ParseError(f"{where}: expected a boolean")
    return value


def scalar(value, where):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ParseError(f"{where}: expected a scalar value")
