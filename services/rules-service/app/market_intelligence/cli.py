"""Local operator command; intentionally no provider, scheduler, or mail side effects."""
from __future__ import annotations
import argparse
from app.config import settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas_brief")
    parser.add_argument("command", choices=("preview", "generate", "send"))
    args = parser.parse_args(argv)
    if args.command == "send":
        if not settings.atlas_market_brief_email_delivery_enabled:
            print("preview-only: email delivery disabled")
            return 2
        print("preview-only: no real delivery adapter is enabled")
        return 2
    if args.command == "generate" and not settings.atlas_market_brief_generation_enabled:
        print("unavailable: market briefing generation disabled")
        return 2
    print(f"{args.command}: local safe preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
