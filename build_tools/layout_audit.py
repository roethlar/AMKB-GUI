"""Read-only layout and validation audit against the live application.

Launches the real desktop shell, reads every connected keyboard (this tool
never references the write path), and then measures every route, Studio
tool, and lighting target at several window sizes. Any element that escapes
the viewport, escapes its non-scrolling container, or is cut by an
overflow-hidden ancestor is reported with the overflow in pixels, so layout
regressions are detected numerically instead of by screenshot inspection.

Usage (requires the desktop extra and, for device coverage, connected
keyboards; runs fine with none connected and audits the empty state):

    uv run --frozen --extra desktop python -m build_tools.layout_audit
"""

from __future__ import annotations

import argparse
import json
import threading
import time

AUDIT_JS = r"""
(function(){
  function desc(el){
    let s=el.tagName.toLowerCase();
    if(el.id)s+='#'+el.id;
    if(el.classList&&el.classList.length)s+='.'+[...el.classList].slice(0,3).join('.');
    return s;
  }
  const out=[]; const seen=new Set();
  const vw=document.documentElement.clientWidth;
  for(const el of document.querySelectorAll('body *')){
    if(!(el instanceof HTMLElement))continue;
    if(el.closest('[hidden]'))continue;
    if(el.closest('dialog')&&!el.closest('dialog').open)continue;
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0)continue;
    const cs=getComputedStyle(el);
    if(cs.position==='fixed')continue;
    if(r.right>vw+2){
      const k='V:'+desc(el);
      if(!seen.has(k)){seen.add(k);out.push('VIEWPORT +'+Math.round(r.right-vw)+'px '+desc(el));}
    }
  }
  const boxes=document.querySelectorAll('.card,.settings-section,.lighting-context,.studio-tool-panel,.led-controls,.frame-list,.macro-list,.assignment-panel,.topbar,.sidebar,.studio-inspector,.text-macro-composer,.macro-editor,.library-toolbar');
  for(const box of boxes){
    if(box.closest('[hidden]'))continue;
    const br=box.getBoundingClientRect();
    if(br.width<=0||br.height<=0)continue;
    const bcs=getComputedStyle(box);
    if(['auto','scroll','hidden','clip'].includes(bcs.overflowX))continue;
    for(const d of box.querySelectorAll('*')){
      if(!(d instanceof HTMLElement))continue;
      if(d.closest('[hidden]'))continue;
      let a=d.parentElement, contained=false;
      while(a&&a!==box){
        const acs=getComputedStyle(a);
        if(['auto','scroll','hidden','clip'].includes(acs.overflowX)){contained=true;break;}
        a=a.parentElement;
      }
      if(contained)continue;
      const dr=d.getBoundingClientRect();
      if(dr.width>0&&dr.height>0&&dr.right>br.right+2){
        const k='E:'+desc(d)+'>'+desc(box);
        if(!seen.has(k)){seen.add(k);out.push('ESCAPE +'+Math.round(dr.right-br.right)+'px '+desc(d)+' out of '+desc(box));}
      }
    }
  }
  for(const el of document.querySelectorAll('body *')){
    if(!(el instanceof HTMLElement))continue;
    if(el.closest('[hidden]'))continue;
    if(el.closest('dialog')&&!el.closest('dialog').open)continue;
    if(el.classList.contains('sr-only'))continue;
    const cs=getComputedStyle(el);
    if(!['hidden','clip'].includes(cs.overflowX))continue;
    if(cs.textOverflow==='ellipsis')continue;
    if(el.clientWidth>0&&el.scrollWidth>el.clientWidth+2){
      const k='C:'+desc(el);
      if(!seen.has(k)){seen.add(k);out.push('CLIP +'+(el.scrollWidth-el.clientWidth)+'px inside '+desc(el));}
    }
  }
  return out.slice(0,50);
})()
"""

SIZES = ((1000, 680), (1280, 800), (1600, 1000), (1780, 1050))


