// SPDX-FileCopyrightText: 2026 OpenTAIG authors
// SPDX-FileType: SOURCE
// SPDX-License-Identifier: Apache-2.0

// Generic disclosure (Show/Hide) sections: the "Display additional
// information" bar, the taxonomy/frameworks filter groups, and the tools
// page's filter bar all use the same [data-disclosure] header pattern --
// a title + a Show/Hide button, where the whole header row (not just the
// button) toggles the body it controls.
(function () {
  "use strict";
  Array.prototype.forEach.call(document.querySelectorAll("[data-disclosure]"), function (header) {
    var btn = header.querySelector(".disclosure-toggle");
    var body = btn && document.getElementById(btn.getAttribute("aria-controls"));
    if (!btn || !body) return;
    header.addEventListener("click", function () {
      var expanded = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
      btn.textContent = expanded ? "Show" : "Hide";
    });
  });
})();

// Generic multi-select dropdown: a compact trigger button that expands into
// a checkbox list, instead of showing every option inline or requiring
// Ctrl/Cmd-click like a native <select multiple>. Used both for the filter
// facets below and for the "Mapped frameworks" chip-visibility control.
// `onChange(checkbox)` fires after each checkbox change (once the trigger
// text is already up to date), so callers can react without re-deriving
// selection state themselves.
function enhanceMultiselect(container, onChange) {
  var trigger = container.querySelector(".multiselect-trigger");
  var panel = container.querySelector(".multiselect-panel");
  if (!trigger || !panel) return;
  var triggerText = trigger.querySelector(".multiselect-trigger-text");
  var checkboxes = Array.prototype.slice.call(panel.querySelectorAll(".chip-toggle-input"));

  function updateTriggerText() {
    var checked = checkboxes.filter(function (c) { return c.checked; });
    var text;
    if (checked.length === 0) text = "None selected";
    else if (checked.length === 1) text = checked[0].closest("label").textContent.trim();
    else text = checked.length + " selected";
    if (checkboxes.length > 0 && checked.length === checkboxes.length) text += " (all)";
    triggerText.textContent = text;
  }
  updateTriggerText();
  // Exposed so external code (e.g. a "Reset" button for a whole section) can
  // refresh the trigger label after clearing checkboxes programmatically.
  container._updateTrigger = updateTriggerText;

  checkboxes.forEach(function (c) {
    c.addEventListener("change", function () {
      updateTriggerText();
      if (onChange) onChange(c);
    });
  });

  function close() {
    panel.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  }

  trigger.addEventListener("click", function (e) {
    e.stopPropagation();
    var open = trigger.getAttribute("aria-expanded") === "true";
    trigger.setAttribute("aria-expanded", String(!open));
    panel.hidden = open;
  });

  document.addEventListener("click", function (e) {
    if (!panel.hidden && !container.contains(e.target)) close();
  });

  // Closing on blur has to survive a mouse press: pressing a checkbox's
  // <label> blurs the trigger on mousedown, but focus only reaches the
  // checkbox on click -- so for the length of the press (any real click
  // lasts longer than a frame) focus is on neither, and a bare focusout
  // check would close the panel out from under the click. Tracking the
  // press lets the blur check stand down until the pointer is released.
  var pressingInside = false;
  container.addEventListener("pointerdown", function () { pressingInside = true; });
  document.addEventListener("pointerup", function () { pressingInside = false; });
  container.addEventListener("focusout", function () {
    requestAnimationFrame(function () {
      if (pressingInside) return;
      if (!container.contains(document.activeElement)) close();
    });
  });

  panel.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      close();
      trigger.focus();
    }
  });
}

function resetMultiselectsIn(scopeEl) {
  Array.prototype.forEach.call(scopeEl.querySelectorAll(".multiselect"), function (ms) {
    Array.prototype.forEach.call(ms.querySelectorAll(".chip-toggle-input"), function (c) { c.checked = false; });
    if (ms._updateTrigger) ms._updateTrigger();
  });
}

