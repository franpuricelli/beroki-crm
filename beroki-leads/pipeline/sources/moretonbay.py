from .qld_arcgis import fetch_source, parse as parse_source


def parse(attributes, since, until):
    return parse_source("moretonbay", attributes, since, until)


def fetch(client, since, until, stats, logger):
    yield from fetch_source("moretonbay", client, since, until, stats, logger)
