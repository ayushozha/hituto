"""Post-processors (design.md §3.4–§3.5).

The headline job is NOT to download images at build time, but to INJECT a runtime
loader so the rendered page resolves go-data-src images itself in the browser —
exactly what the real fractal-explorer artifact does (the dashed Browser->Tools edge).
Plus deterministic quality checks (R10.1).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from urllib.parse import quote_plus

from guidebridge.iframe import (
    IFRAME_RUNTIME_MARKER,
    IFRAME_RUNTIME_VERSION,
    inject_iframe_runtime,
    strip_iframe_runtime,
)

# Marker baked into served artifacts so we can idempotently patch older HTML.
_LIGHTBOX_MARKER = "hituto-lightbox"

# --- Lesson bridge (edit mode, learning events, HTML export) ---
#
# SECURITY MODEL: generated (model) HTML is still forbidden from touching window.parent /
# window.top — that postprocess() check is unchanged and runs BEFORE our scripts are injected.
# Two first-party scripts are appended after the gate, and they are the ONLY things in the
# capsule that talk to the parent:
#   1. this bridge (Hi-Tuto features: edit mode, learning events, HT_GET_HTML export), and
#   2. the GuideBridge iframe runtime (agent page control: observe/click/type/highlight +
#      Tutor cursor), injected via guidebridge.iframe.inject_iframe_runtime().
# Neither grants same-origin access; the iframe stays sandbox="allow-scripts".
#
# Inbound commands are accepted only from event.source === window.parent (an unrelated window
# cannot produce that). Replies use targetOrigin "*" because a sandboxed iframe has an opaque
# origin; the payload is lesson content the parent already served — nothing sensitive.
_BRIDGE_MARKER = "hituto-lesson-bridge"
# Bump when _LESSON_BRIDGE_SCRIPT changes behavior: ensure_artifact_runtime() replaces any
# older-version bridge in stored artifacts on serve, so new actions reach old lessons.
# v8: page control (snapshot/execute/agent cursor) moved out to the GuideBridge runtime;
# this bridge now carries only the Hi-Tuto-specific features. (Also fixes the historic
# skew where Python said "6" while the JS handshake said '7'.)
_BRIDGE_VERSION = "8"
_CHART_CANVAS_CSS_MARKER = "hituto-chart-canvas-fix"
_CHART_CANVAS_CSS = (
    f"<style id=\"{_CHART_CANVAS_CSS_MARKER}\">\n"
    "canvas[id*=\"chart\" i], canvas[id*=\"graph\" i], canvas[data-chart] {\n"
    "  display: block;\n"
    "  width: 100% !important;\n"
    "  height: min(360px, 48vh) !important;\n"
    "  max-height: 420px !important;\n"
    "}\n"
    "</style>"
)
_LEGACY_LESSON_THEME_MARKER = "hituto-generated-lesson-theme-v2"
_LEGACY_LESSON_THEME_REPLACEMENTS = (
    ("#F5F2EA", "#FDF1E7"),
    ("#EFEBDF", "#F2E0CE"),
    ("#1B1A16", "#0B1F10"),
    ("#56524A", "#3E5244"),
    ("#928C7E", "#4B5D52"),
    ("#E6E0D2", "#EBDACA"),
    ("#2C50EE", "#4B2450"),
    ("#1C38C2", "#35193B"),
    ("#E9EDFF", "#E3C8F5"),
    ("#C7ED45", "#2BC15D"),
    ("#A6D119", "#14380E"),
    ("#F2FACB", "#D9F2DC"),
    ("#FF6A3C", "#FE936D"),
    ("#E8501F", "#562D2B"),
    ("#FFEAE0", "#F8C5A8"),
    ("#15A66A", "#2BC15D"),
    ("#E0F5EA", "#D9F2DC"),
    ('"Bricolage Grotesque", ui-sans-serif', '"Plus Jakarta Sans", ui-sans-serif'),
)
_LEGACY_LESSON_THEME_STYLE = f"""
<style id="{_LEGACY_LESSON_THEME_MARKER}">
html,body {{ background:transparent !important; color:#0B1F10 !important; }}
h1,h2,h3,h4,h5,h6,.font-display {{
  font-family:"Plus Jakarta Sans",ui-sans-serif,system-ui,sans-serif !important;
  letter-spacing:-0.025em;
}}
.nav-link.active {{ background:#E3C8F5 !important; color:#3F2447 !important; font-weight:800; }}
.border,.border-line {{ border-color:rgba(11,31,16,.16) !important; }}
.shadow-sm,.shadow-md,.shadow-inner {{ box-shadow:none !important; }}
button,input,select,textarea {{ font:inherit; }}
button {{ min-height:44px; }}
@media (min-width:768px) {{
  body > div.flex {{
    display:block !important;
    max-width:72rem !important;
    margin:0 auto !important;
    padding:0 32px 72px !important;
  }}
  body > div.flex > nav.fixed {{
    display:none !important;
  }}
  body > div.flex > main {{
    max-width:64rem !important;
    margin:0 auto !important;
    padding:40px 0 72px !important;
  }}
  body > div.flex > main > header {{ display:none !important; }}
  body > div.flex > main .bg-surface,
  body > div.flex > main .bg-sand,
  body > div.flex > main .bg-paper {{ background:transparent !important; }}
}}
@media (max-width:767px) {{
  body > div.flex {{ display:block !important; padding:0 24px 64px !important; }}
  body > div.flex > main {{ max-width:none !important; margin:0 !important; padding:28px 0 64px !important; }}
  body > div.flex > main > header {{ display:none !important; }}
  body > div.flex > main .bg-surface,
  body > div.flex > main .bg-sand,
  body > div.flex > main .bg-paper {{ background:transparent !important; }}
}}
</style>
""".strip()

_LESSON_BRIDGE_SCRIPT = """
(function () {
  var SRC = 'hituto-lesson-bridge';
  var events = [];   // ring buffer of recent learner interactions
  var autoN = 0;

  function ensureId(el, prefix) {
    if (el.id) return el.id;
    var id = prefix + '-' + (++autoN);
    while (document.getElementById(id)) id = prefix + '-' + (++autoN);
    el.id = id;
    return id;
  }
  function txt(s, n) { return (s || '').replace(/\\s+/g, ' ').trim().slice(0, n); }
  function pushEvent(evt) {
    evt.at = new Date().toISOString();
    events.push(evt);
    if (events.length > 15) events.shift();
  }
  function notifyLearning(eventType, payload) {
    try {
      window.parent.postMessage({
        source: SRC,
        type: 'HT_LEARNING_EVENT',
        payload: { eventType: eventType, data: payload || {} }
      }, '*');
    } catch (err) {}
  }
  function controlLabel(el) {
    return txt(el.getAttribute('aria-label') || el.dataset.lessonControl || el.innerText ||
               el.placeholder || el.name || el.type || el.tagName.toLowerCase(), 60);
  }
  function controlRole(el) {
    var t = el.tagName.toLowerCase();
    if (t === 'button' || (t === 'input' && (el.type === 'button' || el.type === 'submit'))) return 'button';
    if (t === 'input' && el.type === 'range') return 'range';
    if (t === 'select') return 'select';
    if (t === 'textarea') return 'textarea';
    if (t === 'input') return 'input';
    return 'other';
  }
  // NOTE: agent page control (snapshot/execute/Tutor cursor) moved to the GuideBridge
  // iframe runtime, injected separately (guidebridge.iframe). This bridge now carries
  // only Hi-Tuto features: edit mode, learning events, and HTML export.

  // --- Edit mode (in-iframe contenteditable; parent cannot access opaque DOM) ---
  var editMode = false;
  var selectedEl = null;
  var hoverEl = null;
  var editPrev = null; // { el, outline, offset, contentEditable }

  function isUnsafeEditTarget(el) {
    if (!el || el.nodeType !== 1) return true;
    var t = el.tagName.toLowerCase();
    return t === 'html' || t === 'body' || t === 'script' || t === 'style' ||
           t === 'canvas' || t === 'svg' || t === 'iframe' || t === 'video' || t === 'audio';
  }
  function pickEditable(from) {
    if (!from || !from.closest) return null;
    var el = from.closest('[data-lesson-section],section,[data-lesson-control],article,main,h1,h2,h3,p,li,label,button,a,div');
    if (!el) el = from;
    while (el && isUnsafeEditTarget(el)) el = el.parentElement;
    if (!el || el === document.body || el === document.documentElement) return null;
    // Prefer a sized block over tiny wrappers
    var r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) {
      var up = el.parentElement;
      while (up && up !== document.body) {
        if (!isUnsafeEditTarget(up)) {
          var ur = up.getBoundingClientRect();
          if (ur.width >= 8 && ur.height >= 8) { el = up; break; }
        }
        up = up.parentElement;
      }
    }
    return el;
  }
  function clearEditChrome() {
    if (hoverEl && hoverEl !== selectedEl) {
      hoverEl.style.outline = '';
      hoverEl.style.outlineOffset = '';
      hoverEl = null;
    }
    if (selectedEl) {
      if (editPrev && editPrev.el === selectedEl) {
        selectedEl.style.outline = editPrev.outline || '';
        selectedEl.style.outlineOffset = editPrev.offset || '';
        if (editPrev.contentEditable != null)
          selectedEl.contentEditable = editPrev.contentEditable;
        else selectedEl.removeAttribute('contenteditable');
      } else {
        selectedEl.style.outline = '';
        selectedEl.style.outlineOffset = '';
        selectedEl.removeAttribute('contenteditable');
      }
      selectedEl = null;
      editPrev = null;
    }
  }
  function selectForEdit(el) {
    if (!el) return;
    clearEditChrome();
    selectedEl = el;
    editPrev = {
      el: el,
      outline: el.style.outline,
      offset: el.style.outlineOffset,
      contentEditable: el.getAttribute('contenteditable')
    };
    el.style.outline = '2px solid #2C50EE';
    el.style.outlineOffset = '3px';
    // Do not contenteditable canvas-like or control-only nodes — climb already avoided canvas
    var t = el.tagName.toLowerCase();
    if (t !== 'button' && t !== 'input' && t !== 'select' && t !== 'textarea' && t !== 'a') {
      el.contentEditable = 'true';
      try { el.focus({ preventScroll: true }); } catch (err) { try { el.focus(); } catch (e2) {} }
    }
    var id = ensureId(el, 'tl-edit');
    var rect = el.getBoundingClientRect();
    var html = (el.outerHTML || '').slice(0, 12000);
    var sectionHost = el.closest ? el.closest('[data-lesson-section]') : null;
    var sectionId = (sectionHost && sectionHost.getAttribute('data-lesson-section'))
      || el.getAttribute('data-lesson-section')
      || null;
    window.parent.postMessage({
      source: SRC,
      type: 'HT_ELEMENT_SELECTED',
      payload: {
        id: id,
        tag: t,
        dataLessonSection: sectionId,
        dataLessonControl: el.getAttribute('data-lesson-control') || null,
        textSummary: txt(el.innerText, 200),
        outerHTML: html,
        rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
      }
    }, '*');
  }
  function onEditPointerOver(e) {
    if (!editMode) return;
    var el = pickEditable(e.target);
    if (!el || el === selectedEl) return;
    if (hoverEl && hoverEl !== selectedEl && hoverEl !== el) {
      hoverEl.style.outline = '';
      hoverEl.style.outlineOffset = '';
    }
    hoverEl = el;
    if (el !== selectedEl) {
      el.style.outline = '2px dashed rgba(44,80,238,0.55)';
      el.style.outlineOffset = '2px';
    }
  }
  function onEditPointerOut(e) {
    if (!editMode || !hoverEl) return;
    var el = hoverEl;
    if (el !== selectedEl) {
      el.style.outline = '';
      el.style.outlineOffset = '';
    }
    if (e.relatedTarget && el.contains(e.relatedTarget)) return;
    hoverEl = null;
  }
  function onEditClick(e) {
    if (!editMode) return;
    var el = pickEditable(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    selectForEdit(el);
  }
  function setEditMode(enabled) {
    enabled = !!enabled;
    if (enabled === editMode) return { enabled: editMode };
    editMode = enabled;
    if (editMode) {
      document.addEventListener('mouseover', onEditPointerOver, true);
      document.addEventListener('mouseout', onEditPointerOut, true);
      document.addEventListener('click', onEditClick, true);
      document.documentElement.style.cursor = 'crosshair';
    } else {
      document.removeEventListener('mouseover', onEditPointerOver, true);
      document.removeEventListener('mouseout', onEditPointerOut, true);
      document.removeEventListener('click', onEditClick, true);
      document.documentElement.style.cursor = '';
      clearEditChrome();
    }
    return { enabled: editMode };
  }
  function getDocumentHtml() {
    var was = editMode;
    if (was) setEditMode(false);
    // Strip any leftover contenteditable from a prior session
    document.querySelectorAll('[contenteditable]').forEach(function (n) {
      n.removeAttribute('contenteditable');
    });
    var html = '<!DOCTYPE html>\\n' + document.documentElement.outerHTML;
    if (was) setEditMode(true);
    return { html: html };
  }

  // Learner interaction capture → surfaced in snapshots ("what did I just press?").
  document.addEventListener('click', function (e) {
    if (editMode) return;
    var c = e.target && e.target.closest && e.target.closest('button,[data-lesson-control],a');
    if (c) {
      pushEvent({ type: 'click', id: c.id || null, label: controlLabel(c) });
      notifyLearning('capsule_control_used', {
        control: txt(c.dataset.lessonControl || c.id || controlRole(c), 80)
      });
    }
  }, true);

  // Owned Studio runtime → normalized, content-minimized events. The host still supplies
  // user/course/lesson identity and the API applies its strict per-event payload schema.
  document.addEventListener('hituto:studio-event', function (e) {
    var detail = e && e.detail;
    if (!detail || typeof detail.eventType !== 'string') return;
    var allowed = {
      studio_mode_opened: ['mode', 'manifest_version'],
      studio_part_selected: ['part_id'],
      studio_control_changed: ['control_id', 'value'],
      studio_playback_completed: ['sequence_id'],
      studio_reset: ['mode'],
      studio_degraded: ['reason_code', 'fallback_kind']
    };
    var keys = allowed[detail.eventType];
    if (!keys) return;
    var source = detail.data && typeof detail.data === 'object' ? detail.data : {};
    var data = {};
    keys.forEach(function (key) {
      if (source[key] !== undefined && source[key] !== null) data[key] = txt(source[key], 120);
    });
    notifyLearning(detail.eventType, data);
  });

  try {
    var observedSections = {};
    var sectionObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting || entry.intersectionRatio < 0.5) return;
        var section = entry.target;
        var id = txt(section.dataset.lessonSection || ensureId(section, 'tl-sec'), 80);
        if (observedSections[id]) return;
        observedSections[id] = true;
        notifyLearning('capsule_section_viewed', { section_id: id });
      });
    }, { threshold: [0.5] });
    var learnerSections = document.querySelectorAll('[data-lesson-section],section');
    learnerSections.forEach(function (section) { sectionObserver.observe(section); });
  } catch (err) {}
  document.addEventListener('input', function (e) {
    var c = e.target;
    if (c && ('value' in c))
      pushEvent({ type: 'input', id: c.id || null, label: controlLabel(c), value: String(c.value).slice(0, 60) });
  }, true);

  window.addEventListener('message', function (e) {
    if (e.source !== window.parent) return;                 // only the embedding studio
    var d = e.data;
    if (!d || d.source !== SRC || !d.type) return;
    var reply = { source: SRC, requestId: d.requestId };
    try {
      if (d.type === 'HT_PING') { reply.type = 'HT_PONG'; reply.payload = { version: '8' }; }
      else if (d.type === 'HT_SET_EDIT_MODE') {
        reply.type = 'HT_EDIT_MODE';
        reply.payload = setEditMode(d.payload && d.payload.enabled);
      }
      else if (d.type === 'HT_GET_HTML') { reply.type = 'HT_HTML'; reply.payload = getDocumentHtml(); }
      else return;
    } catch (err) {
      reply.type = 'HT_ERROR'; reply.payload = { error: String(err) };
    }
    window.parent.postMessage(reply, '*');
  });
  window.parent.postMessage({ source: SRC, type: 'HT_BRIDGE_READY', payload: { version: '8' } }, '*');
})();
"""

_MESH_MARKER = "hituto-mesh-runtime v15"
_MESH_SCRIPT = """
(function () {
  function notifyDegraded(holder, reason) {
    if (holder && holder.dataset.hitutoDegradedReported === '1') return;
    if (holder) holder.dataset.hitutoDegradedReported = '1';
    document.dispatchEvent(new CustomEvent('hituto:studio-event', {
      detail: {
        eventType: 'studio_degraded',
        data: { reason_code: reason, fallback_kind: 'procedural_specimen' }
      }
    }));
  }
  function findCanvas(holder) {
    var id = holder.getAttribute('data-mesh-canvas');
    if (id) return document.getElementById(id);
    var parent = holder.closest('section, main, div') || document;
    return parent.querySelector('canvas');
  }
  function initialOrientation(holder) {
    var yawValue = holder ? (holder.getAttribute('data-mesh-yaw') || '') : '';
    var pitchValue = holder ? (holder.getAttribute('data-mesh-pitch') || '') : '';
    // Compatibility for already-persisted Pollinator Studio artifacts. New
    // artifacts carry these values in their manifest; old ones can still resolve
    // the reviewed view from the selected mesh URL and stable subject id.
    var manifest = window.__HITUTO_STUDIO_MANIFEST__;
    var meshSrc = holder ? holder.getAttribute('data-mesh-src') : '';
    var subject = manifest && Array.isArray(manifest.subjects)
      ? manifest.subjects.find(function (item) { return item.mesh_src === meshSrc; })
      : null;
    var reviewed = {
      'garden-tiger': { yaw: 0, pitch: 0 },
      'jewel-beetle': { yaw: 3.14159, pitch: 0 },
      'lesser-long-nosed-bat': { yaw: -1.5708, pitch: 0 }
    };
    var subjectView = subject && reviewed[subject.id];
    if (yawValue === '' && subject && subject.initial_yaw != null) {
      yawValue = String(subject.initial_yaw);
    }
    if (pitchValue === '' && subject && subject.initial_pitch != null) {
      pitchValue = String(subject.initial_pitch);
    }
    if (yawValue === '' && subjectView) yawValue = String(subjectView.yaw);
    if (pitchValue === '' && subjectView) pitchValue = String(subjectView.pitch);
    var yaw = yawValue !== '' ? Number(yawValue) : 0.55;
    var pitch = pitchValue !== '' ? Number(pitchValue) : -0.35;
    return {
      yaw: Number.isFinite(yaw) ? yaw : 0.55,
      pitch: Number.isFinite(pitch) ? pitch : -0.35
    };
  }
  function disposeObject(root) {
    if (!root || !root.traverse) return;
    root.traverse(function (node) {
      if (node.geometry && node.geometry.dispose) node.geometry.dispose();
      if (!node.material) return;
      var materials = Array.isArray(node.material) ? node.material : [node.material];
      materials.forEach(function (material) {
        Object.keys(material).forEach(function (key) {
          var value = material[key];
          if (value && value.isTexture && value.dispose) value.dispose();
        });
        if (material.dispose) material.dispose();
      });
    });
  }
  function clearGroup(group) {
    while (group.children.length) {
      var child = group.children[0];
      group.remove(child);
      disposeObject(child);
    }
  }
  function fitObject(obj, targetSize) {
    var box = new THREE.Box3().setFromObject(obj);
    var size = box.getSize(new THREE.Vector3());
    var maxDim = Math.max(size.x, size.y, size.z, 0.001);
    obj.scale.setScalar((targetSize || 2.4) / maxDim);
    box.setFromObject(obj);
    var center = box.getCenter(new THREE.Vector3());
    obj.position.sub(center);
  }
  function tuneMaterials(root) {
    root.traverse(function (o) {
      if (!o.isMesh || !o.material) return;
      var mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach(function (m) {
        if ('metalnessMap' in m) m.metalnessMap = null;
        if ('metalness' in m) m.metalness = 0.05;
        if ('roughness' in m) m.roughness = Math.max(Number(m.roughness) || 0, 0.65);
        if ('envMapIntensity' in m) m.envMapIntensity = 0.2;
        if (m.map) {
          if (THREE.sRGBEncoding) m.map.encoding = THREE.sRGBEncoding;
          if (THREE.SRGBColorSpace) m.map.colorSpace = THREE.SRGBColorSpace;
          m.map.needsUpdate = true;
        }
        m.side = THREE.DoubleSide;
        m.needsUpdate = true;
      });
    });
  }
  function material(color, options) {
    var settings = options || {};
    return new THREE.MeshStandardMaterial({
      color: color,
      roughness: settings.roughness == null ? 0.58 : settings.roughness,
      metalness: settings.metalness || 0,
      transparent: !!settings.transparent,
      opacity: settings.opacity == null ? 1 : settings.opacity,
      depthWrite: settings.depthWrite !== false,
      side: settings.doubleSide ? THREE.DoubleSide : THREE.FrontSide
    });
  }
  function addSphere(group, position, scale, color, options) {
    var mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 20), material(color, options));
    mesh.position.copy(position);
    mesh.scale.copy(scale);
    group.add(mesh);
    return mesh;
  }
  function addCylinderBetween(group, start, end, radius, color, options) {
    var direction = end.clone().sub(start);
    var length = Math.max(0.001, direction.length());
    var mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, length, 18, 1, false),
      material(color, options)
    );
    mesh.position.copy(start.clone().add(end).multiplyScalar(0.5));
    mesh.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      direction.normalize()
    );
    group.add(mesh);
    return mesh;
  }
  function addTube(group, points, radius, color, options) {
    var curve = new THREE.CatmullRomCurve3(points);
    var geometry = new THREE.TubeGeometry(
      curve,
      Math.max(18, points.length * 10),
      radius,
      9,
      false
    );
    var mesh = new THREE.Mesh(geometry, material(color, options));
    group.add(mesh);
    return mesh;
  }
  function addCapsule(group, length, radius, color, options) {
    addCylinderBetween(
      group,
      new THREE.Vector3(-length / 2, 0, 0),
      new THREE.Vector3(length / 2, 0, 0),
      radius,
      color,
      options
    );
    addSphere(
      group,
      new THREE.Vector3(-length / 2, 0, 0),
      new THREE.Vector3(radius, radius, radius),
      color,
      options
    );
    addSphere(
      group,
      new THREE.Vector3(length / 2, 0, 0),
      new THREE.Vector3(radius, radius, radius),
      color,
      options
    );
  }
  function makePlantCell(group) {
    var wall = new THREE.Mesh(
      new THREE.BoxGeometry(2.35, 1.75, 1.15),
      material(0x72c95a, {
        transparent: true,
        opacity: 0.28,
        depthWrite: false,
        doubleSide: true
      })
    );
    group.add(wall);
    var edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(2.35, 1.75, 1.15)),
      new THREE.LineBasicMaterial({ color: 0x2e7d32, transparent: true, opacity: 0.9 })
    );
    group.add(edges);
    addSphere(
      group,
      new THREE.Vector3(0.25, 0, 0),
      new THREE.Vector3(0.72, 0.58, 0.38),
      0x9bdce5,
      { transparent: true, opacity: 0.68, depthWrite: false }
    );
    addSphere(
      group,
      new THREE.Vector3(-0.63, 0.22, 0.24),
      new THREE.Vector3(0.3, 0.3, 0.3),
      0x7656a8
    );
    addSphere(
      group,
      new THREE.Vector3(-0.63, 0.22, 0.24),
      new THREE.Vector3(0.12, 0.12, 0.12),
      0xf4c84a
    );
    [
      [-0.72, -0.48, 0.22],
      [-0.1, 0.62, -0.2],
      [0.72, 0.48, 0.18],
      [0.82, -0.43, -0.16],
      [-0.35, -0.62, -0.18]
    ].forEach(function (item) {
      addSphere(
        group,
        new THREE.Vector3(item[0], item[1], item[2]),
        new THREE.Vector3(0.25, 0.12, 0.1),
        0x2f984b
      );
    });
  }
  function makeAnimalCell(group) {
    addSphere(
      group,
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(1.18, 0.92, 0.78),
      0x9bd8ef,
      { transparent: true, opacity: 0.25, depthWrite: false, doubleSide: true }
    );
    addSphere(
      group,
      new THREE.Vector3(-0.28, 0.1, 0.14),
      new THREE.Vector3(0.42, 0.4, 0.38),
      0x8264b2,
      { transparent: true, opacity: 0.86 }
    );
    addSphere(
      group,
      new THREE.Vector3(-0.28, 0.1, 0.14),
      new THREE.Vector3(0.15, 0.15, 0.15),
      0xf4c84a
    );
    [
      [0.52, 0.38, 0.18],
      [0.58, -0.33, -0.15],
      [-0.62, -0.4, 0.05],
      [0.15, 0.58, -0.2]
    ].forEach(function (item) {
      addSphere(
        group,
        new THREE.Vector3(item[0], item[1], item[2]),
        new THREE.Vector3(0.25, 0.12, 0.1),
        0xe16d52
      );
    });
    for (var arc = 0; arc < 4; arc += 1) {
      var golgi = new THREE.Mesh(
        new THREE.TorusGeometry(0.26 + arc * 0.06, 0.025, 8, 32, Math.PI * 1.35),
        material(0xf0a44b)
      );
      golgi.position.set(0.34, 0.03, 0.28);
      golgi.rotation.set(0.25, 0.6, -0.5);
      group.add(golgi);
    }
  }
  function makeBacterium(group) {
    addCapsule(
      group,
      1.55,
      0.54,
      0x69b96d,
      { transparent: true, opacity: 0.78, doubleSide: true }
    );
    var dna = [];
    for (var point = 0; point <= 18; point += 1) {
      var t = point / 18;
      dna.push(new THREE.Vector3(
        -0.52 + t * 1.04,
        Math.sin(t * Math.PI * 4) * 0.18,
        Math.cos(t * Math.PI * 4) * 0.12
      ));
    }
    addTube(group, dna, 0.035, 0xf4c84a);
    for (var index = 0; index < 14; index += 1) {
      var angle = index / 14 * Math.PI * 2;
      var x = -0.62 + (index % 5) * 0.31;
      var start = new THREE.Vector3(x, Math.cos(angle) * 0.48, Math.sin(angle) * 0.42);
      var end = start.clone().add(new THREE.Vector3(
        Math.sin(index * 1.7) * 0.14,
        Math.cos(angle) * 0.34,
        Math.sin(angle) * 0.3
      ));
      addTube(group, [start, end], 0.025, 0x3f8150);
    }
    addTube(
      group,
      [
        new THREE.Vector3(0.77, -0.12, 0),
        new THREE.Vector3(1.25, -0.42, 0.1),
        new THREE.Vector3(1.72, 0.05, -0.08),
        new THREE.Vector3(2.12, -0.32, 0.05)
      ],
      0.045,
      0x3f8150
    );
  }
  function makeNeuron(group) {
    addSphere(
      group,
      new THREE.Vector3(-0.45, 0, 0),
      new THREE.Vector3(0.5, 0.42, 0.42),
      0x6b70c7
    );
    addSphere(
      group,
      new THREE.Vector3(-0.45, 0, 0.12),
      new THREE.Vector3(0.2, 0.2, 0.18),
      0xf4a742
    );
    for (var index = 0; index < 10; index += 1) {
      var angle = 0.48 + index / 9 * (Math.PI * 2 - 0.96);
      var z = Math.sin(index * 1.9) * 0.24;
      var start = new THREE.Vector3(
        -0.45 + Math.cos(angle) * 0.43,
        Math.sin(angle) * 0.35,
        z * 0.5
      );
      var mid = new THREE.Vector3(
        -0.45 + Math.cos(angle) * 0.8,
        Math.sin(angle) * 0.68,
        z
      );
      var end = new THREE.Vector3(
        -0.45 + Math.cos(angle + Math.sin(index) * 0.12) * 1.22,
        Math.sin(angle + Math.cos(index) * 0.1) * 1.02,
        z * 1.35
      );
      addTube(group, [start, mid, end], 0.055, 0x6775c9);
      var branchA = end.clone().add(new THREE.Vector3(
        Math.cos(angle + 0.42) * 0.3,
        Math.sin(angle + 0.42) * 0.3,
        0.12
      ));
      var branchB = end.clone().add(new THREE.Vector3(
        Math.cos(angle - 0.42) * 0.28,
        Math.sin(angle - 0.42) * 0.28,
        -0.1
      ));
      addTube(group, [mid, end, branchA], 0.032, 0x8190dc);
      addTube(group, [end, branchB], 0.032, 0x8190dc);
    }
    var axon = [
      new THREE.Vector3(0.02, -0.06, 0),
      new THREE.Vector3(0.62, -0.12, 0.04),
      new THREE.Vector3(1.25, -0.2, -0.02),
      new THREE.Vector3(1.95, -0.12, 0.04)
    ];
    addTube(group, axon, 0.075, 0xd49a62);
    for (var segment = 0; segment < 5; segment += 1) {
      var x = 0.38 + segment * 0.3;
      addCylinderBetween(
        group,
        new THREE.Vector3(x, -0.11 - segment * 0.012, 0.02),
        new THREE.Vector3(x + 0.2, -0.13 - segment * 0.012, 0.01),
        0.13,
        0xe8ddb0
      );
    }
    [0.45, 0, -0.45].forEach(function (offset) {
      addTube(
        group,
        [
          new THREE.Vector3(1.92, -0.12, 0.04),
          new THREE.Vector3(2.2, -0.12 + offset * 0.45, offset * 0.32),
          new THREE.Vector3(2.42, -0.1 + offset, offset * 0.5)
        ],
        0.035,
        0xd49a62
      );
    });
  }
  function makeMuscleFiber(group) {
    addCapsule(
      group,
      2.55,
      0.46,
      0xd97a82,
      { transparent: true, opacity: 0.72, doubleSide: true }
    );
    for (var index = 0; index < 13; index += 1) {
      var ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.465, 0.026, 8, 36),
        material(index % 2 ? 0xf0b0aa : 0x9d4658)
      );
      ring.position.x = -1.18 + index * 0.197;
      ring.rotation.y = Math.PI / 2;
      group.add(ring);
    }
    [
      [-0.82, 0.32, 0.19],
      [0.05, -0.34, 0.16],
      [0.88, 0.28, -0.2]
    ].forEach(function (item) {
      addSphere(
        group,
        new THREE.Vector3(item[0], item[1], item[2]),
        new THREE.Vector3(0.18, 0.08, 0.06),
        0x6950a1
      );
    });
    [-0.22, 0, 0.22].forEach(function (offset) {
      addCylinderBetween(
        group,
        new THREE.Vector3(-1.25, offset, 0.12),
        new THREE.Vector3(1.25, offset, 0.12),
        0.035,
        0xf6c7a5
      );
    });
  }
  function proceduralFallback(scene, group, kind) {
    clearGroup(group);
    if (kind === 'plant-cell') makePlantCell(group);
    else if (kind === 'animal-cell') makeAnimalCell(group);
    else if (kind === 'bacteria') makeBacterium(group);
    else if (kind === 'neuron') makeNeuron(group);
    else if (kind === 'muscle-fiber') makeMuscleFiber(group);
    else {
      var core = new THREE.Mesh(
        new THREE.IcosahedronGeometry(0.9, 2),
        material(0x3c7a2b, { roughness: 0.55 })
      );
      group.add(core);
    }
    fitObject(group, 2.65);
    group.rotation.set(-0.22, 0.42, 0);
  }
  function clearStageOverlays(canvas) {
    // Lesson HTML often stacks absolute chips/labels on the canvas; those steal drags
    // and make the mesh feel like a non-interactive GIF.
    var wrap = canvas.parentElement;
    if (!wrap) return;
    canvas.style.position = 'relative';
    canvas.style.zIndex = '2';
    Array.prototype.forEach.call(wrap.querySelectorAll('.absolute, [class*=\"absolute\"]'), function (el) {
      if (el === canvas || el.contains(canvas)) return;
      var interactive = el.querySelectorAll('button, a, input, select, textarea, [role=\"button\"]');
      if (interactive.length) {
        el.style.pointerEvents = 'none';
        Array.prototype.forEach.call(interactive, function (node) {
          node.style.pointerEvents = 'auto';
          node.style.position = 'relative';
          node.style.zIndex = '3';
        });
      } else {
        el.style.pointerEvents = 'none';
      }
    });
  }
  function wireZoomButtons(camera, canvas) {
    var root = (canvas.closest('section, main, div') || document);
    function dolly(factor) {
      var dist = Math.max(1.6, Math.min(10, camera.position.length() * factor));
      var dir = camera.position.clone().normalize();
      if (dir.lengthSq() < 0.001) dir.set(0, 0.1, 1).normalize();
      camera.position.copy(dir.multiplyScalar(dist));
      camera.lookAt(0, 0, 0);
    }
    Array.prototype.forEach.call(root.querySelectorAll('button'), function (btn) {
      var label = ((btn.getAttribute('aria-label') || btn.title || btn.textContent || '') + '').toLowerCase();
      if (label.indexOf('zoom in') >= 0 || label === '+') {
        btn.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); dolly(0.85); }, true);
      } else if (label.indexOf('zoom out') >= 0 || label === '−' || label === '-') {
        btn.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); dolly(1.18); }, true);
      } else if (label.indexOf('reset') >= 0) {
        btn.addEventListener('click', function (e) {
          e.preventDefault(); e.stopPropagation();
          camera.position.set(0, 0.35, 3.6);
          camera.lookAt(0, 0, 0);
        }, true);
      }
    });
  }
  function bindControls(canvas, camera, group) {
    var dragging = false;
    var moved = false;
    var lastX = 0;
    var lastY = 0;
    var yaw = group.rotation.y || 0;
    var pitch = group.rotation.x || 0;
    var auto = true;
    var dist = camera.position.length();

    canvas.style.touchAction = 'none';
    canvas.style.cursor = 'grab';
    canvas.style.userSelect = 'none';
    clearStageOverlays(canvas);
    wireZoomButtons(camera, canvas);

    function onPointerDown(e) {
      // The model may finish loading after controls are bound. Re-sync here so
      // the first learner drag continues from the reviewed presentation angle.
      if (Number.isFinite(canvas.__tlMeshYaw)) yaw = canvas.__tlMeshYaw;
      else yaw = group.rotation.y || 0;
      if (Number.isFinite(canvas.__tlMeshPitch)) pitch = canvas.__tlMeshPitch;
      else pitch = group.rotation.x || 0;
      dragging = true;
      moved = false;
      auto = false;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.style.cursor = 'grabbing';
      try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
      e.stopPropagation();
    }
    function onPointerMove(e) {
      if (!dragging) return;
      var dx = e.clientX - lastX;
      var dy = e.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      lastX = e.clientX;
      lastY = e.clientY;
      yaw += dx * 0.01;
      pitch = Math.max(-1.2, Math.min(1.2, pitch + dy * 0.01));
      group.rotation.set(pitch, yaw, 0);
      canvas.__tlMeshYaw = yaw;
      canvas.__tlMeshPitch = pitch;
      e.preventDefault();
      e.stopPropagation();
    }
    function onPointerUp(e) {
      dragging = false;
      canvas.style.cursor = 'grab';
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
      e.stopPropagation();
    }
    function onWheel(e) {
      auto = false;
      dist = Math.max(1.6, Math.min(10, dist + e.deltaY * 0.004));
      var dir = camera.position.clone().normalize();
      if (dir.lengthSq() < 0.001) dir.set(0, 0.1, 1).normalize();
      camera.position.copy(dir.multiplyScalar(dist));
      camera.lookAt(0, 0, 0);
      e.preventDefault();
      e.stopPropagation();
    }

    canvas.addEventListener('pointerdown', onPointerDown, true);
    canvas.addEventListener('pointermove', onPointerMove, true);
    canvas.addEventListener('pointerup', onPointerUp, true);
    canvas.addEventListener('pointercancel', onPointerUp, true);
    canvas.addEventListener('wheel', onWheel, { capture: true, passive: false });

    return {
      tickAuto: function () {
        // No idle spin — auto-rotate reads as a GIF and hides that drag works.
      }
    };
  }
  function prepareStage(canvas) {
    var wrap = canvas.parentElement;
    var stage = canvas.closest('.stage-card, .stage-canvas-host, .viewer-section, [data-lesson-section=\"viewer\"]') || wrap;
    if (stage) {
      stage.style.position = stage.style.position || 'relative';
      stage.style.overflow = 'hidden';
      stage.style.isolation = 'isolate';
    }
    if (wrap) {
      wrap.style.position = wrap.style.position || 'relative';
      // Replace fixed Tailwind h-56 squeeze with a stable stage aspect.
      wrap.style.height = 'auto';
      wrap.style.minHeight = '240px';
      wrap.style.aspectRatio = '16 / 10';
      wrap.style.overflow = 'hidden';
      wrap.style.isolation = 'isolate';
    }
    canvas.style.display = 'block';
    canvas.style.position = 'relative';
    canvas.style.zIndex = '1';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.maxWidth = '100%';
    canvas.style.maxHeight = '100%';
    canvas.style.objectFit = 'contain';
  }
  function releaseMounted(canvas) {
    if (!canvas) return;
    if (canvas.__tlMeshFrame) cancelAnimationFrame(canvas.__tlMeshFrame);
    canvas.__tlMeshFrame = 0;
    if (canvas.__tlMeshRo) {
      try { canvas.__tlMeshRo.disconnect(); } catch (e) {}
      canvas.__tlMeshRo = null;
    }
    var mounted = canvas.__tlMeshMounted;
    if (!mounted) return;
    if (mounted.group) clearGroup(mounted.group);
    if (mounted.renderer) {
      try { mounted.renderer.clear(true, true, true); } catch (e2) {}
      try { mounted.renderer.dispose(); } catch (e3) {}
    }
    canvas.__tlMeshMounted = null;
  }
  function mountScene(canvas, group) {
    if (!canvas || typeof THREE === 'undefined') return null;
    releaseMounted(canvas);

    prepareStage(canvas);
    var wrap = canvas.parentElement;

    var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    if ('outputEncoding' in renderer && THREE.sRGBEncoding) renderer.outputEncoding = THREE.sRGBEncoding;
    if ('outputColorSpace' in renderer && THREE.SRGBColorSpace) renderer.outputColorSpace = THREE.SRGBColorSpace;
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f2ea);
    var camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
    // Offset so a cross-section reads as 3D depth, not a flat disc.
    camera.position.set(1.6, 1.1, 3.2);
    camera.lookAt(0, 0, 0);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    scene.add(new THREE.HemisphereLight(0xffffff, 0xb0a090, 0.45));
    var light = new THREE.DirectionalLight(0xffffff, 1.35);
    light.position.set(2.5, 3.5, 4);
    scene.add(light);
    var fill = new THREE.DirectionalLight(0xfff2e0, 0.45);
    fill.position.set(-3, 1, -2);
    scene.add(fill);
    scene.add(group);

    function resize() {
      var rect = canvas.getBoundingClientRect();
      var w = Math.max(2, Math.floor(rect.width || canvas.clientWidth || 640));
      var h = Math.max(2, Math.floor(rect.height || canvas.clientHeight || 420));
      if (h < 140) h = 220;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    var ro = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(function () { resize(); });
      ro.observe(wrap || canvas);
      canvas.__tlMeshRo = ro;
    }
    window.addEventListener('resize', resize);

    var controls = bindControls(canvas, camera, group);
    function tick() {
      controls.tickAuto();
      renderer.render(scene, camera);
      canvas.__tlMeshFrame = requestAnimationFrame(tick);
    }
    tick();
    var mounted = {
      renderer: renderer,
      scene: scene,
      camera: camera,
      group: group,
      resize: resize
    };
    canvas.__tlMeshMounted = mounted;
    return mounted;
  }
  function claimCanvas(canvas) {
    // Lesson HTML often attaches its own Three.js loop + drag handlers to the same
    // canvas. Replace the node so we own WebGL + pointer events exclusively.
    if (canvas.dataset.tlClaimed === '1') return canvas;
    var fresh = canvas.cloneNode(false);
    fresh.id = canvas.id;
    Array.prototype.forEach.call(canvas.attributes, function (attr) {
      if (attr.name === 'id') return;
      fresh.setAttribute(attr.name, attr.value);
    });
    if (canvas.parentNode) canvas.parentNode.replaceChild(fresh, canvas);
    fresh.dataset.tlClaimed = '1';
    return fresh;
  }
  function loadMesh(holder) {
    if (holder.dataset.hitutoMeshBound) return;
    holder.dataset.hitutoMeshBound = '1';
    var src = holder.getAttribute('data-mesh-src');
    var proceduralKind = holder.getAttribute('data-procedural-kind') || '';
    if (!src && !proceduralKind) return;
    var requestId = String((Number(holder.dataset.hitutoMeshRequest || 0) || 0) + 1);
    holder.dataset.hitutoMeshRequest = requestId;
    holder.dataset.hitutoDegradedReported = '';
    var canvas = findCanvas(holder);
    if (!canvas) { notifyDegraded(holder, 'mesh_canvas_missing'); return; }
    if (typeof THREE === 'undefined') { notifyDegraded(holder, 'three_unavailable'); return; }
    canvas = claimCanvas(canvas);
    if (canvas.id) holder.setAttribute('data-mesh-canvas', canvas.id);
    var group = new THREE.Group();
    var mounted = mountScene(canvas, group);
    if (!mounted) { notifyDegraded(holder, 'webgl_unavailable'); return; }
    canvas.addEventListener('webglcontextlost', function (ev) {
      try { ev.preventDefault(); } catch (e) {}
      holder.dataset.hitutoMeshBound = '';
      canvas.dataset.tlClaimed = '';
      setTimeout(function () { loadMesh(holder); }, 60);
    }, false);
    if (!src && proceduralKind) {
      proceduralFallback(mounted.scene, group, proceduralKind);
      return;
    }
    if (typeof THREE.GLTFLoader === 'undefined') {
      proceduralFallback(mounted.scene, group, proceduralKind);
      notifyDegraded(holder, 'gltf_loader_unavailable');
      return;
    }
    fetch(src).then(function (r) {
      if (!r.ok) throw new Error('mesh fetch failed');
      return r.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var loader = new THREE.GLTFLoader();
      loader.load(url, function (gltf) {
        URL.revokeObjectURL(url);
        if (holder.dataset.hitutoMeshRequest !== requestId) {
          disposeObject(gltf.scene || gltf.scenes[0]);
          return;
        }
        clearGroup(group);
        var root = gltf.scene || gltf.scenes[0];
        tuneMaterials(root);
        fitObject(root, 2.4);
        root.traverse(function (o) {
          if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; }
        });
        group.add(root);
        var orientation = initialOrientation(holder);
        group.rotation.set(orientation.pitch, orientation.yaw, 0);
        canvas.__tlMeshPitch = orientation.pitch;
        canvas.__tlMeshYaw = orientation.yaw;
        if (mounted.resize) mounted.resize();
      }, undefined, function () {
        URL.revokeObjectURL(url);
        if (holder.dataset.hitutoMeshRequest !== requestId) return;
        proceduralFallback(mounted.scene, group, proceduralKind);
        notifyDegraded(holder, 'mesh_decode_failed');
      });
    }).catch(function () {
      if (holder.dataset.hitutoMeshRequest !== requestId) return;
      proceduralFallback(mounted.scene, group, proceduralKind);
      notifyDegraded(holder, 'mesh_fetch_failed');
    });
  }
  function scan(root) {
    (root || document)
      .querySelectorAll('[data-mesh-src], [data-procedural-kind]')
      .forEach(loadMesh);
  }
  function reloadMesh(holder) {
    if (!holder) return;
    holder.dataset.hitutoMeshBound = '';
    loadMesh(holder);
  }
  function clearMesh(holder) {
    if (!holder) return;
    holder.dataset.hitutoMeshRequest = String(
      (Number(holder.dataset.hitutoMeshRequest || 0) || 0) + 1
    );
    holder.dataset.hitutoMeshBound = '';
    var canvas = findCanvas(holder);
    releaseMounted(canvas);
    if (canvas) canvas.style.visibility = 'hidden';
  }
  function resetMesh(holder) {
    if (!holder) return;
    var canvas = findCanvas(holder);
    var mounted = canvas && canvas.__tlMeshMounted;
    if (!mounted) return;
    var orientation = initialOrientation(holder);
    mounted.group.rotation.set(orientation.pitch, orientation.yaw, 0);
    canvas.__tlMeshPitch = orientation.pitch;
    canvas.__tlMeshYaw = orientation.yaw;
    mounted.camera.position.set(1.6, 1.1, 3.2);
    mounted.camera.lookAt(0, 0, 0);
  }
  window.__hitutoReloadMesh = reloadMesh;
  window.__hitutoClearMesh = clearMesh;
  window.__hitutoResetMesh = resetMesh;
  function reclaimLater() {
    // Lesson inline scripts often mount Three.js *after* us and steal the WebGL
    // context — leaving a non-interactive blue sphere. Reclaim once they settle.
    document.querySelectorAll('[data-mesh-src], [data-procedural-kind]').forEach(function (holder) {
      var canvas = findCanvas(holder);
      var stolen = canvas && canvas.dataset.tlClaimed === '1' && !canvas.__tlMeshFrame;
      var unclaimed = canvas && canvas.dataset.tlClaimed !== '1';
      if (stolen || unclaimed) {
        holder.dataset.hitutoMeshBound = '';
        if (canvas) canvas.dataset.tlClaimed = '';
        loadMesh(holder);
      }
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { scan(); });
  } else scan();
  setTimeout(reclaimLater, 400);
  setTimeout(reclaimLater, 1500);
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.matches && n.matches('[data-mesh-src], [data-procedural-kind]')) loadMesh(n);
        scan(n);
      });
    });
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
"""
# Additive only — never changes inline layout unless the learner clicks.
_LIGHTBOX_SCRIPT = """
(function () {
  var overlay = null;
  var onKey = null;
  function isShimmer(src) { return !src || src.indexOf('data:image/svg') === 0; }
  function resolvedSrc(el) {
    var s = el.src || '';
    if (!isShimmer(s)) return s;
    return el.getAttribute('go-data-src') || '';
  }
  function closeLightbox() {
    if (overlay) { overlay.remove(); overlay = null; }
    if (onKey) { document.removeEventListener('keydown', onKey); onKey = null; }
    document.body.style.overflow = '';
  }
  function openLightbox(src, alt) {
    closeLightbox();
    overlay = document.createElement('div');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-label', alt || 'Expanded image');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(27,26,22,0.92);display:flex;align-items:center;justify-content:center;padding:24px;cursor:zoom-out';
    var img = document.createElement('img');
    img.src = src;
    img.alt = alt || '';
    img.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,0.35)';
    overlay.appendChild(img);
    overlay.addEventListener('click', closeLightbox);
    onKey = function (e) { if (e.key === 'Escape') closeLightbox(); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    document.body.appendChild(overlay);
  }
  function bindLightbox(el) {
    if (el.dataset.hitutoLightbox) return;
    el.dataset.hitutoLightbox = '1';
    el.style.cursor = 'zoom-in';
    if (!el.title) el.title = 'Click to view full image';
    el.addEventListener('click', function (e) {
      var src = resolvedSrc(el);
      if (!src) return;
      e.preventDefault();
      e.stopPropagation();
      openLightbox(src, el.alt);
    });
  }
  function scanLightbox(root) {
    (root || document).querySelectorAll('img[go-data-src]').forEach(bindLightbox);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { scanLightbox(); });
  } else scanLightbox();
  new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.matches && n.matches('img[go-data-src]')) bindLightbox(n);
        scanLightbox(n);
      });
    });
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
"""

# Shimmer placeholder shown before an image resolves, and a deterministic
# "no image" fallback so the page never renders a broken <img> (R6.5).
_RUNTIME_LOADER = (
    """