// Client-side search + facet filtering over the statically rendered problem
// cards. Reads only what's already in the DOM (data-* attributes baked in at
// build time) -- no fetch, no network calls, works entirely offline.
(function () {
  "use strict";

  var filterBar = document.getElementById("filter-bar");
  if (!filterBar) return; // not on the index page

  var searchInput = document.getElementById("filter-search");
  var hasToolCheckbox = document.getElementById("filter-has-tool");
  var countEl = document.getElementById("filter-count");
  var noResultsEl = document.getElementById("no-results");

  // Excludes .orphan-tools-card ("#0", our own tool-listing convention, not
  // an actual TAIG research question) from filtering and the shown-count.
  var cards = Array.prototype.slice.call(document.querySelectorAll(".problem-card:not(.orphan-tools-card)"));
  var capacityGroups = Array.prototype.slice.call(document.querySelectorAll(".capacity-group"));
  var targetGroups = Array.prototype.slice.call(document.querySelectorAll(".target-group"));
  var areaGroups = Array.prototype.slice.call(document.querySelectorAll(".area-group"));

  // Each facet dropdown (Capacity, Target, Relevant expertise, and one per
  // framework) declares how to read a card's matching data-* attribute:
  // "single" for a one-value-per-card attribute (equality match), "pipe"
  // for a "|term1|term2|"-style attribute (substring match). Selecting more
  // than one option within a facet is an OR; different facets AND together.
  var filterFacets = Array.prototype.slice.call(filterBar.querySelectorAll(".multiselect[data-facet-attr]")).map(function (ms) {
    return {
      type: ms.dataset.facetType,
      attr: ms.dataset.facetAttr,
      checkboxes: Array.prototype.slice.call(ms.querySelectorAll(".chip-toggle-input"))
    };
  });

  function facetMatches(card, facet) {
    var checkedVals = facet.checkboxes.filter(function (c) { return c.checked; }).map(function (c) { return c.dataset.value; });
    if (!checkedVals.length) return true; // nothing selected in this facet -- doesn't narrow the results
    if (facet.type === "single") {
      return checkedVals.indexOf(card.dataset[facet.attr]) !== -1;
    }
    // data-fw-<key> attributes are stored as "|term1|term2|" for safe
    // substring matching. Read via getAttribute rather than .dataset, since
    // underscores/dashes in the key don't convert predictably through the
    // dataset camelCase rules.
    var raw = card.getAttribute("data-" + facet.attr) || "";
    return checkedVals.some(function (v) { return raw.indexOf("|" + v + "|") !== -1; });
  }

  function matches(card) {
    var q = searchInput.value.trim().toLowerCase();
    if (q && (card.dataset.search || "").indexOf(q) === -1) return false;
    if (hasToolCheckbox.checked && card.dataset.hasTool !== "1") return false;
    for (var i = 0; i < filterFacets.length; i++) {
      if (!facetMatches(card, filterFacets[i])) return false;
    }
    return true;
  }

  function applyFilters() {
    var visibleCount = 0;
    cards.forEach(function (card) {
      var show = matches(card);
      card.hidden = !show;
      if (show) visibleCount++;
    });

    areaGroups.forEach(function (group) {
      var anyVisible = Array.prototype.some.call(
        group.querySelectorAll(".problem-card"),
        function (c) { return !c.hidden; }
      );
      group.hidden = !anyVisible;
    });

    targetGroups.forEach(function (group) {
      var anyVisible = Array.prototype.some.call(
        group.querySelectorAll(".problem-card"),
        function (c) { return !c.hidden; }
      );
      group.hidden = !anyVisible;
    });

    capacityGroups.forEach(function (group) {
      var anyVisible = Array.prototype.some.call(
        group.querySelectorAll(".problem-card"),
        function (c) { return !c.hidden; }
      );
      group.hidden = !anyVisible;
    });

    countEl.textContent = visibleCount + " of " + cards.length + " shown";
    noResultsEl.hidden = visibleCount !== 0;
  }

  [searchInput, hasToolCheckbox].forEach(function (el) {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });

  var searchButton = document.getElementById("filter-search-button");
  if (searchButton) searchButton.addEventListener("click", applyFilters);

  filterFacets.forEach(function (facet, i) {
    var container = filterBar.querySelectorAll(".multiselect[data-facet-attr]")[i];
    enhanceMultiselect(container, applyFilters);
  });

  var searchResetBtn = document.getElementById("filter-search-reset");
  if (searchResetBtn) searchResetBtn.addEventListener("click", function () {
    searchInput.value = "";
    hasToolCheckbox.checked = false;
    applyFilters();
  });

  var taigResetBtn = document.getElementById("filter-taig-reset");
  if (taigResetBtn) taigResetBtn.addEventListener("click", function () {
    resetMultiselectsIn(document.getElementById("filter-taig-body"));
    applyFilters();
  });

  var fwResetBtn = document.getElementById("filter-fw-reset");
  if (fwResetBtn) fwResetBtn.addEventListener("click", function () {
    resetMultiselectsIn(document.getElementById("filter-fw-body"));
    applyFilters();
  });

  applyFilters();
})();

