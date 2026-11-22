// Lists the snapshots archived in a Home Assistant media folder as events, newest
// first, grouped by day. The time of an event is the one in the file name
// (YYYY-MM-DD_HH-MM-SS.jpg, written in Home Assistant's time zone), so it is shown
// as written whatever the time zone of the phone.
//
// The pictures are never requested by path: each one is resolved through the
// `media_source/resolve_media` WebSocket command when it scrolls into view, which
// returns a short-lived signed URL for the logged-in user.
//
// It is also a custom panel (panel_custom with this element name): Home Assistant then
// loads the module before it creates the element, which a card on a dashboard does not
// get (after a full reload of the phone app the card was not yet defined when the
// dashboard drew it). As a panel the configuration arrives as the `config` of the panel.
//
// As a panel it also has a Live tab, which starts and stops the camera's live view
// (a switch entity) and shows its frames (an image entity):
//
//   live:
//     switch: switch.front_door_live_view
//     image: image.front_door_live
//     online: binary_sensor.front_door_camera_online
//
//   type: custom:front-door-events-card
//   page_size: 30                    # events added by each "Show older events"
//   sources:                         # one entry per kind of event
//     - label: Motion
//       icon: mdi:motion-sensor
//       media_content_id: media-source://media_source/front_door

const NAME = /^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.jpg$/;
const LATEST = "latest";

const STYLE = `
  :host { display: block; }
  :host([panel]) { min-height: 100%; box-sizing: border-box;
    background: var(--primary-background-color); color: var(--primary-text-color); }
  .toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    font-size: 1.25rem; font-weight: 500; }
  .toolbar button { font-size: 1.4rem; line-height: 1; padding: 6px 12px; }
  .tabs { display: flex; gap: 8px; margin: 0 12px 8px; }
  .tabs button { flex: 1; }
  .tabs button[aria-pressed="true"] { background: var(--primary-color);
    color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .live .controls { display: flex; gap: 8px; margin-bottom: 12px; }
  .live .controls button { flex: 1; }
  .live button:disabled { opacity: 0.5; cursor: default; }
  .live img { display: block; width: 100%; border-radius: 8px;
    background: var(--secondary-background-color); }
  ha-card { padding: 12px; box-sizing: border-box; }
  .bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
  .bar select { flex: 1; min-width: 0; font: inherit; padding: 8px; border-radius: 8px;
    color: var(--primary-text-color); background: var(--card-background-color);
    border: 1px solid var(--divider-color); }
  button { font: inherit; cursor: pointer; padding: 8px 12px; border-radius: 8px;
    color: var(--primary-text-color); background: var(--secondary-background-color);
    border: 1px solid var(--divider-color); }
  .grid { display: grid; gap: 12px 8px;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
  h3 { grid-column: 1 / -1; margin: 12px 0 0; font-size: 1rem; font-weight: 500;
    color: var(--primary-text-color); }
  h3:first-child { margin-top: 0; }
  .event { padding: 0; border: 0; background: none; text-align: left; display: block;
    color: var(--primary-text-color); }
  .event img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover;
    border-radius: 8px; background: var(--secondary-background-color); }
  .event .time { display: block; margin-top: 4px; font-weight: 500;
    font-variant-numeric: tabular-nums; }
  .event .kind { display: flex; align-items: center; gap: 4px; font-size: 0.85rem;
    color: var(--secondary-text-color); }
  .event .kind ha-icon { --mdc-icon-size: 16px; }
  .more { display: block; width: 100%; margin-top: 16px; }
  .note { color: var(--secondary-text-color); padding: 16px 0; }
  dialog { padding: 0; border: 0; background: #000; color: #fff; width: 100vw;
    height: 100vh; max-width: none; max-height: none; }
  dialog::backdrop { background: #000; }
  dialog .stage { position: absolute; inset: 0 0 64px; display: flex;
    align-items: center; justify-content: center; }
  dialog img { max-width: 100%; max-height: 100%; object-fit: contain; }
  dialog .caption { position: absolute; left: 0; right: 0; bottom: 0; height: 64px;
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 0 12px; box-sizing: border-box; }
  dialog .caption span { flex: 1; text-align: center; font-size: 0.9rem; line-height: 1.25; }
  dialog button { color: #fff; background: #333; border-color: #555; min-width: 44px; }
`;

function parse(title, source) {
  const match = NAME.exec(title);
  if (!match) return null;
  const [, year, month, day, hour, minute, second] = match;
  return {
    source,
    title,
    day: `${year}-${month}-${day}`,
    // Wall-clock time in Home Assistant's zone, kept as UTC fields so that
    // formatting with timeZone "UTC" returns it unchanged.
    when: new Date(Date.UTC(+year, +month - 1, +day, +hour, +minute, +second)),
  };
}

