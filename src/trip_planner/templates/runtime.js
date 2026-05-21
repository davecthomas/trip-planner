/* =============================================================================
 * trip-planner — embedded runtime
 *
 * The Python renderer injects a `window.__TRIP__` object before this script
 * loads. Shape:
 *
 *   {
 *     meta:           { title, versionLabel, agendaLabel, defaultPlan,
 *                       storagePrefix },
 *     vehicle:        { name, baselineWhPerMi, acPenaltyWhPerMi,
 *                       acWindowStart, acWindowEnd, climbKwhPer1000ft,
 *                       usablePackKwh, acIndicatorArrivalThresholdPct,
 *                       acIndicatorMinImprovementPp, ... } | null,
 *     plans:          [ { key, label, summary, tagline?, days:[...],
 *                          verification:{} }, ... ],
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
  const VEHICLE = DATA.vehicle || null;
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
   * §3.4 — AC CONSERVATION INDICATOR
   *
   * Render-time computed badge on departure-side charge stop cards. Fires
   * when the projected arrival SoC at the next stop (using the §3.3
   * envelope: baseline + AC penalty if depart time in AC window +
   * elevation penalty) is below the configured threshold AND turning AC
   * off would widen the margin by at least the configured minimum.
   *
   * Mirror of `src/trip_planner/consumption.py`. Keep aligned.
   * =================================================================== */

  function _parsePct(s) {
    if (!s) return null;
    const m = String(s).trim().match(/^(\d+(?:\.\d+)?)\s*%$/);
    return m ? parseFloat(m[1]) : null;
  }
  function _parseClock(s) {
    if (!s) return null;
    const m = String(s).trim().match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return null;
    const h = parseInt(m[1], 10), mm = parseInt(m[2], 10);
    if (h < 0 || h > 23 || mm < 0 || mm > 59) return null;
    return h * 60 + mm;
  }

  /**
   * Evaluate the §3.4 indicator for one charge stop and its outbound leg.
   * @returns {null|{fires, arrivalOn, arrivalOff}} — null when not computable.
   */
  function evaluateAcIndicator(current, nextStop, vehicle) {
    if (!vehicle) return null;
    if (!current || current.type !== "charge") return null;
    if (!nextStop || !nextStop.legMiles || nextStop.legMiles <= 0) return null;

    const socOut = _parsePct(current.socOut);
    if (socOut === null) return null;

    const depart = _parseClock(current.depart);
    const winStart = _parseClock(vehicle.acWindowStart);
    const winEnd = _parseClock(vehicle.acWindowEnd);
    const acInWindow = depart !== null && winStart !== null && winEnd !== null
      && depart >= winStart && depart < winEnd;

    let climbWhPerMi = 0;
    if (current.elevationFt != null && nextStop.elevationFt != null) {
      const netClimb = nextStop.elevationFt - current.elevationFt;
      if (netClimb > 0) {
        // Note: pydantic's to_camel emits `climbKwhPer1000Ft` (capital F),
        // not `…1000ft`. The Python field is `climb_kwh_per_1000ft`.
        const climbKwh = (netClimb / 1000) * vehicle.climbKwhPer1000Ft;
        climbWhPerMi = (climbKwh * 1000) / nextStop.legMiles;
      }
    }

    const base = vehicle.baselineWhPerMi + climbWhPerMi;
    const acPen = acInWindow ? vehicle.acPenaltyWhPerMi : 0;
    const whOn = base + acPen;
    const whOff = base;

    const ppOn = (whOn * nextStop.legMiles / 1000) / vehicle.usablePackKwh * 100;
    const ppOff = (whOff * nextStop.legMiles / 1000) / vehicle.usablePackKwh * 100;
    const arrivalOn = socOut - ppOn;
    const arrivalOff = socOut - ppOff;

    const threshold = vehicle.acIndicatorArrivalThresholdPct;
    const improvementFloor = vehicle.acIndicatorMinImprovementPp;
    const improvement = arrivalOff - arrivalOn;

    const fires = (arrivalOn < threshold) && (improvement >= improvementFloor);
    return { fires, arrivalOn, arrivalOff };
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
    state.mode = (modeRaw === "agenda" || modeRaw === "merged") ? modeRaw : "day";
  }

  /* ===================================================================
   * RENDER — toggles
   * =================================================================== */

  function renderPlanToggle() {
    // Merged view is cross-plan, so no plan is "selected" while in merged mode.
    const inMerged = state.mode === "merged";
    document.querySelectorAll(".plan-toggle .toggle-btn").forEach((b) => {
      const pressed = !inMerged && b.dataset.plan === state.plan;
      b.setAttribute("aria-pressed", pressed ? "true" : "false");
    });
  }
  function renderDayToggle() {
    // Merged view doesn't anchor on a specific day, so the day toggle shows no
    // selection while in merged mode.
    const inMerged = state.mode === "merged";
    const wrap = document.getElementById("day-toggle");
    const days = DAY_LABELS[state.plan] || [];
    wrap.style.setProperty("--day-cols", days.length || 1);
    wrap.innerHTML = days.map((d) =>
      '<button class="toggle-btn" data-day="' + d.n + '" aria-pressed="' +
      (!inMerged && d.n === state.day ? "true" : "false") + '">' +
      escapeHtml(d.label) + '<span class="sub">' + escapeHtml(d.sub) + "</span></button>"
    ).join("");
    wrap.querySelectorAll(".toggle-btn").forEach((b) => {
      b.addEventListener("click", () => {
        state.day = parseInt(b.dataset.day, 10);
        if (state.mode !== "day") state.mode = "day";
        persist();
        renderPlanToggle();
        renderDayToggle();
        renderAgendaToggle();
        renderMergedToggle();
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
  function renderMergedToggle() {
    const btn = document.getElementById("merged-toggle");
    if (state.mode === "merged") {
      btn.innerHTML = '<span class="icon">←</span><span class="label">Back to Day View</span>';
      btn.classList.add("active");
    } else {
      btn.innerHTML = '<span class="icon">⛁</span><span class="label">All Plans · Merged</span>';
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

  function renderStopCard(s, idx, nextStop) {
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
      // §3.4 AC conservation indicator — silent unless trigger fires.
      const ind = evaluateAcIndicator(s, nextStop, VEHICLE);
      if (ind && ind.fires) {
        const acOnPct = Math.round(ind.arrivalOn);
        const acOffPct = Math.round(ind.arrivalOff);
        html += '<div class="row ac-indicator">' +
          '<span class="label">⚠ AC</span>' +
          '<span class="val">Conserve next leg: consider AC OFF. ' +
          'Projected arrival SoC — AC on: ' + acOnPct + '% · AC off: ' + acOffPct + '%.</span>' +
        '</div>';
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

    html += day.stops.map((s, i) => renderStopCard(s, i, day.stops[i + 1])).join("");
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
          // Booking pill + check-in/out + cancel-by — matches the day-view
          // booking block so the green BOOKED pill reads the same in both
          // views.
          if (s.bookingStatus) {
            html += renderBookingBlock(s);
          }
          if (s.phone)      html += '<div class="stop-detail">' + escapeHtml(s.phone) + "</div>";
          if (s.petPolicy)  html += '<div class="pet-policy">' + escapeHtml(s.petPolicy) + "</div>";
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
   * RENDER — merged view (union across all plans)
   *
   * Collects every charge + hotel stop across every plan, dedupes by
   * (type + placeId|address) so a charger that appears in multiple plans
   * shows once, and orders them along the road by projecting each stop
   * onto the vector from the trip origin to the trip destination. Origin
   * and destination bookend the list.
   * =================================================================== */

  function _stopIdentity(s) {
    if (s.placeId) return "place:" + s.placeId;
    if (s.address) return "addr:" + s.address.trim().toLowerCase();
    return "coord:" + s.lat.toFixed(3) + "," + s.lng.toFixed(3);
  }
  function _projectAlongPath(stop, origin, dest) {
    // Dot product of (stop - origin) with (dest - origin). No normalization
    // needed because we only use this for sorting.
    const dLat = dest.lat - origin.lat;
    const dLng = dest.lng - origin.lng;
    return (stop.lat - origin.lat) * dLat + (stop.lng - origin.lng) * dLng;
  }

  function buildMergedStops() {
    // Bookends are the same in every plan; take them from the first plan.
    const firstPlan = DATA.plans[0];
    const origin = firstPlan.days[0].stops[0];
    const lastDay = firstPlan.days[firstPlan.days.length - 1];
    const dest = lastDay.stops[lastDay.stops.length - 1];

    // Stable plan order for chip rendering.
    const planOrder = PLAN_KEYS.slice();
    const planLabelByKey = {};
    DATA.plans.forEach((p) => { planLabelByKey[p.key] = p.label; });

    const merged = new Map();
    DATA.plans.forEach((plan) => {
      plan.days.forEach((day) => {
        day.stops.forEach((s) => {
          if (s.type !== "charge" && s.type !== "hotel") return;
          const key = s.type + "|" + _stopIdentity(s);
          let entry = merged.get(key);
          if (!entry) {
            entry = {
              key,
              stop: s,
              plans: new Set(),
              bookings: [],
            };
            merged.set(key, entry);
          }
          entry.plans.add(plan.key);
          if (s.type === "hotel") {
            entry.bookings.push({
              planKey: plan.key,
              planLabel: s.planLabel || planLabelByKey[plan.key] || plan.key,
              bookingStatus: s.bookingStatus || "PENDING",
              confNumber: s.confNumber || null,
              checkIn: s.checkIn || null,
              checkOut: s.checkOut || null,
              rate: s.rate || null,
            });
          }
        });
      });
    });

    const entries = Array.from(merged.values());
    entries.forEach((e) => {
      e.projection = _projectAlongPath(e.stop, origin, dest);
    });
    // Tie-break: charge before hotel when projections are essentially equal
    // (a charger and a hotel at the same address read more naturally in
    //  "stop to charge, then check in" order).
    entries.sort((a, b) => {
      const dp = a.projection - b.projection;
      if (Math.abs(dp) > 1e-9) return dp;
      if (a.stop.type === b.stop.type) return 0;
      return a.stop.type === "charge" ? -1 : 1;
    });

    return { origin, dest, entries, planOrder, planLabelByKey };
  }

  function _planChipClassForHotel(entry, planKey) {
    // Color-code the chip by this plan's booking status for the hotel so a
    // driver can tell at a glance which hotels along the route already have a
    // reservation vs which would need a fresh booking if they decide to stop.
    const b = entry.bookings.find((x) => x.planKey === planKey);
    if (!b) return "";
    if (b.bookingStatus === "BOOKED") return " booked";
    if (b.bookingStatus === "TO BOOK") return " tobook";
    return " pending";
  }

  function renderMergedView() {
    const m = document.getElementById("merged-view");
    const data = buildMergedStops();
    if (!data) { m.innerHTML = ""; return; }

    let html = '<div class="merged-cover">';
    html += '<h1 class="agenda-title">' + escapeHtml(META.title || "Trip") + "</h1>";
    html += "</div>";

    // Origin bookend.
    html += renderMergedBookend(data.origin, "origin", "Origin");

    // Sequential charger/hotel entries.
    data.entries.forEach((entry, idx) => {
      html += renderMergedEntry(entry, idx + 1, data.planOrder);
    });

    // Destination bookend.
    html += renderMergedBookend(data.dest, "dest", "Destination");

    html += '<div class="merged-floor"><button class="btn btn-secondary" id="back-from-merged">← Back to Day View</button></div>';
    m.innerHTML = html;
    document.getElementById("back-from-merged").addEventListener("click", () => {
      state.mode = "day";
      persist();
      renderMergedToggle();
      renderPlanToggle();
      renderDayToggle();
      renderMode();
    });
  }

  function renderMergedBookend(s, kind, eyebrow) {
    let html = '<div class="merged-stop">';
    html += '<div class="pos"><span class="num ' + kind + '">' +
            (kind === "origin" ? "S" : "E") + "</span></div>";
    html += '<div class="merged-body">';
    html += '<div class="stop-tag">' + escapeHtml(eyebrow) + "</div>";
    html += '<div class="stop-name">' + escapeHtml(s.name) + "</div>";
    html += '<div class="stop-addr">' + escapeHtml(s.address) + "</div>";
    html += '<div class="card-actions" style="margin-top:8px">';
    if (kind !== "origin") {
      html += '<a class="btn btn-primary" href="' + dirUrl(s) + '" target="_blank" rel="noopener">Directions →</a>';
    }
    html += '<a class="btn btn-secondary" href="' + placeUrl(s) + '" target="_blank" rel="noopener">Open in Maps</a>';
    html += "</div></div></div>";
    return html;
  }

  function renderMergedEntry(entry, idx, planOrder) {
    const s = entry.stop;
    let html = '<div class="merged-stop">';
    html += '<div class="pos"><span class="num ' + s.type + '">' + idx + "</span></div>";
    html += '<div class="merged-body">';
    html += '<div class="stop-tag">' + tagLabel(s.type) + "</div>";
    html += '<div class="stop-name">' + escapeHtml(s.name) + "</div>";
    html += '<div class="stop-addr">' + escapeHtml(s.address) + "</div>";

    if (s.type === "charge" && s.chargerType) {
      html += '<div class="stop-detail">' + escapeHtml(s.chargerType) + "</div>";
    } else if (s.type === "hotel" && s.rating) {
      let detail = ratingStr(s.rating);
      if (s.rate) detail += " · " + s.rate;
      if (s.chargerProx) detail += " · " + s.chargerProx;
      html += '<div class="stop-detail">' + escapeHtml(detail) + "</div>";
    }

    // Plan chips — present-in-plan, color-coded for hotels by booking status.
    html += '<div class="plan-chips">';
    planOrder.forEach((pk) => {
      if (!entry.plans.has(pk)) return;
      let cls = "";
      if (s.type === "hotel") cls = _planChipClassForHotel(entry, pk);
      html += '<span class="plan-chip' + cls + '">' + escapeHtml(pk) + "</span>";
    });
    html += "</div>";

    // Inline booking detail for each plan that has a reservation here. Uses
    // the same .booking-pill/.booking-times styling as the day view so the
    // BOOKED/TO BOOK status reads consistently across all three views. The
    // plan-key prefix replaces the day view's "for Plan X" wording since the
    // key is already visible.
    if (s.type === "hotel" && entry.bookings.length) {
      const rows = entry.bookings.filter(
        (b) => b.bookingStatus === "BOOKED" || b.bookingStatus === "TO BOOK"
      );
      if (rows.length) {
        html += '<div class="merged-bookings">';
        rows.forEach((b) => {
          const statusClass = b.bookingStatus === "BOOKED" ? "booked"
                            : (b.bookingStatus === "TO BOOK" ? "tobook" : "pending");
          let pill = b.bookingStatus;
          if (b.bookingStatus === "BOOKED" && b.confNumber) {
            pill += " · Conf #" + b.confNumber;
          }
          let html_ =
            '<div class="row">' +
            '<span class="key">' + escapeHtml(b.planKey) + "</span>" +
            '<span class="val">' +
              '<span class="booking-pill ' + statusClass + '">' + escapeHtml(pill) + "</span>";
          if (b.checkIn && b.checkOut) {
            html_ += '<div class="booking-times">' + escapeHtml(b.checkIn) +
                     " → " + escapeHtml(b.checkOut) + "</div>";
          }
          html_ += "</span></div>";
          html += html_;
        });
        html += "</div>";
      }
    }

    const placeHref = placeUrl(s);
    const dirHref = dirUrl(s);
    const quality = placeQuality(s);
    let badge = "";
    if (quality === "verified") {
      badge = ' <span class="place-badge good" title="Resolves via Google Place ID">✓</span>';
    } else if (quality === "fallback") {
      badge = ' <span class="place-badge warn" title="No Place ID — falls back to name+city query">⚠</span>';
    }

    html += '<div class="card-actions" style="margin-top:10px">';
    html += '<a class="btn btn-primary" href="' + dirHref + '" target="_blank" rel="noopener">Directions →</a>';
    html += '<a class="btn btn-secondary" href="' + placeHref + '" target="_blank" rel="noopener">Open in Maps' + badge + "</a>";
    html += "</div></div></div>";
    return html;
  }

  /* ===================================================================
   * MODE SWITCHING + INIT
   * =================================================================== */

  function renderMode() {
    const dayView = document.getElementById("day-view");
    const agendaView = document.getElementById("agenda-view");
    const mergedView = document.getElementById("merged-view");
    if (state.mode === "agenda") {
      dayView.hidden = true;
      agendaView.hidden = false;
      mergedView.hidden = true;
      renderAgendaView();
      window.scrollTo({ top: 0, behavior: "instant" });
    } else if (state.mode === "merged") {
      dayView.hidden = true;
      agendaView.hidden = true;
      mergedView.hidden = false;
      renderMergedView();
      window.scrollTo({ top: 0, behavior: "instant" });
    } else {
      dayView.hidden = false;
      agendaView.hidden = true;
      mergedView.hidden = true;
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
      // Picking a plan means the user wants to look at that plan's day view —
      // drop out of agenda / merged modes so the click actually lands somewhere
      // the plan selection matters.
      if (state.mode !== "day") state.mode = "day";
      persist();
      renderPlanToggle();
      renderDayToggle();
      renderAgendaToggle();
      renderMergedToggle();
      renderMode();
    });
  });

  document.getElementById("agenda-toggle").addEventListener("click", () => {
    state.mode = state.mode === "agenda" ? "day" : "agenda";
    persist();
    renderAgendaToggle();
    renderMergedToggle();
    renderPlanToggle();
    renderDayToggle();
    renderMode();
  });

  document.getElementById("merged-toggle").addEventListener("click", () => {
    state.mode = state.mode === "merged" ? "day" : "merged";
    persist();
    renderAgendaToggle();
    renderMergedToggle();
    renderPlanToggle();
    renderDayToggle();
    renderMode();
  });

  // Bootstrap.
  loadInitialState();
  renderPlanToggle();
  renderDayToggle();
  renderAgendaToggle();
  renderMergedToggle();
  renderFullMapsToggle();
  renderDayMapsToggle();
  renderMode();
})();
