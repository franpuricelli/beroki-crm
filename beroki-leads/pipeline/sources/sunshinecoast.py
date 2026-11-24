from .developmenti import fetch_lodged_deployment, recheck_deployment
from .qld_arcgis import fetch_source, parse as parse_source

COUNCILS = ("Sunshine Coast",)


def parse(attributes, since, until):
    return parse_source("sunshinecoast", attributes, since, until)


def fetch(client, since, until, stats, logger):
    yield from fetch_source("sunshinecoast", client, since, until, stats, logger)


def fetch_lodged(client, since, until, stats, logger):
    yield from fetch_lodged_deployment(client, since, until, stats, logger, "sunshinecoast")


def recheck(client, numbers, stats, logger):
    yield from recheck_deployment(client, numbers, stats, logger, "sunshinecoast")
