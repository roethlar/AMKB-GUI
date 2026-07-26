"""Raw HID link for QMK/Vial keyboards, and the identity gate that guards it.

This module exists because the AM serial families and a Vial board share nothing
below the device handle: there is no CDC port to open, no 64-byte CRC frame, and
no product-ID string probe. `device.py` and `protocol.py` are left untouched.

The identity problem is the hard part, and the reason this file is longer than a
transport wrapper needs to be. USB `0x05AC:0x024F` is Apple's vendor ID borrowed
so macOS treats the board as a native keyboard; it is reused by many unrelated
keyboards. A `vial:` serial prefix marks any Vial board whatsoever. The USB
product string is firmware-authored. None of those, alone or together, says the
connected device is a Neon 80 — and writing one keyboard's lighting protocol to
another keyboard is exactly the failure this gate exists to prevent.

So identity is staged, and only the last stage authorizes a write:

1. VID/PID narrows candidates.
2. A `vial:` serial prefix confirms Vial firmware.
3. The Vial keyboard definition is fetched from the board and its `name` field
   must read `AM Neon 80`.

Stage 3 is the board declaring its own model over its own protocol. It is not
cryptographic proof — firmware authors that string too — but it is materially
stronger than the first two, and a Vial board that is not a Neon 80 fails it.

Discovery never issues a mutating command. Only the three read subcommands are
reachable from here; `_vial_request` refuses anything else outright rather than
trusting call sites to pass the right constant.
"""

from __future__ import annotations

import json
import lzma
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NEON_VENDOR_ID = 0x05AC
NEON_PRODUCT_ID = 0x024F
RAW_USAGE_PAGE = 0xFF60
RAW_USAGE = 0x61

VIAL_SERIAL_PREFIX = "vial:"
NEON_DEFINITION_NAME = "AM Neon 80"

# The canonical product identifier for each raw-HID family. This is the value
# the routes, the browser, and the typed write confirmation all use; the USB
# product string is a display name and is never substituted for it.
CANONICAL_PRODUCT_IDS = {"NEON": "NEON80"}

REPORT_LENGTH = 32
DEFAULT_TIMEOUT_MS = 1000

_VIAL_PREFIX = 0xFE
# Only these three Vial subcommands read. `0x04` sets an encoder, `0x06`-`0x08`
# are unlock start/poll/lock, and the settings-set subcommands write flash. None
# of them may be issued while merely identifying a device.
_VIAL_GET_KEYBOARD_ID = 0x00
_VIAL_GET_SIZE = 0x01
_VIAL_GET_DEFINITION = 0x02
# `0x05` reports whether the board is unlocked and which keys are being held for
# it. It reads state and changes nothing, unlike `0x06`-`0x08` (unlock start,
# unlock poll, lock), which stay out.
VIAL_GET_UNLOCK_STATUS = 0x05
_VIAL_READ_ONLY = frozenset(
    {_VIAL_GET_KEYBOARD_ID, _VIAL_GET_SIZE, _VIAL_GET_DEFINITION, VIAL_GET_UNLOCK_STATUS}
)

# A definition should be a few hundred bytes. A malformed or hostile size field
# must not turn discovery into an unbounded read loop.
_MAX_DEFINITION_BYTES = 64 * 1024

# The compressed cap above bounds the wrong quantity on its own: 200 MiB of
# zeros compresses to about 30 KiB, which passes it and then expands in full.
# Discovery runs against any attached board, so decompression is reachable
# without a write and must be bounded on its *output*.
_MAX_DEFINITION_DECOMPRESSED_BYTES = 1024 * 1024


class HidError(RuntimeError):
    """Base for raw-HID failures. Messages never contain a device path."""


class HidDeviceAbsent(HidError):
    """No device matching the requested address is attached."""


class HidDeviceBusy(HidError):
    """The device is attached but another process holds it."""


class HidPermissionDenied(HidError):
    """The device is attached but this process may not open it."""


