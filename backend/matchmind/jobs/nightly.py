"""Nightly job: a new match of the day, warmed, and the evaluations re-run to Blob storage.

Runs as the Container Apps job `matchmind-nightly` (schedule 04:00 UTC) with the same image and identity as
the API and the /data share mounted:
    1. generate a match with seed = day of year into /data (the API's catalogue is a directory scan, so the
       running replicas list it without a restart);
    2. warm its agent cache through the public API (one replay per seat profile) so the first viewer of the
       day never waits for Foundry;
    3. re-run the forecast evaluation (a small sample, Foundry calls) and the risk scorecard + calibration
       (no Foundry) and upload the JSON reports to the `eval` container under <date>/.
Each step is independent: a failure is logged and the next step still runs; the exit code is the number of
failed steps.

    python -m matchmind.jobs.nightly --base https://<api-fqdn> [--data /data] [--forecast-matches 4]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
CLUBS = ["THU", "NBF", "CRC", "ALV", "IRA", "MRV", "TGW", "KPF"]


def match_of_the_day(today: date) -> tuple[str, str, int]:
    """Deterministic fixture: the pairing rotates with the day of year, the seed is the date."""
    n = today.timetuple().tm_yday
    home = CLUBS[n % len(CLUBS)]
    away = CLUBS[(n * 3 + 1) % len(CLUBS)]
    if away == home:
        away = CLUBS[(n * 3 + 2) % len(CLUBS)]
    return home, away, int(today.strftime("%Y%m%d"))


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    log.info("$ %s", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, **kw)


def upload(account: str | None, folder: str, files: list[Path]) -> None:
    if not account:
        log.info("MATCHMIND_STORAGE_ACCOUNT not set: reports stay local (%s)", ", ".join(str(f) for f in files))
        return
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    blobs = ContainerClient(f"https://{account}.blob.core.windows.net", "eval",
                            credential=DefaultAzureCredential(exclude_interactive_browser_credential=True))
    for f in files:
        if f.is_file():
            blobs.upload_blob(f"{folder}/{f.name}", f.read_bytes(), overwrite=True)
            log.info("uploaded eval/%s/%s", folder, f.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--data", default=os.environ.get("MATCHMIND_DATA_DIR", "/data"))
    parser.add_argument("--forecast-matches", type=int, default=4)
    parser.add_argument("--risk-matches", type=int, default=40)
    parser.add_argument("--skip-forecasts", action="store_true")
    parser.add_argument("--skip-warm", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    py = [sys.executable, "-m"]
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    folder = today.isoformat()
    out = data / "eval" / folder
    out.mkdir(parents=True, exist_ok=True)
    failures = 0

    home, away, seed = match_of_the_day(today)
    match_id = f"{home}-{away}-{seed % 100:02d}"
    try:
        run(py + ["matchmind.generate_match", "--home", home, "--away", away, "--seed", str(seed), "--out", str(data)])
        metas = sorted(data.glob(f"{home}-{away}-*_meta.json"), key=lambda p: p.stat().st_mtime)
        if metas:
            match_id = metas[-1].name[: -len("_meta.json")]
        log.info("match of the day: %s", match_id)
    except Exception as exc:  # noqa: BLE001
        failures += 1
        log.warning("generation failed: %r", exc)
        match_id = None

    if match_id and not args.skip_warm:
        try:
            run(py + ["matchmind.agents.warm_cache", "--base", args.base, "--match", match_id, "--speed", "40"])
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log.warning("warm failed: %r", exc)

    reports: list[Path] = []
    try:
        scorecard = out / "risk_scorecard.txt"
        scorecard.write_text(run(py + ["matchmind.risk.evaluate", "--matches", str(args.risk_matches)], capture_output=True).stdout, encoding="utf-8")
        calibration = out / "risk_calibration.json"
        run(py + ["matchmind.risk.evaluate", "--matches", str(args.risk_matches), "--calibration", "--out", str(calibration)])
        reports += [scorecard, calibration]
    except Exception as exc:  # noqa: BLE001
        failures += 1
        log.warning("risk evaluation failed: %r", exc)

    if not args.skip_forecasts:
        try:
            forecasts = out / "forecasts.json"
            run(py + ["matchmind.agents.evaluate_forecasts", "--matches", str(args.forecast_matches), "--limit", "6",
                      "--label", f"nightly-{folder}", "--out", str(forecasts)])
            reports.append(forecasts)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log.warning("forecast evaluation failed: %r", exc)

    summary = out / "summary.json"
    summary.write_text(json.dumps({"date": folder, "match_of_the_day": match_id, "failures": failures,
                                   "reports": [r.name for r in reports]}, indent=1), encoding="utf-8")
    try:
        upload(os.environ.get("MATCHMIND_STORAGE_ACCOUNT"), folder, reports + [summary])
    except Exception as exc:  # noqa: BLE001
        failures += 1
        log.warning("upload failed: %r", exc)
    log.info("nightly done, %d failure(s)", failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
