from .developmenti import fetch_deployment, fetch_lodged_deployment, recheck_deployment

COUNCILS = ("Gold Coast",)


def fetch(client, since, until, stats, logger):
    yield from fetch_deployment(client, since, until, stats, logger, "goldcoast", "Gold Coast")


def fetch_lodged(client, since, until, stats, logger):
    yield from fetch_lodged_deployment(client, since, until, stats, logger, "goldcoast")


def recheck(client, numbers, stats, logger):
    yield from recheck_deployment(client, numbers, stats, logger, "goldcoast")
