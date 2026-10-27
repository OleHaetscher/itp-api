'use strict';

// IPC behavior is represented as {Theta, R}; SVG positions are Cartesian.
const SVG_CENTER = 180;
const SVG_RADIUS = 128;
const SVG_NS = 'http://www.w3.org/2000/svg';

/** Create the rendering and input controller for both circumplexes. */
export function createCircumplexUI({ isReady, getSelection, onSelection }) {
  const elements = {
    currentOtherPoint: document.getElementById('current-other-point'),
    currentSelfPoint: document.getElementById('current-self-point'),
    otherHistoryLines: document.getElementById('other-history-lines'),
    otherHistoryPoints: document.getElementById('other-history-points'),
    selfHistoryLines: document.getElementById('self-history-lines'),
    selfHistoryPoints: document.getElementById('self-history-points'),
    selfCircle: document.getElementById('self-circle'),
    otherDescription: document.getElementById('other-description'),
    selfDescription: document.getElementById('self-description'),
    turn: document.getElementById('turn-indicator'),
    status: document.getElementById('status-message'),
    error: document.getElementById('error-message'),
    submit: document.getElementById('submit-button'),
    restart: document.getElementById('restart-button'),
  };

  let activePointer = null;

  /** Format an IPC coordinate pair for a short text summary. */
  function pointText({ Theta, R }) {
    const format = (value, digits) => Number(value).toLocaleString('en-US', {
      maximumFractionDigits: digits,
    });
    return `Θ ${format(Theta, 2)}° · R ${format(R, 3)}`;
  }

  /** Convert a polar IPC state to a position in the SVG viewBox. */
  function polarToSvg({ Theta, R }) {
    const angle = Theta * Math.PI / 180;
    return {
      x: SVG_CENTER + SVG_RADIUS * R * Math.cos(angle),
      y: SVG_CENTER - SVG_RADIUS * R * Math.sin(angle),
    };
  }

  /** Move a point or hide it when no current value is available. */
  function positionPoint(element, polar) {
    if (!polar) {
      element.setAttribute('hidden', '');
      return;
    }
    const { x, y } = polarToSvg(polar);
    element.setAttribute('cx', String(x));
    element.setAttribute('cy', String(y));
    element.removeAttribute('hidden');
  }

  /** Draw all previous states and progressively fade older segments. */
  function renderHistory(linesElement, pointsElement, history, current = null) {
    linesElement.replaceChildren();
    pointsElement.replaceChildren();
    const sequence = current ? [...history, current] : [...history];

    for (let index = 1; index < sequence.length; index += 1) {
      const start = polarToSvg(sequence[index - 1]);
      const end = polarToSvg(sequence[index]);
      const progress = index / (sequence.length - 1);
      const line = document.createElementNS(SVG_NS, 'line');
      line.setAttribute('class', 'history-line');
      line.setAttribute('x1', String(start.x));
      line.setAttribute('y1', String(start.y));
      line.setAttribute('x2', String(end.x));
      line.setAttribute('y2', String(end.y));
      line.setAttribute('opacity', String(0.12 + progress * 0.4));
      linesElement.appendChild(line);
    }

    history.forEach((point, index) => {
      const { x, y } = polarToSvg(point);
      const progress = (index + 1) / history.length;
      const circle = document.createElementNS(SVG_NS, 'circle');
      circle.setAttribute('class', 'history-point');
      circle.setAttribute('cx', String(x));
      circle.setAttribute('cy', String(y));
      circle.setAttribute('r', '6');
      circle.setAttribute('opacity', String(0.12 + progress * 0.48));
      pointsElement.appendChild(circle);
    });
  }

  /** Rebuild both trails and display their newest points in color. */
  function renderCircles(state) {
    const currentOther = state.otherHistory.at(-1) ?? null;
    renderHistory(
      elements.otherHistoryLines,
      elements.otherHistoryPoints,
      state.otherHistory.slice(0, -1),
      currentOther,
    );
    positionPoint(elements.currentOtherPoint, currentOther);

    // A draft selection is current; otherwise the latest submitted action is current.
    const lastSelf = state.selfHistory.at(-1) ?? null;
    const currentSelf = state.selected ?? lastSelf;
    const priorSelf = state.selected ? state.selfHistory : state.selfHistory.slice(0, -1);
    renderHistory(elements.selfHistoryLines, elements.selfHistoryPoints, priorSelf, currentSelf);
    positionPoint(elements.currentSelfPoint, currentSelf);
  }

  /** Render the turn indicator, action buttons, and coordinate summaries. */
  function render(state, maxTurns) {
    renderCircles(state);
    const ready = state.phase === 'ready';
    elements.selfCircle.classList.toggle('is-disabled', !ready);
    elements.selfCircle.setAttribute('aria-disabled', String(!ready));
    elements.submit.disabled = !ready || state.selected === null;
    elements.submit.textContent = state.phase === 'submitting' ? 'Submitting…' : 'Submit response →';
    elements.restart.hidden = state.phase !== 'completed' && state.phase !== 'error';

    if (state.phase === 'completed') {
      elements.turn.textContent = `${state.finalTurn ?? maxTurns} / ${maxTurns} turns`;
    } else if (state.turn !== null) {
      elements.turn.textContent = `Turn ${state.turn} / ${maxTurns}`;
    } else {
      elements.turn.textContent = state.phase === 'starting' ? 'Connecting…' : `Turn 1 / ${maxTurns}`;
    }

    const currentOther = state.otherHistory.at(-1) ?? null;
    elements.otherDescription.textContent = currentOther
      ? `Current behavior: ${pointText(currentOther)}`
      : 'No behavior received yet';

    if (state.selected) {
      elements.selfDescription.textContent = `Current selection: ${pointText(state.selected)}`;
    } else if (ready) {
      elements.selfDescription.textContent = 'Select a point inside the circle';
    } else if (state.phase === 'completed') {
      elements.selfDescription.textContent = 'Interaction completed';
    } else {
      elements.selfDescription.textContent = 'Waiting for the next turn';
    }
  }

  /** Show the latest interaction status in the UI. */
  function setStatus(message) {
    elements.status.textContent = message;
  }

  /** Remove an existing error notice. */
  function clearError() {
    elements.error.hidden = true;
    elements.error.textContent = '';
  }

  /** Display a non-sensitive error message. */
  function setError(message) {
    elements.error.textContent = message;
    elements.error.hidden = false;
  }

  /** Briefly fade in a newly received Other behavior. */
  function animateOtherPoint() {
    elements.currentOtherPoint.classList.add('point-entering');
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      elements.currentOtherPoint.classList.remove('point-entering');
    }));
  }

  /** Convert a pointer event into unit-circle Cartesian coordinates. */
  function coordinatesFromPointer(event) {
    const point = elements.selfCircle.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transform = elements.selfCircle.getScreenCTM();
    if (!transform) {
      return null;
    }
    const result = point.matrixTransform(transform.inverse());
    return {
      x: (result.x - SVG_CENTER) / SVG_RADIUS,
      y: (SVG_CENTER - result.y) / SVG_RADIUS,
    };
  }

  /** Clamp a position to the circle and report it in IPC coordinates. */
  function chooseCartesian(x, y) {
    if (!isReady()) {
      return;
    }
    const distance = Math.hypot(x, y);
    if (distance > 1) {
      x /= distance;
      y /= distance;
    }
    const radius = Math.round(Math.min(1, Math.hypot(x, y)) * 1e6) / 1e6;
    let theta = radius === 0 ? 0 : Math.round(((Math.atan2(y, x) * 180 / Math.PI + 360) % 360) * 1e6) / 1e6;
    if (theta >= 360) {
      theta = 0;
    }
    onSelection({ Theta: theta, R: radius });
  }

  /** Begin a new mouse, touch, or pen selection inside the circle. */
  function onPointerDown(event) {
    if (!isReady() || activePointer !== null) {
      return;
    }
    if (event.pointerType === 'mouse' && event.button !== 0) {
      return;
    }
    const point = coordinatesFromPointer(event);
    if (!point || Math.hypot(point.x, point.y) > 1) {
      return;
    }
    event.preventDefault();
    activePointer = event.pointerId;
    elements.selfCircle.setPointerCapture(event.pointerId);
    chooseCartesian(point.x, point.y);
  }

  /** Update the draft selection while its pointer is being dragged. */
  function onPointerMove(event) {
    if (activePointer !== event.pointerId || !isReady()) {
      return;
    }
    event.preventDefault();
    const point = coordinatesFromPointer(event);
    if (point) {
      chooseCartesian(point.x, point.y);
    }
  }

  /** Finish an active drag, preserving the final pointer position. */
  function releasePointer(event) {
    if (activePointer !== event.pointerId) {
      return;
    }
    if (event.type === 'pointerup' && isReady()) {
      const point = coordinatesFromPointer(event);
      if (point) {
        chooseCartesian(point.x, point.y);
      }
    }
    activePointer = null;
    if (elements.selfCircle.hasPointerCapture(event.pointerId)) {
      elements.selfCircle.releasePointerCapture(event.pointerId);
    }
  }

  /** Support keyboard selection using arrow keys and the Home key. */
  function onKeyDown(event) {
    if (!isReady()) {
      return;
    }
    const arrows = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, 1],
      ArrowDown: [0, -1],
    };
    if (event.key === 'Home') {
      event.preventDefault();
      chooseCartesian(0, 0);
      return;
    }
    if (!Object.prototype.hasOwnProperty.call(arrows, event.key)) {
      return;
    }
    event.preventDefault();
    const current = getSelection() ?? { Theta: 0, R: 0 };
    const angle = current.Theta * Math.PI / 180;
    const delta = event.shiftKey ? 0.15 : 0.05;
    const [dx, dy] = arrows[event.key];
    chooseCartesian(
      current.R * Math.cos(angle) + delta * dx,
      current.R * Math.sin(angle) + delta * dy,
    );
  }

  /** Reset pointer capture when switching to a different interaction. */
  function resetInput() {
    if (activePointer !== null && elements.selfCircle.hasPointerCapture(activePointer)) {
      elements.selfCircle.releasePointerCapture(activePointer);
    }
    activePointer = null;
    elements.currentOtherPoint.classList.remove('point-entering');
  }

  elements.selfCircle.addEventListener('pointerdown', onPointerDown);
  elements.selfCircle.addEventListener('pointermove', onPointerMove);
  elements.selfCircle.addEventListener('pointerup', releasePointer);
  elements.selfCircle.addEventListener('pointercancel', releasePointer);
  elements.selfCircle.addEventListener('lostpointercapture', event => {
    if (activePointer === event.pointerId) {
      activePointer = null;
    }
  });
  elements.selfCircle.addEventListener('keydown', onKeyDown);

  return { render, setStatus, clearError, setError, animateOtherPoint, resetInput };
}