<script>
(function () {
  var SHIMMER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='9'%3E%3Crect width='16' height='9' fill='%23111827'/%3E%3C/svg%3E";
  function fallback(el){ el.style.opacity=0.4; el.alt=(el.alt||'')+' (image unavailable)'; }
  function resolve(el){
    var src = el.getAttribute('go-data-src'); if(!src) return;
    if(!el.getAttribute('src')) el.setAttribute('src', SHIMMER);
    var probe = new Image();
    probe.onload = function(){ el.src = src; el.style.opacity = 1; };
    probe.onerror = function(){ fallback(el); };
    probe.src = src;
  }
  function scan(root){ (root||document).querySelectorAll('img[go-data-src]').forEach(resolve); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function(){ scan(); });
  else scan();
  new MutationObserver(function(muts){ muts.forEach(function(m){
    if (m.type === 'attributes') {
      if (m.target && m.target.matches && m.target.matches('img[go-data-src]')) resolve(m.target);
      return;
    }
    m.addedNodes.forEach(function(n){
      if (n.nodeType === 1) { if (n.matches && n.matches('img[go-data-src]')) resolve(n); scan(n); }
    });
  });}).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['go-data-src']
  });

  // Sandboxed iframes (sandbox="allow-scripts", opaque origin) block native
  // #fragment navigation, so in-page anchor links do nothing. Intercept them
  // and scroll programmatically (only needs allow-scripts).
  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    if (!id) return;
    var t = document.getElementById(id);
    if (!t) return;
    e.preventDefault();
    t.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, true);
})();
// """
    + _LIGHTBOX_MARKER
    + """
"""
    + _LIGHTBOX_SCRIPT
    + """
</script>
"""
)


