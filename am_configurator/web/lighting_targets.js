(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingTargets = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  function targets(values) {
    return Object.freeze(values.map(value => Object.freeze({...value})));
  }

  const DEVICE_TARGETS = Object.freeze({
    CB: targets([
      {key: "keyframes", label: "Switch LEDs"},
      {key: "frames", label: "Top display 40×5"},
    ]),
    ALICE: targets([
      {key: "keyframes", label: "Keys + center"},
    ]),
    "80": targets([
      {key: "keyframes", label: "Per-key"},
      {key: "spotlight_frames", label: "Edge lights"},
    ]),
  });

  function renderTargetControls(host, availableTargets, selectedTarget, locked, onSelect) {
    if (!host || typeof host.replaceChildren !== "function" || !host.ownerDocument) {
      throw new TypeError("A target-control host is required.");
    }
    const document = host.ownerDocument;
    const choices = Array.isArray(availableTargets) ? availableTargets : [];
    if (!choices.length) {
      const empty = document.createElement("button");
      empty.type = "button";
      empty.disabled = true;
      empty.textContent = "Open document";
      host.replaceChildren(empty);
      return;
    }
    const buttons = choices.map(target => {
      const key = String(target.key || "");
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.lightingTarget = key;
      button.textContent = String(target.label || key);
      button.className = key === selectedTarget ? "active" : "";
      button.setAttribute("aria-pressed", String(key === selectedTarget));
      button.disabled = Boolean(locked);
      button.addEventListener("click", () => {
        if (!button.disabled && typeof onSelect === "function") onSelect(key);
      });
      return button;
    });
    host.replaceChildren(...buttons);
  }

  return Object.freeze({DEVICE_TARGETS, renderTargetControls});
});
