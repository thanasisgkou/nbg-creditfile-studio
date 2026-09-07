"""Run the local application with one writer per configured data directory."""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8520)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable AI with your own OpenRouter key, entered privately at startup.",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit(
            "Build the frontend first: run scripts/setup.ps1 or npm ci && npm run build in frontend."
        )
    from creditfile.config import Settings

    settings = Settings(
        execution_mode="live" if args.live else "replay", data_dir=args.data_dir.resolve()
    )
    directory = settings.data_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    lock_file = (directory / ".writer.lock").open("a+b")
    try:
        lock_file.seek(0)
        if not lock_file.read(1):
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        raise SystemExit("Studio is already running for this data directory.") from None
    import uvicorn
    from creditfile.api import create_app
    from creditfile.demo import seed_demo

    app = None
    previous_key = os.environ.get("OPENROUTER_API_KEY")
    try:
        if args.live:
            key = getpass.getpass("OpenRouter API key (not saved): ").strip()
            if not key:
                raise SystemExit("No key entered. Start without --live for the offline examples.")
            os.environ["OPENROUTER_API_KEY"] = key
        app = create_app(settings=settings)
        seed_demo(app.state.store, settings)
        print(
            f"CreditFile Studio: http://127.0.0.1:{args.port} | {settings.execution_mode} | {directory}"
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    finally:
        if app is not None:
            app.state.executor.shutdown(wait=True)
        if args.live:
            if previous_key is None:
                os.environ.pop("OPENROUTER_API_KEY", None)
            else:
                os.environ["OPENROUTER_API_KEY"] = previous_key
        lock_file.close()


if __name__ == "__main__":
    main()
