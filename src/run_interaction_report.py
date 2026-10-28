"""
Write a self-contained HTML report of one recorded interaction.

The report is built from the ITP record alone: the folder the API writes for
an interaction with persistence enabled (results/<timestamp>_<session
prefix>/). Text that a paradigm produced, such as the utterances of a PerTRAIN
chat, is not on the platform; supply it as a CSV with the columns turn, role
and text, and it is joined on turn and role.

The page steps through the interaction turn by turn and exports what it shows
as SVG or PNG. A figure for a paper is that export at one turn, and the page
itself is the supplement.

Run
---
    python -m src.run_interaction_report results/<folder>
    python -m src.run_interaction_report --latest
    python -m src.run_interaction_report results/<folder> --text dialogue.csv \\
        --label A="IPC model" --label B="LASSI model" --out report.html
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.visualization.InteractionRecord import InteractionRecord
from src.visualization.InteractionReport import PANELS, InteractionReport

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_NAME = "interaction_report.html"


def latest_record(
    results_root: Path = REPO_ROOT / "results",
) -> Path:
    """
    Find the most recent results folder.

    Folder names begin with a timestamp, so the last in name order is the
    newest.

    Args:
        results_root: Folder holding the results folders.

    Returns:
        Path of the newest results folder.
    """

    folders = sorted(path for path in results_root.glob("*") if (path / "interaction.json").is_file())

    if not folders:
        raise FileNotFoundError(f"No recorded interaction below {results_root}.")

    return folders[-1]


def parse_labels(
    pairs: list[str],
) -> dict[str, str]:
    """
    Read agent labels given as ROLE=label.

    Args:
        pairs: Arguments such as ["A=IPC model"].

    Returns:
        Dictionary mapping roles to labels.
    """

    labels: dict[str, str] = {}

    for pair in pairs:
        role, separator, label = pair.partition("=")
        if not separator or not role.strip() or not label.strip():
            raise SystemExit(f"--label expects ROLE=label, got {pair!r}.")
        labels[role.strip()] = label.strip()

    return labels


def make_report(
    folder: Path,
    text: Path | None = None,
    text_source: str = "",
    **options,
) -> InteractionReport:
    """
    Read a record, attach its dialogue, and prepare the report.

    Args:
        folder: Results folder of the interaction.
        text: Optional dialogue CSV.
        text_source: Where the dialogue comes from, shown in the report.
        **options: Passed on to InteractionReport.

    Returns:
        Interaction report.
    """

    record = InteractionRecord.from_folder(folder)

    if text is not None:
        record.attach_texts(text, source=text_source)

    return InteractionReport(record=record, **options)


def main() -> None:
    """
    Write the report named on the command line.

    Args:

    Returns:
    """

    parser = argparse.ArgumentParser(description="Write an HTML report of one recorded ITP interaction.")
    parser.add_argument("folder", nargs="?", type=Path, help="results folder of the interaction")
    parser.add_argument("--latest", action="store_true", help="use the newest folder below results/")
    parser.add_argument("--text", type=Path, help="dialogue CSV with the columns turn, role, text")
    parser.add_argument("--text-source", default="", help="where the dialogue comes from, shown in the report")
    parser.add_argument("--label", action="append", default=[], metavar="ROLE=LABEL", help="name of an agent")
    parser.add_argument(
        "--panels",
        default=",".join(PANELS),
        help=f"panels shown when the page opens, from {', '.join(PANELS)}",
    )
    parser.add_argument("--turn", type=int, help="turn shown when the page opens, the last by default")
    parser.add_argument("--time-space", help="state space drawn over turns, ac if an agent speaks it")
    parser.add_argument("--title", default="", help="heading of the page")
    parser.add_argument("--out", type=Path, help=f"output file, {REPORT_NAME} in the results folder by default")
    arguments = parser.parse_args()

    if arguments.latest == (arguments.folder is not None):
        parser.error("name a results folder or pass --latest, not both")

    folder = latest_record() if arguments.latest else arguments.folder
    report = make_report(
        folder=folder,
        text=arguments.text,
        text_source=arguments.text_source,
        panels=tuple(panel.strip() for panel in arguments.panels.split(",") if panel.strip()),
        title=arguments.title,
        initial_turn=arguments.turn,
        time_space=arguments.time_space,
        labels=parse_labels(arguments.label),
    )
    path = report.write(arguments.out or folder / REPORT_NAME)

    print(f"\n  Interaction report  ->  {path}\n")


if __name__ == "__main__":
    main()