def _bridge_version_tag() -> str:
    return f"{_BRIDGE_MARKER} v{_BRIDGE_VERSION}"


def _bridge_patch() -> str:
    return f"<script>\n// {_bridge_version_tag()}\n{_LESSON_BRIDGE_SCRIPT.strip()}\n</script>"


def _strip_bridge(html: str) -> str:
    """Remove a previously injected bridge block (idempotent re-processing).

    Keeps postprocess() safe to run over already-served HTML: without this, our own
    injected `window.parent` usage would trip the parent-access rejection meant for
    MODEL code. Also strips legacy bridge markers.
    """
    html = re.sub(
        r"<script>\s*//\s*" + re.escape(_BRIDGE_MARKER) + r".*?</script>\s*",
        "",
        html,
        flags=re.S,
    )
    return re.sub(
        r"<script>\s*//\s*traillearn-lesson-bridge.*?</script>\s*",
        "",
        html,
        flags=re.S,
    )


def _migrate_legacy_branding(html: str) -> str:
    """Strip legacy runtime injections and rewrite author-facing APIs."""
    html = re.sub(
        r"<script>\s*//\s*traillearn-lightbox.*?</script>\s*",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"<script>\s*//\s*traillearn-ui-height.*?</script>\s*",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r'<style id="traillearn-chart-canvas-fix">.*?</style>\s*',
        "",
        html,
        flags=re.S,
    )
    html = html.replace("__traillearnReloadMesh", "__hitutoReloadMesh")
    html = html.replace("traillearnMeshBound", "hitutoMeshBound")
    html = html.replace("traillearnLightbox", "hitutoLightbox")
    html = html.replace("TrailLearnStudioOrbit", "HitutoStudioOrbit")
    html = html.replace("tl-agent-cursor", "ht-agent-cursor")
    legacy_generated_lesson = "#F5F2EA" in html and "Bricolage Grotesque" in html
    if legacy_generated_lesson:
        for old, new in _LEGACY_LESSON_THEME_REPLACEMENTS:
            html = html.replace(old, new)
        if _LEGACY_LESSON_THEME_MARKER not in html:
            html = _append_before_head_end(html, _LEGACY_LESSON_THEME_STYLE)
    return html


