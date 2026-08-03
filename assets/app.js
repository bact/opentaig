// Client-side search + facet filtering over the statically rendered problem
// cards. Reads only what's already in the DOM (data-* attributes baked in at
// build time) -- no fetch, no network calls, works entirely offline.
(function () {
  "use strict";

  var filterBar = document.getElementById("filter-bar");
  if (!filterBar) return; // not on the index page

  var searchInput = document.getElementById("filter-search");
  var capacitySelect = document.getElementById("filter-capacity");
  var targetSelect = document.getElementById("filter-target");
  var frameworkSelects = Array.prototype.slice.call(document.querySelectorAll(".filter-framework"));
  var hasToolCheckbox = document.getElementById("filter-has-tool");
  var resetButton = document.getElementById("filter-reset");
  var countEl = document.getElementById("filter-count");
  var noResultsEl = document.getElementById("no-results");

  // Excludes .orphan-tools-card ("#0", our own tool-listing convention, not
  // an actual TAIG research question) from filtering and the shown-count.
  var cards = Array.prototype.slice.call(document.querySelectorAll(".problem-card:not(.orphan-tools-card)"));
  var capacityGroups = Array.prototype.slice.call(document.querySelectorAll(".capacity-group"));
  var targetGroups = Array.prototype.slice.call(document.querySelectorAll(".target-group"));
  var areaGroups = Array.prototype.slice.call(document.querySelectorAll(".area-group"));

  function matches(card) {
    var q = searchInput.value.trim().toLowerCase();
    if (q && (card.dataset.search || "").indexOf(q) === -1) return false;

    var cap = capacitySelect.value;
    if (cap && card.dataset.capacity !== cap) return false;

    var tgt = targetSelect.value;
    if (tgt && card.dataset.target !== tgt) return false;

    if (hasToolCheckbox.checked && card.dataset.hasTool !== "1") return false;

    for (var i = 0; i < frameworkSelects.length; i++) {
      var sel = frameworkSelects[i];
      var term = sel.value;
      if (!term) continue;
      var key = sel.dataset.framework; // e.g. "euaiact" (matches build.py's fw["key"])
      // data-fw-<key> attributes are stored as "|term1|term2|" for safe substring
      // matching. Read via getAttribute rather than .dataset, since underscores in
      // `key` don't convert predictably through the dataset camelCase rules.
      var raw = card.getAttribute("data-fw-" + key);
      if (!raw || raw.indexOf("|" + term + "|") === -1) return false;
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

  [searchInput, capacitySelect, targetSelect, hasToolCheckbox]
    .concat(frameworkSelects)
    .forEach(function (el) {
      el.addEventListener("input", applyFilters);
      el.addEventListener("change", applyFilters);
    });

  resetButton.addEventListener("click", function () {
    searchInput.value = "";
    capacitySelect.value = "";
    targetSelect.value = "";
    hasToolCheckbox.checked = false;
    frameworkSelects.forEach(function (s) { s.value = ""; });
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

// Chip visibility preferences: which frameworks' term chips (and the
// expertise chips) show on problem cards.
// Scoped to elements marked [data-fw-chip] only -- tool and framework pages
// always show their own chips, since there they ARE the primary content,
// not supplemental. Default: "aiaaic" and "expertise" on, every other
// framework off. Persisted in localStorage and applied on every page (not
// just the index, where the toggle controls live) so the preference is
// consistent while browsing.
(function () {
  "use strict";

  // Collapse/expand for the "Display additional information" bar (only
  // present on the problem-list page) -- independent of the fwKeys prefs
  // logic below, so it still works even if that section is skipped.
  var visibilityToggle = document.getElementById("chip-visibility-toggle");
  var visibilityBody = document.getElementById("chip-visibility-body");
  if (visibilityToggle && visibilityBody) {
    visibilityToggle.addEventListener("click", function () {
      var expanded = visibilityToggle.getAttribute("aria-expanded") === "true";
      visibilityToggle.setAttribute("aria-expanded", String(!expanded));
      visibilityBody.hidden = expanded;
      visibilityToggle.textContent = expanded ? "Show" : "Hide";
    });
  }

  var STORAGE_KEY = "opentaig-chip-prefs";
  var fwKeys = (document.body.dataset.fwKeys || "").split(",").filter(Boolean);
  if (!fwKeys.length) return;

  function loadPrefs() {
    var defaults = {};
    fwKeys.forEach(function (k) { defaults[k] = (k === "aiaaic" || k === "expertise"); });
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

  var toggles = Array.prototype.slice.call(document.querySelectorAll(".chip-toggle-input"));
  toggles.forEach(function (el) {
    el.checked = !!prefs[el.dataset.fwKey];
    el.addEventListener("change", function () {
      prefs[el.dataset.fwKey] = el.checked;
      savePrefs(prefs);
      applyPrefs(prefs);
    });
  });

  // "Mapped frameworks" multi-select dropdown: a compact trigger button
  // that expands into the checkbox list above, rather than showing every
  // framework checkbox inline.
  var msTrigger = document.getElementById("fw-multiselect-trigger");
  var msPanel = document.getElementById("fw-multiselect-panel");
  if (msTrigger && msPanel) {
    var msCheckboxes = Array.prototype.slice.call(msPanel.querySelectorAll(".chip-toggle-input"));
    var msTriggerText = msTrigger.querySelector(".multiselect-trigger-text");

    function updateMsTrigger() {
      var checked = msCheckboxes.filter(function (c) { return c.checked; });
      if (checked.length === 0) msTriggerText.textContent = "None selected";
      else if (checked.length === 1) msTriggerText.textContent = checked[0].closest("label").textContent.trim();
      else msTriggerText.textContent = checked.length + " selected";
    }
    updateMsTrigger();
    msCheckboxes.forEach(function (c) { c.addEventListener("change", updateMsTrigger); });

    msTrigger.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = msTrigger.getAttribute("aria-expanded") === "true";
      msTrigger.setAttribute("aria-expanded", String(!open));
      msPanel.hidden = open;
    });
    document.addEventListener("click", function (e) {
      if (!msPanel.hidden && !msPanel.contains(e.target) && e.target !== msTrigger) {
        msPanel.hidden = true;
        msTrigger.setAttribute("aria-expanded", "false");
      }
    });
    var msContainer = msTrigger.closest(".multiselect");
    msContainer.addEventListener("focusout", function (e) {
      if (!msContainer.contains(e.relatedTarget)) {
        msPanel.hidden = true;
        msTrigger.setAttribute("aria-expanded", "false");
      }
    });
    msPanel.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        msPanel.hidden = true;
        msTrigger.setAttribute("aria-expanded", "false");
        msTrigger.focus();
      }
    });
  }
})();
