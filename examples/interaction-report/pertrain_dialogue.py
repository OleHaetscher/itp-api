"""
Write the dialogue of a PerTRAIN chat as the text file of an ITP record.

PerTRAIN's ITPGenerator opens one ITP interaction per agent and per dialog, as
agent A of type human in ac against a hosted model as agent B, and names it by
the PerTRAIN session (``clientRequestId``, kept in interaction.json). Each
message the agent receives is assessed and submitted as A's behavior; the
model's answer is the state of the agent's next message. So turn by turn:

    A's k-th turn  = the k-th message from the partner
    B's k-th turn  = the agent's own message that follows it

The texts are in PerTRAIN's database and never on the ITP platform. This script
reads them from the local stack (``podman exec pertrain-db-postgres psql``),
pairs them with the record as above, and writes turn, role, text. It refuses a
record whose turns do not match the messages, for example after an ITP restart
split the dialog over two interactions.

Run from the repository root:

    python examples/interaction-report/pertrain_dialogue.py results/<folder> --out dialogue.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

PSQL = ["podman", "exec", "pertrain-db-postgres", "psql", "-U", "db-admin", "-d", "pertrain", "-t", "-A", "-c"]


def query_json(sql: str) -> object:
    """
    Run a query that returns one JSON value and parse it.

    Args:
        sql: Query selecting a single json value.

    Returns:
        Parsed value.
    """

    output = subprocess.run(PSQL + [sql], capture_output=True, text=True, check=True).stdout
    lines = [line for line in output.splitlines() if line.strip()]

    return json.loads(lines[-1]) if lines else None


def read_dialog(session_id: str) -> dict:
    """
    Read the PerTRAIN session behind an ITP record and its dialog.

    Args:
        session_id: PerTRAIN session id, the record's clientRequestId.

    Returns:
        Dictionary with the dialog id, the participant id of the agent, the
        scenario names by participant, and the messages in order.
    """

    session = query_json(
        f"SELECT json_build_object('dialog', dialog_id, 'self', self_participant_id) "
        f"FROM sessions WHERE id = '{session_id}'"
    )
    if session is None:
        raise SystemExit(f"No PerTRAIN session {session_id} in the local database.")

    messages = query_json(
        "SELECT json_agg(json_build_object('sender', m.sender_id, 'text', m.content, "
        "'scenario', s.name) ORDER BY m.time_sent, m.id) "
        "FROM messages m LEFT JOIN templates t ON t.id = m.sender_id "
        "LEFT JOIN scenarios s ON s.id = t.scenario_id "
        f"WHERE m.dialog_id = '{session['dialog']}'"
    ) or []

    return {"dialog": session["dialog"], "self": session["self"], "messages": messages}


def pair_turns(
    record: dict,
    turns_taken: int,
    dialog: dict,
) -> list[tuple[int, str, str]]:
    """
    Pair the record's turns with the dialog's messages.

    Args:
        record: interaction.json of the ITP record.
        turns_taken: Number of behaviors in the record, one original message
            each. finalTurn is not used, because it also counts a turn that was
            open when the dialog ended.
        dialog: Dialog as returned by read_dialog.

    Returns:
        Rows of turn, role and text.
    """

    roles = {role: agent["type"] for role, agent in record["agents"].items()}
    if roles != {"A": "human", "B": "model"}:
        raise SystemExit(f"Expected a PerTRAIN record (A human, B model), got {roles}.")

    exchanges: list[tuple[str, str | None]] = []
    for message in dialog["messages"]:
        if message["sender"] != dialog["self"]:
            exchanges.append((message["text"], None))
        elif exchanges and exchanges[-1][1] is None:
            exchanges[-1] = (exchanges[-1][0], message["text"])
        # An own message before the first partner message (an opening line)
        # precedes the ITP interaction and has no turn in it.

    # The last partner message may have reached the dialog's end before the
    # ITP, which then refused it, so the record can be one exchange short.
    exchanges_in_record = (turns_taken + 1) // 2
    if exchanges_in_record not in (len(exchanges), len(exchanges) - 1):
        raise SystemExit(
            f"The record has {turns_taken} turns, but the dialog has {len(exchanges)} partner "
            "messages; each should be one A turn followed by one B turn."
        )

    rows = []
    for index, (partner_text, own_text) in enumerate(exchanges[:exchanges_in_record]):
        rows.append((2 * index + 1, "A", partner_text))
        if own_text is not None and 2 * index + 2 <= turns_taken:
            rows.append((2 * index + 2, "B", own_text))

    return rows


def main() -> None:
    """
    Write the dialogue file named on the command line.

    Args:

    Returns:
    """

    parser = argparse.ArgumentParser(description="Write the PerTRAIN dialogue behind an ITP record as turn, role, text.")
    parser.add_argument("folder", type=Path, help="ITP results folder written for a PerTRAIN agent")
    parser.add_argument("--out", type=Path, required=True, help="CSV file to write")
    arguments = parser.parse_args()

    record = json.loads((arguments.folder / "interaction.json").read_text(encoding="utf-8"))
    if not record.get("clientRequestId"):
        raise SystemExit("The record names no clientRequestId; it was not written for a PerTRAIN session.")

    dialog = read_dialog(record["clientRequestId"])
    turns_taken = len(list(arguments.folder.glob("message_*_original.json")))
    rows = pair_turns(record, turns_taken, dialog)

    with arguments.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["turn", "role", "text"])
        writer.writerows(rows)

    scenarios = sorted({m["scenario"] for m in dialog["messages"] if m["scenario"]})
    print(f"  dialog {dialog['dialog']} ({', '.join(scenarios)}): {len(rows)} turns -> {arguments.out}")


if __name__ == "__main__":
    main()
