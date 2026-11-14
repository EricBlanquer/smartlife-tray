'use strict';

(() => {
  const NBSP = ' ';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const REPEAT_DELAY_MS = 400;
  const REPEAT_INTERVAL_MS = 150;
  const STATE_POLL_MS = 5000;
  const MAX_PENDING_KEYS = 8;
  const PRIMARY_BUTTON = 0;
  const KEYBOARD_CLICK_DETAIL = 0;
  const WHEEL_UP_INDEX = 0;
  const WHEEL_DOWN_INDEX = 1;
  const JSON_HEADERS = { 'Content-Type': 'application/json' };
  const STATE_LABELS = new Map([
    [true, `● Télévision${NBSP}: allumée`],
    [false, `○ Télévision${NBSP}: en veille`],
    [null, `Télévision${NBSP}: état inconnu`],
  ]);

  const remote = document.getElementById('remote');
  const panel = document.getElementById('panel');
  const stateLine = document.getElementById('state');
  const message = document.getElementById('message');
  const shortcuts = new Map();
  const actions = { power: null, panel: null };
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

  function setPowerBusy(busy) {
    powerBusy = busy;
    document.querySelectorAll(`[data-key="${actions.power}"]`).forEach((element) => {
      element.classList.toggle('busy', busy);
      element.setAttribute('aria-disabled', String(busy));
    });
  }

  async function togglePower() {
    if (powerBusy) {
      return;
    }
    setPowerBusy(true);
    stateLine.textContent = tvOn ? 'Extinction en cours…' : 'Allumage en cours…';
    try {
      const state = await post('/api/power', {});
      showError('');
      renderState(state.on);
    } catch (ex) {
      showError(ex.message);
      renderState(null);
    } finally {
      setPowerBusy(false);
    }
  }

  function togglePanel() {
    panel.hidden = !panel.hidden;
  }

  function activate(key) {
    if (key === actions.power) {
      togglePower();
    } else if (key === actions.panel) {
      togglePanel();
    } else {
      queueKey(key);
    }
  }

  function bindRepeat(element, key) {
    let delayTimer = null;
    let repeatTimer = null;
    const stop = () => {
      clearTimeout(delayTimer);
      clearInterval(repeatTimer);
      delayTimer = null;
      repeatTimer = null;
      element.classList.remove('pressed');
    };
    element.addEventListener('pointerdown', (event) => {
      if (event.button !== PRIMARY_BUTTON) {
        return;
      }
      event.preventDefault();
      stop();
      element.setPointerCapture(event.pointerId);
      element.classList.add('pressed');
      queueKey(key);
      delayTimer = setTimeout(() => {
        repeatTimer = setInterval(() => queueKey(key), REPEAT_INTERVAL_MS);
      }, REPEAT_DELAY_MS);
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((type) => {
      element.addEventListener(type, stop);
    });
    element.addEventListener('click', (event) => {
      if (event.detail === KEYBOARD_CLICK_DETAIL) {
        queueKey(key);
      }
    });
  }

  function bindActivation(element, key, repeat) {
    element.dataset.key = key;
    if (repeat) {
      bindRepeat(element, key);
    } else {
      element.addEventListener('click', () => activate(key));
    }
  }

  function createButton(cell) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = cell.label;
    button.title = cell.title;
    button.setAttribute('aria-label', cell.title);
    if (cell.style) {
      button.classList.add(`style-${cell.style}`);
    }
    bindActivation(button, cell.key, cell.repeat);
    return button;
  }

  function fillGrid(container, layout) {
    layout.forEach((row) => {
      row.forEach((cell) => {
        container.appendChild(cell ? createButton(cell) : document.createElement('span'));
      });
    });
  }

  function createHotspot(spot) {
    const path = document.createElementNS(SVG_NS, 'path');
    const title = document.createElementNS(SVG_NS, 'title');
    path.setAttribute('d', spot.path);
    path.setAttribute('class', 'hotspot');
    path.setAttribute('role', 'button');
    path.setAttribute('aria-label', spot.title);
    title.textContent = spot.title;
    path.appendChild(title);
    bindActivation(path, spot.key, spot.repeat);
    if (spot.wheel) {
      path.addEventListener('wheel', (event) => {
        if (event.deltaY === 0) {
          return;
        }
        event.preventDefault();
        queueKey(spot.wheel[event.deltaY < 0 ? WHEEL_UP_INDEX : WHEEL_DOWN_INDEX]);
      }, { passive: false });
    }
    return path;
  }

  function createSkin(skin, label) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    const image = document.createElementNS(SVG_NS, 'image');
    svg.setAttribute('viewBox', `0 0 ${skin.width} ${skin.height}`);
    svg.setAttribute('class', 'skin');
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', label);
    image.setAttribute('href', skin.image);
    image.setAttribute('width', skin.width);
    image.setAttribute('height', skin.height);
    svg.appendChild(image);
    skin.hotspots.forEach((spot) => svg.appendChild(createHotspot(spot)));
    return svg;
  }

  function mountSkin(container, skin, label) {
    container.classList.add('has-skin');
    container.style.setProperty('--skin-aspect', `${skin.width} / ${skin.height}`);
    container.appendChild(createSkin(skin, label));
  }

  function registerShortcuts(layout) {
    layout.forEach((row) => {
      row.forEach((cell) => {
        if (cell) {
          cell.web_keys.forEach((name) => shortcuts.set(name, cell));
        }
      });
    });
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
      activate(cell.key);
    }
  }

  async function start() {
    try {
      const layout = await request('/api/layout');
      actions.power = layout.power;
      actions.panel = layout.panel;
      registerShortcuts(layout.layout);
      if (layout.skin) {
        mountSkin(remote, layout.skin, 'Télécommande');
        mountSkin(panel, layout.keypad, 'Autres touches et chiffres');
      } else {
        remote.classList.add('pad');
        fillGrid(remote, layout.layout);
      }
    } catch (ex) {
      showError(ex.message);
      return;
    }
    document.querySelector('.layout').addEventListener('contextmenu', (event) => event.preventDefault());
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('visibilitychange', schedulePolling);
    schedulePolling();
  }

  start();
})();