class HidIdentityError(HidError):
    """The device is reachable but is not a supported model."""


UDEV_RULE_NAME = "60-am-neon-80.rules"


def udev_rule_path() -> Path:
    """Where the shipped udev rule actually is, for this installation.

    The rule travels inside the package rather than in the source tree, because
    the permission error tells the user to install it and wheel and AppImage
    users have no source tree to install it from.
    """

    return Path(__file__).resolve().parent / "data" / UDEV_RULE_NAME


def _permission_remedy() -> str:
    import sys

    if not sys.platform.startswith("linux"):
        return ""
    # Tell the user how to *obtain* the rule, not where it sits: inside an
    # AppImage the path is on a temporary mount that disappears on exit, so a
    # path is worthless to exactly the users who most need this message.
    return (
        " On Linux the raw HID node is root-only until a udev rule grants "
        "access. Run this application with --print-udev-rule and pipe it into "
        f"tee, e.g. '<this application> --print-udev-rule | sudo tee "
        f"/etc/udev/rules.d/{UDEV_RULE_NAME} >/dev/null'. A plain 'sudo ... >' "
        "redirect cannot work: the shell opens the target as you, before sudo "
        "runs. Then 'sudo udevadm control --reload-rules && sudo udevadm "
        "trigger', and replug the keyboard."
    )


@dataclass(frozen=True)
class HidDeviceInfo:
    """One raw-HID endpoint and what identity checking concluded about it.

    Two different identities live here and must not be confused.

    `firmware_uid` (Vial `FE 00`) and `definition_name` are **model** identity:
    Vial's keyboard UID is a firmware build-time constant, so every unit running
    the same Neon firmware reports the same value. It answers "what model is
    this", never "which unit is this".

    `address` is **instance** identity — which physical endpoint to talk to —
    and is derived from the OS device path, the only per-endpoint value
    available. macOS reports that path as an IOKit registry entry ID that
    changes across replug; that instability is wanted, because a confirmation
    must not survive the device being swapped.
    """

    address: str
    path: bytes
    usb_vendor_id: int
    usb_product_id: int
    serial_number: str
    product_string: str
    manufacturer_string: str
    model: str | None
    is_vial: bool
    definition_name: str | None
    identity_error: str | None
    firmware_uid: str = ""
    protocol_version: int = 0

    # Part of the contract every transport's device info satisfies, because the
    # routes read them for any device. A serial board reports a firmware version
    # string and a page count; this one has neither, and `None` says so rather
    # than the attribute being absent — an absent attribute raised
    # AttributeError *after* the hardware had already been written.
    version: str | None = None
    pages: int | None = None

    @property
    def product_id(self) -> str:
        """The canonical AM product identifier. One value, everywhere.

        The device routes and the browser key families off `product_id`, and a
        write confirmation is compared against it exactly. It must therefore
        read the same during a shallow scan and after deep identification — an
        earlier version returned the USB product string (`AM Neon 80`) while
        scanning and the model (`NEON80`) after, so the browser asked the user to
        confirm one value and the server demanded the other, and no write could
        ever succeed.

        The untrusted USB string stays available as `product_string`, for
        display only.
        """

        if self.model:
            return self.model
        # Not yet interrogated. Resolve the canonical id from the USB string
        # rather than exposing the string itself, so the value never changes
        # shape between scan and identification. A device this build does not
        # recognise yields "", which is what keeps it out of every family.
        from . import device_mapping

        try:
            family = device_mapping.led_model(self.product_string)
        except ValueError:
            return ""
        return CANONICAL_PRODUCT_IDS.get(family, "")

    @property
    def is_keyboard(self) -> bool:
        """A Vial board is a keyboard; which model it is, is a separate question.

        Listing requires only that. `writable` is the property that demands the
        definition gate, and it is the one that guards a write.
        """

        return self.is_vial or self.model is not None

    @property
    def writable(self) -> bool:
        """Only a device that cleared every identity stage may be written."""

        return self.model is not None and self.identity_error is None