def _poll_async(window, kickoff: str, timeout: float):
    window.evaluate_js("window.__ar=undefined;" + kickoff)
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = window.evaluate_js(
            "window.__ar===undefined?null:JSON.stringify(window.__ar)"
        )
        if value:
            return json.loads(value)
        time.sleep(0.5)
    raise TimeoutError(kickoff[:80])


def _audit(window, report: dict, label: str) -> None:
    rows = window.evaluate_js(AUDIT_JS) or []
    if rows:
        report["layout"][label] = rows


def _audit_routes(window, report: dict, device_label: str) -> None:
    for width, height in SIZES:
        window.resize(width, height)
        time.sleep(1.0)
        size = f"{width}x{height}"
        for route in ("keymap", "macros", "settings", "lighting/library"):
            window.evaluate_js(f"navigateTo('{route}')")
            time.sleep(0.5)
            _audit(window, report, f"{device_label}|{size}|{route}")
        window.evaluate_js("navigateTo('lighting/edit')")
        time.sleep(0.5)
        target_count = (
            window.evaluate_js("$$('#lighting-target-controls button').length") or 0
        )
        for target_index in range(max(1, int(target_count))):
            if target_count:
                window.evaluate_js(
                    f"$$('#lighting-target-controls button')[{target_index}]?.click()"
                )
                time.sleep(0.5)
            for tool in ("paint", "source", "animate"):
                window.evaluate_js(f"setStudioTool('{tool}',{{focus:false}})")
                time.sleep(0.4)
                _audit(
                    window,
                    report,
                    f"{device_label}|{size}|lighting/edit|target{target_index}|{tool}",
                )


def _run(window, report: dict, out_path: str) -> None:
    try:
        time.sleep(6)
        devices = _poll_async(
            window,
            "(async()=>{try{await scanDevices();"
            "window.__ar=state.devices.filter(d=>d.is_keyboard)"
            ".map(d=>({key:deviceKey(d),pid:d.product_id}));}"
            "catch(e){window.__ar={error:String(e&&e.message||e)};}})()",
            timeout=60,
        )
        if isinstance(devices, dict) and devices.get("error"):
            report["errors"].append(f"scan: {devices['error']}")
            devices = []
        report["devices"] = devices
        if not devices:
            _audit_routes(window, report, "no-device")
        for device in devices:
            key = json.dumps(device["key"])
            loaded = _poll_async(
                window,
                "(async()=>{try{state.selectedDevice=" + key + ";"
                "await readDevice();"
                "window.__ar={product:productId(),file:state.fileName,"
                "layers:layers().length,macros:(state.config.macro_key||[]).length};}"
                "catch(e){window.__ar={error:String(e&&e.message||e)};}})()",
                timeout=180,
            )
            label = device["pid"]
            if isinstance(loaded, dict) and loaded.get("error"):
                report["errors"].append(f"read {label}: {loaded['error']}")
                continue
            result = _poll_async(
                window,
                "(async()=>{try{const r=await validateCurrent(false);"
                "window.__ar=r?{ok:r.ok,errors:r.errors||[],warnings:r.warnings||[],"
                "layers:r.layers,macros:r.macros,pages:r.pages}:{ok:null};}"
                "catch(e){window.__ar={error:String(e&&e.message||e)};}})()",
                timeout=60,
            )
            report["validation"][label] = {"loaded": loaded, "validate": result}
            _audit_routes(window, report, label)
    except Exception as exc:  # noqa: BLE001 - report everything, never hang
        report["errors"].append(repr(exc))
    finally:
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        window.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="layout_audit_report.json",
        help="report destination (JSON)",
    )
    args = parser.parse_args()

    import webview

    from am_configurator.server import create_server

    report = {"devices": [], "validation": {}, "layout": {}, "errors": []}
    server, url = create_server([])
    threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.2},
        daemon=True,
    ).start()
    window = webview.create_window(
        "layout audit", url, width=1440, height=920, min_size=(1000, 680)
    )
    webview.start(
        func=_run, args=(window, report, args.out), gui="edgechromium",
        private_mode=True,
    )
    findings = sum(len(rows) for rows in report["layout"].values())
    print(f"devices={len(report['devices'])} findings={findings} errors={len(report['errors'])}")
    return 1 if (findings or report["errors"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
