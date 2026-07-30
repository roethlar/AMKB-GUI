"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const css = fs.readFileSync(path.join(root, "am_configurator/web/style.css"), "utf8");
const js = fs.readFileSync(path.join(root, "am_configurator/web/app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "am_configurator/web/index.html"), "utf8");

function token(name) {
  const match = css.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert.ok(match, `style.css must define ${name} as a six-digit hex token`);
  return match[1];
}

function luminance(hex) {
  const channel = (value) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(fg, bg) {
  const [light, dark] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

test("normal text tokens hold WCAG AA 4.5:1 on every surface they sit on", () => {
  const text = token("--text");
  const muted = token("--muted");
  const muted2 = token("--muted-2");
  const violet2 = token("--violet-2");
  for (const surface of ["--bg", "--panel", "--panel-2", "--panel-3"]) {
    const bg = token(surface);
    assert.ok(contrast(text, bg) >= 4.5, `--text on ${surface} is ${contrast(text, bg).toFixed(2)}`);
    assert.ok(contrast(muted, bg) >= 4.5, `--muted on ${surface} is ${contrast(muted, bg).toFixed(2)}`);
    assert.ok(contrast(muted2, bg) >= 4.5, `--muted-2 on ${surface} is ${contrast(muted2, bg).toFixed(2)}`);
    assert.ok(contrast(violet2, bg) >= 4.5, `--violet-2 on ${surface} is ${contrast(violet2, bg).toFixed(2)}`);
  }
});

test("control boundaries hold 3:1 against their panels", () => {
  const controlLine = token("--control-line");
  for (const surface of ["--bg", "--panel", "--panel-2", "--panel-3"]) {
    const bg = token(surface);
    assert.ok(contrast(controlLine, bg) >= 3, `--control-line on ${surface} is ${contrast(controlLine, bg).toFixed(2)}`);
  }
  for (const selector of [
    /\.button\.ghost \{[^}]*var\(--control-line\)/,
    /\.icon-button \{[^}]*var\(--control-line\)/,
    /\.segmented \{[^}]*var\(--control-line\)/,
    /\.search-field, \.text-field, \.select-field \{[^}]*var\(--control-line\)/,
    /\.palette-key \{[^}]*var\(--control-line\)/,
    /\.task-card \{[^}]*var\(--control-line\)/,
    /\.library-card \{[^}]*var\(--control-line\)/,
  ]) assert.match(css, selector);
});

test("body text is at least 14px and helper text at least 13px", () => {
  assert.match(css, /:root \{[^}]*font-size: 14px/s);
  const offenders = [];
  for (const [index, line] of css.split(/\r?\n/).entries()) {
    for (const match of line.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)) {
      if (Number(match[1]) < 13 && !/\.keycap span/.test(line)) offenders.push(`${index + 1}: ${line.trim()}`);
    }
  }
  assert.deepEqual(offenders, [], `helper text below the 13px floor:\n${offenders.join("\n")}`);
  for (const match of js.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)) {
    assert.ok(Number(match[1]) >= 13, `app.js inline font-size below floor: ${match[0]}`);
  }
});

test("focus stays visible and disabled controls stay readable", () => {
  assert.match(css, /button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, \[tabindex\]:focus-visible \{ outline: 2px solid var\(--violet-2\); outline-offset: 2px; \}/);
  assert.doesNotMatch(css, /focus-visible[^{]*\{[^}]*outline:\s*(?:none|0)/);
  const buttonDisabled = css.match(/\.button:disabled \{ opacity: \.(\d+)/);
  assert.ok(buttonDisabled && Number(`0.${buttonDisabled[1]}`) >= 0.5, "disabled buttons must keep readable text");
  const iconDisabled = css.match(/\.icon-button:disabled \{ opacity: \.(\d+)/);
  assert.ok(iconDisabled && Number(`0.${iconDisabled[1]}`) >= 0.5, "disabled icon buttons must keep readable glyphs");
});

test("layout keeps narrow-window and reduced-motion coverage", () => {
  for (const breakpoint of ["1450px", "1240px", "1120px", "980px", "720px"]) {
    assert.match(css, new RegExp(`@media \\(max-width: ${breakpoint}\\)`));
  }
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /\.main-content \{[^}]*overflow: auto/);
});

function mediaBlock(width) {
  const start = css.indexOf(`@media (max-width: ${width})`);
  assert.ok(start >= 0, `missing breakpoint ${width}`);
  const end = css.indexOf("\n}", start);
  return css.slice(start, end);
}

test("primary top-bar actions can never be clipped away at narrow widths", () => {
  const block = mediaBlock("1120px");
  assert.match(block, /\.top-actions \{ grid-column: 1 \/ -1; width: 100%; overflow-x: auto;/);
  assert.match(block, /\.topbar \{ height: auto; min-height: 0;/);
  // The always-visible device actions keep short labels that fit the minimum window.
  assert.match(html, /<button id="merge-button"[^>]*title="Merge another JSON"[^>]*>Merge<\/button>/);
});

test("the keymap editor drops to one column before its 620px floor can clip", () => {
  const block = mediaBlock("1240px");
  assert.match(block, /\.editor-grid \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(block, /\.inspector \{ position: static; \}/);
});

test("the keyboard board can never outgrow its card", () => {
  // aspect-ratio + min-height transfers an implicit ~767px min-width to the
  // stage; without a 100% cap the board spills under the key inspector.
  assert.match(css, /\.keyboard-stage \{[^}]*min-height: 260px; max-width: 100%;/);
});

test("panel control rows wrap instead of blowing out of fixed columns", () => {
  // Grid children default to min-width:auto, so a 1fr/1fr row overflows a
  // ~210px tool column as soon as a label's min-content exceeds its track.
  assert.match(css, /\.button-row \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(110px, 1fr\)\);/);
  assert.match(css, /\.button-row > \* \{ min-width: 0; \}/);
  assert.match(css, /\.gif-import-row \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(130px, 1fr\)\);/);
  assert.match(css, /\.gif-import-row > \* \{ min-width: 0; \}/);
  for (const row of ["media-composition-actions", "animation-draft-actions"]) {
    assert.match(css, new RegExp(`\\.${row} \\{ display: grid; grid-template-columns: repeat\\(auto-fit, minmax\\(110px, 1fr\\)\\);`));
    assert.match(css, new RegExp(`\\.${row} > \\* \\{ min-width: 0; \\}`));
  }
  assert.match(css, /\.search-field, \.text-field, \.select-field \{ width: 100%; min-width: 0; max-width: 100%;/);
});