class FrontDoorEventsCard extends HTMLElement {
  constructor() {
    super();
    this._events = [];
    this._shown = 0;
    this._day = LATEST;
    this._urls = new Map();
    this._status = "Loading events…";
    this._tab = "events";
    this._live = null;
    this._loaded = false;
    // Without an observer (an old WebView) every picture is requested at once.
    this._observer =
      typeof IntersectionObserver === "function"
        ? new IntersectionObserver(
            (entries) => {
              for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                this._observer.unobserve(entry.target);
                this._load(entry.target);
              }
            },
            { rootMargin: "400px 0px" },
          )
        : {
            observe: (target) => this._load(target),
            unobserve() {},
            disconnect() {},
          };
    this._onVisible = () => {
      if (document.visibilityState === "visible" && this._loaded) this._fetch();
    };
    this.shadowRoot || this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    try {
      if (!Array.isArray(config?.sources) || config.sources.length === 0) {
        throw new Error("sources must list at least one media folder");
      }
      for (const source of config.sources) {
        if (!source.media_content_id || !source.label) {
          throw new Error("each source needs a label and a media_content_id");
        }
      }
      this._config = {
        page_size: 30,
        ...config,
        sources: config.sources.map((source) => ({ ...source })),
      };
      this._shown = this._config.page_size;
      this._render();
    } catch (error) {
      this._fail("setConfig", error);
    }
  }

  get hass() {
    return this._hass;
  }

  // Home Assistant sets these on a custom panel, in this order: hass, narrow, route, panel.
  set narrow(narrow) {
    const changed = this._narrow !== narrow;
    this._narrow = narrow;
    if (changed && this._panel && this._config) this._renderSafely();
  }

  get narrow() {
    return this._narrow;
  }

  set panel(panel) {
    this._panel = true;
    this.setAttribute("panel", "");
    this.setConfig({ page_size: 30, ...panel?.config });
    if (this._hass && this._config) this._fetch();
  }

  set hass(hass) {
    try {
      const first = !this._hass;
      this._hass = hass;
      if (first && this._config) this._fetch();
      if (this._tab === "live") this._updateLive();
    } catch (error) {
      this._fail("hass", error);
    }
  }

  // Home Assistant hides the message of an error thrown by a card ("Configuration
  // error" and nothing else), so a failure is shown inside the card instead.
  _selectTab(name) {
    if (name === this._tab) return;
    // Leaving the live tab ends the view, so the camera stops sending frames.
    if (this._tab === "live") this._liveCommand("turn_off");
    this._tab = name;
    this._renderSafely();
    if (name === "live") this._updateLive();
  }

  _liveCommand(service) {
    const entity = this._config?.live?.switch;
    if (!entity || !this._hass) return;
    if (service === "turn_off" && this._hass.states?.[entity]?.state !== "on") return;
    this._hass.callService("switch", service, { entity_id: entity }).catch((error) => {
      console.error("front-door-events-card", service, error);
    });
  }

  _renderLive(card) {
    const start = this._element("button", { textContent: "▶ Start", type: "button" });
    const stop = this._element("button", { textContent: "■ Stop", type: "button" });
    // Start sends ON again while the view runs, which renews its 30 seconds.
    start.addEventListener("click", () => this._liveCommand("turn_on"));
    stop.addEventListener("click", () => this._liveCommand("turn_off"));
    const status = this._element("div", { className: "note" });
    const img = this._element("img", { alt: "Live view of the door" });
    img.hidden = true;
    const note = this._element("div", {
      className: "note",
      textContent: "The view stops by itself after about 30 seconds; tap Start again to keep watching.",
    });
    card.append(
      this._element(
        "div",
        { className: "live" },
        this._element("div", { className: "controls" }, start, stop),
        status,
        img,
        note,
      ),
    );
    this._live = { start, stop, status, img };
    this._updateLive();
  }

  // Called with every state change of Home Assistant while the live tab is open.
  _updateLive() {
    const live = this._live;
    const names = this._config?.live;
    if (!live || !names || !this._hass) return;
    const states = this._hass.states || {};
    const online = states[names.online]?.state === "on";
    const on = states[names.switch]?.state === "on";
    live.start.disabled = !online;
    live.stop.disabled = !online;
    live.status.textContent = !online
      ? "The camera is offline. Live view returns by itself when the camera reconnects to the broker."
      : on
        ? ""
        : "Live view is off. Tap Start to watch the door.";
    const frame = states[names.image];
    const picture = frame?.attributes?.entity_picture;
    // The picture exists only while the camera reports the view as on, so a frame
    // from an earlier view is never shown as if it were live.
    if (online && on && picture) {
      // The state of an image entity is the time of its newest picture.
      const url = `${picture}${picture.includes("?") ? "&" : "?"}t=${encodeURIComponent(frame.state)}`;
      if (live.img.dataset.url !== url) {
        live.img.dataset.url = url;
        live.img.src = this._hass.hassUrl(url);
      }
      live.img.hidden = false;
    } else {
      delete live.img.dataset.url;
      live.img.removeAttribute("src");
      live.img.hidden = true;
    }
  }

  _renderSafely() {
    try {
      this._render();
    } catch (error) {
      this._fail("render", error);
    }
  }

  _fail(where, error) {
    try {
      console.error("front-door-events-card", where, error);
      const note = this._element("div", {
        className: "note",
        textContent: `The events card failed in ${where}: ${error?.message || error}`,
      });
      this.shadowRoot.replaceChildren(
        this._element("style", { textContent: STYLE }),
        this._element("ha-card", {}, note),
      );
    } catch (inner) {
      this.textContent = `The events card failed in ${where}.`;
    }
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisible);
    // The pictures stopped being observed when the card left the page.
    if (this._loaded && this.shadowRoot) {
      for (const img of this.shadowRoot.querySelectorAll("img[data-id]")) {
        if (!img.src) this._observer.observe(img);
      }
    }
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisible);
    this._observer.disconnect();
  }

  getCardSize() {
    return 8;
  }

  async _fetch() {
    // Signed URLs expire after a day, so a refresh signs the pictures again.
    this._urls.clear();
    try {
      const lists = await Promise.all(
        this._config.sources.map(async (source) => {
          const folder = await this._hass.callWS({
            type: "media_source/browse_media",
            media_content_id: source.media_content_id,
          });
          return (folder.children || [])
            .filter((child) => child.can_play)
            .map((child) => ({
              ...parse(child.title, source),
              id: child.media_content_id,
            }))
            .filter((event) => event.when);
        }),
      );
      // The name starts with the date, so sorting it sorts by time.
      this._events = lists.flat().sort((a, b) => (a.title < b.title ? 1 : -1));
      this._status = "";
    } catch (error) {
      this._events = [];
      this._status = `Could not list the events: ${error.message || error.code || error}`;
    }
    this._loaded = true;
    try {
      this._render();
    } catch (error) {
      this._fail("render", error);
    }
  }

  async _load(img) {
    const id = img.dataset.id;
    try {
      if (!this._urls.has(id)) {
        const { url } = await this._hass.callWS({
          type: "media_source/resolve_media",
          media_content_id: id,
        });
        this._urls.set(id, this._hass.hassUrl(url));
      }
      img.src = this._urls.get(id);
    } catch (error) {
      img.alt = "Picture unavailable";
    }
  }

  _format(options, date) {
    const language = this._hass?.locale?.language;
    const clock = this._hass?.locale?.time_format;
    const hour12 = clock === "12" ? true : clock === "24" ? false : undefined;
    return new Intl.DateTimeFormat(language, {
      ...options,
      ...(options.hour ? { hour12 } : {}),
      timeZone: "UTC",
    }).format(date);
  }

  _today() {
    const zone = this._hass?.config?.time_zone;
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
  }

  _dayLabel(day) {
    const date = new Date(`${day}T00:00:00Z`);
    const text = this._format(
      { weekday: "long", day: "numeric", month: "long", year: "numeric" },
      date,
    );
    const language = this._hass?.locale?.language;
    const today = Date.parse(`${this._today()}T00:00:00Z`);
    const offset = Math.round((date - today) / 86400000);
    if (offset === 0 || offset === -1) {
      const relative = new Intl.RelativeTimeFormat(language, { numeric: "auto" })
        .format(offset, "day");
      return `${relative.charAt(0).toUpperCase()}${relative.slice(1)}, ${text}`;
    }
    return text;
  }

  _time(event) {
    return this._format(
      { hour: "2-digit", minute: "2-digit", second: "2-digit" },
      event.when,
    );
  }

  _element(tag, props = {}, ...children) {
    const element = document.createElement(tag);
    Object.assign(element, props);
    element.append(...children);
    return element;
  }

  _kind(source) {
    const label = document.createTextNode(source.label);
    if (!source.icon) return [label];
    return [this._element("ha-icon", { icon: source.icon }), label];
  }

  _visibleEvents() {
    if (this._day === LATEST) return this._events.slice(0, this._shown);
    return this._events.filter((event) => event.day === this._day);
  }

  _render() {
    const root = this.shadowRoot;
    root.replaceChildren(this._element("style", { textContent: STYLE }));
    if (this._panel) {
      const toolbar = this._element("div", { className: "toolbar" });
      if (this._narrow) {
        const menu = this._element("button", { textContent: "☰", type: "button", ariaLabel: "Menu" });
        menu.addEventListener("click", () =>
          this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })),
        );
        toolbar.append(menu);
      }
      toolbar.append("Front door events");
      root.append(toolbar);
    }
    if (this._panel && this._config?.live) {
      const tab = (name, label) => {
        const button = this._element("button", {
          textContent: label,
          type: "button",
        });
        button.setAttribute("aria-pressed", String(this._tab === name));
        button.addEventListener("click", () => this._selectTab(name));
        return button;
      };
      root.append(
        this._element("div", { className: "tabs" }, tab("events", "Events"), tab("live", "Live")),
      );
    }
    const card = this._element("ha-card");
    root.append(card);
    if (this._tab === "live" && this._config?.live) {
      this._renderLive(card);
      return;
    }
    this._live = null;

    const days = new Map();
    for (const event of this._events) {
      days.set(event.day, (days.get(event.day) || 0) + 1);
    }
    if (this._day !== LATEST && !days.has(this._day)) this._day = LATEST;

    const select = this._element("select", { ariaLabel: "Day" });
    select.append(this._element("option", { value: LATEST, textContent: "Latest events" }));
    for (const [day, count] of days) {
      select.append(
        this._element("option", { value: day, textContent: `${this._dayLabel(day)} (${count})` }),
      );
    }
    select.value = this._day;
    select.addEventListener("change", () => {
      this._day = select.value;
      this._shown = this._config.page_size;
      this._render();
    });
    const refresh = this._element("button", { textContent: "Refresh", type: "button" });
    refresh.addEventListener("click", () => this._fetch());
    card.append(this._element("div", { className: "bar" }, select, refresh));

    const events = this._visibleEvents();
    this._displayed = events;
    if (events.length === 0) {
      const text = this._status || "No events in the archive.";
      card.append(this._element("div", { className: "note", textContent: text }));
      return;
    }

    const grid = this._element("div", { className: "grid" });
    let previous = "";
    events.forEach((event, index) => {
      if (event.day !== previous) {
        grid.append(this._element("h3", { textContent: this._dayLabel(event.day) }));
        previous = event.day;
      }
      const img = this._element("img", { alt: "", loading: "lazy", decoding: "async" });
      img.dataset.id = event.id;
      this._observer.observe(img);
      const tile = this._element(
        "button",
        { className: "event", type: "button" },
        img,
        this._element("span", { className: "time", textContent: this._time(event) }),
        this._element("span", { className: "kind" }, ...this._kind(event.source)),
      );
      tile.addEventListener("click", () => this._open(index));
      grid.append(tile);
    });
    card.append(grid);

    const older = this._events.length - this._shown;
    if (this._day === LATEST && older > 0) {
      const more = this._element("button", {
        className: "more",
        type: "button",
        textContent: `Show older events (${older})`,
      });
      more.addEventListener("click", () => {
        this._shown += this._config.page_size;
        this._render();
      });
      card.append(more);
    }
  }

  _open(index) {
    const dialog = this._element("dialog");
    const img = this._element("img", { alt: "" });
    const label = this._element("span");
    const previous = this._element("button", { textContent: "‹", type: "button", ariaLabel: "Newer" });
    const next = this._element("button", { textContent: "›", type: "button", ariaLabel: "Older" });
    const close = this._element("button", { textContent: "✕", type: "button", ariaLabel: "Close" });
    dialog.append(
      this._element("div", { className: "stage" }, img),
      this._element("div", { className: "caption" }, previous, label, next, close),
    );
    const show = async (target) => {
      const events = this._displayed;
      index = Math.max(0, Math.min(events.length - 1, target));
      const event = events[index];
      label.textContent = `${this._dayLabel(event.day)}, ${this._time(event)}, ${event.source.label}`;
      previous.disabled = index === 0;
      next.disabled = index === events.length - 1;
      img.removeAttribute("src");
      img.dataset.id = event.id;
      await this._load(img);
    };
    previous.addEventListener("click", () => show(index - 1));
    next.addEventListener("click", () => show(index + 1));
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => dialog.remove());
    let startX = null;
    dialog.addEventListener("touchstart", (event) => {
      startX = event.touches[0].clientX;
    });
    dialog.addEventListener("touchend", (event) => {
      if (startX === null) return;
      const delta = event.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(delta) > 60) show(index + (delta < 0 ? 1 : -1));
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") show(index - 1);
      if (event.key === "ArrowRight") show(index + 1);
    });
    this.shadowRoot.append(dialog);
    dialog.showModal();
    show(index);
  }
}

customElements.define("front-door-events-card", FrontDoorEventsCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "front-door-events-card",
  name: "Front door events",
  description: "Archived camera snapshots from a media folder, newest first, by day.",
});
