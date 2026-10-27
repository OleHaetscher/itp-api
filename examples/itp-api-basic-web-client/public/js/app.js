'use strict';

import { api, cancelRequests, ClientError } from './api.js';
import { createCircumplexUI } from './circumplex.js';

// Temporary state for one ten-turn interaction; no browser persistence.
const MAX_TURNS = 10;
const state = {
  epoch: 0,
  phase: 'starting', // starting | waiting | ready | submitting | completed | error
  sessionActive: false,
  cursor: null,
  lastPerceptionId: null,
  turn: null,
  otherHistory: [],
  selfHistory: [],
  selected: null,
  nextActionNumber: 1,
  finalTurn: null,
};

const ui = createCircumplexUI({
  isReady: () => state.phase === 'ready',
  getSelection: () => state.selected,
  onSelection: behavior => {
    state.selected = behavior;
    ui.render(state, MAX_TURNS);
  },
});

/** Return true only for responses from the current interaction. */
function isCurrent(epoch) {
  return epoch === state.epoch;
}

/** Wait between polling attempts without blocking the UI. */
function sleep(ms) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

/** Display an error and offer a fresh interaction instead of retrying an action. */
function showError(error) {
  state.phase = 'error';
  // An unconfirmed draft must not appear as an accepted Self behavior.
  state.selected = null;
  ui.setStatus('Interaction stopped.');
  ui.setError(error instanceof Error ? error.message : 'Unknown error.');
  ui.render(state, MAX_TURNS);
}

/** Finish the interaction while keeping both behavior trails visible. */
function finish(turn = MAX_TURNS) {
  state.phase = 'completed';
  state.finalTurn = turn;
  state.selected = null;
  ui.clearError();
  ui.setStatus(`Interaction completed – ${turn} of ${MAX_TURNS} turns.`);
  ui.render(state, MAX_TURNS);
}

/** Reset all browser state for a new interaction. */
function resetState() {
  state.sessionActive = false;
  state.cursor = null;
  state.lastPerceptionId = null;
  state.turn = null;
  state.otherHistory = [];
  state.selfHistory = [];
  state.selected = null;
  state.nextActionNumber = 1;
  state.finalTurn = null;
  ui.resetInput();
  ui.render(state, MAX_TURNS);
}

/** Create and register a new LASSI interaction through the PHP adapter. */
async function startNew() {
  const oldActive = state.sessionActive && state.phase !== 'completed';
  const epoch = ++state.epoch;
  cancelRequests();
  state.phase = 'starting';
  resetState();
  ui.clearError();
  ui.setStatus('Waiting for Other…');

  try {
    // An explicit restart ends the old interaction when possible.
    if (oldActive) {
      try {
        await api('end', { method: 'POST', body: {} });
      } catch {
        // A missing or expired old session should not prevent a fresh start.
      }
      if (!isCurrent(epoch)) return;
    }

    const result = await api('start', { method: 'POST', body: {} });
    if (!isCurrent(epoch)) return;
    if (result.ok !== true) throw new ClientError('Could not start the interaction.');

    state.sessionActive = true;
    state.phase = 'waiting';
    ui.render(state, MAX_TURNS);
    void pollPerception(epoch);
  } catch (error) {
    if (!isCurrent(epoch) || error.name === 'AbortError') return;
    showError(error);
  }
}

/** Poll for new Other behavior until Self is allowed to act. */
async function pollPerception(epoch) {
  while (isCurrent(epoch) && state.phase === 'waiting') {
    try {
      const result = await api('perception', { query: { after: state.cursor } });
      if (!isCurrent(epoch) || state.phase !== 'waiting') return;

      if (result.cursor != null) state.cursor = String(result.cursor);
      if (result.state === 'interactionEnded' || result.sessionStatus === 'completed') {
        finish(Number.isInteger(result.finalTurn) ? result.finalTurn : MAX_TURNS);
        return;
      }

      if (result.state === 'perceivable') {
        const behavior = result.experience;
        if (!behavior || !Number.isFinite(behavior.Theta) || !Number.isFinite(behavior.R)) {
          throw new ClientError('The perception contains invalid IPC coordinates.');
        }
        if (result.perceptionId !== state.lastPerceptionId) {
          state.otherHistory.push({ Theta: behavior.Theta, R: behavior.R });
          state.lastPerceptionId = result.perceptionId;
          ui.render(state, MAX_TURNS);
          ui.animateOtherPoint();
        }
      }

      if (result.state === 'perceivable' || result.state === 'actionRequired') {
        if (result.actionRequired === true || result.state === 'actionRequired') {
          if (!Number.isInteger(result.turn) || result.turn < 1 || result.turn > MAX_TURNS) {
            throw new ClientError('The API returned an invalid turn number.');
          }
          state.turn = result.turn;
          state.selected = null;
          state.phase = 'ready';
          ui.setStatus('Choose your response.');
          ui.render(state, MAX_TURNS);
          return;
        }
      } else if (result.state !== 'pending') {
        throw new ClientError('Unknown API state.');
      }

      const delay = Number.isFinite(result.retryAfterMilliseconds)
        ? result.retryAfterMilliseconds : 500;
      await sleep(Math.max(200, Math.min(10000, delay)));
    } catch (error) {
      if (!isCurrent(epoch) || error.name === 'AbortError') return;
      showError(error);
      return;
    }
  }
}

/** Submit one numbered Self action, then wait for the next perception. */
async function submitChoice() {
  if (state.phase !== 'ready' || !state.selected || !Number.isInteger(state.turn)) return;

  const epoch = state.epoch;
  const behavior = { ...state.selected };
  const turn = state.turn;
  const actionId = `action-${state.nextActionNumber++}`;
  state.phase = 'submitting';
  ui.render(state, MAX_TURNS);

  try {
    const result = await api('act', { method: 'POST', body: { actionId, turn, behavior } });
    if (!isCurrent(epoch)) return;
    if (result.status !== 'accepted' || result.turn !== turn) {
      throw new ClientError('The API did not confirm the action.');
    }

    state.selfHistory.push(behavior);
    state.selected = null;
    if (result.sessionStatus === 'completed') {
      finish(MAX_TURNS);
      return;
    }

    state.phase = 'waiting';
    ui.setStatus('Waiting for Other…');
    ui.render(state, MAX_TURNS);
    void pollPerception(epoch);
  } catch (error) {
    if (!isCurrent(epoch) || error.name === 'AbortError') return;
    // Never resend an action whose outcome might already be committed.
    showError(error);
  }
}

// Only the submission and fresh-start controls are needed.
document.getElementById('submit-button').addEventListener('click', () => { void submitChoice(); });
document.getElementById('restart-button').addEventListener('click', () => { void startNew(); });

ui.render(state, MAX_TURNS);
void startNew();
