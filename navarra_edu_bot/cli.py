import click


@click.group()
def main() -> None:
    """Navarra Edu Bot CLI."""


@main.command()
def ping() -> None:
    """Healthcheck ping."""
    click.echo("pong")


if __name__ == "__main__":
    main()
