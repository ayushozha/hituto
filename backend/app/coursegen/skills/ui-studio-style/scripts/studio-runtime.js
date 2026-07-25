/* Hi Tuto Studio v2 deterministic runtime. Generated data configures known behavior only. */
(function () {
  "use strict";

  var manifest = window.__HITUTO_STUDIO_MANIFEST__;
  if (!manifest || manifest.schema_version !== "2.0") return;

  var canvas = document.getElementById("studio-canvas");
  var meshHolder = document.getElementById("mesh-holder");
  var stageImage = document.getElementById("stage-image");
  var selectedSubject = 0;
  var selectedPart = 0;
  var playing = false;
  var elapsed = 0;
  var lastFrame = 0;
  var animationFrame = 0;
  var rotation = -0.35;
  var imageTilt = 0;
  var zoom = 1;
  var dragging = false;
  var dragX = 0;
  var values = {};
  var reducedMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var modeLabels = {
    "specimen": "Specimen explorer",
    "simulation": "Live simulation",
    "process-cutaway": "Process cutaway"
  };
  var modeKickers = {
    "specimen": "Inspect in 3D",
    "simulation": "Change a variable",
    "process-cutaway": "Trace the sequence"
  };

  function byId(id) { return document.getElementById(id); }
  function text(id, value) { var node = byId(id); if (node) node.textContent = value == null ? "" : String(value); }
  function clean(value, fallback) { var result = String(value || "").replace(/\s+/g, " ").trim(); return result || fallback || ""; }
  function currentPart() { return manifest.parts[selectedPart] || manifest.parts[0]; }
  function currentSubject() { return manifest.subjects[selectedSubject] || manifest.subjects[0]; }
  function liveCanvas() { return byId("studio-canvas") || canvas; }
  function subjectUsesThree(subject) { return !!(subject && (subject.mesh_src || subject.procedural_kind)); }
  function subjectUsesImage(subject) { return !!(subject && subject.stage_image_query); }
  function usesAnyThreeStage() { return manifest.subjects.some(subjectUsesThree); }

  function setImageQuery(image, query, aspect) {
    if (!image || !query) return;
    image.style.opacity = ".16";
    image.setAttribute(
      "go-data-src",
      "/image?query=" + encodeURIComponent(query) + "&aspect=" + encodeURIComponent(aspect || "4:3")
    );
  }

  function updateImageTransform() {
    if (!stageImage) return;
    stageImage.style.setProperty("--specimen-tilt", imageTilt + "deg");
    stageImage.style.setProperty("--specimen-zoom", String(zoom));
  }

  function renderFieldGuide(subject) {
    if (!subject || manifest.theme !== "field-guide") return;
    text("evidence-kicker", "Field guide");
    text("evidence-title", subject.label);
    text("evidence-summary", subject.subtitle || "Pollinator specimen");
    text("readout-label", "Field guide number");
    text("readout-value", "No. " + String(selectedSubject + 1).padStart(2, "0"));

    var tags = byId("field-tags");
    tags.textContent = "";
    (subject.tags || []).forEach(function (tag) {
      var chip = document.createElement("span");
      chip.textContent = tag;
      tags.appendChild(chip);
    });

    var image = byId("evidence-image");
    if (image && subject.flower_query) {
      image.alt = subject.label + " flower fit";
      setImageQuery(image, subject.flower_query, "4:3");
      text("evidence-image-label", "Flower fit");
    }

    var copy = byId("evidence-copy");
    copy.textContent = "";
    (subject.field_notes || []).forEach(function (note) {
      var row = document.createElement("div");
      row.className = "evidence-item field-note";
      var label = document.createElement("strong");
      label.textContent = note.label;
      var value = document.createElement("span");
      value.textContent = note.value;
      row.appendChild(label);
      row.appendChild(value);
      copy.appendChild(row);
    });
    text("source-label", "Hi Tuto field guide");
  }

  function emit(type, data) {
    if ((manifest.learning_events || []).indexOf(type) === -1) return;
    document.dispatchEvent(new CustomEvent("hituto:studio-event", {
      detail: { eventType: type, data: data || {} }
    }));
  }

  function openPanel(name) {
    if (document.body.getAttribute("data-open-panel") === name) document.body.removeAttribute("data-open-panel");
    else document.body.setAttribute("data-open-panel", name);
    syncPanelAccessibility();
  }
  function closePanels() {
    document.body.removeAttribute("data-open-panel");
    syncPanelAccessibility();
  }

  function syncPanelAccessibility() {
    var open = document.body.getAttribute("data-open-panel");
    var width = window.innerWidth;
    document.querySelectorAll("[data-mobile-panel]").forEach(function (panel) {
      var name = panel.getAttribute("data-mobile-panel");
      var hidden = width <= 720 ? open !== name : width <= 980 && name === "evidence" && open !== name;
      panel.setAttribute("aria-hidden", hidden ? "true" : "false");
      if (hidden) panel.setAttribute("inert", "");
      else panel.removeAttribute("inert");
    });
  }

  document.querySelectorAll("[data-panel-toggle]").forEach(function (button) {
    button.addEventListener("click", function () { openPanel(button.getAttribute("data-panel-toggle")); });
  });
  document.querySelectorAll("[data-panel-close]").forEach(function (button) {
    button.addEventListener("click", closePanels);
  });

  function renderSubjects() {
    var root = byId("subject-list");
    root.textContent = "";
    var fieldIcons = {
      "orchid-bee": "🐝",
      "garden-tiger": "🦋",
      "jewel-beetle": "🪲",
      "ruby-hummingbird": "🐦",
      "lesser-long-nosed-bat": "🦇"
    };
    manifest.subjects.forEach(function (subject, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "subject-button";
      button.setAttribute("aria-pressed", index === selectedSubject ? "true" : "false");
      button.setAttribute("data-lesson-control", "studio-subject-" + subject.id);
      var glyph = document.createElement("span");
      glyph.className = "subject-glyph";
      glyph.textContent = manifest.theme === "field-guide"
        ? (fieldIcons[subject.id] || "✦")
        : String(index + 1).padStart(2, "0");
      var copy = document.createElement("span");
      copy.className = "subject-copy";
      var label = document.createElement("strong");
      label.textContent = subject.label;
      var subtitle = document.createElement("small");
      subtitle.textContent = subject.subtitle || "Learning object";
      copy.appendChild(label);
      copy.appendChild(subtitle);
      button.appendChild(glyph);
      button.appendChild(copy);
      button.addEventListener("click", function () { selectSubject(index); });
      root.appendChild(button);
    });
  }

  function renderParts() {
    var root = byId("part-list");
    root.textContent = "";
    manifest.parts.forEach(function (part, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "part-button";
      button.setAttribute("aria-pressed", index === selectedPart ? "true" : "false");
      button.setAttribute("data-lesson-control", "studio-part-" + part.id);
      var number = document.createElement("span");
      number.textContent = String(index + 1).padStart(2, "0");
      var label = document.createElement("span");
      label.textContent = part.label;
      button.appendChild(number);
      button.appendChild(label);
      button.addEventListener("click", function () { selectPart(index, true); });
      root.appendChild(button);
    });
  }

  function selectSubject(index) {
    selectedSubject = Math.max(0, Math.min(manifest.subjects.length - 1, index));
    var subject = currentSubject();
    document.querySelectorAll(".subject-button").forEach(function (button, buttonIndex) {
      button.setAttribute("aria-pressed", buttonIndex === selectedSubject ? "true" : "false");
    });
    text("stage-title", subject.label || manifest.lesson.title);
    text("stage-subtitle", subject.subtitle || manifest.lesson.objective);
    var stageCanvas = liveCanvas();
    var canvasWrap = byId("canvas-wrap");
    // A generated GLB is the primary Studio asset. The reference image is retained only
    // as a fail-closed fallback for subjects whose Pixal3D job did not produce a mesh.
    if (subjectUsesThree(subject)) {
      if (canvasWrap) {
        canvasWrap.classList.remove("image-active");
        canvasWrap.classList.add("mesh-active");
      }
      if (stageImage) stageImage.hidden = true;
      if (meshHolder) {
        meshHolder.dataset.meshSrc = subject.mesh_src || "";
        meshHolder.dataset.proceduralKind = subject.procedural_kind || "";
        meshHolder.dataset.meshYaw = subject.initial_yaw == null ? "" : String(subject.initial_yaw);
        meshHolder.dataset.meshPitch = subject.initial_pitch == null ? "" : String(subject.initial_pitch);
        if (stageCanvas) stageCanvas.style.visibility = "";
        text("stage-status-text", subject.mesh_src ? "3D model ready" : "Ready to explore");
        text("gesture-tip", "Drag to rotate · scroll to zoom");
        if (window.__hitutoReloadMesh) window.__hitutoReloadMesh(meshHolder);
      }
    } else if (subjectUsesImage(subject)) {
      if (meshHolder) {
        meshHolder.dataset.meshSrc = "";
        meshHolder.dataset.proceduralKind = "";
        meshHolder.dataset.meshYaw = "";
        meshHolder.dataset.meshPitch = "";
        if (window.__hitutoClearMesh) window.__hitutoClearMesh(meshHolder);
      }
      if (stageCanvas) stageCanvas.style.visibility = "hidden";
      if (canvasWrap) {
        canvasWrap.classList.remove("mesh-active");
        canvasWrap.classList.add("image-active");
      }
      if (stageImage) {
        stageImage.hidden = false;
        stageImage.alt = subject.label + " isolated field guide specimen";
        setImageQuery(stageImage, subject.stage_image_query, "4:3");
        updateImageTransform();
      }
      text("stage-status-text", "Image fallback · 3D unavailable");
      text("gesture-tip", "Image preview · scroll to zoom");
    } else if (meshHolder) {
      if (canvasWrap) canvasWrap.classList.remove("image-active");
      if (stageImage) stageImage.hidden = true;
      // Never leave the previous subject's model visible. A missing asset must fail
      // closed instead of pretending that one specimen represents another.
      meshHolder.dataset.meshSrc = "";
      meshHolder.dataset.proceduralKind = "";
      meshHolder.dataset.meshYaw = "";
      meshHolder.dataset.meshPitch = "";
      if (window.__hitutoClearMesh) window.__hitutoClearMesh(meshHolder);
      if (stageCanvas) stageCanvas.style.visibility = "hidden";
      if (canvasWrap) canvasWrap.classList.remove("mesh-active");
      text("stage-status-text", "3D model unavailable");
      emit("studio_degraded", {
        reason_code: "subject_mesh_missing",
        fallback_kind: "none"
      });
    }
    if (subject.default_part_id) {
      var partIndex = manifest.parts.findIndex(function (part) { return part.id === subject.default_part_id; });
      if (partIndex >= 0) selectPart(partIndex, false);
    }
    renderFieldGuide(subject);
    draw();
    closePanels();
  }

  function selectPart(index, learnerInitiated) {
    selectedPart = Math.max(0, Math.min(manifest.parts.length - 1, index));
    var part = currentPart();
    document.querySelectorAll(".part-button").forEach(function (button, buttonIndex) {
      button.setAttribute("aria-pressed", buttonIndex === selectedPart ? "true" : "false");
    });
    text("annotation-index", String(selectedPart + 1).padStart(2, "0"));
    text("annotation-title", part.label);
    text("annotation-summary", part.summary);
    if (manifest.theme === "field-guide") {
      renderFieldGuide(currentSubject());
    } else {
      text("evidence-title", part.label);
      text("evidence-summary", part.detail || part.summary);
      text("evidence-image-label", part.label + " · visual context");
      var image = byId("evidence-image");
      if (image) {
        var subject = currentSubject();
        var query = clean(subject.image_query, "Single isolated " + subject.label + " educational anatomy reference");
        image.alt = subject.label + " visual reference for " + part.label;
        image.setAttribute("go-data-src", "/image?query=" + encodeURIComponent(query));
      }
      renderEvidence(part);
      updateReadout();
    }
    draw();
    if (learnerInitiated) {
      emit("studio_part_selected", { part_id: part.id });
      closePanels();
    }
  }

  function renderEvidence(part) {
    var root = byId("evidence-copy");
    root.textContent = "";
    var matches = (part.evidence_ids || []).map(function (id) {
      return manifest.evidence.find(function (item) { return item.id === id; });
    }).filter(Boolean);
    if (!matches.length) {
      var explanation = document.createElement("div");
      explanation.className = "evidence-item";
      var marker = document.createElement("span");
      marker.textContent = "01";
      explanation.appendChild(marker);
      explanation.appendChild(document.createTextNode(part.summary));
      root.appendChild(explanation);
      text("source-label", "Lesson explanation");
      return;
    }
    matches.forEach(function (item, index) {
      var row = document.createElement("div");
      row.className = "evidence-item";
      var marker = document.createElement("span");
      marker.textContent = String(index + 1).padStart(2, "0");
      row.appendChild(marker);
      row.appendChild(document.createTextNode(item.claim));
      root.appendChild(row);
    });
    text("source-label", matches[0].source_label || "Lesson evidence");
  }

  function renderControls() {
    var root = byId("control-list");
    root.textContent = "";
    manifest.controls.forEach(function (control) {
      values[control.id] = control.value;
      if (control.kind === "range" || control.kind === "timeline") {
        var field = document.createElement("div");
        field.className = "control-field";
        var label = document.createElement("label");
        label.htmlFor = "control-" + control.id;
        label.textContent = control.label;
        var output = document.createElement("output");
        output.htmlFor = "control-" + control.id;
        output.textContent = formatValue(control, control.value);
        var input = document.createElement("input");
        input.id = "control-" + control.id;
        input.type = "range";
        input.min = control.minimum;
        input.max = control.maximum;
        input.step = control.step;
        input.value = control.value == null ? control.minimum : control.value;
        input.setAttribute("data-lesson-control", control.id);
        input.addEventListener("input", function () {
          values[control.id] = Number(input.value);
          output.textContent = formatValue(control, values[control.id]);
          if (control.kind === "timeline") selectPart(Math.round(Number(input.value)), false);
          updateReadout();
          draw();
        });
        input.addEventListener("change", function () {
          emit("studio_control_changed", { control_id: control.id, value: String(input.value).slice(0, 32) });
        });
        field.appendChild(label);
        field.appendChild(output);
        field.appendChild(input);
        root.appendChild(field);
        return;
      }

      var button = document.createElement("button");
      button.type = "button";
      button.className = control.kind === "button" ? "control-button secondary" : "control-button";
      button.setAttribute("data-lesson-control", control.id);
      button.textContent = control.kind === "playback" ? "▶ " + control.label : "↺ " + control.label;
      button.addEventListener("click", function () {
        if (control.kind === "playback") {
          playing = !playing;
          button.textContent = (playing ? "Ⅱ Pause" : "▶ " + control.label);
          text("stage-status-text", playing ? "Model running" : "Model paused");
          if (playing) startLoop();
          else stopLoop();
          emit("studio_control_changed", { control_id: control.id, value: playing ? "playing" : "paused" });
        } else {
          reset();
          emit("studio_reset", { mode: manifest.mode });
        }
      });
      root.appendChild(button);
    });
  }

  function formatValue(control, value) {
    var numeric = Number(value);
    var display = Number.isFinite(numeric) ? (Math.round(numeric * 100) / 100) : value;
    if (control.kind === "timeline") return String(Math.round(numeric) + 1) + " / " + manifest.parts.length;
    return String(display == null ? "" : display) + (control.unit || "");
  }

  function updateReadout() {
    var part = currentPart();
    if (manifest.mode === "simulation") {
      var rate = Number(values["system-rate"] || 1);
      text("readout-label", "System rate");
      text("readout-value", rate.toFixed(2).replace(/\.00$/, "") + "×");
    } else if (manifest.mode === "process-cutaway") {
      text("readout-label", "Active stage");
      text("readout-value", String(selectedPart + 1) + " / " + manifest.parts.length);
    } else {
      text("readout-label", "Selected focus");
      text("readout-value", part.label);
    }
  }

  function setPlaybackLabel(isPlaying) {
    document.querySelectorAll(".control-button").forEach(function (button) {
      var id = button.getAttribute("data-lesson-control");
      var control = manifest.controls.find(function (item) { return item.id === id; });
      if (control && control.kind === "playback") {
        button.textContent = isPlaying ? "Ⅱ Pause" : "▶ " + control.label;
      }
    });
  }

  function reset() {
    playing = false;
    elapsed = 0;
    rotation = -0.35;
    imageTilt = 0;
    zoom = 1;
    var imageAngle = byId("image-angle");
    if (imageAngle) imageAngle.value = "0";
    updateImageTransform();
    if (meshHolder && window.__hitutoResetMesh) window.__hitutoResetMesh(meshHolder);
    manifest.controls.forEach(function (control) {
      values[control.id] = control.value;
      var input = byId("control-" + control.id);
      if (input && control.value != null) {
        input.value = control.value;
        var output = input.parentNode.querySelector("output");
        if (output) output.textContent = formatValue(control, control.value);
      }
    });
    selectPart(0, false);
    setPlaybackLabel(false);
    text("stage-status-text", "Ready to explore");
    stopLoop();
    draw();
  }

  function sizeCanvas() {
    if (!canvas || usesAnyThreeStage()) return null;
    var rect = canvas.getBoundingClientRect();
    var ratio = Math.min(2, window.devicePixelRatio || 1);
    var width = Math.max(320, Math.round(rect.width * ratio));
    var height = Math.max(260, Math.round(rect.height * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    var context = canvas.getContext("2d");
    if (context) context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { context: context, width: rect.width, height: rect.height };
  }

  function draw() {
    if (!canvas || usesAnyThreeStage()) return;
    var sized = sizeCanvas();
    if (!sized || !sized.context) return;
    var context = sized.context;
    context.clearRect(0, 0, sized.width, sized.height);
    if (manifest.mode === "simulation") drawSimulation(context, sized.width, sized.height);
    else if (manifest.mode === "process-cutaway") drawProcess(context, sized.width, sized.height);
    else drawSpecimen(context, sized.width, sized.height);
  }

  function drawSpecimen(context, width, height) {
    var centerX = width * 0.56;
    var centerY = height * 0.5;
    var radius = Math.min(width, height) * 0.24 * zoom;
    context.save();
    context.translate(centerX, centerY);
    context.rotate(rotation * 0.12);
    var glow = context.createRadialGradient(-radius * .25, -radius * .3, radius * .08, 0, 0, radius * 1.15);
    glow.addColorStop(0, "rgba(255,255,255,.95)");
    glow.addColorStop(.28, "rgba(121,223,134,.92)");
    glow.addColorStop(1, "rgba(36,97,54,.18)");
    context.fillStyle = glow;
    context.beginPath();
    for (var point = 0; point <= 44; point += 1) {
      var angle = point / 44 * Math.PI * 2;
      var ripple = 1 + .08 * Math.sin(angle * 5 + rotation * 3) + .04 * Math.cos(angle * 3);
      var x = Math.cos(angle) * radius * ripple;
      var y = Math.sin(angle) * radius * .78 * ripple;
      if (point === 0) context.moveTo(x, y); else context.lineTo(x, y);
    }
    context.closePath();
    context.fill();
    context.strokeStyle = "rgba(255,255,255,.24)";
    context.lineWidth = 2;
    context.stroke();
    manifest.parts.slice(0, 6).forEach(function (part, index) {
      var angle = rotation + index / Math.max(1, manifest.parts.length) * Math.PI * 2;
      var x = Math.cos(angle) * radius * .5;
      var y = Math.sin(angle) * radius * .33;
      context.beginPath();
      context.fillStyle = index === selectedPart ? "#f4c84a" : "rgba(255,255,255,.72)";
      context.arc(x, y, index === selectedPart ? 9 : 5, 0, Math.PI * 2);
      context.fill();
      if (index === selectedPart) {
        context.strokeStyle = "rgba(244,200,74,.38)";
        context.lineWidth = 8;
        context.stroke();
      }
    });
    context.restore();
    context.strokeStyle = "rgba(121,223,134,.18)";
    context.lineWidth = 1;
    context.beginPath();
    context.ellipse(centerX, centerY, radius * 1.4, radius * .55, -.12, 0, Math.PI * 2);
    context.stroke();
  }

  function drawSimulation(context, width, height) {
    var rate = Number(values["system-rate"] || 1);
    var centerX = width * .54;
    var centerY = height * .48;
    var radius = Math.min(width, height) * .28;
    context.strokeStyle = "rgba(125,199,255,.2)";
    context.lineWidth = 1;
    for (var ring = 1; ring <= 3; ring += 1) {
      context.beginPath();
      context.ellipse(centerX, centerY, radius * ring / 3, radius * .5 * ring / 3, 0, 0, Math.PI * 2);
      context.stroke();
    }
    var count = Math.max(3, Math.min(7, manifest.parts.length + 2));
    for (var index = 0; index < count; index += 1) {
      var angle = elapsed * .001 * rate + index / count * Math.PI * 2;
      var distance = radius * (.45 + (index % 3) * .22);
      var x = centerX + Math.cos(angle) * distance;
      var y = centerY + Math.sin(angle) * distance * .5;
      context.beginPath();
      context.fillStyle = index === selectedPart ? "#f4c84a" : "rgba(125,199,255,.9)";
      context.arc(x, y, index === selectedPart ? 10 : 6, 0, Math.PI * 2);
      context.fill();
    }
    context.fillStyle = "rgba(255,255,255,.92)";
    context.beginPath();
    context.arc(centerX, centerY, 19, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#132947";
    context.font = "800 10px Sora, sans-serif";
    context.textAlign = "center";
    context.fillText(rate.toFixed(2).replace(/\.00$/, "") + "×", centerX, centerY + 3);
  }

  function drawProcess(context, width, height) {
    var count = Math.max(1, manifest.parts.length);
    var gap = 8;
    var available = Math.min(width * .78, 720);
    var boxWidth = Math.max(52, (available - gap * (count - 1)) / count);
    var startX = (width - (boxWidth * count + gap * (count - 1))) / 2;
    var centerY = height * .5;
    manifest.parts.forEach(function (part, index) {
      var x = startX + index * (boxWidth + gap);
      var active = index === selectedPart;
      context.fillStyle = active ? "rgba(255,179,110,.92)" : "rgba(255,255,255,.1)";
      roundedRect(context, x, centerY - 52, boxWidth, 104, 15);
      context.fill();
      context.fillStyle = active ? "#3b251c" : "rgba(255,255,255,.76)";
      context.font = "800 10px Sora, sans-serif";
      context.textAlign = "center";
      context.fillText(String(index + 1).padStart(2, "0"), x + boxWidth / 2, centerY - 10);
      context.font = "700 9px Sora, sans-serif";
      wrapLabel(context, clean(part.label, "Stage"), x + 8, centerY + 8, boxWidth - 16, 12);
      if (index < count - 1) {
        var progress = playing ? (elapsed * .08) % (boxWidth + gap) : boxWidth * .5;
        context.strokeStyle = "rgba(255,179,110,.38)";
        context.lineWidth = 3;
        context.beginPath();
        context.moveTo(x + boxWidth, centerY);
        context.lineTo(x + boxWidth + gap, centerY);
        context.stroke();
        context.fillStyle = "#ffb36e";
        context.beginPath();
        context.arc(x + boxWidth + Math.min(gap, progress), centerY, 3, 0, Math.PI * 2);
        context.fill();
      }
    });
  }

  function roundedRect(context, x, y, width, height, radius) {
    var r = Math.min(radius, width / 2, height / 2);
    context.beginPath();
    context.moveTo(x + r, y);
    context.arcTo(x + width, y, x + width, y + height, r);
    context.arcTo(x + width, y + height, x, y + height, r);
    context.arcTo(x, y + height, x, y, r);
    context.arcTo(x, y, x + width, y, r);
    context.closePath();
  }

  function wrapLabel(context, label, x, y, maxWidth, lineHeight) {
    var words = label.split(" ");
    var line = "";
    var row = 0;
    words.forEach(function (word) {
      var test = line ? line + " " + word : word;
      if (context.measureText(test).width > maxWidth && line) {
        context.fillText(line, x + maxWidth / 2, y + row * lineHeight);
        line = word;
        row += 1;
      } else line = test;
    });
    if (line) context.fillText(line, x + maxWidth / 2, y + row * lineHeight);
  }

  function frame(now) {
    if (!playing) return;
    var delta = lastFrame ? Math.min(80, now - lastFrame) : 16;
    lastFrame = now;
    elapsed += delta;
    if (manifest.mode === "process-cutaway" && !reducedMotion) {
      var duration = 1800;
      var nextStage = Math.min(manifest.parts.length - 1, Math.floor(elapsed / duration));
      if (nextStage !== selectedPart) {
        selectPart(nextStage, false);
        var timeline = byId("control-process-stage");
        if (timeline) {
          timeline.value = nextStage;
          var output = timeline.parentNode.querySelector("output");
          var control = manifest.controls.find(function (item) { return item.id === "process-stage"; });
          if (output && control) output.textContent = formatValue(control, nextStage);
        }
      }
      if (elapsed >= duration * manifest.parts.length) {
        playing = false;
        setPlaybackLabel(false);
        emit("studio_playback_completed", { sequence_id: "primary-process" });
        text("stage-status-text", "Sequence complete");
      }
    }
    draw();
    if (playing) animationFrame = requestAnimationFrame(frame);
  }
  function startLoop() {
    if (reducedMotion && manifest.mode === "process-cutaway") {
      selectPart(manifest.parts.length - 1, false);
      playing = false;
      setPlaybackLabel(false);
      emit("studio_playback_completed", { sequence_id: "primary-process" });
      text("stage-status-text", "Sequence complete");
      draw();
      return;
    }
    if (usesAnyThreeStage() || reducedMotion) {
      draw();
      return;
    }
    cancelAnimationFrame(animationFrame);
    lastFrame = 0;
    animationFrame = requestAnimationFrame(frame);
  }
  function stopLoop() { cancelAnimationFrame(animationFrame); animationFrame = 0; lastFrame = 0; draw(); }

  if (!usesAnyThreeStage() && manifest.mode === "specimen") {
    canvas.addEventListener("pointerdown", function (event) { dragging = true; dragX = event.clientX; canvas.setPointerCapture(event.pointerId); });
    canvas.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      rotation += (event.clientX - dragX) * .012;
      dragX = event.clientX;
      draw();
    });
    canvas.addEventListener("pointerup", function (event) { dragging = false; canvas.releasePointerCapture(event.pointerId); });
    canvas.addEventListener("wheel", function (event) {
      event.preventDefault();
      zoom = Math.max(.72, Math.min(1.42, zoom - event.deltaY * .001));
      draw();
    }, { passive: false });
  }

  var imageWrap = byId("canvas-wrap");
  if (imageWrap) {
    imageWrap.addEventListener("pointerdown", function (event) {
      if (!imageWrap.classList.contains("image-active")) return;
      if (event.target && event.target.closest && event.target.closest(".image-angle-control")) return;
      dragging = true;
      dragX = event.clientX;
      imageWrap.setPointerCapture(event.pointerId);
    });
    imageWrap.addEventListener("pointermove", function (event) {
      if (!dragging || !imageWrap.classList.contains("image-active")) return;
      imageTilt = Math.max(-12, Math.min(12, imageTilt + (event.clientX - dragX) * .08));
      dragX = event.clientX;
      var angle = byId("image-angle");
      if (angle) angle.value = String(Math.round(imageTilt));
      updateImageTransform();
    });
    imageWrap.addEventListener("pointerup", function (event) {
      if (!dragging) return;
      dragging = false;
      imageWrap.releasePointerCapture(event.pointerId);
    });
    imageWrap.addEventListener("wheel", function (event) {
      if (!imageWrap.classList.contains("image-active")) return;
      event.preventDefault();
      zoom = Math.max(.82, Math.min(1.28, zoom - event.deltaY * .001));
      updateImageTransform();
    }, { passive: false });
  }

  var imageAngleControl = byId("image-angle");
  if (imageAngleControl) {
    imageAngleControl.addEventListener("input", function () {
      imageTilt = Number(imageAngleControl.value || 0);
      updateImageTransform();
    });
    imageAngleControl.addEventListener("change", function () {
      emit("studio_control_changed", { control_id: "specimen-angle", value: imageAngleControl.value });
    });
  }
  var imageFit = byId("image-fit");
  if (imageFit) imageFit.addEventListener("click", function () {
    imageTilt = 0;
    zoom = 1;
    if (imageAngleControl) imageAngleControl.value = "0";
    updateImageTransform();
    emit("studio_reset", { mode: manifest.mode });
  });

  function initialize() {
    document.title = manifest.lesson.title + " · Hi Tuto Studio";
    text("studio-objective", manifest.lesson.objective);
    text("mode-chip", modeLabels[manifest.mode] || "Interactive lab");
    text("stage-kicker", modeKickers[manifest.mode] || "Live model");
    text("stage-title", currentSubject().label || manifest.lesson.title);
    text("stage-subtitle", currentSubject().subtitle || manifest.lesson.objective);
    text("control-prompt", manifest.mode === "specimen" ? "Inspect from another angle" : manifest.mode === "simulation" ? "Change one variable" : "Move through the system");
    text("subject-kicker", manifest.subjects.length > 1 ? "Choose a subject" : "Learning object");
    text("subject-heading", manifest.subjects.length > 1 ? "Subjects" : "Explore");
    text("part-kicker", manifest.mode === "process-cutaway" ? "Process stages" : "Focus points");
    text("part-heading", manifest.mode === "process-cutaway" ? "Follow the flow" : "What to notice");
    text("rail-tip", manifest.mode === "specimen" ? "Drag the object to rotate it. Choose a focus point to connect shape and meaning." : manifest.mode === "simulation" ? "Change the rate, then pause to inspect how the system responds." : "Move through each stage to trace the transformation from input to output.");
    text("gesture-tip", usesAnyThreeStage() || manifest.mode === "specimen" ? "Drag to rotate · scroll to zoom" : manifest.mode === "simulation" ? "Adjust the rate · play or pause" : "Choose a stage · play the sequence");

    if (manifest.theme === "field-guide") {
      text("mode-chip", "Pollinator field guide");
      text("stage-kicker", "Specimen spotlight");
      text("subject-kicker", "Pollinators");
      text("subject-heading", "Field collection");
      text("evidence-kicker", "Field guide");
      text("rail-tip", "Today’s discovery · Pollination links flowers, food webs, and entire ecosystems.");
      text("gesture-tip", "Drag for depth · scroll to zoom");
    }

    if (usesAnyThreeStage() && meshHolder) {
      meshHolder.dataset.meshSrc = currentSubject().mesh_src || manifest.stage.asset.src || "";
      meshHolder.dataset.proceduralKind = currentSubject().procedural_kind || "";
      byId("canvas-wrap").classList.add("mesh-active");
    }
    renderSubjects();
    renderParts();
    renderControls();
    syncPanelAccessibility();
    // Apply the first subject through the same path as every later selection so
    // its own mesh, evidence image, and matching focus point are all initialized.
    selectSubject(0);
    draw();
    emit("studio_mode_opened", { mode: manifest.mode, manifest_version: manifest.schema_version });
  }

  window.addEventListener("resize", function () { syncPanelAccessibility(); draw(); });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopLoop();
    else if (playing) startLoop();
  });
  initialize();
})();
