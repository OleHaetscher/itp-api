from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.API.StateSpaceSchema import StateSpaceSchema
from src.ITPSpecification import ITPSpecification

# Columns of a dialogue file. The text a paradigm produces (for example the
# utterances of a PerTRAIN chat) is not part of the ITP record, so it is
# supplied beside it and joined on the turn and the role of the sender.
TEXT_COLUMNS = ("turn", "role", "text")


class InteractionRecord:
    """
    One recorded interaction, read from the folder the API writes it to.

    The folder holds interaction.json and one file per ITP message, as written
    by Communication.save_message. Every behavior appears once as sent, in the
    state space of its sender, and, when the two agents speak different state
    spaces, once more as converted into the state space of the receiver. This
    class pairs the two into one turn, so that a figure can show the same
    behavior in both spaces.

    A turn here is one message, the API's turn (timecode.api_turn): agent A
    acts in turn 1, agent B in turn 2, and so on. timecode.interaction_turn
    counts exchanges instead and is not used for stepping.

    Args:

    Returns:
    """

    specification = ITPSpecification()

    def __init__(
        self,
        interaction: dict[str, Any],
        messages: list[dict[str, Any]],
        folder_name: str = "",
    ) -> None:
        """
        Build a record from the interaction description and its messages.

        Args:
            interaction: Content of interaction.json.
            messages: ITP messages in the order they were stored.
            folder_name: Name of the results folder, kept for reference.

        Returns:
        """

        for message in messages:
            self.specification.validate_message(message=message)

        self.interaction = interaction
        self.messages = messages
        self.folder_name = folder_name
        self.agents = self._collect_agents()
        self.turns = self._pair_turns()
        self.texts: dict[int, str] = {}
        self.text_source = ""

    @classmethod
    def from_folder(
        cls,
        folder: str | Path,
    ) -> InteractionRecord:
        """
        Read a results folder written by the API.

        Args:
            folder: Path to results/<timestamp>_<session prefix>/.

        Returns:
            Interaction record.
        """

        folder = Path(folder)
        interaction_path = folder / "interaction.json"

        if not interaction_path.is_file():
            raise FileNotFoundError(f"No interaction.json in {folder}.")

        interaction = json.loads(interaction_path.read_text(encoding="utf-8"))
        messages = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("message_*.json"))
        ]

        if not messages:
            raise ValueError(f"{folder} holds no ITP messages.")

        return cls(interaction=interaction, messages=messages, folder_name=folder.name)

    def _collect_agents(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Describe both agents, with the state space each one speaks.

        Args:

        Returns:
            Dictionary mapping roles to agent descriptions.
        """

        agents: dict[str, dict[str, Any]] = {}

        for role, agent in sorted(self.interaction["agents"].items()):
            model = agent.get("model")
            agents[role] = {
                "role": role,
                "id": agent["agentId"],
                "type": agent["type"],
                "model": model["name"] if model else None,
                "modelId": model["id"] if model else None,
                "stateSpace": describe_state_space(agent["stateSpace"]),
            }

        return agents

    def _pair_turns(
        self,
    ) -> list[dict[str, Any]]:
        """
        Pair each sent behavior with its converted copy.

        Args:

        Returns:
            Turns in order, each with the behavior as sent and as received.
        """

        role_of = {agent["id"]: role for role, agent in self.agents.items()}
        turns: dict[int, dict[str, Any]] = {}
        originals = 0

        for message in self.messages:
            metadata = message.get("metadata") or {}
            converted = metadata.get("message_type") == "converted"

            if not converted:
                originals += 1

            # Records written before api_turn existed fall back to the order
            # of the original messages, which is the same thing.
            turn = message["timecode"].get("api_turn", originals)
            role = role_of[message["source_agent"]["id"]]
            entry = turns.setdefault(
                turn,
                {"turn": turn, "role": role, "messages": {}},
            )

            if entry["role"] != role:
                raise ValueError(f"Turn {turn} holds messages from both agents.")

            values = {
                "stateSpace": message["values"]["state_space"],
                "data": message["values"]["data"],
            }

            if converted:
                values["converter"] = metadata["conversion"]["converter"]
                entry["received"] = values
                entry["messages"]["converted"] = message
            else:
                entry["sent"] = values
                entry["interactionTurn"] = message["timecode"].get("interaction_turn")
                entry["messages"]["original"] = message

        for entry in turns.values():
            if "sent" not in entry:
                raise ValueError(f"Turn {entry['turn']} has no original message.")

            # Without a conversion the receiver got exactly what was sent.
            entry.setdefault("received", dict(entry["sent"]))

        return [turns[turn] for turn in sorted(turns)]

    def attach_texts(
        self,
        path: str | Path,
        source: str = "",
    ) -> None:
        """
        Join a dialogue file to the record.

        The file is a CSV with the columns turn, role and text. Every row must
        name a turn of this record and the role that acted in it; a row that
        does not is an error rather than a silent mismatch, because a text
        shown beside the wrong numbers is worse than none.

        Args:
            path: Path to the dialogue CSV.
            source: Short statement of where the text comes from, shown in
                the report.

        Returns:
        """

        role_by_turn = {entry["turn"]: entry["role"] for entry in self.turns}
        texts: dict[int, str] = {}

        with open(path, encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)

            missing = [column for column in TEXT_COLUMNS if column not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path} lacks the columns {', '.join(missing)}.")

            for line, row in enumerate(reader, start=2):
                turn = int(row["turn"])
                role = row["role"].strip()

                if turn not in role_by_turn:
                    raise ValueError(f"{path}, line {line}: the record has no turn {turn}.")
                if role != role_by_turn[turn]:
                    raise ValueError(
                        f"{path}, line {line}: turn {turn} was taken by agent "
                        f"{role_by_turn[turn]}, not {role}."
                    )
                if turn in texts:
                    raise ValueError(f"{path}, line {line}: turn {turn} appears twice.")

                texts[turn] = row["text"].strip()

        self.texts = texts
        self.text_source = source

    def to_report_data(
        self,
    ) -> dict[str, Any]:
        """
        Collect everything a report needs, as JSON-serializable data.

        Args:

        Returns:
            Report data.
        """

        return {
            "sessionId": self.interaction.get("sessionId"),
            "resultsFolder": self.folder_name,
            "context": self.interaction.get("context"),
            "status": self.interaction.get("status"),
            "endReason": self.interaction.get("endReason"),
            "numberOfTurns": self.interaction.get("numberOfTurns"),
            "agents": self.agents,
            "turns": self.turns,
            "texts": {str(turn): text for turn, text in self.texts.items()},
            "textSource": self.text_source,
        }


def describe_state_space(
    state_space: str,
) -> dict[str, Any]:
    """
    Describe a state space in the terms a plane or a time axis needs.

    Cartesian spaces put communion on the horizontal and agency on the
    vertical axis when they have both, which is the orientation of the
    circumplex (angle zero at positive communion, counterclockwise toward
    positive agency). Two spaces drawn side by side then point the same way.

    Args:
        state_space: ITP state space identifier.

    Returns:
        Identifier, names, coordinate system and dimensions with their ranges.
    """

    description = StateSpaceSchema.from_state_space(state_space).describe()
    space = description["stateSpaceDescription"]
    coordinates = space["coordinates"]
    system = coordinates["system"]

    if system == "polar":
        angle = coordinates["angle"]
        radius = coordinates["radius"]
        dimensions = [
            {
                "key": angle["abbreviation"],
                "caption": angle["caption"],
                "minimum": 0,
                "maximum": 360,
                "unit": angle.get("unit", "degree"),
            },
            {
                "key": radius["abbreviation"],
                "caption": radius["caption"],
                "minimum": radius["range"]["minimum"],
                "maximum": radius["range"]["maximum"],
            },
        ]
        axes = {"angle": angle["abbreviation"], "radius": radius["abbreviation"]}
    else:
        dimensions = [
            {
                "key": dimension["abbreviation"],
                "caption": dimension["caption"],
                "minimum": dimension["range"]["minimum"],
                "maximum": dimension["range"]["maximum"],
            }
            for dimension in coordinates["dimensions"]
        ]
        keys = [dimension["key"] for dimension in dimensions]
        captions = {dimension["caption"].lower(): dimension["key"] for dimension in dimensions}
        horizontal = captions.get("communion", keys[0])
        vertical = captions.get("agency", next(key for key in keys if key != horizontal))
        axes = {"x": horizontal, "y": vertical}

    return {
        "id": description["stateSpace"],
        "abbreviation": space["abbreviation"],
        "caption": space["caption"],
        "type": space["type"],
        "system": system,
        "dimensions": dimensions,
        "axes": axes,
    }