// Client-side search + type filtering for the tools index -- same
// read-the-DOM-attributes approach as the problem-list filter above.
(function () {
  "use strict";

  var filterBar = document.getElementById("tools-filter-bar");
  if (!filterBar) return; // not on the tools index page

  var searchInput = document.getElementById("tools-filter-search");
  var softwareCheckbox = document.getElementById("tools-filter-software");
  var specCheckbox = document.getElementById("tools-filter-spec");
  var resetButton = document.getElementById("tools-filter-reset");
  var countEl = document.getElementById("tools-filter-count");
  var noResultsEl = document.getElementById("tools-no-results");
  var items = Array.prototype.slice.call(document.querySelectorAll("#tool-list .tool-list-item"));

  function matches(item) {
    var q = searchInput.value.trim().toLowerCase();
    if (q && (item.dataset.search || "").indexOf(q) === -1) return false;
    var checkedTypes = [];
    if (softwareCheckbox.checked) checkedTypes.push("software");
    if (specCheckbox.checked) checkedTypes.push("specification");
    if (checkedTypes.length && checkedTypes.indexOf(item.dataset.type) === -1) return false;
    return true;
  }

  function applyFilters() {
    var visibleCount = 0;
    items.forEach(function (item) {
      var show = matches(item);
      item.hidden = !show;
      if (show) visibleCount++;
    });
    countEl.textContent = visibleCount + " of " + items.length + " shown";
    noResultsEl.hidden = visibleCount !== 0;
  }

  [searchInput, softwareCheckbox, specCheckbox].forEach(function (el) {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  });

  resetButton.addEventListener("click", function () {
    searchInput.value = "";
    softwareCheckbox.checked = false;
    specCheckbox.checked = false;
    applyFilters();
  });

  applyFilters();
})();

// Chip visibility preferences: which frameworks' term chips show on problem
// cards. Scoped to elements marked [data-fw-chip] only -- tool and framework
// pages always show their own chips, since there they ARE the primary
// content, not supplemental. (Expertise chips are unconditional now, not a
// preference, so they carry no [data-fw-chip] marker.) Default: "aiaaic" on,
// every other framework off. Persisted in localStorage and applied on every
// page (not just the index, where the toggle controls live) so the
// preference is consistent while browsing.
(function () {
  "use strict";

  var STORAGE_KEY = "opentaig-chip-prefs";
  var fwKeys = (document.body.dataset.fwKeys || "").split(",").filter(Boolean);
  if (!fwKeys.length) return;

  function loadPrefs() {
    var defaults = {};
    fwKeys.forEach(function (k) { defaults[k] = (k === "aiaaic"); });
    var stored = {};
    try {
      stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    } catch (e) { stored = {}; }
    fwKeys.forEach(function (k) {
      if (typeof stored[k] === "boolean") defaults[k] = stored[k];
    });
    return defaults;
  }

  function savePrefs(prefs) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch (e) { /* storage unavailable -- preference just won't persist */ }
  }

  function applyPrefs(prefs) {
    Array.prototype.forEach.call(document.querySelectorAll("[data-fw-chip]"), function (el) {
      el.style.display = prefs[el.dataset.fwChip] ? "" : "none";
    });
  }

  var prefs = loadPrefs();
  applyPrefs(prefs);

  var msTrigger = document.getElementById("fw-multiselect-trigger");
  if (msTrigger) {
    var msContainer = msTrigger.closest(".multiselect");
    var msCheckboxes = Array.prototype.slice.call(msContainer.querySelectorAll(".chip-toggle-input"));
    msCheckboxes.forEach(function (el) { el.checked = !!prefs[el.dataset.fwKey]; });
    enhanceMultiselect(msContainer, function (checkbox) {
      prefs[checkbox.dataset.fwKey] = checkbox.checked;
      savePrefs(prefs);
      applyPrefs(prefs);
    });
  }
})();
