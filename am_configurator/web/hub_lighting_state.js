(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HubLightingState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SURFACE_FIELDS = new Set(["effect_id", "brightness", "speed", "color"]);
  const RGB = /^#[0-9A-F]{6}$/;
  const MAX_PIXELS = 1024;
  const MAX_ANIMATIONS = 64;
  const MAX_FRAMES = 1024;

  function plainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    if (!plainObject(value)) return value;
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, clone(child)]),
    );
  }

  function freeze(value) {
    if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
    for (const child of Object.values(value)) freeze(child);
    return Object.freeze(value);
  }

  function integer(value, label) {
    if (!Number.isSafeInteger(value) || typeof value === "boolean") {
      throw new TypeError(`${label} must be an integer.`);
    }
    return value;
  }

  function boundedInteger(value, range, label) {
    const number = integer(value, label);
    if (number < range.min || number > range.max) {
      throw new RangeError(`${label} is outside the proved range.`);
    }
    return number;
  }

  function range(value, label) {
    if (!plainObject(value)) throw new TypeError(`${label} range is invalid.`);
    const minimum = integer(value.min, `${label} minimum`);
    const maximum = integer(value.max, `${label} maximum`);
    if (minimum > maximum) throw new RangeError(`${label} range is invalid.`);
    return freeze({min: minimum, max: maximum});
  }

  function colorDescriptor(value, label) {
    if (!plainObject(value) || !["hsv", "rgb"].includes(value.space)) {
      throw new TypeError(`${label} color capability is invalid.`);
    }
    if (!Array.isArray(value.channels) || !value.channels.length || value.channels.length > 3) {
      throw new TypeError(`${label} color channels are invalid.`);
    }
    return freeze({
      space: value.space,
      channels: freeze(value.channels.map((channel, index) => (
        range(channel, `${label} color channel ${index + 1}`)
      ))),
    });
  }

  function lightingCapabilities(profile) {
    if (!plainObject(profile) || profile.schema_version !== 2 || !plainObject(profile.identity)) {
      throw new TypeError("The schema-v2 hub profile is invalid.");
    }
    const source = profile.capabilities?.lighting?.surfaces;
    if (source === undefined) return freeze([]);
    if (!Array.isArray(source)) throw new TypeError("Hub lighting capabilities are invalid.");
    const ids = new Set();
    return freeze(source.map((surface, surfaceIndex) => {
      const label = `Lighting surface ${surfaceIndex + 1}`;
      if (!plainObject(surface) || typeof surface.id !== "string" || !surface.id) {
        throw new TypeError(`${label} identity is invalid.`);
      }
      if (ids.has(surface.id)) throw new TypeError(`${label} identity is repeated.`);
      ids.add(surface.id);
      const result = {
        id: surface.id,
        role: String(surface.role || ""),
        generation: String(surface.generation || ""),
      };
      if (surface.effects !== undefined) {
        if (!Array.isArray(surface.effects)) throw new TypeError(`${label} effects are invalid.`);
        const effectIds = new Set();
        result.effects = freeze(surface.effects.map((effect) => {
          if (!plainObject(effect)) throw new TypeError(`${label} effect is invalid.`);
          const id = integer(effect.id, `${label} effect id`);
          if (effectIds.has(id)) throw new TypeError(`${label} effect id is repeated.`);
          effectIds.add(id);
          return freeze({id, ...(effect.semantic ? {semantic: String(effect.semantic)} : {})});
        }));
      }
      for (const field of ["brightness", "speed"]) {
        if (surface[field] !== undefined) result[field] = range(surface[field], `${label} ${field}`);
      }
      if (surface.color !== undefined) {
        result.color = colorDescriptor(surface.color, label);
      }
      if (surface.per_key !== undefined) {
        if (!plainObject(surface.per_key)) throw new TypeError(`${label} per-key capability is invalid.`);
        const pixelCount = integer(surface.per_key.pixel_count, `${label} pixel count`);
        if (pixelCount <= 0) throw new RangeError(`${label} pixel count is invalid.`);
        result.per_key = {
          pixel_count: pixelCount,
          ...(surface.per_key.color
            ? {color: colorDescriptor(surface.per_key.color, `${label} per-key`)}
            : {}),
        };
      }
      if (surface.stream !== undefined) result.stream = clone(surface.stream);
      return freeze(result);
    }));
  }

  function lightingStateMap(profile) {
    const surfaces = profile.lighting?.surfaces;
    if (surfaces === undefined) return new Map();
    if (!Array.isArray(surfaces)) throw new TypeError("Hub lighting state is invalid.");
    return new Map(surfaces.map((surface) => {
      if (!plainObject(surface) || typeof surface.id !== "string" || !surface.id) {
        throw new TypeError("A hub lighting surface state is invalid.");
      }
      return [surface.id, surface];
    }));
  }

  function validatedGeometry(value) {
    if (!Array.isArray(value)) throw new TypeError("Hub lighting geometry is invalid.");
    if (value.length > MAX_PIXELS) throw new RangeError("Hub lighting geometry is too large.");
    const identities = new Set();
    const ledIndexes = new Set();
    return freeze(value.map((item) => {
      const identity = `${item?.surface_id}\0${item?.pixel_id}`;
      const ledIdentity = `${item?.surface_id}\0${item?.led_index}`;
      if (
        !plainObject(item)
        || typeof item.surface_id !== "string"
        || !item.surface_id
        || typeof item.pixel_id !== "string"
        || !item.pixel_id
        || identities.has(identity)
        || ledIndexes.has(ledIdentity)
        || !Number.isSafeInteger(item.led_index)
        || item.led_index < 0
        || item.led_index > 255
        || typeof item.x !== "number"
        || !Number.isFinite(item.x)
        || typeof item.y !== "number"
        || !Number.isFinite(item.y)
      ) {
        throw new TypeError("A hub lighting geometry item is invalid.");
      }
      identities.add(identity);
      ledIndexes.add(ledIdentity);
      return freeze(clone(item));
    }));
  }

  function evidenceFor(profile, surface, pixels) {
    if (!pixels.length) return null;
    if (profile.identity.ecosystem === "via") return "user_imported_definition";
    if (
      profile.identity.ecosystem === "vial"
      && surface.generation === "vialrgb"
    ) return "device_proven_vialrgb";
    return "device_proven";
  }

  function createHubLightingState({profile, geometry = [], targetCurrent = false}) {
    const capabilities = lightingCapabilities(profile);
    const states = lightingStateMap(profile);
    const checkedGeometry = validatedGeometry(geometry);
    const surfaces = capabilities.map((capability) => {
      const pixels = targetCurrent
        ? checkedGeometry.filter(item => item.surface_id === capability.id)
        : freeze([]);
      const state = freeze(clone(states.get(capability.id) || {id: capability.id}));
      const canPaint = Boolean(
        capability.per_key
        && pixels.length === capability.per_key.pixel_count,
      );
      const canAnimate = Boolean(
        capability.stream
        && pixels.length === capability.stream.pixel_count,
      );
      const hasPersistentEffect = Boolean(
        capability.effects?.some(effect => !(
          capability.generation === "vialrgb" && effect.id === 1
        )),
      );
      return freeze({
        id: capability.id,
        role: capability.role,
        generation: capability.generation,
        capability,
        state,
        controls: freeze({
          effect: hasPersistentEffect,
          brightness: Boolean(capability.brightness),
          speed: Boolean(capability.speed),
          color: Boolean(capability.color),
          perKey: canPaint,
          animation: canAnimate,
        }),
        pixels,
        evidence: evidenceFor(profile, capability, pixels),
      });
    });
    return freeze({
      available: surfaces.length > 0,
      targetCurrent: Boolean(targetCurrent),
      surfaces: freeze(surfaces),
    });
  }

  function surfaceCapability(profile, surfaceId) {
    if (typeof surfaceId !== "string" || !surfaceId) {
      throw new TypeError("The lighting surface identity is invalid.");
    }
    const capability = lightingCapabilities(profile).find(surface => surface.id === surfaceId);
    if (!capability) throw new RangeError(`Lighting surface ${surfaceId} is not exposed.`);
    return capability;
  }

  function validateColor(value, descriptor, label) {
    if (!Array.isArray(value) || value.length !== descriptor.channels.length) {
      throw new TypeError(`${label} does not match the proved color channels.`);
    }
    return value.map((channel, index) => (
      boundedInteger(channel, descriptor.channels[index], `${label} channel ${index + 1}`)
    ));
  }

  function mutableSurface(profile, surfaceId) {
    if (!plainObject(profile.lighting)) profile.lighting = {};
    if (!Array.isArray(profile.lighting.surfaces)) profile.lighting.surfaces = [];
    let surface = profile.lighting.surfaces.find(item => item?.id === surfaceId);
    if (!surface) {
      surface = {id: surfaceId};
      profile.lighting.surfaces.push(surface);
    }
    return surface;
  }

  function setSurfaceField(profile, action) {
    const capability = surfaceCapability(profile, action.surfaceId);
    if (!SURFACE_FIELDS.has(action.field)) {
      throw new RangeError(`Unknown hub lighting control ${action.field}.`);
    }
    const surface = mutableSurface(profile, capability.id);
    if (action.field === "effect_id") {
      if (!capability.effects) throw new RangeError("This surface does not expose effect.");
      const effectId = integer(action.value, "Lighting effect id");
      if (!capability.effects.some(effect => effect.id === effectId)) {
        throw new RangeError("The lighting effect is not exposed by this surface.");
      }
      surface.effect_id = effectId;
      return;
    }
    if (action.field === "color") {
      if (!capability.color) throw new RangeError("This surface does not expose color.");
      surface.color = validateColor(action.value, capability.color, "Lighting color");
      return;
    }
    const descriptor = capability[action.field];
    if (!descriptor) throw new RangeError(`This surface does not expose ${action.field}.`);
    surface[action.field] = boundedInteger(
      action.value,
      descriptor,
      `Lighting ${action.field}`,
    );
  }

  function setPixelColor(profile, action, context) {
    const capability = surfaceCapability(profile, action.surfaceId);
    if (!capability.per_key) throw new RangeError("This surface does not expose per-key color.");
    if (context.targetCurrent !== true) {
      throw new RangeError("Read the target again before editing per-key lighting.");
    }
    const geometry = validatedGeometry(context.geometry || []);
    const surfaceGeometry = geometry.filter(item => item.surface_id === capability.id);
    if (surfaceGeometry.length !== capability.per_key.pixel_count) {
      throw new RangeError("The current geometry does not prove every per-key pixel.");
    }
    const proved = surfaceGeometry.some(item => (
      item.surface_id === capability.id && item.pixel_id === action.pixelId
    ));
    if (!proved) throw new RangeError("The pixel identity is absent from current geometry.");
    const descriptor = capability.per_key.color || capability.color;
    if (!descriptor) throw new RangeError("This surface exposes no per-key color channels.");
    const surface = mutableSurface(profile, capability.id);
    if (!plainObject(surface.per_key)) surface.per_key = {};
    surface.per_key[action.pixelId] = validateColor(
      action.value,
      descriptor,
      `Pixel ${action.pixelId} color`,
    );
  }

  function setAnimation(profile, action, context) {
    const capability = surfaceCapability(profile, action.surfaceId);
    if (!capability.stream) throw new RangeError("This surface does not expose animation streaming.");
    if (context.targetCurrent !== true) {
      throw new RangeError("Read the target again before editing an animation.");
    }
    if (typeof action.name !== "string" || !action.name || action.name.length > 128) {
      throw new TypeError("The animation name is invalid.");
    }
    const geometry = validatedGeometry(context.geometry || []).filter(
      item => item.surface_id === capability.id,
    );
    if (geometry.length !== capability.stream.pixel_count) {
      throw new RangeError("The current geometry does not prove every streamed pixel.");
    }
    const provedIds = geometry.map(item => item.pixel_id);
    if (
      !Array.isArray(action.pixelIds)
      || action.pixelIds.length !== provedIds.length
      || action.pixelIds.some((pixelId, index) => pixelId !== provedIds[index])
    ) {
      throw new RangeError("The animation pixel identities do not match current geometry.");
    }
    if (!Array.isArray(action.frames) || !action.frames.length) {
      throw new TypeError("The animation has no frames.");
    }
    if (action.frames.length > MAX_FRAMES) {
      throw new RangeError("The animation has too many frames.");
    }
    const frames = action.frames.map((frame) => {
      if (!Array.isArray(frame) || frame.length !== provedIds.length) {
        throw new TypeError("An animation frame has the wrong pixel count.");
      }
      return frame.map((color) => {
        if (typeof color !== "string" || !RGB.test(color)) {
          throw new TypeError("An animation color must be uppercase #RRGGBB.");
        }
        return color;
      });
    });
    const animation = {
      name: action.name,
      surface_id: capability.id,
      pixel_ids: [...action.pixelIds],
      frames,
      placement: "geometry_seam",
    };
    if (action.frameMs !== undefined) {
      animation.frame_ms = boundedInteger(
        action.frameMs,
        {min: 1, max: 65535},
        "Animation frame time",
      );
    }
    if (action.brightness !== undefined) {
      animation.brightness = boundedInteger(
        action.brightness,
        {min: 0, max: 100},
        "Animation brightness",
      );
    }
    if (!plainObject(profile.lighting)) profile.lighting = {};
    const existing = Array.isArray(profile.lighting.animations)
      ? profile.lighting.animations
      : [];
    const replacing = existing.some(item => (
      item?.surface_id === capability.id && item?.name === action.name
    ));
    if (!replacing && existing.length >= MAX_ANIMATIONS) {
      throw new RangeError("The profile has too many lighting animations.");
    }
    profile.lighting.animations = [
      ...existing.filter(item => !(
        item?.surface_id === capability.id && item?.name === action.name
      )),
      animation,
    ];
  }

  function reduceHubLightingProfile(source, action, context = {}) {
    lightingCapabilities(source);
    if (!plainObject(action) || typeof action.type !== "string") {
      throw new TypeError("The hub lighting transition is invalid.");
    }
    const profile = clone(source);
    if (action.type === "SET_SURFACE_FIELD") setSurfaceField(profile, action);
    else if (action.type === "SET_PIXEL_COLOR") setPixelColor(profile, action, context);
    else if (action.type === "SET_ANIMATION") setAnimation(profile, action, context);
    else throw new RangeError(`Unknown hub lighting transition ${action.type}.`);
    return freeze(profile);
  }

  function createHubStreamState() {
    return freeze({
      phase: "idle",
      token: null,
      confirmation: null,
      animationIndex: null,
      status: null,
      error: null,
    });
  }

  function reduceHubStreamState(source, event) {
    if (!plainObject(source) || !plainObject(event) || typeof event.type !== "string") {
      throw new TypeError("The volatile preview transition is invalid.");
    }
    if (event.type === "RESET") return createHubStreamState();
    if (event.type === "PREFLIGHT_SUCCEEDED") {
      if (
        typeof event.token !== "string"
        || !event.token
        || typeof event.confirmation !== "string"
        || !event.confirmation
        || !Number.isSafeInteger(event.animationIndex)
      ) {
        throw new TypeError("The volatile preview preflight is invalid.");
      }
      return freeze({
        phase: "ready",
        token: event.token,
        confirmation: event.confirmation,
        animationIndex: event.animationIndex,
        status: clone(event.status || {state: "ready"}),
        error: null,
      });
    }
    if (event.type === "START_REQUESTED") {
      if (source.phase !== "ready") throw new RangeError("Preview is not ready to start.");
      return freeze({...clone(source), phase: "starting", error: null});
    }
    if (event.type === "STOP_REQUESTED") {
      if (!["starting", "running"].includes(source.phase)) {
        throw new RangeError("Preview is not running.");
      }
      return freeze({...clone(source), phase: "stopping"});
    }
    if (event.type === "STATUS_RECEIVED") {
      if (event.token !== source.token) return source;
      if (!plainObject(event.status) || typeof event.status.state !== "string") {
        throw new TypeError("The volatile preview status is invalid.");
      }
      const phase = ["ready", "starting", "running", "stopping", "completed", "stopped", "cancelled", "error"].includes(event.status.state)
        ? event.status.state
        : "error";
      return freeze({
        ...clone(source),
        phase,
        status: clone(event.status),
        error: phase === "error" ? String(event.status.error || "Preview failed.") : null,
      });
    }
    if (event.type === "FAILED") {
      return freeze({...clone(source), phase: "error", error: String(event.error || "Preview failed.")});
    }
    throw new RangeError(`Unknown volatile preview transition ${event.type}.`);
  }

  return Object.freeze({
    createHubLightingState,
    createHubStreamState,
    reduceHubLightingProfile,
    reduceHubStreamState,
  });
});