def _append_before_body(html: str, patch: str) -> str:
    if "</body>" in html:
        return html.replace("</body>", patch + "\n</body>", 1)
    return html + patch


def _append_before_head_end(html: str, patch: str) -> str:
    if "</head>" in html:
        return html.replace("</head>", patch + "\n</head>", 1)
    return patch + "\n" + html


def _strip_inline_script_fences(html: str) -> str:
    """Remove Markdown fences accidentally emitted inside inline JavaScript.

    A fenced block inside ``<script>`` is not a harmless formatting error: its first
    backtick starts a template literal and prevents the rest of the lesson script from
    parsing. Apply this at serve time too, so existing saved lessons recover without a
    regeneration.
    """
    def clean_script(match: re.Match) -> str:
        opening, body, closing = match.groups()
        if re.search(r"\bsrc\s*=", opening, flags=re.I):
            return match.group(0)
        body = re.sub(r"(?m)^[ \t]*```(?:javascript|js)?[ \t]*\r?\n?", "", body)
        return f"{opening}{body}{closing}"

    return re.sub(r"(<script\b[^>]*>)(.*?)(</script\s*>)", clean_script, html, flags=re.I | re.S)


def _strip_mesh_runtime(html: str) -> str:
    """Remove any previously injected hituto/traillearn mesh-runtime block."""
    html = re.sub(
        r"<script>\s*//\s*hituto-mesh-runtime[\s\S]*?</script\s*>",
        "",
        html,
        flags=re.I,
    )
    return re.sub(
        r"<script>\s*//\s*traillearn-mesh-runtime[\s\S]*?</script\s*>",
        "",
        html,
        flags=re.I,
    )


