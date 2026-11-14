'use strict';

(() => {
  const NBSP = ' ';
  const REPEAT_DELAY_MS = 400;
  const REPEAT_INTERVAL_MS = 150;
  const STATE_POLL_MS = 5000;
  const MAX_PENDING_KEYS = 8;
  const PRIMARY_BUTTON = 0;
  const KEYBOARD_CLICK_DETAIL = 0;
  const JSON_HEADERS = { 'Content-Type': 'application/json' };
  const STATE_LABELS = new Map([
    [true, `● Télévision${NBSP}: allumée`],
    [false, `○ Télévision${NBSP}: en veille`],
    [null, `Télévision${NBSP}: état inconnu`],
  ]);

  const pad = document.getElementById('pad');
  const stateLine = document.getElementById('state');
  const message = document.getElementById('message');
  const shortcuts = new Map();
  let pendingKeys = [];
  let sending = false;
  let powerBusy = false;
  let tvOn = null;
  let pollTimer = null;

  async function readError(response) {
    try {
      const body = await response.json();
      return body.error || response.statusText;
    } catch (ex) {
      return response.statusText;
    }
  }

  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    return response.status === 204 ? null : response.json();
  }

  function post(path, body) {
    return request(path, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body) });
  }

  function showError(text) {
    message.textContent = text ? `Échec${NBSP}: ${text}` : '';
  }

  function renderState(on) {
    tvOn = on === true || on === false ? on : null;
    stateLine.textContent = STATE_LABELS.get(tvOn);
  }

  async function refreshState() {
    try {
      const state = await request('/api/state');
      if (!powerBusy) {
        renderState(state.on);
      }
    } catch (ex) {
      if (!powerBusy) {
        renderState(null);
      }
    }
  }

  function schedulePolling() {
    clearInterval(pollTimer);
    pollTimer = null;
    if (document.visibilityState === 'visible') {
      refreshState();
      pollTimer = setInterval(refreshState, STATE_POLL_MS);
    }
  }

  async function sendPendingKeys() {
    sending = true;
    while (pendingKeys.length > 0) {
      const key = pendingKeys.shift();
      try {
        await post('/api/key', { key });
        showError('');
      } catch (ex) {
        pendingKeys = [];
        showError(ex.message);
      }
    }
    sending = false;
  }

  function queueKey(key) {
    if (pendingKeys.length >= MAX_PENDING_KEYS) {
      return;
    }
    pendingKeys.push(key);
    if (!sending) {
      sendPendingKeys();
    }
  }

  async function togglePower(button) {
    if (powerBusy) {
      return;
    }
    powerBusy = true;
    button.disabled = true;
    stateLine.textContent = tvOn ? 'Extinction en cours…' : 'Allumage en cours…';
    try {
      const state = await post('/api/power', {});
      showError('');
      renderState(state.on);
    } catch (ex) {
      showError(ex.message);
      renderState(null);
    } finally {
      powerBusy = false;
      button.disabled = false;
    }
  }

  function bindRepeat(button, key) {
    let delayTimer = null;
    let repeatTimer = null;
    const stop = () => {
      clearTimeout(delayTimer);
      clearInterval(repeatTimer);
      delayTimer = null;
      repeatTimer = null;
      button.classList.remove('pressed');
    };
    button.addEventListener('pointerdown', (event) => {
      if (event.button !== PRIMARY_BUTTON) {
        return;
      }
      event.preventDefault();
      stop();
      button.setPointerCapture(event.pointerId);
      button.classList.add('pressed');
      queueKey(key);
      delayTimer = setTimeout(() => {
        repeatTimer = setInterval(() => queueKey(key), REPEAT_INTERVAL_MS);
      }, REPEAT_DELAY_MS);
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((type) => {
      button.addEventListener(type, stop);
    });
    button.addEventListener('click', (event) => {
      if (event.detail === KEYBOARD_CLICK_DETAIL) {
        queueKey(key);
      }
    });
  }

  function createButton(cell, powerAction) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = cell.label;
    button.title = cell.title;
    button.setAttribute('aria-label', cell.title);
    if (cell.style) {
      button.classList.add(`style-${cell.style}`);
    }
    if (cell.key === powerAction) {
      button.addEventListener('click', () => togglePower(button));
    } else if (cell.repeat) {
      bindRepeat(button, cell.key);
    } else {
      button.addEventListener('click', () => queueKey(cell.key));
    }
    cell.web_keys.forEach((name) => shortcuts.set(name, cell));
    return button;
  }

  function onKeyDown(event) {
    if (event.ctrlKey || event.altKey || event.metaKey) {
      return;
    }
    const name = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    const cell = shortcuts.get(name);
    if (!cell) {
      return;
    }
    event.preventDefault();
    if (!event.repeat || cell.repeat) {
      queueKey(cell.key);
    }
  }

  async function start() {
    try {
      const { layout, power } = await request('/api/layout');
      layout.forEach((row) => {
        row.forEach((cell) => {
          pad.appendChild(cell ? createButton(cell, power) : document.createElement('span'));
        });
      });
    } catch (ex) {
      showError(ex.message);
      return;
    }
    pad.addEventListener('contextmenu', (event) => event.preventDefault());
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('visibilitychange', schedulePolling);
    schedulePolling();
  }

  start();
})();
