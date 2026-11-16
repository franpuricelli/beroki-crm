from .qld_arcgis import fetch_source, parse as parse_source


def parse(attributes, since, until):
    return parse_source("logan", attributes, since, until)


def fetch(client, since, until, stats, logger):
    yield from fetch_source("logan", client, since, until, stats, logger)
