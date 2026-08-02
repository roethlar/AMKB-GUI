(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingComposer = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const TRANSFORM_FIELDS = new Set([
    "version",
    "offset_x",
    "offset_y",
    "scale_x",
    "scale_y",
    "aspect_locked",
    "sampling",
    "background",
  ]);
  const EFFECT_FIELDS = new Set([
    "version",
    "type",
    "frame_count",
    "duration_ms",
    "parameters",
  ]);
  const SAMPLING = new Set(["nearest", "box", "lanczos"]);
  const DIRECTIONS = new Set([
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "diagonal",
  ]);
  const RGB = /^#[0-9A-Fa-f]{6}$/;
  const MIN_SCALE = 0.01;
  const MAX_SCALE = 32;
  const MAX_OFFSET = 8;

  function hasExactFields(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const fields = Object.keys(value);
    return fields.length === expected.size && fields.every(field => expected.has(field));
  }

  function finiteNumber(value, label) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new TypeError(`${label} must be a finite number.`);
    }
    return Object.is(value, -0) ? 0 : value;
  }

  function boundedNumber(value, minimum, maximum, label) {
    const number = finiteNumber(value, label);
    if (number < minimum || number > maximum) {
      throw new RangeError(`${label} is outside its supported range.`);
    }
    return number;
  }

  function boundedInteger(value, minimum, maximum, label) {
    if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
      throw new RangeError(`${label} is outside its supported range.`);
    }
    return value;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function createLatestTaskScheduler({
    delayMs = 75,
    setTimer = (callback, delay) => setTimeout(callback, delay),
    clearTimer = timer => clearTimeout(timer),
    run,
  } = {}) {
    if (
      typeof run !== "function"
      || typeof setTimer !== "function"
      || typeof clearTimer !== "function"
      || !Number.isSafeInteger(delayMs)
      || delayMs < 0
    ) {
      throw new TypeError("The latest-task scheduler is invalid.");
    }
    let generation = 0;
    let completedGeneration = 0;
    let latest = null;
    let timer = null;
    let running = null;
    let flushNext = false;
    const waiters = [];

    const settleWaiters = (failedGeneration = null, error = null) => {
      for (let index = waiters.length - 1; index >= 0; index -= 1) {
        const waiter = waiters[index];
        if (waiter.generation > completedGeneration) continue;
        waiters.splice(index, 1);
        if (failedGeneration !== null && failedGeneration >= waiter.generation) {
          waiter.reject(error);
        } else {
          waiter.resolve();
        }
      }
    };

    const clearPendingTimer = () => {
      if (timer === null) return;
      clearTimer(timer);
      timer = null;
    };

    let launch;
    const schedule = () => {
      if (!latest || running || timer !== null) return;
      timer = setTimer(() => {
        timer = null;
        launch();
      }, delayMs);
    };

    launch = () => {
      if (running || !latest) return running?.promise || Promise.resolve();
      clearPendingTimer();
      const task = latest;
      latest = null;
      let promise;
      try {
        promise = Promise.resolve(run(task.value));
      } catch (error) {
        promise = Promise.reject(error);
      }
      running = {generation: task.generation, promise};
      promise.then(
        () => {
          if (running?.generation !== task.generation) return;
          running = null;
          completedGeneration = Math.max(completedGeneration, task.generation);
          settleWaiters();
          if (!latest) return;
          if (flushNext) {
            flushNext = false;
            launch();
          } else {
            schedule();
          }
        },
        error => {
          if (running?.generation !== task.generation) return;
          running = null;
          completedGeneration = Math.max(completedGeneration, task.generation);
          settleWaiters(task.generation, error);
          if (!latest) return;
          if (flushNext) {
            flushNext = false;
            launch();
          } else {
            schedule();
          }
        },
      );
      return promise;
    };

    const request = value => {
      generation += 1;
      latest = {generation, value};
      clearPendingTimer();
      if (!running) schedule();
      return generation;
    };

    const flush = () => {
      const requestedGeneration = generation;
      if (requestedGeneration <= completedGeneration || (!latest && !running)) {
        return Promise.resolve();
      }
      const promise = new Promise((resolve, reject) => {
        waiters.push({generation: requestedGeneration, resolve, reject});
      });
      clearPendingTimer();
      if (running) flushNext = true;
      else launch();
      return promise;
    };

    const cancel = () => {
      clearPendingTimer();
      latest = null;
      flushNext = false;
      completedGeneration = Math.max(completedGeneration, generation);
      settleWaiters();
    };

    return Object.freeze({request, flush, cancel});
  }

  function validateSourceTransform(value) {
    if (!hasExactFields(value, TRANSFORM_FIELDS)) {
      throw new TypeError("The source transform schema is unsupported.");
    }
    if (value.version !== 1) {
      throw new RangeError("The source transform version is unsupported.");
    }
    const offsetX = boundedNumber(
      value.offset_x,
      -MAX_OFFSET,
      MAX_OFFSET,
      "offset_x",
    );
    const offsetY = boundedNumber(
      value.offset_y,
      -MAX_OFFSET,
      MAX_OFFSET,
      "offset_y",
    );
    const scaleX = boundedNumber(value.scale_x, MIN_SCALE, MAX_SCALE, "scale_x");
    const scaleY = boundedNumber(value.scale_y, MIN_SCALE, MAX_SCALE, "scale_y");
    if (typeof value.aspect_locked !== "boolean") {
      throw new TypeError("aspect_locked must be a boolean.");
    }
    if (value.aspect_locked && Math.abs(scaleX - scaleY) > 1e-12) {
      throw new RangeError("Locked source transforms require equal scales.");
    }
    if (typeof value.sampling !== "string" || !SAMPLING.has(value.sampling)) {
      throw new RangeError("The source transform sampling mode is unsupported.");
    }
    if (
      typeof value.background !== "string"
      || !RGB.test(value.background)
      || value.background.toUpperCase() !== "#000000"
    ) {
      throw new RangeError("The source transform background is invalid.");
    }
    return {
      version: 1,
      offset_x: offsetX,
      offset_y: offsetY,
      scale_x: scaleX,
      scale_y: scaleY,
      aspect_locked: value.aspect_locked,
      sampling: value.sampling,
      background: "#000000",
    };
  }

  function defaultSourceTransform(sampling = "box") {
    return validateSourceTransform({
      version: 1,
      offset_x: 0,
      offset_y: 0,
      scale_x: 1,
      scale_y: 1,
      aspect_locked: true,
      sampling,
      background: "#000000",
    });
  }

  function validateSize(value, label) {
    if (
      !value
      || typeof value !== "object"
      || Array.isArray(value)
      || !Number.isSafeInteger(value.width)
      || !Number.isSafeInteger(value.height)
      || value.width <= 0
      || value.height <= 0
    ) {
      throw new TypeError(`${label} size is invalid.`);
    }
    return {width: value.width, height: value.height};
  }

  function validateDestinationSizes(value) {
    const values = Array.isArray(value) ? value : [value];
    if (values.length === 0) {
      throw new TypeError("At least one destination size is required.");
    }
    return values.map((size, index) => validateSize(
      size,
      `Destination ${index + 1}`,
    ));
  }

  function roundGeometry(value) {
    return Math.floor(value + 0.5);
  }

  function resolveSourceGeometry(sourceSize, destinationSizes, transform) {
    const source = validateSize(sourceSize, "Source");
    const destinations = validateDestinationSizes(destinationSizes);
    const checked = validateSourceTransform(transform);
    const dimensions = [];
    const limits = [];
    for (const destination of destinations) {
      const baseScale = Math.max(
        destination.width / source.width,
        destination.height / source.height,
      );
      const renderedWidth = Math.max(
        1,
        roundGeometry(source.width * baseScale * checked.scale_x),
      );
      const renderedHeight = Math.max(
        1,
        roundGeometry(source.height * baseScale * checked.scale_y),
      );
      dimensions.push(Object.freeze({renderedWidth, renderedHeight}));
      limits.push(Object.freeze({
        maxX: Math.min(
          MAX_OFFSET,
          Math.abs(renderedWidth - destination.width) / (2 * destination.width),
        ),
        maxY: Math.min(
          MAX_OFFSET,
          Math.abs(renderedHeight - destination.height) / (2 * destination.height),
        ),
      }));
    }
    const maxX = Math.min(...limits.map(limit => limit.maxX));
    const maxY = Math.min(...limits.map(limit => limit.maxY));
    const canonical = Object.freeze(validateSourceTransform({
      ...checked,
      offset_x: clamp(checked.offset_x, -maxX, maxX),
      offset_y: clamp(checked.offset_y, -maxY, maxY),
    }));
    const boxes = Object.freeze(destinations.map((destination, index) => {
      const {renderedWidth, renderedHeight} = dimensions[index];
      return Object.freeze({
        rendered_width: renderedWidth,
        rendered_height: renderedHeight,
        left: roundGeometry(
          (destination.width - renderedWidth) / 2
            + canonical.offset_x * destination.width,
        ),
        top: roundGeometry(
          (destination.height - renderedHeight) / 2
            + canonical.offset_y * destination.height,
        ),
      });
    }));
    return Object.freeze({
      transform: canonical,
      limits: Object.freeze({max_x: maxX, max_y: maxY}),
      boxes,
    });
  }

  function canonicalizeSourceTransform(transform, sourceSize, destinationSizes) {
    return resolveSourceGeometry(
      sourceSize,
      destinationSizes,
      transform,
    ).transform;
  }

  function canonicalizeWhenSized(transform, sourceSize, destinationSizes) {
    if (sourceSize === undefined && destinationSizes === undefined) {
      return validateSourceTransform(transform);
    }
    if (sourceSize === undefined || destinationSizes === undefined) {
      throw new TypeError("Source transform geometry is incomplete.");
    }
    return canonicalizeSourceTransform(transform, sourceSize, destinationSizes);
  }

  function normalizedPointer(point, bounds) {
    if (!point || typeof point !== "object" || Array.isArray(point)) {
      throw new TypeError("The pointer is invalid.");
    }
    const left = finiteNumber(bounds?.left, "bounds.left");
    const top = finiteNumber(bounds?.top, "bounds.top");
    const width = boundedNumber(bounds?.width, Number.EPSILON, Number.MAX_VALUE, "bounds.width");
    const height = boundedNumber(bounds?.height, Number.EPSILON, Number.MAX_VALUE, "bounds.height");
    const clientX = finiteNumber(point.clientX, "pointer.clientX");
    const clientY = finiteNumber(point.clientY, "pointer.clientY");
    return {
      x: clamp((clientX - left) / width, 0, 1),
      y: clamp((clientY - top) / height, 0, 1),
    };
  }

  function presetSourceTransform(
    mode,
    sourceSize,
    destinationSizes,
    current = defaultSourceTransform(),
  ) {
    const source = validateSize(sourceSize, "Source");
    const destinations = validateDestinationSizes(destinationSizes);
    const destination = destinations[0];
    const checked = validateSourceTransform(current);
    if (!["fit", "fill", "center", "reset"].includes(mode)) {
      throw new RangeError("The source transform preset is unsupported.");
    }
    let scale = 1;
    if (mode === "fit") {
      const fill = Math.max(
        destination.width / source.width,
        destination.height / source.height,
      );
      const fit = Math.min(
        destination.width / source.width,
        destination.height / source.height,
      );
      scale = clamp(fit / fill, MIN_SCALE, MAX_SCALE);
    } else if (mode === "center") {
      scale = clamp(1 / Math.max(
        destination.width / source.width,
        destination.height / source.height,
      ), MIN_SCALE, MAX_SCALE);
    }
    scale = clamp(scale, MIN_SCALE, MAX_SCALE);
    return canonicalizeSourceTransform({
      ...checked,
      offset_x: 0,
      offset_y: 0,
      scale_x: scale,
      scale_y: scale,
      aspect_locked: true,
    }, source, destinations);
  }

  function panSourceTransform(
    value,
    deltaX,
    deltaY,
    sourceSize = undefined,
    destinationSizes = undefined,
  ) {
    const checked = validateSourceTransform(value);
    return canonicalizeWhenSized({
      ...checked,
      offset_x: clamp(
        checked.offset_x + finiteNumber(deltaX, "delta_x"),
        -MAX_OFFSET,
        MAX_OFFSET,
      ),
      offset_y: clamp(
        checked.offset_y + finiteNumber(deltaY, "delta_y"),
        -MAX_OFFSET,
        MAX_OFFSET,
      ),
    }, sourceSize, destinationSizes);
  }

  function scaleSourceTransform(
    value,
    factor,
    axis = "both",
    sourceSize = undefined,
    destinationSizes = undefined,
  ) {
    const checked = validateSourceTransform(value);
    const multiplier = boundedNumber(factor, MIN_SCALE, MAX_SCALE, "scale factor");
    if (!["both", "x", "y"].includes(axis)) {
      throw new RangeError("The source transform scale axis is unsupported.");
    }
    const scaleX = axis === "y"
      ? checked.scale_x
      : clamp(checked.scale_x * multiplier, MIN_SCALE, MAX_SCALE);
    const scaleY = axis === "x"
      ? checked.scale_y
      : clamp(checked.scale_y * multiplier, MIN_SCALE, MAX_SCALE);
    return canonicalizeWhenSized({
      ...checked,
      scale_x: scaleX,
      scale_y: scaleY,
      aspect_locked: axis === "both" ? checked.aspect_locked : false,
    }, sourceSize, destinationSizes);
  }

  function wireSourceTransformStage(stage, options = {}) {
    if (
      !stage
      || typeof stage.addEventListener !== "function"
      || typeof stage.removeEventListener !== "function"
    ) {
      throw new TypeError("A source transform stage is required.");
    }
    const {
      isActive,
      activate,
      getTransform,
      getGeometry,
      commit,
      getBounds = () => stage.getBoundingClientRect(),
    } = options;
    for (const [name, callback] of Object.entries({
      isActive,
      activate,
      getTransform,
      getGeometry,
      commit,
      getBounds,
    })) {
      if (typeof callback !== "function") {
        throw new TypeError(`The source transform ${name} callback is required.`);
      }
    }

    let session = null;
    const setDragging = value => stage.classList?.toggle("dragging", value);
    const removeSessionListeners = () => {
      stage.removeEventListener("pointermove", pointerMove);
      stage.removeEventListener("pointerup", releasePointer);
      stage.removeEventListener("pointercancel", releasePointer);
      stage.removeEventListener("lostpointercapture", releasePointer);
    };
    const finishSession = () => {
      session = null;
      removeSessionListeners();
      setDragging(false);
    };
    const mutate = (event, reducer) => {
      if (!isActive()) return false;
      const geometry = getGeometry();
      if (!geometry?.sourceSize || !geometry?.destinationSizes) return false;
      activate();
      commit(reducer(getTransform(), geometry));
      event.preventDefault?.();
      return true;
    };

    function releasePointer(event) {
      if (!session || (
        event?.pointerId !== undefined
        && event.pointerId !== session.pointerId
      )) return false;
      finishSession();
      return true;
    }

    function pointerMove(event) {
      if (!session || event.pointerId !== session.pointerId || !isActive()) {
        return false;
      }
      const next = normalizedPointer(event, getBounds());
      const previous = session.point;
      const changed = mutate(event, (transform, geometry) => panSourceTransform(
        transform,
        next.x - previous.x,
        next.y - previous.y,
        geometry.sourceSize,
        geometry.destinationSizes,
      ));
      if (changed) session.point = next;
      return changed;
    }

    function pointerDown(event) {
      if (
        session
        || !isActive()
        || event?.isPrimary === false
        || event?.button !== 0
        || !Number.isInteger(event?.pointerId)
      ) return false;
      const geometry = getGeometry();
      if (!geometry?.sourceSize || !geometry?.destinationSizes) return false;
      const point = normalizedPointer(event, getBounds());
      activate();
      event.preventDefault?.();
      stage.focus?.({preventScroll: true});
      session = {pointerId: event.pointerId, point};
      stage.addEventListener("pointermove", pointerMove);
      stage.addEventListener("pointerup", releasePointer);
      stage.addEventListener("pointercancel", releasePointer);
      stage.addEventListener("lostpointercapture", releasePointer);
      setDragging(true);
      try {
        stage.setPointerCapture?.(event.pointerId);
      } catch (error) {
        if (error?.name !== "NotFoundError") {
          finishSession();
          throw error;
        }
      }
      return true;
    }

    function wheel(event) {
      const delta = Number(event?.deltaY);
      if (!Number.isFinite(delta) || delta === 0) return false;
      return mutate(event, (transform, geometry) => scaleSourceTransform(
        transform,
        delta < 0 ? 1.08 : 1 / 1.08,
        "both",
        geometry.sourceSize,
        geometry.destinationSizes,
      ));
    }

    function keyDown(event) {
      const step = event?.shiftKey ? 0.1 : 0.025;
      const geometry = getGeometry();
      const primaryIndex = Number.isSafeInteger(geometry?.primaryIndex)
        && geometry.primaryIndex >= 0
        && geometry.primaryIndex < (geometry.destinationSizes?.length || 0)
        ?geometry.primaryIndex
        :0;
      const primary = geometry?.destinationSizes?.[primaryIndex];
      const xStep = Number.isFinite(primary?.width) && primary.width > 0
        ?Math.max(step, 1 / primary.width)
        :step;
      const yStep = Number.isFinite(primary?.height) && primary.height > 0
        ?Math.max(step, 1 / primary.height)
        :step;
      const pan = {
        ArrowLeft: [-xStep, 0],
        ArrowRight: [xStep, 0],
        ArrowUp: [0, -yStep],
        ArrowDown: [0, yStep],
      }[event?.key];
      if (pan) {
        return mutate(event, (transform, geometry) => panSourceTransform(
          transform,
          pan[0],
          pan[1],
          geometry.sourceSize,
          geometry.destinationSizes,
        ));
      }
      if (!["+", "=", "-", "_"].includes(event?.key)) return false;
      return mutate(event, (transform, geometry) => scaleSourceTransform(
        transform,
        ["-", "_"].includes(event.key) ? 1 / 1.08 : 1.08,
        "both",
        geometry.sourceSize,
        geometry.destinationSizes,
      ));
    }

    stage.addEventListener("pointerdown", pointerDown);
    stage.addEventListener("wheel", wheel, {passive: false});
    stage.addEventListener("keydown", keyDown);
    return Object.freeze({
      teardown() {
        finishSession();
        stage.removeEventListener("pointerdown", pointerDown);
        stage.removeEventListener("wheel", wheel);
        stage.removeEventListener("keydown", keyDown);
      },
    });
  }

  function exactParameters(value, fields, label) {
    const expected = new Set(fields);
    if (!hasExactFields(value, expected)) {
      throw new TypeError(`${label} parameters are invalid.`);
    }
    return value;
  }

  function validateEffectSpec(
    value,
    {frameLimit = 256, stillSource = false} = {},
  ) {
    const limit = boundedInteger(frameLimit, 2, 256, "Effect frame limit");
    if (!hasExactFields(value, EFFECT_FIELDS)) {
      throw new TypeError("The local effect schema is unsupported.");
    }
    if (value.version !== 1) {
      throw new RangeError("The local effect version is unsupported.");
    }
    if (typeof value.type !== "string") {
      throw new TypeError("The local effect type is invalid.");
    }
    const frameCount = boundedInteger(
      value.frame_count,
      2,
      limit,
      "Effect frame count",
    );
    const durationMs = boundedInteger(
      value.duration_ms,
      10,
      60_000,
      "Effect frame duration",
    );
    let parameters;
    if (value.type === "pulse") {
      const raw = exactParameters(
        value.parameters,
        ["minimum_brightness"],
        "Pulse",
      );
      parameters = {
        minimum_brightness: boundedNumber(
          raw.minimum_brightness,
          0,
          1,
          "Pulse minimum brightness",
        ),
      };
    } else if (value.type === "hue_cycle") {
      const raw = exactParameters(value.parameters, ["turns"], "Hue cycle");
      parameters = {
        turns: boundedNumber(raw.turns, 0.125, 4, "Hue cycle turns"),
      };
    } else if (value.type === "sweep") {
      const raw = exactParameters(
        value.parameters,
        ["direction", "width", "minimum_brightness"],
        "Sweep",
      );
      if (typeof raw.direction !== "string" || !DIRECTIONS.has(raw.direction)) {
        throw new RangeError("The Sweep direction is unsupported.");
      }
      parameters = {
        direction: raw.direction,
        width: boundedNumber(raw.width, 0.05, 2, "Sweep width"),
        minimum_brightness: boundedNumber(
          raw.minimum_brightness,
          0,
          1,
          "Sweep minimum brightness",
        ),
      };
    } else if (value.type === "shimmer") {
      const raw = exactParameters(value.parameters, ["depth", "seed"], "Shimmer");
      parameters = {
        depth: boundedNumber(raw.depth, 0, 1, "Shimmer depth"),
        seed: boundedInteger(raw.seed, 0, 0xFFFFFFFF, "Shimmer seed"),
      };
    } else if (value.type === "move_zoom") {
      if (stillSource !== true) {
        throw new RangeError("Move & zoom requires one imported still source.");
      }
      const raw = exactParameters(
        value.parameters,
        ["start_transform", "end_transform"],
        "Move & zoom",
      );
      const start = validateSourceTransform(raw.start_transform);
      const end = validateSourceTransform(raw.end_transform);
      if (
        start.aspect_locked !== end.aspect_locked
        || start.sampling !== end.sampling
        || start.background !== end.background
      ) {
        throw new RangeError("Move & zoom endpoints use incompatible transforms.");
      }
      parameters = {
        start_transform: start,
        end_transform: end,
      };
    } else {
      throw new RangeError("The local effect type is unsupported.");
    }
    return {
      version: 1,
      type: value.type,
      frame_count: frameCount,
      duration_ms: durationMs,
      parameters,
    };
  }

  function parseColor(value) {
    if (typeof value !== "string" || !RGB.test(value)) {
      throw new TypeError("A local effect source color is invalid.");
    }
    return [
      Number.parseInt(value.slice(1, 3), 16),
      Number.parseInt(value.slice(3, 5), 16),
      Number.parseInt(value.slice(5, 7), 16),
    ];
  }

  function hexColor(red, green, blue) {
    return `#${[red, green, blue]
      .map(channel => clamp(Math.round(channel), 0, 255).toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()}`;
  }

  function scaleColor(color, multiplier) {
    const [red, green, blue] = parseColor(color);
    return hexColor(red * multiplier, green * multiplier, blue * multiplier);
  }

  function rgbToHsv([redByte, greenByte, blueByte]) {
    const red = redByte / 255;
    const green = greenByte / 255;
    const blue = blueByte / 255;
    const maximum = Math.max(red, green, blue);
    const minimum = Math.min(red, green, blue);
    const delta = maximum - minimum;
    let hue = 0;
    if (delta > 0) {
      if (maximum === red) hue = ((green - blue) / delta) % 6;
      else if (maximum === green) hue = (blue - red) / delta + 2;
      else hue = (red - green) / delta + 4;
      hue /= 6;
      if (hue < 0) hue += 1;
    }
    return [hue, maximum === 0 ? 0 : delta / maximum, maximum];
  }

  function hsvToRgb([hueValue, saturation, value]) {
    const hue = ((hueValue % 1) + 1) % 1;
    const section = hue * 6;
    const index = Math.floor(section);
    const fraction = section - index;
    const low = value * (1 - saturation);
    const falling = value * (1 - fraction * saturation);
    const rising = value * (1 - (1 - fraction) * saturation);
    const channels = [
      [value, rising, low],
      [falling, value, low],
      [low, value, rising],
      [low, falling, value],
      [rising, low, value],
      [value, low, falling],
    ][index % 6];
    return channels.map(channel => channel * 255);
  }

  function hueColor(color, turns) {
    const hsv = rgbToHsv(parseColor(color));
    hsv[0] += turns;
    return hexColor(...hsvToRgb(hsv));
  }

  function noisePhase(seed, pixelIndex) {
    let value = (
      (seed >>> 0)
      ^ Math.imul((pixelIndex + 1) >>> 0, 0x9E3779B1)
    ) >>> 0;
    value ^= value >>> 16;
    value = Math.imul(value, 0x7FEB352D) >>> 0;
    value ^= value >>> 15;
    value = Math.imul(value, 0x846CA68B) >>> 0;
    value ^= value >>> 16;
    return (value / 0x100000000) * Math.PI * 2;
  }

  function validatedCoordinates(value, length) {
    if (!Array.isArray(value) || value.length !== length) {
      throw new TypeError("Sweep coordinates do not match the source frame.");
    }
    return value.map((coordinate, index) => {
      if (!coordinate || typeof coordinate !== "object" || Array.isArray(coordinate)) {
        throw new TypeError(`Sweep coordinate ${index + 1} is invalid.`);
      }
      return {
        x: boundedNumber(coordinate.x, 0, 1, `Sweep coordinate ${index + 1} x`),
        y: boundedNumber(coordinate.y, 0, 1, `Sweep coordinate ${index + 1} y`),
      };
    });
  }

  function sweepPosition(coordinate, direction) {
    if (direction === "left_to_right") return coordinate.x;
    if (direction === "right_to_left") return 1 - coordinate.x;
    if (direction === "top_to_bottom") return coordinate.y;
    if (direction === "bottom_to_top") return 1 - coordinate.y;
    return (coordinate.x + coordinate.y) / 2;
  }

  function renderColorEffect(sourceFrames, effect, coordinates = null) {
    const checked = validateEffectSpec(effect, {
      frameLimit: effect?.frame_count,
      stillSource: false,
    });
    if (checked.type === "move_zoom") {
      throw new RangeError("Move & zoom renders source transforms, not LED colors.");
    }
    if (!Array.isArray(sourceFrames) || sourceFrames.length === 0) {
      throw new TypeError("A local effect requires source frames.");
    }
    const pixelCount = Array.isArray(sourceFrames[0])
      ? sourceFrames[0].length
      : -1;
    if (pixelCount <= 0) {
      throw new TypeError("A local effect source frame is empty.");
    }
    const frames = sourceFrames.map((frame, frameIndex) => {
      if (!Array.isArray(frame) || frame.length !== pixelCount) {
        throw new TypeError(`Local effect source frame ${frameIndex + 1} is invalid.`);
      }
      return frame.map(color => {
        parseColor(color);
        return color.toUpperCase();
      });
    });
    const positions = checked.type === "sweep"
      ? validatedCoordinates(coordinates, pixelCount)
      : null;
    const output = [];
    for (let frameIndex = 0; frameIndex < checked.frame_count; frameIndex += 1) {
      const sourceIndex = Math.min(
        frames.length - 1,
        Math.floor(frameIndex * frames.length / checked.frame_count),
      );
      const source = frames[sourceIndex];
      if (checked.type === "pulse") {
        const phase = frameIndex / (checked.frame_count - 1);
        const wave = Math.sin(Math.PI * phase) ** 2;
        const minimum = checked.parameters.minimum_brightness;
        output.push(source.map(color => scaleColor(
          color,
          1 - (1 - minimum) * wave,
        )));
      } else if (checked.type === "hue_cycle") {
        const turns = (
          checked.parameters.turns
          * frameIndex
          / checked.frame_count
        );
        output.push(source.map(color => hueColor(color, turns)));
      } else if (checked.type === "sweep") {
        const width = checked.parameters.width;
        const progress = frameIndex / (checked.frame_count - 1);
        const center = -width + progress * (1 + width * 2);
        const minimum = checked.parameters.minimum_brightness;
        output.push(source.map((color, pixelIndex) => {
          const distance = Math.abs(
            sweepPosition(positions[pixelIndex], checked.parameters.direction)
            - center
          );
          const mask = clamp(1 - distance / width, 0, 1);
          return scaleColor(color, minimum + (1 - minimum) * mask);
        }));
      } else {
        const depth = checked.parameters.depth;
        const loopPhase = Math.PI * 2 * frameIndex / checked.frame_count;
        output.push(source.map((color, pixelIndex) => {
          const wave = 0.5 + 0.5 * Math.sin(
            loopPhase + noisePhase(checked.parameters.seed, pixelIndex),
          );
          return scaleColor(color, 1 - depth + depth * wave);
        }));
      }
    }
    return output;
  }

  function selectDemonstrativeEffectFrame(sourceFrame, effectFrames) {
    if (!Array.isArray(sourceFrame) || sourceFrame.length === 0) {
      throw new TypeError("A demonstrative effect frame needs source colors.");
    }
    const source = sourceFrame.map(color => parseColor(color));
    if (!Array.isArray(effectFrames) || effectFrames.length === 0) {
      throw new TypeError("A demonstrative effect frame needs rendered frames.");
    }
    let bestIndex = null;
    let bestDifference = 0;
    effectFrames.forEach((frame, frameIndex) => {
      if (!Array.isArray(frame) || frame.length !== source.length) {
        throw new TypeError("A rendered effect frame has the wrong number of colors.");
      }
      let difference = 0;
      frame.forEach((color, colorIndex) => {
        const channels = parseColor(color);
        for (let channel = 0; channel < 3; channel += 1) {
          difference += Math.abs(channels[channel] - source[colorIndex][channel]);
        }
      });
      if (difference > bestDifference) {
        bestDifference = difference;
        bestIndex = frameIndex;
      }
    });
    return bestIndex;
  }

  function interpolateMoveZoom(
    effect,
    sourceSize = undefined,
    destinationSizes = undefined,
  ) {
    const checked = validateEffectSpec(effect, {
      frameLimit: effect?.frame_count,
      stillSource: true,
    });
    if (checked.type !== "move_zoom") {
      throw new RangeError("Only Move & zoom produces transform keyframes.");
    }
    const start = checked.parameters.start_transform;
    const end = checked.parameters.end_transform;
    const result = [];
    for (let index = 0; index < checked.frame_count; index += 1) {
      const progress = index / (checked.frame_count - 1);
      result.push(canonicalizeWhenSized({
        ...start,
        offset_x: start.offset_x + (end.offset_x - start.offset_x) * progress,
        offset_y: start.offset_y + (end.offset_y - start.offset_y) * progress,
        scale_x: start.scale_x + (end.scale_x - start.scale_x) * progress,
        scale_y: start.scale_y + (end.scale_y - start.scale_y) * progress,
      }, sourceSize, destinationSizes));
    }
    return result;
  }

  return Object.freeze({
    canonicalizeSourceTransform,
    createLatestTaskScheduler,
    defaultSourceTransform,
    interpolateMoveZoom,
    normalizedPointer,
    panSourceTransform,
    presetSourceTransform,
    renderColorEffect,
    resolveSourceGeometry,
    scaleSourceTransform,
    selectDemonstrativeEffectFrame,
    validateEffectSpec,
    validateSourceTransform,
    wireSourceTransformStage,
  });
});
