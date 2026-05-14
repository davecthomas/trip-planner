/* =============================================================================
 * trip-planner — embedded runtime
 *
 * The Python renderer injects a `window.__TRIP__` object before this script
 * loads. Shape:
 *
 *   {
 *     meta:           { title, versionLabel, agendaLabel, defaultPlan,
 *                       storagePrefix },
 *     vehicle:        { name, notes } | null,
 *     plans:          [ { key, label, summary, days:[...], verification:{} }, ... ],
 *     dayLabels:      { <planKey>: [ { n, label, sub }, ... ], ... },
 *   }
 *
 * Stop / Day / Plan field names are camelCase (matching the JS-friendly
 * alias dump on the Python side). All rendering, URL building, and state
 * persistence happens here at runtime — Python doesn't pre-render any HTML
 * fragments; it just hands off the data.
 * ============================================================================= */

(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Data handles (validated at start; failure is loud and human-readable)
  // ---------------------------------------------------------------------
  const DATA = window.__TRIP__;
  if (!DATA || !DATA.plans || !DATA.plans.length) {
    document.body.innerHTML =
      '<pre style="padding:20px;font-family:monospace;color:#c2410c">' +
      'trip-planner runtime: window.__TRIP__ is missing or empty. ' +
      'The renderer should have injected it before this script.' +
      "</pre>";
    return;
  }

  // Indexed-by-key for O(1) lookup. The plan order in DATA.plans is the
  // render order in the plan toggle.
  const TRIPS = {};
  DATA.plans.forEach((p) => { TRIPS[p.key] = p; });

  const DAY_LABELS = DATA.dayLabels || {};
  const META = DATA.meta || {};
  const PLAN_KEYS = DATA.plans.map((p) => p.key);

  const STORE_KEYS = {
    plan: META.storagePrefix + "-plan",
    day:  META.storagePrefix + "-day",
    mode: META.storagePrefix + "-mode",
  };

  // Mutable view state. Initial values are placeholders — `loadInitialState`
  // replaces them with sourced values.
  const state = {
    plan: META.defaultPlan || PLAN_KEYS[0],
    day: 1,
    mode: "day",
  };

  /* ===================================================================
   * GOOGLE MAPS URL BUILDERS (§18, §12.1, §12.2)
   *
   * Mirror of the Python implementation in src/trip_planner/maps.py.
   * If you change behavior here, update the Python module and tests too.
   * =================================================================== */

  const BUSINESS_TYPES = { charge: 1, hotel: 1, meal: 1 };

  function isBusiness(stop) { return BUSINESS_TYPES[stop.type] === 1; }

  function dirUrl(stop) {
    let url = "https://www.google.com/maps/dir/?api=1&destination=" +
      encodeURIComponent(stop.address);
    if (stop.placeId) url += "&destination_place_id=" + encodeURIComponent(stop.placeId);
    return url;
  }

  function placeUrl(stop) {
    let queryText;
    if (isBusiness(stop)) {
      queryText = stop.cityHint ? (stop.name + " " + stop.cityHint) : stop.name;
    } else {
      queryText = stop.address;
    }
    let url = "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(queryText);
    if (stop.placeId) url += "&query_place_id=" + encodeURIComponent(stop.placeId);
    return url;
  }

  function placeQuality(stop) {
    if (!isBusiness(stop)) return "n/a";
    return stop.placeId ? "verified" : "fallback";
  }

  function telLink(phone) {
    if (!phone) return null;
    return "tel:" + phone.replace(/[^+\d]/g, "");
  }

  /**
   * Encode a list of stops as a path-style /maps/dir/seg1/.../segN URL.
   * Consecutive stops collapse when their address matches case-insensitively
   * or their coordinates are within ~110 m (0.001° on each axis).
   */
  function encodeStopsAsMapsPath(stops) {
    const dedup = [];
    for (const s of stops) {
      const last = dedup[dedup.length - 1];
      if (last) {
        const sameAddr = last.address && s.address &&
          last.address.trim().toLowerCase() === s.address.trim().toLowerCase();
        const closeLat = Math.abs(last.lat - s.lat) < 0.001;
        const closeLng = Math.abs(last.lng - s.lng) < 0.001;
        if (sameAddr || (closeLat && closeLng)) continue;
      }
      dedup.push(s);
    }
    const segments = dedup.map((s) => {
      const text = isBusiness(s) ? (s.name + ", " + s.address) : s.address;
      return encodeURIComponent(text).replace(/%20/g, "+").replace(/%2C/g, ",");
    });
    return "https://www.google.com/maps/dir/" + segments.join("/");
  }

  function buildFullTripMapsUrl(planKey) {
    const allStops = TRIPS[planKey].days.flatMap((d) => d.stops);
    return encodeStopsAsMapsPath(allStops);
  }

  function buildDayMapsUrl(planKey, dayIdx) {
    return encodeStopsAsMapsPath(TRIPS[planKey].days[dayIdx].stops);
  }

  /* ===================================================================
   * STATE — load / persist / fragment
   * =================================================================== */

  function readFragment() {
    const h = location.hash.replace(/^#/, "");
    if (!h) return {};
    const out = {};
    h.split("&").forEach((seg) => {
      const [k, v] = seg.split("=");
      if (k && v !== undefined) out[k] = decodeURIComponent(v);
    });
    return out;
  }
  function writeFragment() {
    history.replaceState(null, "",
      "#plan=" + state.plan + "&day=" + state.day + "&mode=" + state.mode);
  }
  function persist() {
    try {
      localStorage.setItem(STORE_KEYS.plan, state.plan);
      localStorage.setItem(STORE_KEYS.day, String(state.day));
      localStorage.setItem(STORE_KEYS.mode, state.mode);
    } catch (e) { /* private mode etc. — silently ignore */ }
    writeFragment();
  }
  function loadInitialState() {
    const frag = readFragment();
    let lsPlan = null, lsDay = null, lsMode = null;
    try {
      lsPlan = localStorage.getItem(STORE_KEYS.plan);
      lsDay  = localStorage.getItem(STORE_KEYS.day);
      lsMode = localStorage.getItem(STORE_KEYS.mode);
    } catch (e) { /* private mode */ }

    const planRaw = frag.plan || lsPlan || (META.defaultPlan || PLAN_KEYS[0]);
    state.plan = PLAN_KEYS.includes(planRaw) ? planRaw : PLAN_KEYS[0];

    const dayRaw = parseInt(frag.day || lsDay || "1", 10);
    const maxDay = TRIPS[state.plan].days.length;
    state.day = (dayRaw >= 1 && dayRaw <= maxDay) ? dayRaw : 1;

    // Legacy migration: any persisted 'map' value silently maps to 'day'.
    const modeRaw = frag.mode || lsMode || "day";
    state.mode = (modeRaw === "agenda") ? "agenda" : "day";
  }

  /* ===================================================================
   * RENDER — toggles
   * =================================================================== */

  function renderPlanToggle() {
    document.querySelectorAll(".plan-toggle .toggle-btn").forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.plan === state.plan ? "true" : "false");
    });
  }
  function renderDayToggle() {
    const wrap = document.getElementById("day-toggle");
    const days = DAY_LABELS[state.plan] || [];
    wrap.style.setProperty("--day-cols", days.length || 1);
    wrap.innerHTML = days.map((d) =>
      '<button class="toggle-btn" data-day="' + d.n + '" aria-pressed="' +
      (d.n === state.day ? "true" : "false") + '">' +
      escapeHtml(d.label) + '<span class="sub">' + escapeHtml(d.sub) + "</span></button>"
    ).join("");
    wrap.querySelectorAll(".toggle-btn").forEach((b) => {
      b.addEventListener("click", () => {
        state.day = parseInt(b.dataset.day, 10);
        if (state.mode === "agenda") state.mode = "day";
        persist();
        renderDayToggle();
        renderMode();
      });
    });
  }
  function renderAgendaToggle() {
    const btn = document.getElementById("agenda-toggle");
    if (state.mode === "agenda") {
      btn.innerHTML = '<span class="icon">←</span><span class="label">Back to Day View</span>';
      btn.classList.add("active");
    } else {
      btn.innerHTML = '<span class="icon">☰</span><span class="label">Full Trip Agenda</span>';
      btn.classList.remove("active");
    }
  }
  function renderFullMapsToggle() {
    const a = document.getElementById("full-maps-toggle");
    a.href = buildFullTripMapsUrl(state.plan);
  }
  function renderDayMapsToggle() {
    const a = document.getElementById("day-maps-toggle");
    a.href = buildDayMapsUrl(state.plan, state.day - 1);
    const labelEl = a.querySelector(".label");
    if (labelEl) labelEl.textContent = "Day " + state.day + " in Maps";
  }

  /* ===================================================================
   * RENDER — helpers
   * =================================================================== */

  function tagLabel(type) {
    return ({ origin: "Origin", charge: "Charge", meal: "Meal", hotel: "Hotel", dest: "Arrive" })[type] || type;
  }
  function ratingStr(r) {
    if (!r) return "";
    return "★".repeat(r.stars) + " · " + r.user.toFixed(1) + " guest";
  }
  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function renderBookingBlock(s) {
    const status = s.bookingStatus || "PENDING";
    const statusClass = status === "BOOKED" ? "booked"
                      : (status === "TO BOOK" ? "tobook" : "pending");
    let pillText;
    if (status === "BOOKED") {
      pillText = "BOOKED for " + (s.planLabel || "plan") +
                 " · Conf #" + (s.confNumber || "—");
    } else if (status === "TO BOOK") {
      pillText = "TO BOOK for " + (s.planLabel || "plan");
    } else {
      pillText = status + " for " + (s.planLabel || "plan");
    }

    let html = '<div class="booking-block">';
    html += '<div class="booking-pill ' + statusClass + '">' + escapeHtml(pillText) + "</div>";
    if (s.checkIn && s.checkOut) {
      html += '<div class="booking-times">Check-in ' + escapeHtml(s.checkIn) +
              " → Check-out " + escapeHtml(s.checkOut) + "</div>";
    }
    if (s.cancelBy) {
      html += '<div class="booking-cancel">' + escapeHtml(s.cancelBy) + "</div>";
    }
    html += "</div>";
    return html;
  }

  function renderActions(s) {
    const dirHref = dirUrl(s);
    const placeHref = placeUrl(s);
    const quality = placeQuality(s);
    let badge = "";
    if (quality === "verified") {
      badge = ' <span class="place-badge good" title="Resolves via Google Place ID">✓</span>';
    } else if (quality === "fallback") {
      badge = ' <span class="place-badge warn" title="No Place ID — falls back to name+city query">⚠</span>';
    }

    let html = '<div class="card-actions">';
    if (s.type !== "origin") {
      html += '<a class="btn btn-primary" href="' + dirHref + '" target="_blank" rel="noopener">Directions →</a>';
    }
    html += '<a class="btn btn-secondary" href="' + placeHref + '" target="_blank" rel="noopener">Open in Maps' + badge + "</a>";
    const tel = telLink(s.phone);
    if (tel) {
      html += '<a class="btn btn-secondary" href="' + tel + '">Call ' + escapeHtml(s.phone) + "</a>";
    }
    html += "</div>";
    return html;
  }

  /* ===================================================================
   * RENDER — day view (stop cards)
   * =================================================================== */

  function renderStopCard(s, idx) {
    let html = '<article class="stop-card">';
    html += '<div class="card-head">';
    html += '<div class="card-num ' + s.type + '">' + (idx + 1) + "</div>";
    html += '<div class="card-body">';
    html += '<div class="card-tag">' + tagLabel(s.type) + "</div>";
    html += '<div class="card-name">' + escapeHtml(s.name) + "</div>";
    html += '<div class="card-addr">' + escapeHtml(s.address) + "</div>";

    const timeParts = [];
    if (s.arrive) timeParts.push('<span><span class="label">arr</span>' + s.arrive + "</span>");
    if (s.depart) timeParts.push('<span><span class="label">dep</span>' + s.depart + "</span>");
    if (s.legMiles !== undefined && s.legMiles !== null && idx > 0) {
      timeParts.push('<span><span class="label">leg</span>' + s.legMiles + " mi</span>");
    }
    if (s.legDrive && idx > 0) {
      timeParts.push('<span><span class="label">drive</span>' + s.legDrive + "</span>");
    }
    if (timeParts.length) {
      html += '<div class="card-times">' + timeParts.join("") + "</div>";
    }

    if (s.type === "charge") {
      html += '<div class="card-meta">';
      if (s.socIn && s.socOut) {
        html += '<div class="row"><span class="label">SoC</span><span class="val soc-line">' +
                s.socIn + '<span class="arrow">→</span>' + s.socOut + "</span></div>";
      }
      if (s.chargerType) {
        html += '<div class="row"><span class="label">Charger</span><span class="val">' +
                escapeHtml(s.chargerType) + "</span></div>";
      }
      if (s.meal && s.meal !== "no meal") {
        html += '<div class="row"><span class="label">Meal</span><span class="val">' + escapeHtml(s.meal);
        if (s.restaurants && s.restaurants.length) {
          html += '<ul class="restaurants">';
          s.restaurants.forEach((r) => {
            html += "<li>" + escapeHtml(r.name) +
                    '<span class="cuisine">— ' + escapeHtml(r.cuisine) + "</span></li>";
          });
          html += "</ul>";
        } else {
          html += '<div style="color:var(--warn);font-size:12px;margin-top:4px">No restaurant identified — gap</div>';
        }
        html += "</span></div>";
      }
      html += "</div>";
    } else if (s.type === "hotel") {
      html += '<div class="card-meta">';
      if (s.rating) {
        html += '<div class="row"><span class="label">Rating</span><span class="val">' +
                ratingStr(s.rating) + "</span></div>";
      }
      if (s.rate) {
        html += '<div class="row"><span class="label">Rate</span><span class="val">' +
                escapeHtml(s.rate) + "/night</span></div>";
      }
      if (s.chargerProx) {
        html += '<div class="row"><span class="label">Charger</span><span class="val">' +
                escapeHtml(s.chargerProx) + "</span></div>";
      }
      html += "</div>";
      html += renderBookingBlock(s);
      if (s.petPolicy) {
        html += '<div class="pet-policy">' + escapeHtml(s.petPolicy) + "</div>";
      }
    }

    if (s.notes) {
      html += '<div class="card-notes">' + escapeHtml(s.notes) + "</div>";
    }
    html += renderActions(s);
    html += "</div></div></article>";
    return html;
  }

  function renderDayView() {
    const trip = TRIPS[state.plan];
    const day = trip.days[state.day - 1];
    const m = document.getElementById("day-view");

    let html = '<div class="day-head">';
    html += '<div class="day-eyebrow">Day ' + state.day + " of " + trip.days.length +
            " · " + trip.label.split("·")[0].trim() + "</div>";
    html += '<h2 class="day-title">' + escapeHtml(day.title) + "</h2>";
    html += '<div class="day-date">' + escapeHtml(day.date) + "</div>";
    html += '<div class="day-stats">';
    html += '<span><span class="stat-label">miles</span> ' + day.stats.miles + "</span>";
    html += '<span><span class="stat-label">drive</span> ' + day.stats.drive + "</span>";
    html += '<span><span class="stat-label">charges</span> ' + day.stats.charges + "</span>";
    html += "</div></div>";

    html += day.stops.map((s, i) => renderStopCard(s, i)).join("");
    html += renderVerification(trip.verification);
    m.innerHTML = html;
  }

  function renderVerification(v) {
    const audit = runOpenInMapsAudit();
    let html = '<section class="verification">';
    html += '<div class="group confirmed"><h4>Confirmed</h4><ul>' +
      (v.confirmed || []).map((x) => "<li>" + escapeHtml(x) + "</li>").join("") +
      "</ul></div>";
    html += '<div class="group estimates"><h4>Estimates</h4><ul>' +
      (v.estimates || []).map((x) => "<li>" + escapeHtml(x) + "</li>").join("") +
      "</ul></div>";
    html += '<div class="group tradeoffs"><h4>Tradeoffs</h4><ul>' +
      (v.tradeoffs || []).map((x) => "<li>" + escapeHtml(x) + "</li>").join("") +
      "</ul></div>";

    html += '<div class="group audit"><h4>Open in Maps · Quality Audit</h4>';
    html += "<ul>";
    html += "<li><strong>" + audit.verifiedCount + "</strong> business stops resolve via Google Place ID (lands on Place page with phone, hours, photos).</li>";
    if (audit.fallbacks.length === 0) {
      html += "<li>0 stops on name-query fallback — all business stops are place-verified.</li>";
    } else {
      html += "<li><strong>" + audit.fallbacks.length + "</strong> business stops use name+city query fallback (Place ID not yet captured):";
      html += "<ul>";
      audit.fallbacks.forEach((f) => { html += "<li>" + escapeHtml(f) + "</li>"; });
      html += "</ul></li>";
    }
    html += "</ul></div>";
    html += "</section>";
    return html;
  }

  function runOpenInMapsAudit() {
    const trip = TRIPS[state.plan];
    const verified = new Set();
    const fallbacks = new Set();
    trip.days.forEach((d) => {
      d.stops.forEach((s) => {
        const q = placeQuality(s);
        if (q === "verified") verified.add(s.name);
        else if (q === "fallback") fallbacks.add(s.name);
      });
    });
    if (fallbacks.size > 0) {
      console.warn("[Open-in-Maps audit] Plan " + state.plan + " — " +
                   fallbacks.size + " fallback(s):", Array.from(fallbacks));
    }
    return { verifiedCount: verified.size, fallbacks: Array.from(fallbacks) };
  }

  /* ===================================================================
   * RENDER — agenda view
   * =================================================================== */

  function renderAgendaView() {
    const trip = TRIPS[state.plan];
    const totalMiles   = trip.days.reduce((a, d) => a + d.stats.miles, 0);
    const totalCharges = trip.days.reduce((a, d) => a + d.stats.charges, 0);
    const m = document.getElementById("agenda-view");

    let html = '<div class="agenda-cover">';
    html += '<div class="agenda-eyebrow">' + escapeHtml(META.agendaLabel || "Full Trip Agenda") + "</div>";
    html += '<h1 class="agenda-title">' + escapeHtml(trip.label) + "</h1>";
    html += '<div class="agenda-summary">' + escapeHtml(trip.summary) + "</div>";
    html += '<div class="agenda-totals">';
    html += '<span><span class="label">total miles</span> ' + totalMiles + "</span>";
    html += '<span><span class="label">days · nights</span> ' + trip.days.length +
            " · " + (trip.days.length - 1) + "</span>";
    html += '<span><span class="label">charges</span> ' + totalCharges + "</span>";
    html += "</div></div>";

    trip.days.forEach((day, dIdx) => {
      html += '<div class="agenda-day">';
      html += '<div class="day-eyebrow">Day ' + (dIdx + 1) + " · " + escapeHtml(day.date) + "</div>";
      html += '<h3 class="agenda-day-title">' + escapeHtml(day.title) + "</h3>";
      html += '<div class="agenda-day-stats">' + day.stats.miles + " mi · " +
              day.stats.drive + " driving · " + day.stats.charges + " charges</div>";

      day.stops.forEach((s, sIdx) => {
        if (sIdx > 0 && s.legMiles !== undefined && s.legMiles !== null) {
          html += '<div class="leg-connector">↓ ' + s.legMiles + " mi · " + (s.legDrive || "") + "</div>";
        }
        html += '<div class="agenda-stop">';
        let timeText = "";
        if (s.arrive && s.depart) timeText = s.arrive + "<br>" + s.depart;
        else if (s.arrive) timeText = s.arrive;
        else if (s.depart) timeText = s.depart;
        html += '<div class="agenda-time">' + timeText + "</div>";
        html += '<div class="agenda-body">';
        html += '<div class="stop-tag">' + tagLabel(s.type) + "</div>";
        html += '<div class="stop-name">' + escapeHtml(s.name) + "</div>";
        html += '<div class="stop-addr">' + escapeHtml(s.address) + "</div>";

        if (s.type === "charge") {
          let detail = "";
          if (s.socIn && s.socOut) detail += "SoC " + s.socIn + " → " + s.socOut;
          if (s.chargerType) detail += (detail ? " · " : "") + s.chargerType;
          if (s.meal && s.meal !== "no meal") detail += (detail ? " · " : "") + s.meal;
          if (detail) html += '<div class="stop-detail">' + escapeHtml(detail) + "</div>";
          if (s.restaurants && s.restaurants.length) {
            html += '<div class="stop-detail">' +
                    s.restaurants.map((r) => escapeHtml(r.name)).join(", ") + "</div>";
          }
        } else if (s.type === "hotel") {
          if (s.rating) {
            html += '<div class="stop-detail">' + ratingStr(s.rating) +
                    (s.rate ? " · " + s.rate : "") +
                    (s.chargerProx ? " · " + s.chargerProx : "") + "</div>";
          }
          if (s.bookingStatus === "BOOKED") {
            html += '<div class="stop-detail">BOOKED for ' + escapeHtml(s.planLabel || "") +
                    " · Conf #" + escapeHtml(s.confNumber || "") + "</div>";
          } else if (s.bookingStatus === "TO BOOK") {
            html += '<div class="stop-detail">TO BOOK for ' + escapeHtml(s.planLabel || "") + "</div>";
          }
          if (s.checkIn && s.checkOut) {
            html += '<div class="stop-detail">Check-in ' + escapeHtml(s.checkIn) +
                    " → " + escapeHtml(s.checkOut) + "</div>";
          }
          if (s.cancelBy)   html += '<div class="stop-detail">' + escapeHtml(s.cancelBy) + "</div>";
          if (s.phone)      html += '<div class="stop-detail">' + escapeHtml(s.phone) + "</div>";
          if (s.petPolicy)  html += '<div class="stop-detail">' + escapeHtml(s.petPolicy) + "</div>";
        }
        html += "</div></div>";
      });

      html += "</div>";
    });

    html += '<div class="agenda-floor"><button class="btn btn-secondary" id="back-to-day">← Back to Day View</button></div>';
    m.innerHTML = html;
    document.getElementById("back-to-day").addEventListener("click", () => {
      state.mode = "day";
      persist();
      renderAgendaToggle();
      renderMode();
    });
  }

  /* ===================================================================
   * MODE SWITCHING + INIT
   * =================================================================== */

  function renderMode() {
    const dayView = document.getElementById("day-view");
    const agendaView = document.getElementById("agenda-view");
    if (state.mode === "agenda") {
      dayView.hidden = true;
      agendaView.hidden = false;
      renderAgendaView();
      window.scrollTo({ top: 0, behavior: "instant" });
    } else {
      dayView.hidden = false;
      agendaView.hidden = true;
      renderDayView();
    }
    renderFullMapsToggle();
    renderDayMapsToggle();
  }

  // Plan toggle click wiring (the buttons themselves are emitted by the
  // Python template; their data-plan attributes match plan keys).
  document.querySelectorAll(".plan-toggle .toggle-btn").forEach((b) => {
    b.addEventListener("click", () => {
      state.plan = b.dataset.plan;
      const maxDay = TRIPS[state.plan].days.length;
      if (state.day > maxDay) state.day = 1;
      persist();
      renderPlanToggle();
      renderDayToggle();
      renderMode();
    });
  });

  document.getElementById("agenda-toggle").addEventListener("click", () => {
    state.mode = state.mode === "agenda" ? "day" : "agenda";
    persist();
    renderAgendaToggle();
    renderMode();
  });

  // Bootstrap.
  loadInitialState();
  renderPlanToggle();
  renderDayToggle();
  renderAgendaToggle();
  renderFullMapsToggle();
  renderDayMapsToggle();
  renderMode();
})();