def _mesh_runtime_patch() -> str:
    return f"<script>\n// {_MESH_MARKER}\n{_MESH_SCRIPT.strip()}\n</script>"


def _ensure_pinned_mesh_scripts(html: str) -> str:
    """Rewrite stale three/GLTFLoader CDN tags and inject GLTFLoader when a mesh is present.

    Older artifacts pin three@0.160 whose examples/js/GLTFLoader 404s on jsDelivr, so the
    runtime falls back to procedural spheres. Serving always rewrites to the pinned pair.
    """
    html = re.sub(
        r"""https://cdn\.jsdelivr\.net/npm/three@[^"'>\s]+/build/three\.min\.js""",
        THREE_JS_CDN,
        html,
    )
    html = re.sub(
        r"""https://(?:cdn\.jsdelivr\.net/npm/three@[^"'>\s]+|unpkg\.com/three@[^"'>\s]+)/examples/js/loaders/GLTFLoader\.js""",
        GLTF_LOADER_CDN,
        html,
    )
    if "data-mesh-src" not in html:
        return html
    if GLTF_LOADER_CDN in html:
        return html
    # Inject GLTFLoader immediately after the pinned three.js tag when missing.
    three_tag = f'<script src="{THREE_JS_CDN}"></script>'
    loader_tag = f'<script src="{GLTF_LOADER_CDN}"></script>'
    if three_tag in html:
        return html.replace(three_tag, three_tag + "\n" + loader_tag, 1)
    return html.replace("<head>", f"<head>\n{three_tag}\n{loader_tag}", 1)


