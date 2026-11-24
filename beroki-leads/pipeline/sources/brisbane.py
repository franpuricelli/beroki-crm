from .developmenti import fetch_deployment, fetch_lodged_deployment, recheck_deployment

COUNCILS = ("Brisbane",)


def fetch(client, since, until, stats, logger):
    yield from fetch_deployment(client, since, until, stats, logger, "brisbane", "Brisbane")


def fetch_lodged(client, since, until, stats, logger):
    yield from fetch_lodged_deployment(client, since, until, stats, logger, "brisbane")


def recheck(client, numbers, stats, logger):
    yield from recheck_deployment(client, numbers, stats, logger, "brisbane")
