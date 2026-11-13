from .qld_arcgis import fetch_source, parse as parse_source


def parse(attributes, since, until):
    return parse_source("sunshinecoast", attributes, since, until)


def fetch(client, since, until, stats, logger):
    yield from fetch_source("sunshinecoast", client, since, until, stats, logger)