def ensure_artifact_runtime(html: str) -> str:
    """Patch served artifact HTML with runtime features missing from older generations."""
    html = _migrate_legacy_branding(html)
    html = _strip_inline_script_fences(html)
    html = _materialize_lesson_ids(html)
    html = _ensure_chart_canvas_css(html)
    html = _normalize_reading_column_width(html)
    html = _ensure_pinned_mesh_scripts(html)
    if _LIGHTBOX_MARKER not in html:
        html = _append_before_body(
            html, f"<script>\n// {_LIGHTBOX_MARKER}\n{_LIGHTBOX_SCRIPT.strip()}\n</script>"
        )
    if _bridge_version_tag() not in html:
        # Replace any older-version bridge (or inject fresh) so stored artifacts pick up
        # new behavior without regeneration. Older fat bridges (v6/v7, which still carried
        # page control) are stripped version-agnostically and replaced by the slim v8.
        html = _append_before_body(_strip_bridge(html), _bridge_patch())
    if f"{IFRAME_RUNTIME_MARKER} v{IFRAME_RUNTIME_VERSION}" not in html:
        # GuideBridge page-control runtime (agent observe/act + Tutor cursor); replaces
        # any older runtime version at serve time.
        html = inject_iframe_runtime(html)
    if _HEIGHT_MARKER not in html:
        html = _append_before_body(
            html, f"<script>\n// {_HEIGHT_MARKER}\n{_HEIGHT_SCRIPT.strip()}\n</script>"
        )
    if "data-mesh-src" in html and _MESH_MARKER not in html:
        html = _append_before_body(_strip_mesh_runtime(html), _mesh_runtime_patch())
    return html


