/* Server-owned game runtime. Classic Three.js r147 UMD only — no modules. */
(function () {
  "use strict";

  var manifestEl = document.getElementById("game-manifest");
  var canvas = document.getElementById("stage3d");
  var plaqueKicker = document.getElementById("plaque-kicker");
  var plaqueTitle = document.getElementById("plaque-title");
  var plaqueCopy = document.getElementById("plaque-copy");
  var gestureTip = document.getElementById("gesture-tip");

  if (!manifestEl || !canvas || typeof THREE === "undefined" || !THREE.GLTFLoader) {
    if (plaqueCopy) plaqueCopy.textContent = "3D runtime unavailable in this environment.";
    return;
  }

  var manifest;
  try {
    manifest = JSON.parse(manifestEl.textContent || "{}");
  } catch (err) {
    plaqueCopy.textContent = "Could not read game manifest.";
    return;
  }

  var mode = manifest.mode || "toon-gallery";
  var loader = new THREE.GLTFLoader();
  var mixers = [];
  var clock = new THREE.Clock();

  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x0b1220, 1);
  renderer.outputEncoding = THREE.sRGBEncoding;

  var scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0b1220, 12, 28);

  var camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
  var orbit = { yaw: 0.55, pitch: 0.32, radius: 9.2, target: new THREE.Vector3(0, 1.2, 0) };

  scene.add(new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.95));
  var key = new THREE.DirectionalLight(0xfff7ed, 1.15);
  key.position.set(4, 8, 3);
  scene.add(key);
  var fill = new THREE.DirectionalLight(0x93c5fd, 0.35);
  fill.position.set(-5, 3, -2);
  scene.add(fill);

  var floor = new THREE.Mesh(
    new THREE.CircleGeometry(10, 48),
    new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.92, metalness: 0.05 })
  );
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);

  function setPlaque(kicker, title, copy) {
    plaqueKicker.textContent = kicker;
    plaqueTitle.textContent = title;
    plaqueCopy.textContent = copy;
  }

  function playClip(actor, name, loop) {
    if (!actor || !actor.actions) return;
    var next = actor.actions[name] || actor.actions.Idle;
    if (!next) return;
    if (actor.current === next) return;
    if (actor.current) actor.current.fadeOut(0.2);
    next.reset().setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
    if (!loop) next.clampWhenFinished = true;
    next.fadeIn(0.2).play();
    actor.current = next;
  }

  function loadCharacter(src, onReady, onFail) {
    var kitUrl = new URL(src, window.location.href).href;
    fetch(kitUrl)
      .then(function (r) {
        if (!r.ok) throw new Error("kit fetch failed");
        return r.blob();
      })
      .then(function (blob) {
        var objectUrl = URL.createObjectURL(blob);
        loader.load(
          objectUrl,
          function (gltf) {
            URL.revokeObjectURL(objectUrl);
            var root = gltf.scene || gltf.scenes[0];
            root.traverse(function (node) {
              if (node.isMesh && node.material) {
                node.castShadow = false;
                node.receiveShadow = false;
                node.material.side = THREE.FrontSide;
                if (node.material.map) node.material.map.encoding = THREE.sRGBEncoding;
                node.material.needsUpdate = true;
              }
            });
            var actor = { root: root, actions: {}, current: null };
            if (gltf.animations && gltf.animations.length) {
              var mixer = new THREE.AnimationMixer(root);
              mixers.push(mixer);
              for (var a = 0; a < gltf.animations.length; a++) {
                actor.actions[gltf.animations[a].name] = mixer.clipAction(gltf.animations[a]);
              }
              playClip(actor, "Idle", true);
            }
            onReady(actor);
          },
          undefined,
          function () {
            URL.revokeObjectURL(objectUrl);
            if (onFail) onFail();
          }
        );
      })
      .catch(function () {
        if (onFail) onFail();
      });
  }

  function resize() {
    var wrap = canvas.parentElement;
    var w = wrap.clientWidth || 640;
    var h = wrap.clientHeight || 360;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  function applyOrbit() {
    var cp = Math.cos(orbit.pitch);
    var sp = Math.sin(orbit.pitch);
    var cy = Math.cos(orbit.yaw);
    var sy = Math.sin(orbit.yaw);
    camera.position.set(
      orbit.target.x + orbit.radius * cp * sy,
      orbit.target.y + orbit.radius * sp,
      orbit.target.z + orbit.radius * cp * cy
    );
    camera.lookAt(orbit.target);
  }

  var dragging = false;
  var lastX = 0;
  var lastY = 0;
  canvas.addEventListener("pointerdown", function (ev) {
    dragging = true;
    canvas.classList.add("is-dragging");
    lastX = ev.clientX;
    lastY = ev.clientY;
    try { canvas.setPointerCapture(ev.pointerId); } catch (e) {}
  });
  canvas.addEventListener("pointermove", function (ev) {
    if (!dragging) return;
    var dx = ev.clientX - lastX;
    var dy = ev.clientY - lastY;
    lastX = ev.clientX;
    lastY = ev.clientY;
    orbit.yaw -= dx * 0.005;
    orbit.pitch = Math.max(0.08, Math.min(1.1, orbit.pitch + dy * 0.004));
  });
  function endDrag(ev) {
    dragging = false;
    canvas.classList.remove("is-dragging");
    try { canvas.releasePointerCapture(ev.pointerId); } catch (e) {}
  }
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  window.addEventListener("resize", resize);

  function tick() {
    requestAnimationFrame(tick);
    var dt = clock.getDelta();
    for (var i = 0; i < mixers.length; i++) mixers[i].update(dt);
    applyOrbit();
    renderer.render(scene, camera);
  }

  // ---------- toon-gallery ----------
  function startGallery() {
    var stations = Array.isArray(manifest.stations) ? manifest.stations : [];
    if (stations.length < 2) {
      setPlaque("Error", "Gallery", "This gallery needs at least two stations.");
      return;
    }
    document.getElementById("gallery-controls").hidden = false;
    gestureTip.textContent = "Drag to orbit · click a character · Next to advance";

    var btnNext = document.getElementById("btn-next");
    var btnReset = document.getElementById("btn-reset");
    var visitEl = document.getElementById("visit-count");
    var visited = {};
    var focusIndex = 0;
    var won = false;
    var stationActors = [];
    var PEDESTAL_COLORS = [0x16a34a, 0x2563eb, 0xef4444];
    var raycaster = new THREE.Raycaster();
    var pointer = new THREE.Vector2();

    function stationAngle(i) {
      var n = stations.length;
      var span = Math.PI * 0.9;
      var start = -span / 2;
      return start + (n === 1 ? span / 2 : (span * i) / (n - 1));
    }

    function makePedestal(color, x, z) {
      var group = new THREE.Group();
      group.position.set(x, 0, z);
      var base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.55, 0.65, 0.22, 24),
        new THREE.MeshStandardMaterial({ color: color, roughness: 0.55, metalness: 0.1 })
      );
      base.position.y = 0.11;
      group.add(base);
      var plate = new THREE.Mesh(
        new THREE.CylinderGeometry(0.48, 0.48, 0.06, 24),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.7, metalness: 0.2 })
      );
      plate.position.y = 0.25;
      group.add(plate);
      return group;
    }

    function updateVisitUi() {
      var total = stations.length;
      var count = Object.keys(visited).length;
      visitEl.textContent = "Visited " + count + " / " + total;
      visitEl.classList.toggle("is-win", count >= total);
      if (count >= total && !won) {
        won = true;
        setPlaque("Complete", "Gallery cleared", manifest.win_copy || "Nice work.");
      }
    }

    function visitStation(index, fromClick) {
      if (index < 0 || index >= stations.length) return;
      focusIndex = index;
      var station = stations[index];
      visited[station.id] = true;
      setPlaque(fromClick ? "Visited" : "Now viewing", station.title, station.plaque || "");
      playClip(stationActors[index], station.visit_clip || "Wave", false);
      window.setTimeout(function () { playClip(stationActors[index], "Idle", true); }, 1600);
      orbit.yaw = stationAngle(index) + Math.PI;
      orbit.pitch = 0.32;
      orbit.radius = 8.2;
      updateVisitUi();
    }

    canvas.addEventListener("click", function (ev) {
      var rect = canvas.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      var hits = raycaster.intersectObjects(scene.children, true);
      for (var i = 0; i < hits.length; i++) {
        var obj = hits[i].object;
        while (obj) {
          if (typeof obj.userData.stationIndex === "number") {
            visitStation(obj.userData.stationIndex, true);
            return;
          }
          obj = obj.parent;
        }
      }
    });

    btnNext.addEventListener("click", function () {
      visitStation((focusIndex + 1) % stations.length, false);
    });
    btnReset.addEventListener("click", function () {
      visited = {};
      won = false;
      focusIndex = 0;
      orbit.yaw = 0.55;
      orbit.pitch = 0.28;
      orbit.radius = 9.5;
      for (var i = 0; i < stationActors.length; i++) playClip(stationActors[i], "Idle", true);
      setPlaque("Station", stations[0].title, stations[0].plaque || "");
      updateVisitUi();
    });

    for (var s = 0; s < stations.length; s++) {
      (function (i) {
        var station = stations[i];
        var angle = stationAngle(i);
        var radius = 3.2;
        var x = Math.sin(angle) * radius;
        var z = -Math.cos(angle) * radius;
        var pedestal = makePedestal(PEDESTAL_COLORS[i % PEDESTAL_COLORS.length], x, z);
        pedestal.userData.stationIndex = i;
        scene.add(pedestal);
        stationActors[i] = null;
        loadCharacter(
          station.src,
          function (actor) {
            actor.root.scale.setScalar(1.15);
            actor.root.position.set(0, 0.28, 0);
            actor.root.rotation.y = angle + Math.PI;
            actor.root.traverse(function (node) { node.userData.stationIndex = i; });
            pedestal.add(actor.root);
            stationActors[i] = actor;
          },
          function () {
            if (i === 0) {
              plaqueCopy.textContent =
                (plaqueCopy.textContent || "") + " (Character failed to load — pedestal still works.)";
            }
          }
        );
      })(s);
    }

    setPlaque("Station", stations[0].title, stations[0].plaque || "");
    updateVisitUi();
  }

  // ---------- stack-builder ----------
  function startStackBuilder() {
    var frames = Array.isArray(manifest.frames) ? manifest.frames : [];
    var challenge = manifest.challenge;
    if (frames.length < 2 || !challenge) {
      setPlaque("Error", "Stack game", "This challenge is missing frames.");
      return;
    }
    document.getElementById("stack-panel").hidden = false;
    gestureTip.textContent = "Drag to orbit · watch the stack grow and shrink";

    var frameById = {};
    for (var i = 0; i < frames.length; i++) frameById[frames[i].id] = frames[i];

    var phase = "push"; // push | pop | done
    var stack = []; // frame ids, bottom → top
    var pushIndex = 0;
    var popIndex = 0;
    var coach = null;
    var stackRoot = new THREE.Group();
    stackRoot.position.set(0, 0, 0);
    scene.add(stackRoot);
    var frameActors = {}; // id → {actor, pedestal}
    var COLORS = [0x16a34a, 0x2563eb, 0xef4444, 0xf59e0b];

    var phaseKicker = document.getElementById("phase-kicker");
    var storyEl = document.getElementById("stack-story");
    var programEl = document.getElementById("program-block");
    var actionsEl = document.getElementById("stack-actions");
    var btnPop = document.getElementById("btn-pop");
    var btnReset = document.getElementById("btn-stack-reset");
    var statusEl = document.getElementById("stack-status");

    storyEl.textContent = challenge.story || "";
    programEl.textContent = (challenge.program_lines || []).join("\n");

    orbit.target.set(0, 1.4, 0);
    orbit.radius = 8.5;
    orbit.yaw = 0.4;
    orbit.pitch = 0.35;

    // Guide character off to the side
    var guidePad = new THREE.Mesh(
      new THREE.CylinderGeometry(0.5, 0.58, 0.18, 24),
      new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.55 })
    );
    guidePad.position.set(-3.2, 0.09, 1.2);
    scene.add(guidePad);

    function stackLabel() {
      if (!stack.length) return "empty";
      return stack
        .map(function (id) { return (frameById[id] && frameById[id].label) || id; })
        .join(" → ");
    }

    function refreshUi() {
      statusEl.textContent = "Stack: " + stackLabel();
      statusEl.classList.toggle("is-win", phase === "done");
      if (phase === "push") {
        phaseKicker.textContent = "Phase 1 · Push";
        btnPop.hidden = true;
        var nextId = challenge.push_order[pushIndex];
        var buttons = actionsEl.querySelectorAll(".frame-btn");
        for (var b = 0; b < buttons.length; b++) {
          var id = buttons[b].getAttribute("data-frame-id");
          var used = stack.indexOf(id) !== -1;
          buttons[b].disabled = used || phase !== "push";
          buttons[b].classList.toggle("is-next", id === nextId && !used);
        }
      } else if (phase === "pop") {
        phaseKicker.textContent = "Phase 2 · Pop";
        btnPop.hidden = false;
        var btns = actionsEl.querySelectorAll(".frame-btn");
        for (var j = 0; j < btns.length; j++) {
          btns[j].disabled = true;
          btns[j].classList.remove("is-next");
        }
      } else {
        phaseKicker.textContent = "Complete";
        btnPop.hidden = true;
        var doneBtns = actionsEl.querySelectorAll(".frame-btn");
        for (var k = 0; k < doneBtns.length; k++) {
          doneBtns[k].disabled = true;
          doneBtns[k].classList.remove("is-next");
        }
      }
    }

    function relayoutStack() {
      var ids = Object.keys(frameActors);
      for (var i = 0; i < ids.length; i++) {
        var entry = frameActors[ids[i]];
        if (!entry) continue;
        var idx = stack.indexOf(ids[i]);
        if (idx === -1) {
          entry.group.visible = false;
          continue;
        }
        entry.group.visible = true;
        entry.group.position.set(0.6, 0.2 + idx * 1.15, 0);
      }
    }

    function react(ok, frame) {
      if (!coach) return;
      playClip(coach, ok ? "Yes" : "No", false);
      window.setTimeout(function () { playClip(coach, "Idle", true); }, 1200);
      if (ok && frame && frameActors[frame.id] && frameActors[frame.id].actor) {
        playClip(frameActors[frame.id].actor, ok ? "Wave" : "Idle", false);
        window.setTimeout(function () {
          if (frameActors[frame.id] && frameActors[frame.id].actor) {
            playClip(frameActors[frame.id].actor, "Idle", true);
          }
        }, 1400);
      }
    }

    function onPush(frameId) {
      if (phase !== "push") return;
      var expected = challenge.push_order[pushIndex];
      var frame = frameById[frameId];
      if (frameId !== expected) {
        react(false, frame);
        setPlaque(
          "Not yet",
          "Wrong frame",
          "The next call is " +
            ((frameById[expected] && frameById[expected].label) || expected) +
            ". Push that one first."
        );
        return;
      }
      stack.push(frameId);
      pushIndex += 1;
      relayoutStack();
      react(true, frame);
      setPlaque("Pushed", frame.label + "()", frame.hint || "A new frame lands on top.");
      if (pushIndex >= challenge.push_order.length) {
        phase = "pop";
        setPlaque(
          "Phase 2",
          "Now pop!",
          "Functions finish from the top. Pop " +
            ((frameById[challenge.pop_order[0]] && frameById[challenge.pop_order[0]].label) || "the top") +
            " next."
        );
      }
      refreshUi();
    }

    function onPop() {
      if (phase !== "pop" || !stack.length) return;
      var expected = challenge.pop_order[popIndex];
      var top = stack[stack.length - 1];
      if (top !== expected) {
        react(false, frameById[top]);
        setPlaque("Not yet", "Wrong pop", "Only the top frame can finish. Try Pop again.");
        return;
      }
      var frame = frameById[top];
      stack.pop();
      popIndex += 1;
      relayoutStack();
      react(true, frame);
      setPlaque("Popped", (frame && frame.label) + "() finished", "That frame leaves the stack.");
      if (popIndex >= challenge.pop_order.length) {
        phase = "done";
        setPlaque("You did it!", "Stack complete", manifest.win_copy || "That's a call stack.");
        if (coach) playClip(coach, "Wave", false);
      }
      refreshUi();
    }

    function resetAll() {
      phase = "push";
      stack = [];
      pushIndex = 0;
      popIndex = 0;
      relayoutStack();
      setPlaque(
        "Coach",
        "Build the stack",
        "Push frames in the order the program calls them. Start with the first line."
      );
      if (coach) playClip(coach, "Idle", true);
      refreshUi();
    }

    // Frame buttons
    for (var f = 0; f < frames.length; f++) {
      (function (frame, colorIndex) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "frame-btn";
        btn.textContent = "Push " + frame.label + "()";
        btn.setAttribute("data-frame-id", frame.id);
        btn.setAttribute("data-lesson-control", "push-" + frame.id);
        btn.addEventListener("click", function () { onPush(frame.id); });
        actionsEl.appendChild(btn);

        var group = new THREE.Group();
        group.visible = false;
        var pedestal = new THREE.Mesh(
          new THREE.CylinderGeometry(0.45, 0.52, 0.16, 20),
          new THREE.MeshStandardMaterial({
            color: COLORS[colorIndex % COLORS.length],
            roughness: 0.55,
            metalness: 0.12,
          })
        );
        pedestal.position.y = 0.08;
        group.add(pedestal);
        var labelSprite = makeTextPlane(frame.label);
        labelSprite.position.set(0, 2.05, 0);
        group.add(labelSprite);
        stackRoot.add(group);
        frameActors[frame.id] = { group: group, actor: null };

        loadCharacter(
          frame.src,
          function (actor) {
            actor.root.scale.setScalar(0.95);
            actor.root.position.set(0, 0.16, 0);
            group.add(actor.root);
            frameActors[frame.id].actor = actor;
          },
          null
        );
      })(frames[f], f);
    }

    btnPop.addEventListener("click", onPop);
    btnReset.addEventListener("click", resetAll);

    // Coach uses first frame's kit or soldier
    var coachSrc = (frames[0] && frames[0].src) || "/game-kits/toon/Character_Soldier.gltf";
    loadCharacter(
      coachSrc,
      function (actor) {
        actor.root.scale.setScalar(1.2);
        actor.root.position.set(-3.2, 0.18, 1.2);
        actor.root.rotation.y = Math.PI * 0.35;
        scene.add(actor.root);
        coach = actor;
      },
      null
    );

    resetAll();
  }

  function makeTextPlane(text) {
    var c = document.createElement("canvas");
    c.width = 256;
    c.height = 64;
    var ctx = c.getContext("2d");
    ctx.clearRect(0, 0, 256, 64);
    ctx.fillStyle = "rgba(15,23,42,0.9)";
    ctx.fillRect(16, 8, 224, 48);
    ctx.fillStyle = "#f4f4f5";
    ctx.font = "bold 28px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(text || "").slice(0, 12), 128, 34);
    var tex = new THREE.CanvasTexture(c);
    tex.encoding = THREE.sRGBEncoding;
    var mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true });
    return new THREE.Mesh(new THREE.PlaneGeometry(1.4, 0.35), mat);
  }

  if (mode === "stack-builder") startStackBuilder();
  else startGallery();

  resize();
  applyOrbit();
  tick();
})();
