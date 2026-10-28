# Interaction report example

The run behind Figure 2 of the ITP paper, and its report.

Open `interaction_report.html` in a browser. It needs no server and fetches nothing. The slider
steps through the eight turns. *Download SVG* and *Download PNG* export the figure at the selected
turn; the paper shows turn 8.

## What is here

| File | What it is |
|---|---|
| `record/20261028_084932_e673581f/` | The record the API wrote: `interaction.json` and one file per ITP message |
| `dialogue.csv` | The text of each turn, joined on `turn` and `role` |
| `interaction_report.html` | The report written from both |

## The interaction

Agent A runs the dummy IPC model (`dummy-ipc`) in the interpersonal circumplex. Agent B runs the
LASSI model (`lassi`) in the agency-communion box. A acts first, for eight turns, with
persistence on. Every behavior crosses state spaces, so each turn is stored twice: once as sent
and once as converted for the partner.

The run was recorded in-process through `APISpecification`, with the catalogue of
`src.run_model_api.make_catalogue()`. This is the same as sending the following request to a
running API:

```json
{
  "modelId": "dummy-ipc",
  "numberOfTurns": 8,
  "persistence": {"enabled": true},
  "agents": {"A": {"type": "model"}, "B": {"type": "model", "modelId": "lassi"}}
}
```

A new run gives different numbers, because the dummy model starts from a random state and LASSI
samples its behavior. The record in this folder is therefore the reference, not the command.

## The dialogue is illustrative

No language model produced `dialogue.csv`. The text was written by hand to fit the recorded
values. Agent A starts very submissive (A = 1 after conversion) and moves toward friendly and
slightly dominant. Agent B stays warm and moderately dominant. The report states this in its
header. Text from a real paradigm, such as a PerTRAIN chat, is exported there and supplied the
same way. It is never stored on the ITP platform.

## Rebuild the report

From the repository root:

```bash
python -m src.run_interaction_report examples/interaction-report/record/20261028_084932_e673581f \
    --text examples/interaction-report/dialogue.csv \
    --text-source "illustrative text written to fit the recorded values, not produced by a language model" \
    --label A="IPC model" --label B="LASSI model" \
    --title "IPC model and LASSI model, eight turns" \
    --out examples/interaction-report/interaction_report.html
```