# Content-height reporter for auto-sizing a capsule iframe (generate_ui / Path B). Posts a
# HT_UI_HEIGHT message to the parent via the same bridge SOURCE + identity model as the lesson
# bridge; the lesson viewer simply ignores it, so it is harmless on ordinary lesson artifacts.
_HEIGHT_MARKER = "hituto-ui-height"
_HEIGHT_SCRIPT = """
(function () {
  var SRC = 'hituto-lesson-bridge';
  function report() {
    var h = Math.max(
      document.documentElement ? document.documentElement.scrollHeight : 0,
      document.body ? document.body.scrollHeight : 0
    );
    try { parent.postMessage({ source: SRC, type: 'HT_UI_HEIGHT', payload: { height: h } }, '*'); }
    catch (e) {}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', report);
  else report();
  window.addEventListener('load', report);
  try { new ResizeObserver(report).observe(document.documentElement); } catch (e) {}
  window.addEventListener('resize', report);
})();
"""

# The TWO external libraries lessons may load, besides Tailwind: three.js (3D) and
# Chart.js (standard charts/graphs). Each is version-pinned to a single file so the
# attack surface is an exact, immutable URL. MUST stay in sync with the artifact
# CSP `script-src` in app/api/v1/courses.py / capsule/csp.py.
# Pin three@0.147 — last npm release that still ships the classic UMD GLTFLoader under
# examples/js/ (0.148+ only has ESM addons, which capsules cannot load under CSP).
THREE_JS_CDN = "https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"
GLTF_LOADER_CDN = "https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/loaders/GLTFLoader.js"
CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"
_ALLOWED_SCRIPT_SRC = ("https://cdn.tailwindcss.com", THREE_JS_CDN, GLTF_LOADER_CDN, CHART_JS_CDN)
_PLACEHOLDER_TOKENS = ("lorem ipsum", "todo", "{{", "[image]", "placeholder text")
_SHIMMER = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='9'%3E"
    "%3Crect width='16' height='9' fill='%23020617'/%3E%3C/svg%3E"
)
# Page reading column: max-w-3xl (768px) — matches the consistent fractal-style capsules.
# Wider section columns (4xl–6xl) or bare full-bleed sections get coerced; shell max-w-7xl
# and prose max-w-2xl-and-below are left alone. Studio capsules are skipped.
_WIDE_READING_MAX_W = re.compile(r"\bmax-w-(?:4xl|5xl|6xl)\b")
_HAS_READING_OR_NARROWER = re.compile(r"\bmax-w-(?:sm|md|lg|xl|2xl|3xl)\b")
_CLASS_ATTR = re.compile(r"""\bclass=(['"])(.*?)\1""", flags=re.I | re.S)


def postprocess(html: str) -> tuple[str, dict]:
    """Return (clean_html, checks). checks['passed'] gates the lesson to ready (R10.3)."""
    failed: list[str] = []
    placeholder_tokens: list[str] = []

    # 1. Strip markdown fences / stray prose the model may wrap around the doc.
    html = re.sub(r"^\s*```(?:html)?\s*", "", html)
    html = re.sub(r"\s*```\s*$", "", html.strip())
    # Drop any prior injected bridge AND guidebridge runtime so the parent-access
    # check below only ever judges MODEL code (idempotent when re-processing stored
    # artifacts — both first-party scripts legitimately use window.parent).
    html = _migrate_legacy_branding(html)
    html = _strip_bridge(html)
    html = strip_iframe_runtime(html)

    # 2. Strip disallowed external <script src=...> (keep only the exact allowlist).
    #    Exact equality, NOT startswith: a prefix match lets look-alike hosts/paths
    #    (e.g. "https://cdn.tailwindcss.com.evil.com/x.js") slip through. The CSP is
    #    the runtime backstop, but this stripper must enforce the pin on its own.
    def _script_sub(m: re.Match) -> str:
        src = m.group(1).strip()
        return m.group(0) if src in _ALLOWED_SCRIPT_SRC else ""

    # Match any <script ... src=...> opening tag regardless of how it closes
    # (paired </script>, self-closing "/>", or unclosed) — browsers execute an
    # external-src script in all three forms, so all three must be gated.
    html = re.sub(
        r"<script\b[^>]*\bsrc=['\"]([^'\"]+)['\"][^>]*>(?:\s*</script>)?",
        _script_sub,
        html,
        flags=re.I,
    )
    html = _materialize_lesson_ids(html)
    html = _ensure_chart_canvas_css(html)
    html = _normalize_images(html)
    html = _normalize_reading_column_width(html)

    # 3. Basic structural checks.
    low = html.lower()
    if "<!doctype html" not in low:
        html = "<!DOCTYPE html>\n" + html
    if "<body" not in low:
        failed.append("missing <body>")
    if "</body>" not in low:
        failed.append("truncated: missing </body>")
    if "</html>" not in low:
        failed.append("truncated: missing </html>")
    if "cdn.tailwindcss.com" not in low:
        failed.append("missing Tailwind CDN")
    if "window.parent" in low or "window.top" in low:
        failed.append("unsafe parent/top window access")
    if "localstorage" in low or "sessionstorage" in low:
        failed.append("unsafe browser storage access")

    # 4. Placeholder scan (R10.1).
    for tok in _PLACEHOLDER_TOKENS:
        if tok in low:
            placeholder_tokens.append(tok)
            failed.append(f"placeholder token: {tok!r}")

    img_count = len(re.findall(r"<img\b", html, flags=re.I))
    lazy_img_count = len(re.findall(r"\bgo-data-src=", html, flags=re.I))
    canvas_count = len(re.findall(r"<canvas\b", html, flags=re.I))
    svg_count = len(re.findall(r"<svg\b", html, flags=re.I))
    control_count = len(re.findall(r"<(?:button|input|select|textarea)\b", html, flags=re.I))
    # Prefer drawn graphics (canvas/SVG). Photographs are optional — not a hard requirement.
    if canvas_count == 0 and svg_count == 0:
        failed.append("missing drawn graphic (canvas or svg)")
    if control_count == 0:
        failed.append("missing learner controls")

    # 5. Inject the runtime image loader + lesson bridge + guidebridge runtime before
    #    </body>. NOTE: the structural checks above ran on `low`, a snapshot taken BEFORE
    #    this injection — the window.parent usage in our own scripts never gates a lesson.
    if _RUNTIME_LOADER.strip() not in html and "</body>" in html:
        html = html.replace("</body>", _RUNTIME_LOADER + "\n</body>", 1)
    elif _RUNTIME_LOADER.strip() not in html:
        html += _RUNTIME_LOADER
    html = _append_before_body(html, _bridge_patch())
    html = inject_iframe_runtime(html)

    checks = {
        "passed": not failed,
        "failed": failed,
        "console_errors": [],
        "img_count": img_count,
        "lazy_img_count": lazy_img_count,
        "unresolved_assets": [],
        "canvas_count": canvas_count,
        "svg_count": svg_count,
        "control_count": control_count,
        "placeholder_tokens": placeholder_tokens,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }
    return html, checks


def _class_to_reading_column(class_value: str, *, force_column: bool) -> str:
    """Coerce a class list onto the shared max-w-3xl reading column."""
    value = _WIDE_READING_MAX_W.sub("max-w-3xl", class_value)
    if force_column and not _HAS_READING_OR_NARROWER.search(value) and "max-w-7xl" not in value:
        extras: list[str] = []
        if not re.search(r"\bmx-auto\b", value):
            extras.append("mx-auto")
        if not re.search(r"\bw-full\b", value):
            extras.append("w-full")
        extras.append("max-w-3xl")
        value = f"{value} {' '.join(extras)}".strip()
    return re.sub(r"\s+", " ", value).strip()


