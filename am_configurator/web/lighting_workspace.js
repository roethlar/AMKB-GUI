(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.LightingWorkspace = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  const RGB_COLOR = /^#[0-9A-F]{6}$/i;
  const TARGET_NAME = /^[a-z][a-z0-9_]*$/;
  const PROVENANCE = new Set([
    "document",
    "local_effect",
    "media_render",
    "procedural_result",
  ]);
  const validatedFrameSets = new WeakSet();

  class LightingWorkspaceError extends Error {
    constructor(code, message) {
      super(message);
      this.name = "LightingWorkspaceError";
      this.code = code;
    }
  }

  function fail(code, message) {
    throw new LightingWorkspaceError(code, message);
  }

  function isObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function safeNonNegativeInteger(value, code, message) {
    if (!Number.isSafeInteger(value) || value < 0) fail(code, message);
    return value;
  }

  function safePositiveInteger(value, code, message) {
    if (!Number.isSafeInteger(value) || value <= 0) fail(code, message);
    return value;
  }

  function safeTarget(value) {
    if (typeof value !== "string" || !TARGET_NAME.test(value)) {
      fail("invalid_target", "The lighting target is invalid.");
    }
    return value;
  }

  function safePreviewSessionId(value) {
    if (
      typeof value !== "string"
      || value.length < 32
      || value.length > 200
      || !/^[A-Za-z0-9_-]+$/.test(value)
    ) fail("invalid_context", "The media preview session is invalid.");
    return value;
  }

  function normalizeTargetLengths(value) {
    if (!isObject(value) || !Object.keys(value).length) {
      fail("invalid_target", "Target sizes are unavailable.");
    }
    const normalized = {};
    for (const [target, length] of Object.entries(value)) {
      normalized[safeTarget(target)] = safePositiveInteger(
        length,
        "invalid_target",
        "A target size is invalid.",
      );
    }
    return normalized;
  }

  function normalizeAllowedDurations(value) {
    if (!Array.isArray(value) || !value.length) {
      fail("invalid_duration", "Firmware timing information is unavailable.");
    }
    const normalized = new Set();
    for (const duration of value) {
      normalized.add(safePositiveInteger(
        duration,
        "invalid_duration",
        "A firmware timing value is invalid.",
      ));
    }
    return normalized;
  }

  function normalizeRevision(value) {
    if (Number.isSafeInteger(value) && value >= 0) return value;
    if (typeof value === "string" && value.length && value.length <= 512) return value;
    fail("invalid_context", "The lighting revision is invalid.");
  }

  function normalizeContext(value) {
    if (!isObject(value)) fail("invalid_context", "Lighting context is unavailable.");
    const sourceKind = value.source_kind;
    if (!PROVENANCE.has(sourceKind)) {
      fail("invalid_context", "The lighting source is invalid.");
    }
    return Object.freeze({
      document_epoch: safeNonNegativeInteger(
        value.document_epoch,
        "invalid_context",
        "The document context is invalid.",
      ),
      slot: safeNonNegativeInteger(
        value.slot,
        "invalid_context",
        "The lighting slot is invalid.",
      ),
      target: safeTarget(value.target),
      source_kind: sourceKind,
      revision: normalizeRevision(value.revision),
    });
  }

  function normalizeTimeline(value, frameCount) {
    if (!Array.isArray(value) || value.length !== frameCount) {
      fail("invalid_frame", "The lighting timeline does not match its frames.");
    }
    return Object.freeze(value.map((entry, index) => {
      if (!isObject(entry) || entry.index !== index) {
        fail("invalid_frame", "A lighting timeline entry is invalid.");
      }
      const normalized = {index};
      if (entry.source_frame_index !== undefined) {
        normalized.source_frame_index = safeNonNegativeInteger(
          entry.source_frame_index,
          "invalid_frame",
          "A source frame reference is invalid.",
        );
      }
      if (entry.label !== undefined) {
        if (typeof entry.label !== "string" || entry.label.length > 160) {
          fail("invalid_frame", "A frame label is invalid.");
        }
        normalized.label = entry.label;
      }
      return Object.freeze(normalized);
    }));
  }

  function createBoardFrameSet(value, options = {}) {
    if (!isObject(value)) fail("invalid_shape", "Lighting preview data is unavailable.");
    const targetLengths = normalizeTargetLengths(options.targetLengths);
    const allowedDurations = normalizeAllowedDurations(options.allowedDurations);
    const context = normalizeContext(value.context);
    const frameCount = safePositiveInteger(
      value.frame_count,
      "invalid_frame",
      "The lighting frame count is invalid.",
    );
    const maxFrames = options.maxFrames === undefined
      ? 256
      : safePositiveInteger(options.maxFrames, "invalid_frame", "The frame limit is invalid.");
    if (frameCount > maxFrames) fail("invalid_frame", "The lighting has too many frames.");
    if (!allowedDurations.has(value.duration_ms)) {
      fail("invalid_duration", "The lighting timing is not supported by this keyboard.");
    }
    if (!PROVENANCE.has(value.provenance) || value.provenance !== context.source_kind) {
      fail("invalid_context", "The lighting source does not match its context.");
    }
    if (!isObject(value.frames_by_target) || !Object.keys(value.frames_by_target).length) {
      fail("invalid_frame", "The lighting contains no target frames.");
    }

    const framesByTarget = {};
    for (const [rawTarget, rawFrames] of Object.entries(value.frames_by_target)) {
      const target = safeTarget(rawTarget);
      const expectedLength = targetLengths[target];
      if (!expectedLength) fail("invalid_target", "The lighting targets an unsupported keyboard area.");
      if (!Array.isArray(rawFrames) || rawFrames.length !== frameCount) {
        fail("invalid_frame", "A lighting target has the wrong number of frames.");
      }
      framesByTarget[target] = Object.freeze(rawFrames.map(rawFrame => {
        if (!Array.isArray(rawFrame) || rawFrame.length !== expectedLength) {
          fail("invalid_frame", "A lighting frame has the wrong number of colors.");
        }
        const frame = rawFrame.map(color => {
          if (typeof color !== "string" || !RGB_COLOR.test(color)) {
            fail("invalid_color", "A lighting frame contains an invalid color.");
          }
          return color.toUpperCase();
        });
        return Object.freeze(frame);
      }));
    }
    if (!framesByTarget[context.target]) {
      fail("invalid_target", "The selected keyboard area has no lighting frames.");
    }

    const result = Object.freeze({
      context,
      frames_by_target: Object.freeze(framesByTarget),
      frame_count: frameCount,
      duration_ms: value.duration_ms,
      timeline: normalizeTimeline(value.timeline, frameCount),
      provenance: value.provenance,
    });
    validatedFrameSets.add(result);
    return result;
  }

  function defaultTimeline(frameCount) {
    return Array.from({length: frameCount}, (_, index) => ({index}));
  }

  function frameColors(value) {
    if (Array.isArray(value)) return value;
    if (isObject(value) && Array.isArray(value.frame_RGB)) return value.frame_RGB;
    fail("invalid_frame", "A lighting frame is unavailable.");
  }

  function boardFrameSetFromDocument({
    context,
    track,
    durationMs,
    targetLengths,
    allowedDurations,
    maxFrames,
  }) {
    if (!isObject(track) || !Array.isArray(track.frame_data) || !track.frame_data.length) {
      fail("invalid_frame", "The document track contains no frames.");
    }
    return createBoardFrameSet({
      context,
      frames_by_target: {
        [context.target]: track.frame_data.map(frameColors),
      },
      frame_count: track.frame_data.length,
      duration_ms: durationMs,
      timeline: defaultTimeline(track.frame_data.length),
      provenance: "document",
    }, {targetLengths, allowedDurations, maxFrames});
  }

  function boardFrameSetFromLocalEffect({
    context,
    draft,
    targetLengths,
    allowedDurations,
    maxFrames,
  }) {
    if (!isObject(draft) || !Array.isArray(draft.frames) || !draft.frames.length) {
      fail("invalid_frame", "The effect preview contains no frames.");
    }
    return createBoardFrameSet({
      context,
      frames_by_target: {
        [context.target]: draft.frames.map(frameColors),
      },
      frame_count: draft.frames.length,
      duration_ms: draft.effect?.duration_ms,
      timeline: defaultTimeline(draft.frames.length),
      provenance: "local_effect",
    }, {targetLengths, allowedDurations, maxFrames});
  }

  function boardFrameSetFromMappedResult({
    context,
    mappedResult,
    timeline = null,
    provenance,
    targetLengths,
    allowedDurations,
    maxFrames,
  }) {
    if (!isObject(mappedResult) || !isObject(mappedResult.tracks)) {
      fail("invalid_shape", "The rendered lighting result is unavailable.");
    }
    if (!new Set(["media_render", "procedural_result"]).has(provenance)) {
      fail("invalid_context", "The rendered lighting source is invalid.");
    }
    const framesByTarget = {};
    let frameCount = null;
    for (const [target, track] of Object.entries(mappedResult.tracks)) {
      if (!isObject(track) || !Array.isArray(track.frames) || !track.frames.length) {
        fail("invalid_frame", "A rendered lighting track contains no frames.");
      }
      if (track.frame_count !== track.frames.length) {
        fail("invalid_frame", "A rendered lighting track has an invalid frame count.");
      }
      if (frameCount === null) frameCount = track.frames.length;
      if (track.frames.length !== frameCount) {
        fail("invalid_frame", "Rendered lighting tracks do not share one timeline.");
      }
      framesByTarget[target] = track.frames.map(frameColors);
    }
    if (frameCount === null) fail("invalid_frame", "The rendered lighting contains no frames.");
    return createBoardFrameSet({
      context,
      frames_by_target: framesByTarget,
      frame_count: frameCount,
      duration_ms: mappedResult.duration_ms,
      timeline: timeline === null ? defaultTimeline(frameCount) : timeline,
      provenance,
    }, {targetLengths, allowedDurations, maxFrames});
  }

  function boardFrameSetFromMappedFrame({
    context,
    mappedFrame,
    timelineEntry,
    targetLengths,
    allowedDurations,
  }) {
    if (!isObject(mappedFrame) || !isObject(mappedFrame.tracks)) {
      fail("invalid_shape", "The rendered lighting frame is unavailable.");
    }
    if (!isObject(timelineEntry)) {
      fail("invalid_frame", "The rendered lighting timeline entry is unavailable.");
    }
    safeNonNegativeInteger(
      timelineEntry.index,
      "invalid_frame",
      "The rendered lighting frame index is invalid.",
    );
    const sourceFrameIndex = safeNonNegativeInteger(
      timelineEntry.source_frame_index,
      "invalid_frame",
      "The rendered lighting source frame is invalid.",
    );
    const durationMs = safePositiveInteger(
      timelineEntry.duration_ms,
      "invalid_duration",
      "The rendered lighting timing is invalid.",
    );
    const framesByTarget = {};
    for (const [target, track] of Object.entries(mappedFrame.tracks)) {
      if (!isObject(track) || !Array.isArray(track.colors)) {
        fail("invalid_frame", "A rendered lighting target frame is unavailable.");
      }
      framesByTarget[target] = [track.colors];
    }
    return createBoardFrameSet({
      context,
      frames_by_target: framesByTarget,
      frame_count: 1,
      duration_ms: durationMs,
      timeline: [{index: 0, source_frame_index: sourceFrameIndex}],
      provenance: "media_render",
    }, {targetLengths, allowedDurations, maxFrames: 1});
  }

  function projectBoardFrame(frameSet, target, index, options = {}) {
    const checked = validatedFrameSets.has(frameSet)
      ? frameSet
      : createBoardFrameSet(frameSet, options);
    const checkedTarget = safeTarget(target);
    const frames = checked.frames_by_target[checkedTarget];
    if (!frames) fail("invalid_target", "The selected keyboard area has no lighting frames.");
    if (!Number.isSafeInteger(index) || index < 0 || index >= checked.frame_count) {
      fail("invalid_frame", "The selected lighting frame is unavailable.");
    }
    return frames[index];
  }

  const ERROR_MESSAGES = Object.freeze({
    invalid_target: "This lighting does not match the selected keyboard area.",
    invalid_color: "One or more light colors are invalid. Create the preview again.",
    invalid_frame: "This lighting preview is incomplete. Create the preview again.",
    invalid_shape: "This lighting preview could not be read. Create it again.",
    invalid_duration: "This animation speed is not supported by the selected keyboard.",
    no_preview: "There is no finished lighting preview to use yet.",
    render_failed: "The lighting preview could not be updated. Try again.",
  });

  function friendlyWorkspaceError(error, revision = 0) {
    const code = typeof error?.code === "string" && ERROR_MESSAGES[error.code]
      ? error.code
      : "render_failed";
    return Object.freeze({
      key: `${revision}:${code}`,
      code,
      title: "Could not update lights",
      message: ERROR_MESSAGES[code],
    });
  }

  function workspaceContextKey(value, revision) {
    const context = value?.context || value;
    if (!isObject(context)) fail("invalid_context", "Lighting context is unavailable.");
    const contextEpoch = safeNonNegativeInteger(
      value?.context_epoch ?? context.context_epoch ?? 0,
      "invalid_context",
      "The lighting context generation is invalid.",
    );
    const acceptedRevision = revision === undefined
      ? value?.preview?.accepted_epoch ?? context.revision ?? 0
      : revision;
    return JSON.stringify([
      safeNonNegativeInteger(
        context.document_epoch,
        "invalid_context",
        "The document context is invalid.",
      ),
      safeNonNegativeInteger(context.slot, "invalid_context", "The lighting slot is invalid."),
      safeTarget(context.target),
      contextEpoch,
      normalizeRevision(acceptedRevision),
    ]);
  }

  function workspaceDestinationKey(value) {
    const context = value?.context || value;
    if (!isObject(context)) fail("invalid_context", "Lighting context is unavailable.");
    return JSON.stringify([
      safeNonNegativeInteger(
        context.document_epoch,
        "invalid_context",
        "The document context is invalid.",
      ),
      safeNonNegativeInteger(context.slot, "invalid_context", "The lighting slot is invalid."),
      safeTarget(context.target),
    ]);
  }

  function captureWorkspaceAsyncContext(state) {
    if (!isObject(state)) fail("invalid_context", "Lighting context is unavailable.");
    return Object.freeze({
      context_epoch: safeNonNegativeInteger(
        state.context_epoch,
        "invalid_context",
        "The lighting context generation is invalid.",
      ),
      destination_key: workspaceDestinationKey(state),
    });
  }

  function workspaceAsyncContextMatches(state, captured) {
    return Boolean(
      isObject(state)
      && isObject(captured)
      && state.context_epoch === captured.context_epoch
      && workspaceDestinationKey(state) === captured.destination_key
    );
  }

  function initialPreview(context, contextEpoch = 0) {
    return {
      status: "idle",
      request_epoch: 0,
      accepted_epoch: 0,
      context_key: workspaceContextKey({context, context_epoch: contextEpoch}, 0),
      request_context_key: null,
      board_frame_set: null,
      selected_frame: null,
      timeline: [],
      error: null,
    };
  }

  function createLightingWorkspace({
    documentEpoch = 0,
    slot = 5,
    target = "keyframes",
    tool = "paint",
    route = "lighting/edit",
  } = {}) {
    const context = {
      document_epoch: safeNonNegativeInteger(
        documentEpoch,
        "invalid_context",
        "The document context is invalid.",
      ),
      slot: safeNonNegativeInteger(slot, "invalid_context", "The lighting slot is invalid."),
      target: safeTarget(target),
    };
    if (typeof tool !== "string" || !tool.length) fail("invalid_context", "The tool is invalid.");
    if (typeof route !== "string" || !route.length) fail("invalid_context", "The route is invalid.");
    return {
      context,
      context_epoch: 0,
      route,
      tool,
      playhead: {index: 0, playing: false, session_id: 0},
      destination_playheads: {[workspaceDestinationKey(context)]: 0},
      media: null,
      preview: initialPreview(context, 0),
      effect_draft: null,
    };
  }

  function unchanged(state, ignored) {
    return {state, intents: [], ...(ignored ? {ignored} : {})};
  }

  function cancelPlaybackIntent(state) {
    return {
      type: "cancel-playback",
      session_id: state.playhead.session_id,
      context_key: workspaceContextKey(state),
    };
  }

  function stopPlayhead(state, index = state.playhead.index) {
    return {
      index,
      playing: false,
      session_id: state.playhead.session_id + 1,
    };
  }

  function contextTransition(state, nextContext, extra = {}) {
    const oldKey = workspaceDestinationKey(state.context);
    const nextKey = workspaceDestinationKey(nextContext);
    const contextEpoch = state.context_epoch + 1;
    const destinationPlayheads = {
      ...state.destination_playheads,
      [oldKey]: state.playhead.index,
    };
    const remembered = extra.playheadIndex === undefined
      ? destinationPlayheads[nextKey] ?? 0
      : safeNonNegativeInteger(
        extra.playheadIndex,
        "invalid_frame",
        "The selected lighting frame is invalid.",
      );
    destinationPlayheads[nextKey] = remembered;
    return {
      ...state,
      ...extra.state,
      context: nextContext,
      context_epoch: contextEpoch,
      playhead: stopPlayhead(state, remembered),
      destination_playheads: destinationPlayheads,
      preview: initialPreview(nextContext, contextEpoch),
      effect_draft: extra.clearEffect === false ? state.effect_draft : null,
    };
  }

  function frameSetEqual(left, right) {
    if (!left || !right) return false;
    if (
      left.frame_count !== right.frame_count
      || left.duration_ms !== right.duration_ms
      || left.provenance !== right.provenance
      || left.context.document_epoch !== right.context.document_epoch
      || left.context.slot !== right.context.slot
      || left.context.target !== right.context.target
      || left.context.source_kind !== right.context.source_kind
      || JSON.stringify(left.timeline) !== JSON.stringify(right.timeline)
    ) return false;
    const leftTargets = Object.keys(left.frames_by_target).sort();
    const rightTargets = Object.keys(right.frames_by_target).sort();
    if (leftTargets.length !== rightTargets.length) return false;
    for (let targetIndex = 0; targetIndex < leftTargets.length; targetIndex++) {
      const target = leftTargets[targetIndex];
      if (target !== rightTargets[targetIndex]) return false;
      const leftFrames = left.frames_by_target[target];
      const rightFrames = right.frames_by_target[target];
      for (let frameIndex = 0; frameIndex < leftFrames.length; frameIndex++) {
        const leftFrame = leftFrames[frameIndex];
        const rightFrame = rightFrames[frameIndex];
        for (let colorIndex = 0; colorIndex < leftFrame.length; colorIndex++) {
          if (leftFrame[colorIndex] !== rightFrame[colorIndex]) return false;
        }
      }
    }
    return true;
  }

  function acceptFrameSet(state, event) {
    const checked = createBoardFrameSet(event.frame_set, {
      targetLengths: event.target_lengths,
      allowedDurations: event.allowed_durations,
      maxFrames: event.max_frames,
    });
    if (
      checked.context.document_epoch !== state.context.document_epoch
      || checked.context.slot !== state.context.slot
      || checked.context.target !== state.context.target
    ) return unchanged(state, "stale");
    const mediaRevision = checked.provenance === "media_render"
      ? safeNonNegativeInteger(
        event.media_revision ?? state.media?.requested_revision,
        "invalid_context",
        "The media preview revision is invalid.",
      )
      : null;
    if (
      mediaRevision !== null
      && (
        !isObject(state.media)
        || state.media.requested_revision !== mediaRevision
      )
    ) return unchanged(state, "stale");
    if (
      !state.preview.selected_frame
      && frameSetEqual(state.preview.board_frame_set, checked)
      && (mediaRevision === null || state.media?.accepted_revision === mediaRevision)
    ) return unchanged(state);

    const acceptedEpoch = state.preview.accepted_epoch + 1;
    const canonical = createBoardFrameSet({
      ...checked,
      context: {...checked.context, revision: acceptedEpoch},
    }, {
      targetLengths: event.target_lengths,
      allowedDurations: event.allowed_durations,
      maxFrames: event.max_frames,
    });
    const index = Math.min(state.playhead.index, canonical.frame_count - 1);
    const key = workspaceDestinationKey(state.context);
    const next = {
      ...state,
      media: canonical.provenance === "media_render" && isObject(state.media)
        ? {
          ...state.media,
          accepted_revision: mediaRevision,
          accepted_frame_revision: mediaRevision,
          preview_timeline: canonical.timeline,
        }
        : state.media,
      playhead: stopPlayhead(state, index),
      destination_playheads: {...state.destination_playheads, [key]: index},
      preview: {
        ...state.preview,
        status: "ready",
        accepted_epoch: acceptedEpoch,
        context_key: workspaceContextKey(state, acceptedEpoch),
        request_context_key: null,
        board_frame_set: canonical,
        selected_frame: null,
        timeline: canonical.timeline,
        error: null,
      },
    };
    return {
      state: next,
      intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
    };
  }

  function acceptSelectedFrame(state, event) {
    const checked = createBoardFrameSet(event.frame_set, {
      targetLengths: event.target_lengths,
      allowedDurations: event.allowed_durations,
      maxFrames: 1,
    });
    if (
      checked.provenance !== "media_render"
      || checked.frame_count !== 1
      || checked.context.document_epoch !== state.context.document_epoch
      || checked.context.slot !== state.context.slot
      || checked.context.target !== state.context.target
    ) return unchanged(state, "stale");
    const mediaRevision = safeNonNegativeInteger(
      event.media_revision,
      "invalid_context",
      "The media preview revision is invalid.",
    );
    const timelineIndex = safeNonNegativeInteger(
      event.frame_index,
      "invalid_frame",
      "The selected lighting frame is invalid.",
    );
    if (
      !isObject(state.media)
      || state.media.requested_revision !== mediaRevision
      || state.playhead.index !== timelineIndex
    ) return unchanged(state, "stale");

    const acceptedEpoch = state.preview.accepted_epoch + 1;
    const canonical = createBoardFrameSet({
      ...checked,
      context: {...checked.context, revision: acceptedEpoch},
    }, {
      targetLengths: event.target_lengths,
      allowedDurations: event.allowed_durations,
      maxFrames: 1,
    });
    const contextKey = workspaceContextKey(state, acceptedEpoch);
    const selectedFrame = Object.freeze({
      frame_set: canonical,
      timeline_index: timelineIndex,
      media_revision: mediaRevision,
      context_key: contextKey,
    });
    const key = workspaceDestinationKey(state.context);
    const next = {
      ...state,
      media: {...state.media, accepted_frame_revision: mediaRevision},
      playhead: stopPlayhead(state, timelineIndex),
      destination_playheads: {...state.destination_playheads, [key]: timelineIndex},
      preview: {
        ...state.preview,
        status: "ready",
        accepted_epoch: acceptedEpoch,
        context_key: contextKey,
        request_context_key: null,
        selected_frame: selectedFrame,
        error: null,
      },
    };
    return {
      state: next,
      intents: [cancelPlaybackIntent(state), {type: "render-board"}],
    };
  }

  function requestMatches(state, event) {
    const mediaRevisionMatches = event.media_revision === undefined || Boolean(
      isObject(state.media)
      && Number.isSafeInteger(event.media_revision)
      && event.media_revision === state.media.requested_revision
    );
    return mediaRevisionMatches
      && Number.isSafeInteger(event.request_epoch)
      && event.request_epoch === state.preview.request_epoch
      && typeof event.context_key === "string"
      && event.context_key === state.preview.request_context_key
      && event.context_key === workspaceContextKey(state);
  }

  function errorResult(state, error) {
    const friendly = friendlyWorkspaceError(error, state.preview.request_epoch);
    if (state.preview.error?.key === friendly.key) return unchanged(state);
    const next = {
      ...state,
      preview: {...state.preview, status: "error", error: friendly},
    };
    return {
      state: next,
      intents: [{type: "show-error", error: friendly}, {type: "render-workspace"}],
    };
  }

  function reduceLightingWorkspace(state, event) {
    if (!isObject(state) || !isObject(event) || typeof event.type !== "string") {
      fail("invalid_context", "The workspace event is invalid.");
    }
    switch (event.type) {
      case "DOCUMENT_OPENED": {
        const documentEpoch = event.document_epoch === undefined
          ? state.context.document_epoch + 1
          : safeNonNegativeInteger(
            event.document_epoch,
            "invalid_context",
            "The document context is invalid.",
          );
        const nextContext = {
          document_epoch: documentEpoch,
          slot: event.slot === undefined ? state.context.slot : safeNonNegativeInteger(
            event.slot,
            "invalid_context",
            "The lighting slot is invalid.",
          ),
          target: event.target === undefined ? state.context.target : safeTarget(event.target),
        };
        return {
          state: contextTransition(state, nextContext, {playheadIndex: event.playhead_index}),
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "DOCUMENT_CLOSED": {
        const nextContext = {
          ...state.context,
          document_epoch: event.document_epoch === undefined
            ? state.context.document_epoch + 1
            : safeNonNegativeInteger(
              event.document_epoch,
              "invalid_context",
              "The document context is invalid.",
            ),
        };
        return {
          state: contextTransition(state, nextContext, {state: {media: null}}),
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "DESTINATION_CHANGED": {
        const nextContext = {
          ...state.context,
          slot: event.slot === undefined ? state.context.slot : safeNonNegativeInteger(
            event.slot,
            "invalid_context",
            "The lighting slot is invalid.",
          ),
          target: event.target === undefined ? state.context.target : safeTarget(event.target),
        };
        if (
          nextContext.slot === state.context.slot
          && nextContext.target === state.context.target
        ) return unchanged(state);
        return {
          state: contextTransition(state, nextContext),
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "TOOL_SELECTED": {
        if (typeof event.tool !== "string" || !event.tool.length) {
          fail("invalid_context", "The selected tool is invalid.");
        }
        if (event.tool === state.tool) return unchanged(state);
        const contextEpoch = state.context_epoch + 1;
        const next = {
          ...state,
          tool: event.tool,
          context_epoch: contextEpoch,
          playhead: stopPlayhead(state),
          preview: initialPreview(state.context, contextEpoch),
          effect_draft: event.tool === "animate" ? state.effect_draft : null,
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "ROUTE_CHANGED": {
        if (typeof event.route !== "string" || !event.route.length) {
          fail("invalid_context", "The workspace route is invalid.");
        }
        if (event.route === state.route) return unchanged(state);
        const contextEpoch = state.context_epoch + 1;
        const next = {
          ...state,
          route: event.route,
          context_epoch: contextEpoch,
          playhead: stopPlayhead(state),
          preview: initialPreview(state.context, contextEpoch),
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "MEDIA_OPENED": {
        const contextEpoch = state.context_epoch + 1;
        const media = isObject(event.media)
          ? {
            ...event.media,
            requested_revision: safeNonNegativeInteger(
              event.media.requested_revision ?? 0,
              "invalid_context",
              "The media preview revision is invalid.",
            ),
          }
          : null;
        const next = {
          ...state,
          media,
          tool: "source",
          context_epoch: contextEpoch,
          playhead: stopPlayhead(state, 0),
          preview: initialPreview(state.context, contextEpoch),
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "MEDIA_SESSION_READY": {
        if (
          !workspaceAsyncContextMatches(state, event.captured)
          || !isObject(state.media)
          || event.catalog_id !== state.media.catalog_id
          || event.asset_id !== state.media.asset_id
        ) return unchanged(state, "stale");
        const next = {
          ...state,
          media: {
            ...state.media,
            preview_session_id: safePreviewSessionId(event.preview_session_id),
          },
        };
        return {state: next, intents: [{type: "render-workspace"}]};
      }
      case "MEDIA_SESSION_INVALIDATED": {
        if (
          !isObject(state.media)
          || event.catalog_id !== state.media.catalog_id
          || event.asset_id !== state.media.asset_id
          || event.preview_session_id !== state.media.preview_session_id
        ) return unchanged(state, "stale");
        const {preview_session_id: expiredSessionId, ...media} = state.media;
        void expiredSessionId;
        return {
          state: {...state, media, playhead: stopPlayhead(state)},
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "MEDIA_CANCELLED": {
        const contextEpoch = state.context_epoch + 1;
        const next = {
          ...state,
          media: null,
          context_epoch: contextEpoch,
          playhead: stopPlayhead(state, 0),
          preview: initialPreview(state.context, contextEpoch),
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "TRANSFORM_REQUESTED":
      case "EFFECT_REQUESTED": {
        const media = isObject(state.media) ? {...state.media} : {};
        if (event.type === "TRANSFORM_REQUESTED") media.requested_transform = event.transform;
        else media.effects = event.effects;
        media.requested_revision = safeNonNegativeInteger(
          event.media_revision,
          "invalid_context",
          "The media preview revision is invalid.",
        );
        delete media.accepted_revision;
        delete media.accepted_frame_revision;
        const next = {
          ...state,
          media,
          playhead: stopPlayhead(state),
          preview: {...state.preview, status: "updating", error: null},
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "FRAME_RENDER_STARTED":
      case "SEQUENCE_RENDER_STARTED": {
        const requestEpoch = state.preview.request_epoch + 1;
        const next = {
          ...state,
          playhead: stopPlayhead(state),
          preview: {
            ...state.preview,
            status: "updating",
            request_epoch: requestEpoch,
            request_context_key: workspaceContextKey(state),
            error: null,
          },
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "BOARD_FRAME_SET_ACCEPTED":
        return acceptFrameSet(state, event);
      case "BOARD_COLOR_UPDATED": {
        const frameSet = state.preview.board_frame_set;
        if (
          !frameSet
          || frameSet.provenance !== "document"
          || event.context_key !== workspaceContextKey(state)
          || event.target !== state.context.target
        ) return unchanged(state, "stale");
        const frameIndex = safeNonNegativeInteger(
          event.frame_index,
          "invalid_frame",
          "The selected lighting frame is invalid.",
        );
        const colorIndex = safeNonNegativeInteger(
          event.color_index,
          "invalid_frame",
          "The selected light is invalid.",
        );
        if (typeof event.color !== "string" || !RGB_COLOR.test(event.color)) {
          fail("invalid_color", "The selected light color is invalid.");
        }
        const targetFrames = frameSet.frames_by_target[event.target];
        if (
          !targetFrames
          || frameIndex >= targetFrames.length
          || colorIndex >= targetFrames[frameIndex].length
        ) fail("invalid_frame", "The selected light is unavailable.");
        if (targetFrames[frameIndex][colorIndex] === event.color) return unchanged(state);

        const nextFrame = Object.freeze([
          ...targetFrames[frameIndex].slice(0, colorIndex),
          event.color,
          ...targetFrames[frameIndex].slice(colorIndex + 1),
        ]);
        const nextTargetFrames = Object.freeze([
          ...targetFrames.slice(0, frameIndex),
          nextFrame,
          ...targetFrames.slice(frameIndex + 1),
        ]);
        const acceptedEpoch = state.preview.accepted_epoch + 1;
        const nextFrameSet = Object.freeze({
          ...frameSet,
          context: Object.freeze({...frameSet.context, revision: acceptedEpoch}),
          frames_by_target: Object.freeze({
            ...frameSet.frames_by_target,
            [event.target]: nextTargetFrames,
          }),
        });
        validatedFrameSets.add(nextFrameSet);
        const next = {
          ...state,
          playhead: stopPlayhead(state, frameIndex),
          destination_playheads: {
            ...state.destination_playheads,
            [workspaceDestinationKey(state.context)]: frameIndex,
          },
          preview: {
            ...state.preview,
            status: "ready",
            accepted_epoch: acceptedEpoch,
            context_key: workspaceContextKey(state, acceptedEpoch),
            board_frame_set: nextFrameSet,
            error: null,
          },
        };
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-board"}],
        };
      }
      case "FRAME_RENDER_ACCEPTED":
        if (!requestMatches(state, event)) return unchanged(state, "stale");
        return acceptSelectedFrame(state, event);
      case "SEQUENCE_RENDER_ACCEPTED":
        if (!requestMatches(state, event)) return unchanged(state, "stale");
        return acceptFrameSet(state, event);
      case "FRAME_RENDER_FAILED":
      case "SEQUENCE_RENDER_FAILED":
        if (!requestMatches(state, event)) return unchanged(state, "stale");
        return errorResult(state, event.error);
      case "WORKSPACE_ERROR_REPORTED": {
        const friendly = friendlyWorkspaceError(event.error, state.preview.request_epoch);
        if (state.preview.error?.key === friendly.key) return unchanged(state);
        const acceptedEpoch = state.preview.accepted_epoch + 1;
        const next = {
          ...state,
          playhead: stopPlayhead(state, 0),
          preview: {
            ...state.preview,
            status: "error",
            accepted_epoch: acceptedEpoch,
            context_key: workspaceContextKey(state, acceptedEpoch),
            request_context_key: null,
            board_frame_set: null,
            timeline: [],
            error: friendly,
          },
        };
        return {
          state: next,
          intents: [
            cancelPlaybackIntent(state),
            {type: "show-error", error: friendly},
            {type: "render-workspace"},
          ],
        };
      }
      case "PLAY_REQUESTED": {
        const frameSet = state.preview.board_frame_set;
        if (
          state.tool === "source"
          && isObject(state.media)
          && state.media.accepted_revision !== state.media.requested_revision
        ) return unchanged(state, "stale");
        if (!frameSet || state.preview.context_key !== workspaceContextKey(state)) {
          return errorResult(state, {code: "no_preview"});
        }
        const sessionId = state.playhead.session_id + 1;
        const next = {
          ...state,
          playhead: {...state.playhead, playing: true, session_id: sessionId},
        };
        return {
          state: next,
          intents: [{
            type: "start-playback",
            session_id: sessionId,
            context_key: workspaceContextKey(next),
            duration_ms: frameSet.duration_ms,
          }, {type: "render-workspace"}],
        };
      }
      case "PLAYBACK_TICK": {
        if (
          !state.playhead.playing
          || event.session_id !== state.playhead.session_id
          || event.context_key !== workspaceContextKey(state)
          || !state.preview.board_frame_set
        ) return unchanged(state, "stale");
        const index = (state.playhead.index + 1) % state.preview.board_frame_set.frame_count;
        if (state.preview.board_frame_set.provenance === "media_render") {
          const timelineEntry = state.preview.board_frame_set.timeline[index];
          if (!Number.isSafeInteger(timelineEntry?.source_frame_index)) {
            return unchanged(state, "stale");
          }
          return {
            state,
            intents: [{
              type: "prepare-source-frame",
              session_id: state.playhead.session_id,
              context_key: workspaceContextKey(state),
              from_index: state.playhead.index,
              timeline_index: index,
              source_frame_index: timelineEntry.source_frame_index,
            }],
          };
        }
        const key = workspaceDestinationKey(state.context);
        const next = {
          ...state,
          playhead: {...state.playhead, index},
          destination_playheads: {...state.destination_playheads, [key]: index},
        };
        return {state: next, intents: [{type: "render-board"}]};
      }
      case "SOURCE_FRAME_READY": {
        if (
          !state.playhead.playing
          || event.session_id !== state.playhead.session_id
          || event.context_key !== workspaceContextKey(state)
          || !state.preview.board_frame_set
          || state.preview.board_frame_set.provenance !== "media_render"
          || event.from_index !== state.playhead.index
        ) return unchanged(state, "stale");
        const index = (state.playhead.index + 1) % state.preview.board_frame_set.frame_count;
        const timelineEntry = state.preview.board_frame_set.timeline[index];
        if (
          event.timeline_index !== index
          || event.source_frame_index !== timelineEntry?.source_frame_index
        ) return unchanged(state, "stale");
        const key = workspaceDestinationKey(state.context);
        const next = {
          ...state,
          playhead: {...state.playhead, index},
          destination_playheads: {...state.destination_playheads, [key]: index},
        };
        return {state: next, intents: [{type: "render-board"}]};
      }
      case "PAUSE_REQUESTED": {
        const next = {...state, playhead: stopPlayhead(state)};
        return {
          state: next,
          intents: [cancelPlaybackIntent(state), {type: "render-workspace"}],
        };
      }
      case "PLAYHEAD_SCRUBBED": {
        const index = safeNonNegativeInteger(
          event.index,
          "invalid_frame",
          "The selected lighting frame is invalid.",
        );
        if (index === state.playhead.index && !state.playhead.playing) return unchanged(state);
        const key = workspaceDestinationKey(state.context);
        const next = {
          ...state,
          playhead: state.playhead.playing
            ? stopPlayhead(state, index)
            : {...state.playhead, index},
          destination_playheads: {...state.destination_playheads, [key]: index},
        };
        return {
          state: next,
          intents: [
            ...(state.playhead.playing ? [cancelPlaybackIntent(state)] : []),
            {type: "render-board"},
          ],
        };
      }
      case "APPLY_REQUESTED": {
        if (!state.preview.board_frame_set || state.preview.context_key !== workspaceContextKey(state)) {
          return errorResult(state, {code: "no_preview"});
        }
        return {
          state,
          intents: [{
            type: "apply-board-frame-set",
            context_key: workspaceContextKey(state),
            board_frame_set: state.preview.board_frame_set,
          }],
        };
      }
      case "APPLY_COMPLETED":
        return unchanged(state);
      case "WORKSPACE_ERROR_DISMISSED": {
        if (!state.preview.error) return unchanged(state);
        return {
          state: {...state, preview: {...state.preview, error: null}},
          intents: [],
        };
      }
      default:
        fail("invalid_context", "The workspace event is unsupported.");
    }
  }

  function selectBoardProjection(state) {
    const frameSet = state?.preview?.board_frame_set;
    const selectedFrame = state?.preview?.selected_frame;
    if (state?.preview?.context_key !== workspaceContextKey(state)) return null;
    if (selectedFrame?.context_key === workspaceContextKey(state)) {
      const selectedSet = selectedFrame.frame_set;
      const controlsFrameSet = frameSet || selectedSet;
      const index = frameSet
        ? Math.min(selectedFrame.timeline_index, frameSet.frame_count - 1)
        : 0;
      return Object.freeze({
        target: state.context.target,
        index,
        colors: projectBoardFrame(selectedSet, state.context.target, 0),
        frame_set: controlsFrameSet,
        selected_frame: selectedFrame,
      });
    }
    if (!frameSet) return null;
    const index = Math.min(state.playhead.index, frameSet.frame_count - 1);
    return Object.freeze({
      target: state.context.target,
      index,
      colors: projectBoardFrame(frameSet, state.context.target, index),
      frame_set: frameSet,
    });
  }

  function selectSourceProjection(state) {
    const board = selectBoardProjection(state);
    if (
      !board
      || (board.selected_frame?.frame_set?.provenance ?? board.frame_set.provenance) !== "media_render"
      || !isObject(state.media)
      || typeof state.media.catalog_id !== "string"
      || typeof state.media.preview_session_id !== "string"
    ) return null;
    const timelineEntry = board.selected_frame
      ? board.selected_frame.frame_set.timeline[0]
      : board.frame_set.timeline[board.index];
    if (!Number.isSafeInteger(timelineEntry?.source_frame_index)) return null;
    return Object.freeze({
      catalog_id: state.media.catalog_id,
      preview_session_id: safePreviewSessionId(state.media.preview_session_id),
      source_frame_index: timelineEntry.source_frame_index,
      timeline_index: board.selected_frame?.timeline_index ?? board.index,
      context_key: workspaceContextKey(state),
    });
  }

  function paintBoardProjection(state, {
    destination_key: destinationKey,
    pixels = [],
    frame_items: frameItems = [],
  } = {}) {
    if (destinationKey !== workspaceDestinationKey(state)) return null;
    const projection = selectBoardProjection(state);
    if (!projection) return null;
    for (const pixel of pixels) {
      const color = projection.colors[Number(pixel?.dataset?.pixel)] || "#000000";
      if (pixel?.style) {
        pixel.style.background = color;
        pixel.style.setProperty?.("--pixel-color", color);
      }
    }
    frameItems.forEach((node, index) => {
      const selected = index === projection.index;
      node?.classList?.toggle?.("active", selected);
      node?.setAttribute?.("aria-pressed", String(selected));
      node?.setAttribute?.(
        "aria-label",
        `Frame ${index + 1}${selected ? ", selected" : ""}`,
      );
    });
    return projection;
  }

  function createLightingPlaybackRuntime({
    dispatch,
    setTimer,
    clearTimer,
    lifecycleTarget = null,
  } = {}) {
    if (
      typeof dispatch !== "function"
      || typeof setTimer !== "function"
      || typeof clearTimer !== "function"
    ) fail("invalid_context", "Lighting playback is unavailable.");
    if (
      lifecycleTarget !== null
      && (
        typeof lifecycleTarget?.addEventListener !== "function"
        || typeof lifecycleTarget?.removeEventListener !== "function"
      )
    ) fail("invalid_context", "Lighting playback cleanup is unavailable.");

    let active = null;
    let disposed = false;
    const cancel = intent => {
      if (!active) return false;
      if (
        intent
        && (
          intent.session_id !== active.session_id
          || intent.context_key !== active.context_key
        )
      ) return false;
      const timer = active.timer;
      active = null;
      clearTimer(timer);
      return true;
    };
    const onPageHide = () => {
      const wasActive = cancel();
      if (wasActive) dispatch({type: "PAUSE_REQUESTED"});
    };
    lifecycleTarget?.addEventListener("pagehide", onPageHide);

    const execute = intent => {
      if (disposed || !isObject(intent)) return false;
      if (intent.type === "cancel-playback") return cancel(intent);
      if (intent.type !== "start-playback") return false;
      const sessionId = safeNonNegativeInteger(
        intent.session_id,
        "invalid_context",
        "The playback session is invalid.",
      );
      const duration = safePositiveInteger(
        intent.duration_ms,
        "invalid_frame",
        "The playback speed is invalid.",
      );
      if (
        typeof intent.context_key !== "string"
        || !intent.context_key.length
        || intent.context_key.length > 512
      ) fail("invalid_context", "The playback context is invalid.");

      cancel();
      const session = {
        session_id: sessionId,
        context_key: intent.context_key,
        timer: null,
      };
      active = session;
      try {
        session.timer = setTimer(() => {
          if (active !== session) return;
          dispatch({
            type: "PLAYBACK_TICK",
            session_id: session.session_id,
            context_key: session.context_key,
          });
        }, duration);
      } catch (error) {
        if (active === session) active = null;
        throw error;
      }
      return true;
    };
    const dispose = () => {
      if (disposed) return;
      disposed = true;
      cancel();
      lifecycleTarget?.removeEventListener("pagehide", onPageHide);
    };
    return Object.freeze({execute, dispose});
  }

  return Object.freeze({
    LightingWorkspaceError,
    boardFrameSetFromDocument,
    boardFrameSetFromLocalEffect,
    boardFrameSetFromMappedFrame,
    boardFrameSetFromMappedResult,
    captureWorkspaceAsyncContext,
    createBoardFrameSet,
    createLightingPlaybackRuntime,
    createLightingWorkspace,
    friendlyWorkspaceError,
    paintBoardProjection,
    projectBoardFrame,
    reduceLightingWorkspace,
    selectBoardProjection,
    selectSourceProjection,
    workspaceContextKey,
    workspaceAsyncContextMatches,
    workspaceDestinationKey,
  });
});
