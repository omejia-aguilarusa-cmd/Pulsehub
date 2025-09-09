from __future__ import annotations

import asyncio
from typing import Optional

import typer

from confluence.logging import setup_logging
from confluence.scheduler.jobs import run_scan
from confluence.db.session import init_db
from confluence.connectors.binance import BinanceClient
from confluence.connectors.robinhood_crypto import RobinhoodCryptoClient


app = typer.Typer(help="Confluence CLI")


@app.command()
def scan(mode: str = typer.Option("day", help="day|swing|hold")) -> None:
    """Run a one-off scan and emit alerts (if enabled)."""
    setup_logging()
    asyncio.run(init_db())
    asyncio.run(run_scan(mode))


@app.command("heads-up")
def heads_up() -> None:
    """Placeholder for heads-up alerts (pre-market, catalysts)."""
    setup_logging()
    typer.echo("Heads-up not yet implemented")


@app.command("exec")
def exec_order(
    broker: str = typer.Option(..., help="binance|rh-crypto"),
    signal: str = typer.Option(..., help="Signal ID"),
    confirm: bool = typer.Option(False, help="Require explicit confirmation"),
) -> None:
    setup_logging()
    if not confirm:
        typer.echo("Dry run only. Use --confirm to execute.")
        raise typer.Exit(code=0)
    if broker == "binance":
        typer.echo("Binance execution placeholder (confirm acknowledged)")
    elif broker == "rh-crypto":
        client = RobinhoodCryptoClient()
        try:
            asyncio.run(client.place_order())
        except NotImplementedError:
            typer.echo("Robinhood Crypto API not configured (official-only)")
    else:
        raise typer.BadParameter("Unknown broker")


@app.command("set")
def set_thresholds(
    min_score: Optional[int] = typer.Option(None),
    min_rr: Optional[float] = typer.Option(None),
    min_prob: Optional[float] = typer.Option(None),
) -> None:
    typer.echo("Runtime threshold update not yet persisted in config")


if __name__ == "__main__":
    app()

