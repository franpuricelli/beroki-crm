from .developmenti import fetch_deployment


def fetch(client, since, until, stats, logger):
    yield from fetch_deployment(client, since, until, stats, logger, "ipswich", "Ipswich")