def _normalize_reading_column_width(html: str) -> str:
    """Keep page capsules on one reading-column width (`max-w-3xl` / 768px).

    Skills ask authors for a centered ``max-w-3xl`` column so side gutters stay even and
    more of each section fits on screen. This gate coerces wider section columns
    (``max-w-4xl``…``6xl``) and bare full-bleed ``<section>`` regions to that contract.
    Studio and slide capsules are left alone, as is the outer ``max-w-7xl`` shell;
    prose ``max-w-2xl`` (and narrower) stays.
    """
    if re.search(r"\bdata-studio-mode\s*=", html, flags=re.I):
        return html
    if re.search(
        r'<meta\s+[^>]*name=["\']hituto-presentation["\'][^>]*content=["\']studio["\']',
        html,
        flags=re.I,
    ):
        return html
    if re.search(
        r'<meta\s+[^>]*name=["\']hituto-presentation["\'][^>]*content=["\']slide["\']',
        html,
        flags=re.I,
    ):
        return html
    # Compatibility for already-persisted slide decks created before the metadata
    # contract: slide sections use the required ``slide-N`` lesson-section slugs.
    if re.search(r'\bdata-lesson-section\s*=\s*["\']slide-[^"\']+["\']', html, flags=re.I):
        return html

    def rewrite_tag(tag: str, *, force_column: bool) -> str:
        if _CLASS_ATTR.search(tag):

            def class_repl(m: re.Match) -> str:
                quote, value = m.group(1), m.group(2)
                return f"class={quote}{_class_to_reading_column(value, force_column=force_column)}{quote}"

            return _CLASS_ATTR.sub(class_repl, tag, count=1)
        if not force_column:
            return tag
        # Bare <section> / lesson region with no class — attach the reading column.
        return re.sub(
            r"<([a-zA-Z][\w:-]*)\b",
            r'<\1 class="mx-auto w-full max-w-3xl"',
            tag,
            count=1,
        )

    def section_region(m: re.Match) -> str:
        return rewrite_tag(m.group(0), force_column=True)

    html = re.sub(r"<section\b[^>]*>", section_region, html, flags=re.I)
    html = re.sub(
        r"<(?!section\b)([a-zA-Z][\w:-]*)\b[^>]*\bdata-lesson-section\b[^>]*>",
        section_region,
        html,
        flags=re.I,
    )

    # Nested centered columns that still use a wider max-w (order of tokens varies).
    def centered_wide(m: re.Match) -> str:
        return rewrite_tag(m.group(0), force_column=False)

    html = re.sub(
        r"<[a-zA-Z][\w:-]*\b[^>]*\bclass=(['\"])[^'\"]*\bmx-auto\b[^'\"]*"
        r"\bmax-w-(?:4xl|5xl|6xl)\b[^'\"]*\1[^>]*>"
        r"|<[a-zA-Z][\w:-]*\b[^>]*\bclass=(['\"])[^'\"]*\bmax-w-(?:4xl|5xl|6xl)\b"
        r"[^'\"]*\bmx-auto\b[^'\"]*\2[^>]*>",
        centered_wide,
        html,
        flags=re.I,
    )
    return html


def _normalize_images(html: str) -> str:
    """Keep generated pages on the verified lazy image contract."""

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        if "go-data-src" in tag:
            if re.search(r"\ssrc=", tag, flags=re.I):
                return re.sub(r"\ssrc=['\"][^'\"]*['\"]", f' src="{_SHIMMER}"', tag, count=1, flags=re.I)
            return tag[:-1] + f' src="{_SHIMMER}">'
        src_m = re.search(r"\ssrc=['\"]([^'\"]+)['\"]", tag, flags=re.I)
        alt_m = re.search(r"\salt=['\"]([^'\"]*)['\"]", tag, flags=re.I)
        alt = alt_m.group(1) if alt_m else "generated learning visual"
        if not src_m:
            query = quote_plus(alt or "generated learning visual")
            return tag[:-1] + f' src="{_SHIMMER}" go-data-src="/image?query={query}&aspect=16:9">'
        src = src_m.group(1)
        if src.startswith("data:"):
            return tag
        if src.startswith("/gen") or src.startswith("/image") or src.startswith("/sources/"):
            tag = re.sub(r"\ssrc=['\"][^'\"]*['\"]", f' src="{_SHIMMER}"', tag, count=1, flags=re.I)
            return tag[:-1] + f' go-data-src="{src}">' if "go-data-src" not in tag else tag
        query = quote_plus(alt or src)
        tag = re.sub(r"\ssrc=['\"][^'\"]*['\"]", f' src="{_SHIMMER}"', tag, count=1, flags=re.I)
        return tag[:-1] + f' go-data-src="/image?query={query}&aspect=16:9">'

    return re.sub(r"<img\b[^>]*>", repl, html, flags=re.I)


def _materialize_lesson_ids(html: str) -> str:
    """Promote stable data-lesson slugs to ids when the model forgot the id attribute.

    Generated scripts commonly bind controls with document.getElementById("<slug>") while the
    markup only has data-lesson-control="<slug>". Serving-time repair keeps older artifacts alive
    and gives the voice page bridge stable target ids.
    """
    used = {m.group(2) for m in re.finditer(r"\bid\s*=\s*(['\"])([^'\"]+)\1", html, flags=re.I)}

    def add_id(match: re.Match) -> str:
        tag = match.group(0)
        if re.search(r"\bid\s*=", tag, flags=re.I):
            return tag
        slug_match = re.search(
            r"\bdata-lesson-(?:control|section)\s*=\s*(['\"])([^'\"]+)\1",
            tag,
            flags=re.I,
        )
        if not slug_match:
            return tag
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", slug_match.group(2).strip()).strip("-")
        if not slug or slug in used:
            return tag
        used.add(slug)
        return re.sub(r"<([A-Za-z][^\s/>]*)", rf'<\1 id="{slug}"', tag, count=1)

    return re.sub(
        r"<(?!/|!)([A-Za-z][\w:-]*)(?=[^>]*\bdata-lesson-(?:control|section)\s*=)[^>]*>",
        add_id,
        html,
        flags=re.I,
    )


def _ensure_chart_canvas_css(html: str) -> str:
    """Keep generated Chart.js canvases from ballooning into blank, page-tall panels."""
    if _CHART_CANVAS_CSS_MARKER in html:
        return html
    return _append_before_head_end(html, _CHART_CANVAS_CSS)


async def _exercise_interactivity(page, checks: dict, errors: list) -> dict:
    """Click controls and confirm the page actually reacts (tasks.md #70/#71).

    A button that exists but changes nothing is a dead artifact — the old check only COUNTED
    controls, so dead UIs shipped as 'passed'. Here we click and compare a DOM+canvas signature.
    Best-effort: quirks are recorded under checks['interactivity'], not fatal on their own.
    """
    try:
        sig = (
            "() => { const c = document.querySelector('canvas'); let cd = 0;"
            " try { cd = c ? c.toDataURL().length : 0; } catch (e) { cd = -1; }"
            " return document.body.innerHTML.length + '|' + cd; }"
        )
        before = await page.evaluate(sig)
        exercised = 0
        for sel in ("button", "input[type=checkbox]"):
            loc = page.locator(sel)
            for i in range(min(await loc.count(), 6)):
                try:
                    await loc.nth(i).click(timeout=500)
                    exercised += 1
                except Exception:
                    pass
        await page.wait_for_timeout(250)
        after = await page.evaluate(sig)
        produced_change = after != before
        checks["interactivity"] = {"exercised": exercised, "produced_change": produced_change}
        if exercised > 0 and not produced_change and not errors:
            checks["failed"] = [
                *checks.get("failed", []),
                "controls produced no visible change (possible dead UI)",
            ]
    except Exception as e:
        checks["interactivity"] = f"skipped: {e}"
    return checks


# fast_gen Phase 1: one warm Chromium per process. A cold `chromium.launch()` costs
# seconds and ran once per validation attempt (so up to 3× per lesson through the
# repair loop); the pool launches once and hands out fresh pages.
_pw_handle = None
_pw_browser = None
_pw_lock = asyncio.Lock()


async def _get_browser():
    """Return the shared headless Chromium, (re)launching it if absent or crashed."""
    global _pw_handle, _pw_browser
    from playwright.async_api import async_playwright

    async with _pw_lock:
        if _pw_browser is not None and _pw_browser.is_connected():
            return _pw_browser
        if _pw_handle is None:
            _pw_handle = await async_playwright().start()
        _pw_browser = await _pw_handle.chromium.launch(headless=True)
        return _pw_browser


async def validate_artifact_runtime(html: str, checks: dict) -> dict:
    """Best-effort browser smoke validation. Launch failures are recorded, not hidden."""
    from ..core.config import get_settings

    if not get_settings().runtime_validation_enabled:
        checks["browser_validation"] = "disabled"
        return checks

    errors: list[str] = []
    page = None
    try:
        browser = await _get_browser()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.set_content(html, wait_until="domcontentloaded")
        await page.wait_for_timeout(750)
        checks["canvas_count"] = await page.locator("canvas").count()
        checks["control_count"] = await page.locator("button,input,select,textarea").count()
        checks = await _exercise_interactivity(page, checks, errors)
    except Exception as e:
        checks["browser_validation"] = f"skipped: {e}"
        return checks
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:  # noqa: BLE001 — a dead page relaunches via _get_browser
                pass

    checks["console_errors"] = errors
    if errors:
        checks["failed"] = [*checks.get("failed", []), *[f"console error: {e}" for e in errors]]
    if checks.get("canvas_count", 0) == 0:
        checks["failed"] = [*checks.get("failed", []), "browser found no canvas"]
    if checks.get("control_count", 0) == 0:
        checks["failed"] = [*checks.get("failed", []), "browser found no controls"]
    checks["passed"] = not checks.get("failed")
    checks["browser_validation"] = "passed" if checks["passed"] else "failed"
    checks["validated_at"] = datetime.now(timezone.utc).isoformat()
    return checks