def endpoint_address(path: bytes) -> str:
    """An opaque, connection-scoped token for one physical raw-HID endpoint.

    Derived from the OS device path because that is the only per-endpoint value
    available: the USB serial is identical on every Vial board, and the Vial
    keyboard UID is identical on every unit of a model. The token is opaque so
    no caller is tempted to parse a path out of it, and it is not stable across
    replug — which is correct, because an approval bound to it must not survive
    the device changing.
    """

    return "hid:" + path.hex()


def _hid():
    """Import `hid` lazily, as the serial modules are imported lazily."""

    import hid

    return hid


def raw_endpoints(vendor_id: int = NEON_VENDOR_ID, product_id: int = NEON_PRODUCT_ID):
    """Every raw-HID endpoint for a VID/PID, ignoring keyboard and mouse ones."""

    return [
        entry
        for entry in _hid().enumerate(vendor_id, product_id)
        if entry.get("usage_page") == RAW_USAGE_PAGE and entry.get("usage") == RAW_USAGE
    ]


def _classify_open_failure(path: bytes) -> HidError:
    """Work out *why* an open failed, since hidapi will not say.

    The locked hidapi binding raises `OSError('open failed')` for every failure
    — no errno, no distinguishing text. Matching on that string was dead code:
    permission problems reported as "not attached", which hid the udev remedy
    that is the whole point of shipping a rule.

    So classify from the device node instead, where the platform exposes one.
    On Linux the path is a `/dev/hidraw*` node whose existence and access bits
    answer the question directly. Elsewhere the path is an opaque OS handle with
    nothing to inspect, so the honest answer is that the cause is unknown — say
    that rather than assert a cause that was never determined.
    """

    import os
    import sys

    if sys.platform.startswith("linux"):
        try:
            node = os.fsdecode(path)
        except (UnicodeDecodeError, ValueError):
            node = ""
        if node.startswith("/dev/"):
            if not os.path.exists(node):
                return HidDeviceAbsent("The keyboard is no longer attached.")
            if not os.access(node, os.R_OK | os.W_OK):
                return HidPermissionDenied(
                    "Permission denied opening the keyboard." + _permission_remedy()
                )
            # It exists and is accessible, so the most likely remaining cause is
            # another process holding it exclusively.
            return HidDeviceBusy(
                "The keyboard is open in another application; close it and retry."
            )

    # This function's contract is to *return* an error, never to raise one:
    # `identify` catches only `HidError`, so anything escaping here would crash
    # discovery instead of marking one device unidentified. Re-enumeration
    # touches the USB stack and can fail on its own, so it cannot be trusted to
    # stay quiet.
    try:
        still_present = any(entry.get("path") == path for entry in raw_endpoints())
    except Exception:
        still_present = True
    if not still_present:
        return HidDeviceAbsent("The keyboard is no longer attached.")
    return HidError(
        "The keyboard could not be opened. It may be in use by another "
        "application, or this process may lack permission to open it."
        + _permission_remedy()
    )


def _open(path: bytes):
    hid = _hid()
    handle = hid.device()
    try:
        handle.open_path(path)
    except OSError:
        raise _classify_open_failure(path) from None
    return handle


