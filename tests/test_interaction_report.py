"""
Tests of the interaction report: reading a recorded interaction, pairing each
behavior with its converted copy, joining a dialogue file on turn and role,
and writing the self-contained page. The two records of the PerTRAIN dialog
in examples/interaction-report/ are fixtures; the others are recorded
in-process through FastAPI's test client, so no port is involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.API.APISpecification import APISpecification
from src.converter.ConverterRegistry import make_default_converter_registry
from src.run_interaction_report import latest_record, make_report, parse_labels
from src.run_model_api import make_catalogue
from src.visualization.InteractionRecord import InteractionRecord, describe_state_space
from src.visualization.InteractionReport import DATA_PLACEHOLDER, InteractionReport

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "interaction-report"
EXAMPLE_RECORD = next((EXAMPLE / "record").iterdir())
EXAMPLE_LASSI_RECORD = next((EXAMPLE / "lassi_record").iterdir())


def record_interaction(
    results_root: Path,
    model_a: str,
    model_b: str,
    turns: int,
) -> Path:
    """
    Run a model-model interaction in-process and return its results folder.

    Args:
        results_root: Directory the API writes results below.
        model_a: Model of agent A, which starts.
        model_b: Model of agent B.
        turns: Number of turns.

    Returns:
        Path of the results folder.
    """

    api = APISpecification(
        catalogue=make_catalogue(),
        converter=make_default_converter_registry(),
        results_root=results_root,
    )
    client = TestClient(api.app)
    response = client.post(
        "/api/v1/interactions",
        json={
            "modelId": model_a,
            "numberOfTurns": turns,
            "persistence": {"enabled": True},
            "agents": {"A": {"type": "model"}, "B": {"type": "model", "modelId": model_b}},
        },
    )
    assert response.status_code == 201, response.json()

    return next((results_root / "results").iterdir())


def write_csv(path: Path, rows: list[tuple]) -> Path:
    """
    Write a dialogue CSV.

    Args:
        path: Path of the file.
        rows: Rows below the header turn, role, text.

    Returns:
        Path of the file.
    """

    lines = ["turn,role,text"] + [f'{turn},{role},"{text}"' for turn, role, text in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return path


def test_example_record_pairs_each_behavior_with_its_conversion() -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)

    assert [entry["turn"] for entry in record.turns] == list(range(1, 9))
    assert [entry["role"] for entry in record.turns] == ["A", "B"] * 4
    # A PerTRAIN record: Daniel's assessed text as human agent A in ac, the
    # dummy IPC model that steers Lukas as B.
    assert record.agents["A"]["type"] == "human"
    assert record.agents["A"]["stateSpace"]["id"] == "ac"
    assert record.agents["B"]["stateSpace"]["id"] == "ipc"

    for entry in record.turns:
        sender = record.agents[entry["role"]]["stateSpace"]["id"]
        receiver = record.agents["B" if entry["role"] == "A" else "A"]["stateSpace"]["id"]
        assert entry["sent"]["stateSpace"] == sender
        assert entry["received"]["stateSpace"] == receiver
        assert entry["received"]["converter"] in ("IPCToACConverter", "ACToIPCConverter")


def test_example_lassi_record_carries_the_template_parameters() -> None:
    record = InteractionRecord.from_folder(EXAMPLE_LASSI_RECORD)

    assert record.agents["B"]["modelId"] == "lassi"
    assert record.agents["B"]["parameters"]["values"] == {"A": {"BD": 5.5, "IR": -0.6}, "C": {"BD": 3.0, "IR": 0.7}}
    assert all(entry["received"] == entry["sent"] for entry in record.turns)


def test_same_space_turns_are_received_as_sent(tmp_path: Path) -> None:
    folder = record_interaction(tmp_path, "dummy-ipc", "dummy-ipc", turns=4)
    record = InteractionRecord.from_folder(folder)

    assert len(record.turns) == 4
    for entry in record.turns:
        assert entry["received"] == entry["sent"]
        assert "converter" not in entry["received"]
        assert set(entry["messages"]) == {"original"}


def test_dialogue_is_joined_on_turn_and_role(tmp_path: Path) -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)
    record.attach_texts(write_csv(tmp_path / "d.csv", [(1, "A", "Hello."), (2, "B", "Hi.")]), source="test")

    assert record.texts == {1: "Hello.", 2: "Hi."}
    assert record.to_report_data()["texts"] == {"1": "Hello.", "2": "Hi."}


@pytest.mark.parametrize(
    "rows, message",
    [
        ([(1, "B", "Wrong agent.")], "taken by agent A"),
        ([(9, "A", "No such turn.")], "no turn 9"),
        ([(1, "A", "Once."), (1, "A", "Twice.")], "appears twice"),
    ],
)
def test_dialogue_that_does_not_fit_the_record_is_refused(tmp_path: Path, rows: list[tuple], message: str) -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)

    with pytest.raises(ValueError, match=message):
        record.attach_texts(write_csv(tmp_path / "d.csv", rows))


def test_dialogue_without_its_columns_is_refused(tmp_path: Path) -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)
    path = tmp_path / "d.csv"
    path.write_text("turn,speaker,text\n1,A,Hello.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="lacks the columns role"):
        record.attach_texts(path)


def test_planes_put_communion_right_and_agency_up() -> None:
    ac = describe_state_space("ac")
    ipc = describe_state_space("ipc")

    assert ac["system"] == "cartesian"
    assert ac["axes"] == {"x": "C", "y": "A"}
    assert ipc["system"] == "polar"
    assert ipc["axes"] == {"angle": "Theta", "radius": "R"}


def test_report_embeds_the_record_and_nothing_else(tmp_path: Path) -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)
    record.attach_texts(write_csv(tmp_path / "d.csv", [(1, "A", "A </script> inside.")]))
    report = InteractionReport(record=record, labels={"A": "Daniel Becker"})

    html = report.render()

    assert DATA_PLACEHOLDER not in html
    assert "</script> inside" not in html
    assert "<\\/script> inside" in html
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "https://" not in html

    start = html.index("const DATA = ") + len("const DATA = ")
    data = json.loads(html[start:html.index("\n", start)].rstrip(";").replace("<\\/", "</"))
    assert data["agents"]["A"]["label"] == "Daniel Becker"
    assert data["agents"]["B"]["label"] == "Dummy interpersonal circumplex model"
    assert data["timeSpace"] == "ac"
    assert data["initialTurn"] == 8
    assert len(data["turns"]) == 8
    assert data["printWidth"] == 6.2


@pytest.mark.parametrize(
    "options, message",
    [
        ({"panels": ("dialogue", "table")}, "Unknown panels: table"),
        ({"time_space": "sasb"}, "No agent speaks sasb"),
        ({"initial_turn": 9}, "turns 1 to 8"),
        ({"labels": {"C": "Third"}}, "role C"),
        ({"print_width": 30.0}, "not a page"),
    ],
)
def test_report_refuses_options_the_record_cannot_meet(options: dict, message: str) -> None:
    record = InteractionRecord.from_folder(EXAMPLE_RECORD)

    with pytest.raises(ValueError, match=message):
        InteractionReport(record=record, **options)


def test_runner_writes_the_report_of_the_latest_record(tmp_path: Path) -> None:
    record_interaction(tmp_path, "lassi", "dummy-ipc", turns=4)
    folder = latest_record(tmp_path / "results")
    path = make_report(folder, labels=parse_labels(["A=LASSI model"])).write(tmp_path / "report.html")

    assert path.is_file()
    assert "LASSI model" in path.read_text(encoding="utf-8")


def test_labels_must_name_a_role() -> None:
    assert parse_labels(["A=IPC model", " B = LASSI "]) == {"A": "IPC model", "B": "LASSI"}

    with pytest.raises(SystemExit):
        parse_labels(["IPC model"])