def _vial_request(handle, subcommand: int, *args: int, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> bytes:
    """Issue one Vial read subcommand and return its 32-byte reply.

    Refuses any subcommand outside the read-only set. A mistyped constant here
    would write to the keyboard, so the guard is in the transport rather than
    left to callers.
    """

    if subcommand not in _VIAL_READ_ONLY:
        raise HidError(
            f"Refusing Vial subcommand 0x{subcommand:02X}: not a read-only command."
        )
    packet = bytes([_VIAL_PREFIX, subcommand, *args])
    handle.write(b"\x00" + packet.ljust(REPORT_LENGTH, b"\x00"))
    reply = bytes(handle.read(REPORT_LENGTH, timeout_ms))
    if len(reply) < REPORT_LENGTH:
        raise HidError("The keyboard did not answer a Vial request.")
    return reply


def fetch_keyboard_uid(handle) -> tuple[int, str]:
    """Return the Vial protocol version and the board's own 8-byte UID.

    This UID — not the USB serial — is what distinguishes two Vial boards. The
    serial suffix `f64c2b3c` is a fixed magic string every Vial keyboard
    reports, which is why Vial can publish one udev rule matching it literally.
    """

    reply = _vial_request(handle, _VIAL_GET_KEYBOARD_ID)
    return struct.unpack("<I", reply[0:4])[0], reply[4:12].hex()


def _decompress_bounded(blob: bytes) -> bytes:
    """Decompress device-supplied data with an explicit ceiling on the output.

    Decompresses incrementally and stops the moment the output would exceed the
    ceiling, so a small payload that expands enormously is rejected instead of
    being materialized. A stream that is incomplete, or that carries trailing
    bytes after its end, is rejected too — a well-formed definition has neither.
    """

    decompressor = lzma.LZMADecompressor()
    try:
        decoded = decompressor.decompress(
            blob, max_length=_MAX_DEFINITION_DECOMPRESSED_BYTES + 1
        )
    except lzma.LZMAError:
        raise HidIdentityError(
            "The keyboard's definition could not be decompressed."
        ) from None
    if len(decoded) > _MAX_DEFINITION_DECOMPRESSED_BYTES:
        raise HidIdentityError(
            "The keyboard's definition expands beyond "
            f"{_MAX_DEFINITION_DECOMPRESSED_BYTES} bytes and was rejected."
        )
    if not decompressor.eof:
        raise HidIdentityError("The keyboard's definition is truncated or oversized.")
    if decompressor.unused_data:
        raise HidIdentityError("The keyboard's definition has trailing data.")
    return decoded


def fetch_definition(handle) -> dict[str, Any]:
    """Fetch and decode the Vial keyboard definition.

    The payload is XZ-compressed JSON — verified on hardware, and not the
    LZMA-alone format some Vial documentation implies.
    """

    size = struct.unpack("<I", _vial_request(handle, _VIAL_GET_SIZE)[0:4])[0]
    if not 0 < size <= _MAX_DEFINITION_BYTES:
        raise HidIdentityError(
            f"The keyboard reported an implausible definition size ({size} bytes)."
        )
    blob = bytearray()
    for block in range((size + REPORT_LENGTH - 1) // REPORT_LENGTH):
        blob += _vial_request(
            handle, _VIAL_GET_DEFINITION, block & 0xFF, (block >> 8) & 0xFF
        )
    decoded = _decompress_bounded(bytes(blob[:size]))
    try:
        definition = json.loads(decoded)
    except ValueError:
        raise HidIdentityError("The keyboard's definition is not valid JSON.") from None
    if not isinstance(definition, dict):
        raise HidIdentityError("The keyboard's definition is not an object.")
    return definition


def identify(entry: dict[str, Any], *, deep: bool = True) -> HidDeviceInfo:
    """Run the identity gate against one enumerated endpoint.

    Never raises for an unidentified device: a board that fails a stage is
    returned as non-writable with the reason recorded, because discovery must
    still list it rather than silently omit or, worse, silently accept it.

    `deep=False` stops after the cheap USB stages and opens nothing. Scans run
    shallow: opening and interrogating every attached Vial board on every scan
    is slow, contends with other applications for exclusive access, and made the
    test suite trap at interpreter shutdown. The definition gate then runs when
    a specific device is resolved, which is the only moment its answer is
    needed.
    """

    serial = str(entry.get("serial_number") or "")
    vendor_id = int(entry.get("vendor_id") or 0)
    product_id = int(entry.get("product_id") or 0)
    # The address must identify a physical endpoint, and neither USB value can.
    # Every Vial board reports the same `vial:f64c2b3c` serial, and the Vial
    # keyboard UID is a firmware build-time constant shared by every unit of a
    # model — both were tried and both collide between two units. The OS device
    # path is the only per-endpoint value available, so the address is an opaque
    # token derived from it.
    common = {
        "address": endpoint_address(entry.get("path") or b""),
        "path": entry.get("path") or b"",
        "usb_vendor_id": vendor_id,
        "usb_product_id": product_id,
        "serial_number": serial,
        "product_string": str(entry.get("product_string") or ""),
        "manufacturer_string": str(entry.get("manufacturer_string") or ""),
    }

    # Stage 2. A `vial:` prefix proves Vial firmware and nothing more, but its
    # absence is decisive: without it there is no definition to ask for.
    if not serial.startswith(VIAL_SERIAL_PREFIX):
        return HidDeviceInfo(
            **common,
            model=None,
            is_vial=False,
            definition_name=None,
            identity_error="This device does not report Vial firmware.",
        )

    if not deep:
        return HidDeviceInfo(
            **common,
            model=None,
            is_vial=True,
            definition_name=None,
            identity_error=None,
        )

    # Stage 3. Ask the board what it is. This is the only stage that can
    # authorize a write, and it is the only one a non-Neon Vial board fails.
    try:
        handle = _open(common["path"])
    except HidError as error:
        return HidDeviceInfo(
            **common, model=None, is_vial=True, definition_name=None,
            identity_error=str(error),
        )
    try:
        protocol, uid = fetch_keyboard_uid(handle)
        common["firmware_uid"] = uid
        common["protocol_version"] = protocol
        definition = fetch_definition(handle)
    except HidError as error:
        return HidDeviceInfo(
            **common, model=None, is_vial=True, definition_name=None,
            identity_error=str(error),
        )
    finally:
        handle.close()

    name = str(definition.get("name") or "")
    if protocol <= 0 or uid == "0" * 16:
        return HidDeviceInfo(
            **common, model=None, is_vial=True, definition_name=name or None,
            identity_error=(
                "This keyboard did not report a coherent Vial identity."
            ),
        )
    if name != NEON_DEFINITION_NAME:
        return HidDeviceInfo(
            **common, model=None, is_vial=True, definition_name=name or None,
            identity_error=(
                f"This is a Vial keyboard, but its definition identifies it as "
                f"{name or 'an unnamed model'}, not an {NEON_DEFINITION_NAME}."
            ),
        )

    return HidDeviceInfo(
        **common, model="NEON80", is_vial=True, definition_name=name,
        identity_error=None,
    )


def list_devices(*, deep: bool = False) -> list[HidDeviceInfo]:
    """Every raw-HID candidate. Shallow by default: opens no device."""

    return [identify(entry, deep=deep) for entry in raw_endpoints()]


def find(address: str) -> HidDeviceInfo:
    """Resolve an address to a currently attached, fully identified device.

    Always deep: this is the answer a caller acts on, so it is the moment the
    definition gate must run.
    """

    for entry in raw_endpoints():
        if endpoint_address(entry.get("path") or b"") == address:
            return identify(entry, deep=True)
    raise HidDeviceAbsent("That keyboard is no longer attached.")


# Minted once per process. A `WriteApproval` is only honoured if it carries
# this exact object, which only `approve_write` can attach — so a hand-built
# approval, however well-formed, cannot authorize a write.
_APPROVAL_TOKEN = object()


@dataclass(frozen=True)
class WriteApproval:
    """A typed confirmation bound to one validated device on one connection.

    The binding is the point. A confirmation typed for one keyboard must not
    authorize a write to a different one that arrived afterwards, so the
    approval carries both the identity that was validated and the OS path that
    identity was validated through. `matches` re-checks both.
    """

    address: str
    model: str
    path: bytes
    confirmation: str

    model_uid: str = ""
    # Provenance. `open_approved` honours an approval only if this is the
    # module's own token, which only `approve_write` attaches, so a hand-built
    # approval cannot authorize a write however well-formed it looks.
    token: object = None

    def matches(self, info: HidDeviceInfo) -> bool:
        return (
            info.writable
            and info.address == self.address
            and info.model == self.model
            and info.path == self.path
            and info.firmware_uid == self.model_uid
        )


def approve_write(info: HidDeviceInfo, confirmation: str) -> WriteApproval:
    """Bind a typed confirmation to a device that cleared the identity gate."""

    if not info.writable:
        raise HidIdentityError(
            info.identity_error or "This device is not a supported keyboard."
        )
    if confirmation.strip() != info.model:
        raise HidIdentityError(
            f"Type {info.model} exactly to confirm writing to this keyboard."
        )
    return WriteApproval(
        address=info.address,
        model=info.model,
        path=info.path,
        confirmation=confirmation,
        model_uid=info.firmware_uid,
        token=_APPROVAL_TOKEN,
    )


class _RawSession:
    """An open raw-HID connection.

    Private on purpose. Nothing outside this module may obtain one by path:
    transmitting to a keyboard goes through `open_approved`, which re-proves
    identity on the very handle it hands back. A public path-taking session
    would let any caller skip the approval entirely, which is exactly what it
    used to do.
    """

    def __init__(self, path: bytes) -> None:
        self._path = path
        self._handle = None

    def __enter__(self) -> _RawSession:
        # Idempotent on purpose. `open_approved` hands back a session that is
        # already open and already identity-checked; the ordinary
        # `with session:` idiom would otherwise call this again, open a second
        # handle that nothing validated, and silently replace the validated one
        # — defeating the entire re-check.
        if self._handle is None:
            self._handle = _open(self._path)
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _require(self):
        if self._handle is None:
            raise HidError("The keyboard connection is closed.")
        return self._handle

    def send(self, payload: bytes) -> None:
        """Write one 32-byte report."""

        if len(payload) > REPORT_LENGTH:
            raise HidError(
                f"A raw HID report is {REPORT_LENGTH} bytes; got {len(payload)}."
            )
        self._require().write(b"\x00" + payload.ljust(REPORT_LENGTH, b"\x00"))

    def receive(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> bytes:
        """Read one report, or raise on timeout."""

        reply = bytes(self._require().read(REPORT_LENGTH, timeout_ms))
        if not reply:
            raise HidError("The keyboard did not answer within the timeout.")
        return reply


def open_approved(approval: WriteApproval) -> _RawSession:
    """Open the approved device and re-prove its identity on that same handle.

    Validation during discovery and transmission afterwards used to happen on
    two different handles, with the device closed in between. That gap is the
    whole vulnerability: a device swapped after confirmation can occupy the same
    OS path and receive writes meant for the confirmed keyboard.

    So this re-reads the Vial identity through the handle it returns, and hands
    back a session only if that identity still matches the approval. The handle
    is never closed and reopened in between, so nothing can be substituted
    inside the window.
    """

    if approval.token is not _APPROVAL_TOKEN:
        raise HidIdentityError(
            "This write approval was not issued by approve_write and is refused."
        )
    if approval.confirmation.strip() != approval.model:
        raise HidIdentityError(
            "The typed confirmation does not match the approved model."
        )

    session = _RawSession(approval.path)
    session.__enter__()
    try:
        protocol, uid = fetch_keyboard_uid(session._require())
        if uid != approval.model_uid or protocol <= 0:
            raise HidIdentityError(
                "This is not the keyboard the write was confirmed for."
            )
        definition = fetch_definition(session._require())
        if str(definition.get("name") or "") != NEON_DEFINITION_NAME:
            raise HidIdentityError(
                "This is not the keyboard the write was confirmed for."
            )
        if endpoint_address(approval.path) != approval.address:
            raise HidIdentityError("The approved device address no longer matches.")
    except BaseException:
        session.close()
        raise
    return session
