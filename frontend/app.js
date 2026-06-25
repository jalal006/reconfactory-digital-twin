const stationLayout = {
  input_queue: { x: 115, y: 360, w: 130, h: 70, label: "Input" },
  vision: { x: 310, y: 360, w: 150, h: 86, label: "Vision" },
  processing_buffer: { x: 480, y: 360, w: 124, h: 62, label: "Process Buffer" },
  station_a: { x: 675, y: 205, w: 160, h: 82, label: "Processing A" },
  station_b: { x: 675, y: 505, w: 160, h: 82, label: "Processing B" },
  quality_buffer: { x: 870, y: 360, w: 124, h: 62, label: "QC Buffer" },
  quality: { x: 1035, y: 360, w: 150, h: 86, label: "Quality" },
  accepted_output: { x: 1180, y: 230, w: 132, h: 70, label: "Accepted" },
  reject_output: { x: 1180, y: 500, w: 132, h: 70, label: "Rejected" },
  recovery_buffer: { x: 880, y: 635, w: 150, h: 64, label: "Recovery" },
};

const factoryLayout = {
  input_queue: { x: 112, y: 360, w: 104, h: 72, label: "Input" },
  vision: { x: 300, y: 360, w: 132, h: 108, label: "Vision" },
  processing_buffer: { x: 474, y: 360, w: 104, h: 66, label: "Buffer" },
  station_a: { x: 690, y: 210, w: 160, h: 112, label: "Drill / Assemble" },
  station_b: { x: 690, y: 508, w: 160, h: 112, label: "Drill / Polish" },
  quality_buffer: { x: 858, y: 360, w: 102, h: 66, label: "QC buffer" },
  quality: { x: 1040, y: 360, w: 138, h: 108, label: "Quality" },
  accepted_output: { x: 1190, y: 244, w: 104, h: 78, label: "Accepted" },
  reject_output: { x: 1190, y: 506, w: 104, h: 78, label: "Rejected" },
  recovery_buffer: { x: 908, y: 628, w: 126, h: 62, label: "Recovery" },
  conveyor_main: { x: 520, y: 162, w: 120, h: 54, label: "PLC" },
};

const routeSegments = {
  input_to_vision: [
    [164, 360],
    [238, 360],
    [300, 360],
  ],
  vision_to_buffer: [
    [300, 360],
    [366, 360],
    [474, 360],
  ],
  vision_to_station_a: [
    [366, 360],
    [526, 360],
    [592, 264],
    [610, 210],
    [690, 210],
  ],
  vision_to_station_b: [
    [366, 360],
    [526, 360],
    [592, 456],
    [610, 508],
    [690, 508],
  ],
  processing_buffer_to_station_a: [
    [474, 360],
    [526, 360],
    [592, 264],
    [610, 210],
    [690, 210],
  ],
  processing_buffer_to_station_b: [
    [474, 360],
    [526, 360],
    [592, 456],
    [610, 508],
    [690, 508],
  ],
  station_a_to_quality_buffer: [
    [770, 210],
    [818, 244],
    [858, 360],
  ],
  station_a_to_quality: [
    [770, 210],
    [818, 244],
    [884, 360],
    [1040, 360],
  ],
  station_b_to_quality_buffer: [
    [770, 508],
    [818, 476],
    [858, 360],
  ],
  station_b_to_quality: [
    [770, 508],
    [818, 476],
    [884, 360],
    [1040, 360],
  ],
  quality_buffer_to_quality: [
    [858, 360],
    [1040, 360],
  ],
  quality_to_accepted: [
    [1108, 360],
    [1140, 360],
    [1140, 244],
    [1190, 244],
  ],
  quality_to_reject: [
    [1108, 360],
    [1140, 360],
    [1140, 506],
    [1190, 506],
  ],
};

const routeByLocationPair = {
  "input_queue>vision": routeSegments.input_to_vision,
  "vision>processing_buffer": routeSegments.vision_to_buffer,
  "vision>station_a": [
    [300, 360],
    [366, 360],
    [474, 360],
    [526, 360],
    [592, 264],
    [610, 210],
    [690, 210],
  ],
  "vision>station_b": [
    [300, 360],
    [366, 360],
    [474, 360],
    [526, 360],
    [592, 456],
    [610, 508],
    [690, 508],
  ],
  "processing_buffer>station_a": routeSegments.processing_buffer_to_station_a,
  "processing_buffer>station_b": routeSegments.processing_buffer_to_station_b,
  "station_a>quality_buffer": routeSegments.station_a_to_quality_buffer,
  "station_a>quality": [
    [690, 210],
    [770, 210],
    [818, 244],
    [858, 360],
    [1040, 360],
  ],
  "station_b>quality_buffer": routeSegments.station_b_to_quality_buffer,
  "station_b>quality": [
    [690, 508],
    [770, 508],
    [818, 476],
    [858, 360],
    [1040, 360],
  ],
  "quality_buffer>quality": routeSegments.quality_buffer_to_quality,
  "quality>accepted_output": routeSegments.quality_to_accepted,
  "quality>reject_output": routeSegments.quality_to_reject,
  "station_a>recovery_buffer": [
    [690, 210],
    [760, 390],
    [908, 628],
  ],
  "station_b>recovery_buffer": [
    [690, 508],
    [770, 560],
    [908, 628],
  ],
};

const routeNameByLocationPair = {
  "input_queue>vision": "input_to_vision",
  "vision>processing_buffer": "vision_to_buffer",
  "vision>station_a": "vision_to_station_a",
  "vision>station_b": "vision_to_station_b",
  "processing_buffer>station_a": "processing_buffer_to_station_a",
  "processing_buffer>station_b": "processing_buffer_to_station_b",
  "station_a>quality_buffer": "station_a_to_quality_buffer",
  "station_a>quality": "station_a_to_quality",
  "station_b>quality_buffer": "station_b_to_quality_buffer",
  "station_b>quality": "station_b_to_quality",
  "quality_buffer>quality": "quality_buffer_to_quality",
  "quality>accepted_output": "quality_to_accepted",
  "quality>reject_output": "quality_to_reject",
  "station_a>recovery_buffer": "station_to_recovery",
  "station_b>recovery_buffer": "station_to_recovery",
};

const productColors = {
  red_block: "#ef4444",
  blue_cylinder: "#3b82f6",
  green_component: "#22c55e",
};

let latestState = null;
let fallbackPoll = null;
let animationFrame = null;
let activeVisualView = "main";
const visualProducts = new Map();
const seenEventIds = new Set();
const detectorDoneUntil = new Map();
const routeIndicatorUntil = new Map();
const productRouteHistoryLength = new Map();
const ROUTE_INDICATOR_HOLD_MS = 1600;

const routeDisplaySegments = {
  vision_to_station_a: ["vision_to_buffer", "processing_buffer_to_station_a"],
  vision_to_station_b: ["vision_to_buffer", "processing_buffer_to_station_b"],
  station_a_to_quality: ["station_a_to_quality_buffer", "quality_buffer_to_quality"],
  station_b_to_quality: ["station_b_to_quality_buffer", "quality_buffer_to_quality"],
};

const physicalRouteNames = [
  "input_to_vision",
  "vision_to_buffer",
  "processing_buffer_to_station_a",
  "processing_buffer_to_station_b",
  "station_a_to_quality_buffer",
  "station_b_to_quality_buffer",
  "quality_buffer_to_quality",
  "quality_to_accepted",
  "quality_to_reject",
];

function latestRouteIndex(route, location) {
  for (let index = route.length - 1; index >= 0; index -= 1) {
    if (route[index] === location) return index;
  }
  return -1;
}

function activeSegmentsForDestination(product, destination) {
  const route = normalizedProductRoute(product);
  const index = latestRouteIndex(route, destination);
  const previous = index > 0 ? route[index - 1] : "";
  if (destination === "processing_buffer") return ["vision_to_buffer"];
  if (destination === "station_a") return ["vision_to_buffer", "processing_buffer_to_station_a"];
  if (destination === "station_b") return ["vision_to_buffer", "processing_buffer_to_station_b"];
  if (destination === "quality_buffer") {
    if (previous === "station_b") return ["station_b_to_quality_buffer"];
    return ["station_a_to_quality_buffer"];
  }
  if (destination === "quality") {
    if (route.includes("station_b") && !route.includes("station_a")) {
      return ["station_b_to_quality_buffer", "quality_buffer_to_quality"];
    }
    if (previous === "quality_buffer") return ["quality_buffer_to_quality"];
    return ["station_a_to_quality_buffer", "quality_buffer_to_quality"];
  }
  if (destination === "accepted_output") return ["quality_to_accepted"];
  if (destination === "reject_output") return ["quality_to_reject"];
  if (destination === "vision") return ["input_to_vision"];
  return [];
}

function machinePosition(machineId) {
  return stationLayout[machineId] || stationLayout.processing_buffer;
}

function stationPort(id, side = "center") {
  const layout = machinePosition(id);
  if (side === "left") return [layout.x - layout.w / 2, layout.y];
  if (side === "right") return [layout.x + layout.w / 2, layout.y];
  if (side === "top") return [layout.x, layout.y - layout.h / 2];
  if (side === "bottom") return [layout.x, layout.y + layout.h / 2];
  return [layout.x, layout.y];
}

function pathData(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" ");
}

function hashText(text) {
  return Array.from(text).reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 7);
}

function productPosition(product, index) {
  const base = stationLayout[product.current_location] || stationLayout.processing_buffer;
  const slot = index % 5;
  const offsetX = (slot - 2) * 18;
  const offsetY = (Math.floor(index / 5) % 2) * 18;
  if (product.current_location === "input_queue") return { x: base.x + offsetX, y: base.y - base.h / 2 - 24 - offsetY };
  if (product.current_location === "accepted_output") return { x: base.x + offsetX, y: base.y - base.h / 2 - 24 - offsetY };
  if (product.current_location === "reject_output") return { x: base.x + offsetX, y: base.y + base.h / 2 + 24 + offsetY };
  if (product.status === "paused") return { x: stationLayout.recovery_buffer.x + offsetX, y: stationLayout.recovery_buffer.y - 54 - offsetY };
  return { x: base.x + offsetX, y: base.y - base.h / 2 - 24 - offsetY };
}

function svgEl(name, attrs = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function renderStations(state) {
  const layer = document.getElementById("stationLayer");
  if (!layer) return;
  layer.innerHTML = "";
  const stations = [
    { id: "input_queue", name: "Input Queue", state: "queue", capabilities: [] },
    ...state.machines,
    { id: "accepted_output", name: "Accepted", state: "output", capabilities: [] },
    { id: "reject_output", name: "Rejected", state: "output", capabilities: [] },
    { id: "recovery_buffer", name: "Recovery Buffer", state: "buffer", capabilities: [] },
  ];

  stations.forEach((station) => {
    const pos = machinePosition(station.id || station.machine_id);
    const id = station.id || station.machine_id;
    const group = svgEl("g", { class: `station ${station.state}`, transform: `translate(${pos.x - pos.w / 2} ${pos.y - pos.h / 2})` });
    group.appendChild(svgEl("rect", { width: pos.w, height: pos.h }));
    const title = svgEl("text", { x: pos.w / 2, y: pos.h / 2 - 7 });
    title.textContent = station.name || pos.label || id;
    group.appendChild(title);
    const detail = svgEl("text", { class: "state", x: pos.w / 2, y: pos.h / 2 + 17 });
    detail.textContent = station.state ? station.state.replaceAll("_", " ").toUpperCase() : "READY";
    group.appendChild(detail);
    layer.appendChild(group);
  });
}

function renderRoutes(state) {
  const layer = document.getElementById("routeLayer");
  if (!layer) return;
  layer.innerHTML = "";
  const routeStatus = state.route_status || {};
  const trackMap = {
    input_to_vision: pathData([stationPort("input_queue", "right"), stationPort("vision", "left")]),
    vision_to_station_a: pathData([
      stationPort("vision", "right"),
      stationPort("processing_buffer", "left"),
      stationPort("processing_buffer", "right"),
      [565, 300],
      [590, 205],
      stationPort("station_a", "left"),
    ]),
    vision_to_station_b: pathData([
      stationPort("vision", "right"),
      stationPort("processing_buffer", "left"),
      stationPort("processing_buffer", "right"),
      [565, 420],
      [590, 505],
      stationPort("station_b", "left"),
    ]),
    station_a_to_quality: pathData([
      stationPort("station_a", "right"),
      [775, 205],
      [820, 300],
      stationPort("quality_buffer", "left"),
      stationPort("quality_buffer", "right"),
      stationPort("quality", "left"),
    ]),
    station_b_to_quality: pathData([
      stationPort("station_b", "right"),
      [775, 505],
      [820, 420],
      stationPort("quality_buffer", "left"),
      stationPort("quality_buffer", "right"),
      stationPort("quality", "left"),
    ]),
    quality_to_accepted: pathData([stationPort("quality", "right"), [1124, 360], [1124, 230], stationPort("accepted_output", "left")]),
    quality_to_reject: pathData([stationPort("quality", "right"), [1124, 360], [1124, 500], stationPort("reject_output", "left")]),
  };
  Object.entries(trackMap).forEach(([route, d]) => {
    const path = svgEl("path", { class: "track", d, "data-route": route, "marker-end": "url(#arrow)" });
    path.classList.toggle("blocked", routeStatus[route] === "blocked");
    path.classList.toggle("active-route", routeStatus[route] !== "blocked");
    layer.appendChild(path);
  });

  const recoveryRoutes = [
    [stationPort("station_a", "bottom"), [735, 420], [810, 570], stationPort("recovery_buffer", "left")],
    [stationPort("station_b", "bottom"), [735, 560], [810, 610], stationPort("recovery_buffer", "left")],
  ];
  recoveryRoutes.forEach((points) => {
    layer.appendChild(svgEl("path", { class: "track recovery-route", d: pathData(points), "marker-end": "url(#arrow)" }));
  });
}

function renderProducts(state) {
  const layer = document.getElementById("productLayer");
  if (!layer) return;
  layer.innerHTML = "";
  state.products.forEach((product, index) => {
    const pos = productPosition(product, index);
    const group = svgEl("g", { class: "product", transform: `translate(${pos.x} ${pos.y})` });
    group.appendChild(svgEl("circle", { r: 16, fill: productColors[product.product_type] || "#64748b" }));
    const label = svgEl("text", { y: 1 });
    label.textContent = product.product_id.split("-")[1].slice(-2);
    group.appendChild(label);
    layer.appendChild(group);
  });
}

function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  const width = Math.max(640, Math.floor(rect.width * dpr));
  const height = Math.max(360, Math.floor(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: width / dpr, height: height / dpr };
}

function scaledScene(ctx, width, height) {
  const scene = { width: 1280, height: 720 };
  const scale = Math.min(width / scene.width, height / scene.height);
  const offsetX = (width - scene.width * scale) / 2;
  const offsetY = (height - scene.height * scale) / 2;
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);
}

function roundedRect(ctx, x, y, w, h, r = 8) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function drawLabel(ctx, text, x, y, opts = {}) {
  ctx.fillStyle = opts.color || "#0f172a";
  ctx.font = `${opts.weight || 800} ${opts.size || 16}px Inter, system-ui, sans-serif`;
  ctx.textAlign = opts.align || "center";
  ctx.textBaseline = opts.baseline || "middle";
  ctx.fillText(text, x, y);
}

function pointDistance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function pathLength(points) {
  let length = 0;
  forEachSegment(points, (a, b) => {
    length += pointDistance(a, b);
  });
  return length;
}

function pointOnPath(points, progress) {
  if (points.length === 0) return [0, 0];
  if (points.length === 1) return points[0];
  const total = Math.max(1, pathLength(points));
  let remaining = total * Math.max(0, Math.min(1, progress));
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const segment = pointDistance(start, end);
    if (remaining <= segment) {
      const t = segment ? remaining / segment : 1;
      return [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t];
    }
    remaining -= segment;
  }
  return points[points.length - 1];
}

function pointAtPath(points, progress) {
  return pointOnPath(points, progress);
}

function locationKey(product) {
  if (product.status === "paused") return "recovery_buffer";
  if (product.status === "processing" && product.assigned_station) return product.assigned_station;
  return product.current_location || "processing_buffer";
}

function stationForCompletionEvent(event) {
  const dataStation = event.data?.station;
  if (dataStation) return dataStation;
  if (["vision", "station_a", "station_b", "quality"].includes(event.source)) return event.source;
  return null;
}

function processDetectorEvents(state) {
  const now = performance.now();
  state.events.forEach((event) => {
    if (seenEventIds.has(event.event_id)) return;
    seenEventIds.add(event.event_id);
    if (event.event_type === "process_completed" || event.event_type === "vision_passed") {
      const station = stationForCompletionEvent(event);
      if (station) detectorDoneUntil.set(station, now + 1500);
    }
    if (event.event_type === "product_completed") {
      detectorDoneUntil.set("quality", now + 1500);
      detectorDoneUntil.set("accepted_output", now + 1500);
    }
    if (event.event_type === "product_rejected") {
      detectorDoneUntil.set(event.source === "vision" ? "vision" : "quality", now + 1500);
      detectorDoneUntil.set("reject_output", now + 1500);
    }
  });
}

function freshGazeboVisuals(state) {
  const visuals = state.gazebo_visuals;
  return Boolean(
    visuals?.source === "gazebo" &&
    visuals.updated_at &&
    Date.now() / 1000 - Number(visuals.updated_at) <= 2.0
  );
}

function detectorState(id, state, machines) {
  const now = performance.now();
  const machine = machines[id];
  if (machine?.state === "fault" || machine?.state === "emergency_stop") return "fault";

  const visualMovingToThisLocation = Array.from(visualProducts.values()).some((visual) =>
    visual.destination === id && isVisualTransporting(visual, now)
  );
  if (visualMovingToThisLocation) return "processing";
  if (id === "conveyor_main" && visualRouteSet(state).size) return "processing";

  if (machine?.current_product_id) {
    const visual = visualProducts.get(machine.current_product_id);
    if (visual && visual.location === id && !isVisualTransporting(visual, now)) return "processing";
    return "idle";
  }
  if ((detectorDoneUntil.get(id) || 0) > now) return "done";
  if (id === "input_queue" && state.queues?.input?.length) return "processing";
  if (["processing_buffer", "quality_buffer", "recovery_buffer"].includes(id)) {
    if (state.products.some((product) => {
      const visual = visualProducts.get(product.product_id);
      return visual ? visual.location === id && !isVisualTransporting(visual, now) : product.current_location === id;
    })) return "processing";
  }
  return "idle";
}

function drawFactoryShell(ctx) {
  ctx.fillStyle = "#d7ddd9";
  ctx.fillRect(0, 0, 1280, 720);

  ctx.fillStyle = "#f3f1ec";
  roundedRect(ctx, 34, 42, 1212, 632, 8);
  ctx.fill();

  ctx.strokeStyle = "rgba(122, 113, 101, 0.16)";
  ctx.lineWidth = 1;
  for (let x = 78; x < 1210; x += 72) {
    ctx.beginPath();
    ctx.moveTo(x, 104);
    ctx.lineTo(x, 650);
    ctx.stroke();
  }
  for (let y = 118; y < 650; y += 72) {
    ctx.beginPath();
    ctx.moveTo(58, y);
    ctx.lineTo(1222, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#2f3437";
  ctx.lineWidth = 8;
  roundedRect(ctx, 34, 42, 1212, 632, 8);
  ctx.stroke();

  ctx.fillStyle = "#d7d2ca";
  ctx.fillRect(52, 52, 1176, 38);
  drawLabel(ctx, "ReConFactory smart production cell", 640, 72, { size: 18 });

  ctx.fillStyle = "rgba(161, 98, 7, 0.12)";
  roundedRect(ctx, 78, 584, 1092, 42, 6);
  ctx.fill();
  ctx.strokeStyle = "#9a6a2f";
  ctx.lineWidth = 3;
  ctx.setLineDash([12, 8]);
  ctx.stroke();
  ctx.setLineDash([]);
  drawLabel(ctx, "operator safety aisle", 626, 605, { size: 13, color: "#6b3f14", weight: 750 });
}

function drawPolyline(ctx, points, width, color, lineDash = []) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.setLineDash(lineDash);
  ctx.beginPath();
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.restore();
}

function forEachSegment(points, callback) {
  for (let index = 0; index < points.length - 1; index += 1) {
    callback(points[index], points[index + 1]);
  }
}

function drawConveyor(ctx, routeName, points, routeStatus, activeRoutes = new Set()) {
  const blocked = routeStatus[routeName] === "blocked";
  const activeTransport = activeRoutes.has(routeName);
  const pulse = activeTransport ? 0.78 + Math.sin(performance.now() / 130) * 0.22 : 0;
  const activeColor = pulse > 0.92 ? "#f97316" : "#f59e0b";
  drawPolyline(ctx, points, 46, "#2f3437");
  drawPolyline(ctx, points, 32, "#4b4a45");
  drawPolyline(ctx, points, 6, blocked ? "#991b1b" : activeTransport ? activeColor : "#2f855a", blocked ? [14, 11] : []);

  ctx.fillStyle = "#9a958d";
  forEachSegment(points, ([x1, y1], [x2, y2]) => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy);
    const steps = Math.floor(length / 28);
    for (let i = 1; i < steps; i += 1) {
      const t = i / steps;
      const x = x1 + dx * t;
      const y = y1 + dy * t;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
    }

    const angle = Math.atan2(dy, dx);
    const ax = x1 + dx * 0.68;
    const ay = y1 + dy * 0.68;
    ctx.save();
    ctx.translate(ax, ay);
    ctx.rotate(angle);
    ctx.fillStyle = blocked ? "#fecaca" : activeTransport ? activeColor : "#b8c9b8";
    ctx.beginPath();
    ctx.moveTo(11, 0);
    ctx.lineTo(-9, -7);
    ctx.lineTo(-9, 7);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  });
}

function drawRouteArrow(ctx, x, y, angle, color, scale = 1) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = "rgba(15, 23, 42, 0.22)";
  ctx.beginPath();
  ctx.moveTo(17 * scale, 3 * scale);
  ctx.lineTo(-13 * scale, -8 * scale);
  ctx.lineTo(-9 * scale, 0);
  ctx.lineTo(-13 * scale, 8 * scale);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = color;
  ctx.strokeStyle = "#fff7ed";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(16 * scale, 0);
  ctx.lineTo(-14 * scale, -10 * scale);
  ctx.lineTo(-9 * scale, 0);
  ctx.lineTo(-14 * scale, 10 * scale);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawActiveRouteIndicators(ctx, activeRoutes, routeStatus) {
  const now = performance.now();
  const pulse = 0.78 + Math.sin(now / 120) * 0.22;
  const color = pulse > 0.92 ? "#fb923c" : "#f59e0b";
  physicalRouteNames.forEach((routeName) => {
    if (!activeRoutes.has(routeName)) return;
    if (routeStatus[routeName] === "blocked") return;
    const points = routeSegments[routeName];
    if (!points || points.length < 2) return;
    const total = pathLength(points);
    const count = Math.max(1, Math.min(4, Math.floor(total / 160) + 1));
    const phase = (now % 900) / 900;
    for (let index = 0; index < count; index += 1) {
      const progress = (phase + index / count) % 1;
      const [x, y] = pointAtPath(points, progress);
      const [nx, ny] = pointAtPath(points, Math.min(1, progress + 0.025));
      const angle = Math.atan2(ny - y, nx - x);
      drawRouteArrow(ctx, x, y, angle, color, total < 190 ? 0.82 : 1);
    }
  });
}

function stateColor(state) {
  if (state === "fault" || state === "emergency_stop") return "#dc2626";
  if (state === "processing") return "#d97706";
  if (state === "done") return "#16a34a";
  if (state === "running") return "#57534e";
  if (state === "maintenance" || state === "paused" || state === "blocked") return "#9a6a2f";
  return "#78716c";
}

function drawDetector(ctx, x, y, state) {
  const color = stateColor(state);
  const fill =
    state === "processing" ? "#d97706" :
    state === "done" ? "#16a34a" :
    state === "fault" ? "#dc2626" :
    "#6b7280";

  ctx.save();
  ctx.strokeStyle = "#2f3437";
  ctx.lineWidth = 4;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x, y + 10);
  ctx.lineTo(x, y + 25);
  ctx.stroke();

  ctx.fillStyle = "rgba(15, 23, 42, 0.18)";
  roundedRect(ctx, x - 20, y - 8, 42, 24, 8);
  ctx.fill();

  ctx.fillStyle = "#1f2933";
  roundedRect(ctx, x - 22, y - 12, 44, 24, 8);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  roundedRect(ctx, x - 22, y - 12, 44, 24, 8);
  ctx.stroke();

  ctx.fillStyle = fill;
  roundedRect(ctx, x - 14, y - 6, 28, 12, 6);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 255, 255, 0.28)";
  roundedRect(ctx, x - 10, y - 4, 10, 4, 3);
  ctx.fill();
  ctx.restore();
}

function drawMachineDetails(ctx, machine, layout, detector = "idle") {
  const status = machine?.state || "idle";
  const healthy = machine?.healthy !== false;
  const compact = layout.h < 70;
  const fill = status === "fault" || status === "emergency_stop" ? "#efe0dd" : healthy ? "#d7d2ca" : "#e6d7bd";
  const border = stateColor(status);
  const x = layout.x - layout.w / 2;
  const y = layout.y - layout.h / 2;

  ctx.fillStyle = "rgba(15, 23, 42, 0.13)";
  roundedRect(ctx, x + 8, y + 10, layout.w, layout.h, 10);
  ctx.fill();

  ctx.fillStyle = fill;
  ctx.strokeStyle = border;
  ctx.lineWidth = 3;
  roundedRect(ctx, x, y, layout.w, layout.h, 10);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "#b8b2aa";
  roundedRect(ctx, x + 12, y + 10, layout.w - 24, compact ? 22 : 26, 6);
  ctx.fill();
  drawLabel(ctx, layout.label, layout.x, y + (compact ? 21 : 25), { size: compact ? 13 : 14, color: "#171717" });

  drawDetector(ctx, layout.x, y - 18, detector);
}

function drawProcessHardware(ctx, machineId, layout) {
  const x = layout.x;
  const y = layout.y;
  ctx.strokeStyle = "#4b5563";
  ctx.lineWidth = 6;
  ctx.lineCap = "round";

  if (machineId === "vision") {
    ctx.beginPath();
    ctx.moveTo(x - 16, y - 8);
    ctx.lineTo(x - 16, y - 42);
    ctx.lineTo(x + 20, y - 42);
    ctx.stroke();
    ctx.fillStyle = "#1c1917";
    roundedRect(ctx, x + 10, y - 54, 44, 24, 6);
    ctx.fill();
    ctx.fillStyle = "#9ca3af";
    ctx.beginPath();
    ctx.arc(x + 20, y - 42, 5, 0, Math.PI * 2);
    ctx.fill();
  } else if (machineId === "station_a") {
    ctx.fillStyle = "#1c1917";
    roundedRect(ctx, x - 38, y - 16, 76, 12, 5);
    ctx.fill();
    roundedRect(ctx, x - 8, y - 8, 16, 42, 5);
    ctx.fill();
  } else if (machineId === "station_b") {
    ctx.strokeStyle = "#57534e";
    ctx.beginPath();
    ctx.arc(x, y, 30, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#a8a29e";
    ctx.beginPath();
    ctx.arc(x, y, 18, 0, Math.PI * 2);
    ctx.fill();
  } else if (machineId === "quality") {
    ctx.fillStyle = "#57534e";
    roundedRect(ctx, x - 36, y - 38, 72, 20, 6);
    ctx.fill();
    ctx.strokeStyle = "#3f3f3f";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x - 42, y + 36);
    ctx.lineTo(x + 42, y + 36);
    ctx.stroke();
  }
}

function drawBuffersAndBins(ctx) {
  const bufferIds = ["input_queue", "processing_buffer", "quality_buffer", "recovery_buffer"];
  bufferIds.forEach((id) => {
    const layout = factoryLayout[id];
    const x = layout.x - layout.w / 2;
    const y = layout.y - layout.h / 2;
    ctx.fillStyle = id === "recovery_buffer" ? "#ded2b6" : "#d6d3d1";
    ctx.strokeStyle = id === "recovery_buffer" ? "#8a5a23" : "#57534e";
    ctx.lineWidth = 2.5;
    roundedRect(ctx, x, y, layout.w, layout.h, 8);
    ctx.fill();
    ctx.stroke();
    drawLabel(ctx, layout.label, layout.x, y + 18, { size: 13, color: "#292524" });
  });

  [
    ["accepted_output", "#d4d1c8", "#4f5b45", "Accepted"],
    ["reject_output", "#d4d1c8", "#6f3f35", "Rejected"],
  ].forEach(([id, fill, stroke, label]) => {
    const layout = factoryLayout[id];
    const x = layout.x - layout.w / 2;
    const y = layout.y - layout.h / 2;
    ctx.fillStyle = fill;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 3;
    roundedRect(ctx, x, y, layout.w, layout.h, 8);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = stroke;
    ctx.fillRect(x + 14, y + 16, layout.w - 28, 12);
    drawLabel(ctx, label, layout.x, y + 55, { size: 14, color: "#0f172a" });
  });
}

function productTarget(product, index, overrideLocation = null) {
  const location = overrideLocation || locationKey(product);
  const layout = factoryLayout[location] || factoryLayout.processing_buffer;
  const slot = hashText(product.product_id) % 5;
  const lane = (hashText(`${product.product_id}-lane`) % 3) - 1;
  const enclosedLocations = new Set(["vision", "station_a", "station_b", "quality", "accepted_output", "reject_output"]);
  const bufferLocations = new Set(["input_queue", "processing_buffer", "quality_buffer", "recovery_buffer"]);
  let offsetX = (slot - 2) * 14;
  let offsetY = lane * 13 + (index % 2) * 7;

  if (enclosedLocations.has(location)) {
    offsetX = ((slot % 3) - 1) * 11;
    offsetY = lane * 8;
  } else if (bufferLocations.has(location)) {
    offsetX = ((slot % 3) - 1) * 12;
    offsetY = lane * 9;
  }

  return {
    x: layout.x + offsetX,
    y: layout.y + offsetY,
  };
}

function productStartTarget(product) {
  const layout = factoryLayout.input_queue;
  const lane = (hashText(`${product.product_id}-lane`) % 3) - 1;
  return {
    x: layout.x,
    y: layout.y + lane * 13,
  };
}

function visualTiming(state) {
  const sync = state.visual_sync || {};
  const speed = Math.max(0.25, Number(state.simulation_speed || 1));
  return {
    minMs: Number(sync.min_transition_ms || 1100) / speed,
    maxMs: Number(sync.max_transition_ms || 2500) / speed,
    pxPerSecond: Number(sync.browser_px_per_second || 310) * speed,
  };
}

function transitionDurationMs(path, state) {
  const timing = visualTiming(state);
  const distance = pathLength(path);
  const duration = (distance / Math.max(1, timing.pxPerSecond)) * 1000;
  return Math.max(timing.minMs, Math.min(timing.maxMs, duration));
}

function routeNameForLocations(fromLocation, toLocation) {
  return routeNameByLocationPair[`${fromLocation}>${toLocation}`] || `${fromLocation}_to_${toLocation}`;
}

function displaySegmentsForRoute(routeName) {
  return routeDisplaySegments[routeName] || [routeName];
}

function expandedRouteSet(routes) {
  const expanded = new Set();
  routes.forEach((route) => {
    expanded.add(route);
    displaySegmentsForRoute(route).forEach((segment) => expanded.add(segment));
  });
  return expanded;
}

function normalizedProductRoute(product) {
  const knownLocations = new Set(Object.keys(factoryLayout));
  const route = (product.route || []).filter((location) => typeof location === "string" && knownLocations.has(location));
  const target = locationKey(product);
  if (!route.length) route.push("input_queue");
  if (target && knownLocations.has(target) && route[route.length - 1] !== target) route.push(target);
  return route.filter((location, index) => index === 0 || route[index - 1] !== location);
}

function activateRouteLeg(fromLocation, toLocation, state, now = performance.now()) {
  if (!fromLocation || !toLocation || fromLocation === toLocation) return;
  const routeName = routeNameForLocations(fromLocation, toLocation);
  const points = routeByLocationPair[`${fromLocation}>${toLocation}`] || routeSegments[routeName];
  if (!points) return;
  const until = now + transitionDurationMs(points, state) + ROUTE_INDICATOR_HOLD_MS;
  routeIndicatorUntil.set(routeName, until);
  displaySegmentsForRoute(routeName).forEach((segment) => routeIndicatorUntil.set(segment, until));
}

function syncRouteIndicatorsFromProductHistory(state, now = performance.now()) {
  const liveProducts = new Set();
  state.products.forEach((product) => {
    liveProducts.add(product.product_id);
    const route = normalizedProductRoute(product);
    if (route.length < 2) {
      productRouteHistoryLength.set(product.product_id, route.length);
      return;
    }
    const previousLength = productRouteHistoryLength.get(product.product_id);
    const startIndex = previousLength == null ? Math.max(1, route.length - 2) : Math.max(1, previousLength);
    for (let index = startIndex; index < route.length; index += 1) {
      activateRouteLeg(route[index - 1], route[index], state, now);
    }
    productRouteHistoryLength.set(product.product_id, route.length);
  });
  for (const productId of productRouteHistoryLength.keys()) {
    if (!liveProducts.has(productId)) productRouteHistoryLength.delete(productId);
  }
}

function visualTargetsForProduct(product, currentLocation) {
  const route = normalizedProductRoute(product);
  const target = locationKey(product);
  const lastCurrentIndex = route.lastIndexOf(currentLocation);
  const targets = lastCurrentIndex >= 0 ? route.slice(lastCurrentIndex + 1) : [target];
  const deduped = [];
  targets.forEach((location) => {
    if (location === currentLocation) return;
    if (deduped[deduped.length - 1] === location) return;
    deduped.push(location);
  });
  return deduped;
}

function nextTriggeredDestination(product, triggerLocation) {
  const hiddenTransitStops = new Set(["processing_buffer", "quality_buffer"]);
  const finalOutputs = new Set(["accepted_output", "reject_output"]);
  const route = normalizedProductRoute(product).filter((location) => !hiddenTransitStops.has(location));
  const target = locationKey(product);
  if (target && factoryLayout[target] && !hiddenTransitStops.has(target) && route[route.length - 1] !== target) {
    route.push(target);
  }

  if (triggerLocation === "processing_buffer") {
    const processingStation = route.find((location) => location === "station_a" || location === "station_b");
    return processingStation || triggerLocation;
  }
  if (triggerLocation === "quality_buffer") {
    return route.includes("quality") || finalOutputs.has(target) ? "quality" : triggerLocation;
  }

  const triggerIndex = route.lastIndexOf(triggerLocation);
  if (triggerIndex >= 0) {
    return route[triggerIndex + 1] || triggerLocation;
  }
  if (triggerLocation === "input_queue" && route.includes("vision")) return "vision";
  if (triggerLocation === "vision") {
    const processingStation = route.find((location) => location === "station_a" || location === "station_b");
    if (processingStation) return processingStation;
  }
  if ((triggerLocation === "station_a" || triggerLocation === "station_b") && route.includes("quality")) {
    return "quality";
  }
  if ((triggerLocation === "station_a" || triggerLocation === "station_b") && finalOutputs.has(target)) {
    return "quality";
  }
  if (finalOutputs.has(target)) return triggerLocation;
  return target && factoryLayout[target] && !hiddenTransitStops.has(target) ? target : triggerLocation;
}

function mergeVisualPending(visual, destinations) {
  if (!visual.pendingDestinations) visual.pendingDestinations = [];
  destinations.forEach((destination) => {
    if (visual.pendingDestinations[visual.pendingDestinations.length - 1] === destination) return;
    if (visual.pendingDestinations.includes(destination)) return;
    visual.pendingDestinations.push(destination);
  });
}

function shiftVisualPending(visual) {
  if (!visual.pendingDestinations?.length) return null;
  const destination = visual.pendingDestinations.shift();
  if (!visual.pendingDestinations.length) visual.pendingDestinations = [];
  return destination;
}

function transitionPath(fromLocation, toLocation, current, target) {
  const routed = routeByLocationPair[`${fromLocation}>${toLocation}`];
  const points = routed ? routed.map(([x, y]) => [x, y]) : [[current.x, current.y], [target.x, target.y]];
  points[0] = [current.x, current.y];
  points[points.length - 1] = [target.x, target.y];
  return points;
}

function isVisualTransporting(visual, now = performance.now()) {
  return Boolean(visual?.route && now < (visual.transportUntil || 0));
}

function setVisualRoute(visual, route, now = performance.now()) {
  if (visual.route && visual.route !== route) {
    routeIndicatorUntil.delete(visual.route);
  }
  visual.route = route;
  if (route) routeIndicatorUntil.set(route, now + ROUTE_INDICATOR_HOLD_MS);
}

function startVisualMovement(current, product, index, destination, state, now = performance.now()) {
  const routeTarget = productTarget(product, index, destination);
  const path = transitionPath(current.location, destination, current, routeTarget);
  current.path = path;
  current.destination = destination;
  setVisualRoute(current, routeNameForLocations(current.location, destination), now);
  current.transportStartedAt = now;
  current.transportUntil = now + transitionDurationMs(path, state);
  current.pendingDestination = null;
  current.targetX = routeTarget.x;
  current.targetY = routeTarget.y;
}

function visualRouteSet(state) {
  const now = performance.now();
  const routes = new Set();
  for (const visual of visualProducts.values()) {
    if (isVisualTransporting(visual, now) && visual.route) {
      routes.add(visual.route);
      routeIndicatorUntil.set(visual.route, now + ROUTE_INDICATOR_HOLD_MS);
    }
  }
  for (const [route, until] of routeIndicatorUntil.entries()) {
    if (until > now) routes.add(route);
    else routeIndicatorUntil.delete(route);
  }
  return expandedRouteSet(routes);
}

function updateProductTargets(state) {
  const now = performance.now();
  const hasFreshGazeboVisuals = freshGazeboVisuals(state);
  if (!hasFreshGazeboVisuals) syncRouteIndicatorsFromProductHistory(state, now);
  const gazeboLocations = hasFreshGazeboVisuals ? state.gazebo_visuals.product_locations || {} : {};
  const seen = new Set();
  state.products.forEach((product, index) => {
    seen.add(product.product_id);
    let current = visualProducts.get(product.product_id);
    const nextLocation = locationKey(product);
    const rawGazeboLocation = gazeboLocations[product.product_id];
    const gazeboLocation = factoryLayout[rawGazeboLocation] ? rawGazeboLocation : null;
    const productDone = product.status === "completed" || product.status === "rejected";
    let requestedLocation = nextLocation;
    if (hasFreshGazeboVisuals) {
      if (gazeboLocation) {
        requestedLocation = nextTriggeredDestination(product, gazeboLocation);
      } else if (current) {
        requestedLocation = isVisualTransporting(current, now)
          ? current.destination
          : current.location;
      } else {
        requestedLocation = "input_queue";
      }
    }
    if (!current) {
      const startLocation = gazeboLocation || requestedLocation || "input_queue";
      const start = productTarget(product, index, startLocation);
      visualProducts.set(product.product_id, {
        x: start.x,
        y: start.y,
        targetX: start.x,
        targetY: start.y,
        angle: 0,
        useGazeboPose: false,
        location: startLocation,
        destination: startLocation,
        pendingDestination: null,
        pendingDestinations: [],
        route: "",
        transportStartedAt: 0,
        transportUntil: 0,
        path: [[start.x, start.y]],
        product,
        index,
      });
      current = visualProducts.get(product.product_id);
      if (current && state.running && startLocation !== requestedLocation) {
        startVisualMovement(current, product, index, requestedLocation, state, now);
      }
    } else {
      if (current.route && now >= current.transportUntil) {
        current.location = current.destination;
        setVisualRoute(current, "", now);
        current.pendingDestination = current.pendingDestination || null;
        const arrived = productTarget(product, index, current.location);
        current.x = arrived.x;
        current.y = arrived.y;
      }

      if (!state.running && !productDone) {
        current.pendingDestination = null;
        if (!isVisualTransporting(current, now)) {
          const target = productTarget(product, index, current.location);
          current.targetX = target.x;
          current.targetY = target.y;
          current.x = target.x;
          current.y = target.y;
        }
        current.useGazeboPose = false;
        current.product = product;
        current.index = index;
        return;
      }

      if (isVisualTransporting(current, now) && requestedLocation !== current.destination) {
        current.pendingDestination = requestedLocation;
      }

      const destination = current.pendingDestination || requestedLocation;
      if (!isVisualTransporting(current, now) && current.location !== destination) {
        startVisualMovement(current, product, index, destination, state, now);
      } else if (!isVisualTransporting(current, now)) {
        const target = productTarget(product, index, current.location);
        current.targetX = target.x;
        current.targetY = target.y;
        current.x = target.x;
        current.y = target.y;
      }
      current.useGazeboPose = false;
      current.product = product;
      current.index = index;
    }
  });

  for (const productId of visualProducts.keys()) {
    if (!seen.has(productId)) visualProducts.delete(productId);
  }
}

function drawProduct(ctx, visual) {
  const now = performance.now();
  if (visual.route && now >= (visual.transportUntil || 0)) {
    visual.location = visual.destination;
    setVisualRoute(visual, "", now);
    visual.x = visual.targetX;
    visual.y = visual.targetY;
  }

  if (isVisualTransporting(visual, now)) {
    const duration = Math.max(1, (visual.transportUntil || now) - (visual.transportStartedAt || now));
    const progress = 1 - Math.max(0, (visual.transportUntil - now) / duration);
    const [x, y] = pointOnPath(visual.path || [[visual.x, visual.y], [visual.targetX, visual.targetY]], progress);
    visual.x = x;
    visual.y = y;
  } else if (visual.useGazeboPose) {
    visual.x += (visual.targetX - visual.x) * 0.46;
    visual.y += (visual.targetY - visual.y) * 0.46;
  } else {
    visual.x = visual.targetX;
    visual.y = visual.targetY;
  }

  const product = visual.product;
  const color = productColors[product.product_type] || "#64748b";
  ctx.save();
  ctx.translate(visual.x, visual.y);
  ctx.rotate(visual.useGazeboPose ? visual.angle || 0 : 0);
  ctx.fillStyle = "rgba(15, 23, 42, 0.2)";
  ctx.beginPath();
  ctx.ellipse(4, 18, 22, 7, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "#0f172a";
  ctx.lineWidth = 2;
  ctx.fillStyle = color;
  if (product.product_type === "blue_cylinder") {
    ctx.beginPath();
    ctx.ellipse(0, 0, 19, 14, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
    ctx.beginPath();
    ctx.ellipse(-4, -4, 9, 5, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (product.product_type === "green_component") {
    roundedRect(ctx, -19, -13, 38, 26, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#dcfce7";
    ctx.fillRect(-8, -13, 16, 26);
  } else {
    roundedRect(ctx, -17, -17, 34, 34, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
    ctx.fillRect(-13, -13, 14, 10);
  }

  if (!["accepted_output", "reject_output"].includes(product.current_location)) {
    drawLabel(ctx, product.product_id.split("-")[1], 0, 31, { size: 11, color: "#0f172a", weight: 800 });
  }
  ctx.restore();
}

function drawComponentDetectors(ctx, state, machines) {
  [
    "input_queue",
    "processing_buffer",
    "quality_buffer",
    "recovery_buffer",
    "accepted_output",
    "reject_output",
  ].forEach((id) => {
    const layout = factoryLayout[id];
    const x = layout.x;
    const y = layout.y - layout.h / 2 - 16;
    drawDetector(ctx, x, y, detectorState(id, state, machines));
  });
}

function mainActiveRouteSet(state) {
  return visualRouteSet(state);
}

function drawMainProducts(ctx, state) {
  const drawn = new Set();
  for (const visual of visualProducts.values()) {
    drawn.add(visual.product.product_id);
    drawProduct(ctx, visual);
  }
  state.products.forEach((product, index) => {
    if (drawn.has(product.product_id)) return;
    const target = productTarget(product, index, locationKey(product));
    drawProduct(ctx, {
      x: target.x,
      y: target.y,
      targetX: target.x,
      targetY: target.y,
      angle: 0,
      useGazeboPose: false,
      location: locationKey(product),
      destination: locationKey(product),
      route: "",
      transportUntil: 0,
      product,
      index,
    });
  });
}

function drawFactoryTwin(state) {
  if (activeVisualView !== "main") return;
  const canvas = document.getElementById("factoryCanvas");
  const { ctx, width, height } = resizeCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  ctx.save();
  scaledScene(ctx, width, height);

  const machines = Object.fromEntries(state.machines.map((machine) => [machine.machine_id, machine]));
  const routeStatus = state.route_status || {};
  const activeRoutes = mainActiveRouteSet(state);
  processDetectorEvents(state);

  drawFactoryShell(ctx);
  physicalRouteNames.forEach((routeName) => drawConveyor(ctx, routeName, routeSegments[routeName], routeStatus, activeRoutes));
  drawBuffersAndBins(ctx);
  drawComponentDetectors(ctx, state, machines);

  ["vision", "station_a", "station_b", "quality", "conveyor_main"].forEach((machineId) => {
    const layout = factoryLayout[machineId];
    drawMachineDetails(ctx, machines[machineId], layout, detectorState(machineId, state, machines));
  });

  drawActiveRouteIndicators(ctx, activeRoutes, routeStatus);

  drawMainProducts(ctx, state);

  drawLabel(ctx, `Tick ${state.tick} | ${state.running ? "running" : "paused"}`, 1054, 122, {
    size: 15,
    color: "#0f766e",
    weight: 850,
  });
  ctx.restore();
}

function animationLoop() {
  if (latestState) drawFactoryTwin(latestState);
  animationFrame = requestAnimationFrame(animationLoop);
}

function startAnimation() {
  if (!animationFrame) animationLoop();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function classToken(value) {
  return String(value || "info").toLowerCase().replace(/[^a-z0-9_-]/g, "_");
}

function displayLabel(value) {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replace(/\b[a-z]/g, (char) => char.toUpperCase());
}

function badge(text, extra = "") {
  const rawText = String(text ?? "");
  const cssClass = classToken(extra || rawText);
  return `<span class="badge ${cssClass}">${escapeHtml(rawText.replaceAll("_", " "))}</span>`;
}

function renderMetrics(state) {
  const stats = state.stats;
  const metrics = [
    ["Total", stats.total_products],
    ["Completed", stats.completed_products],
    ["Rejected", stats.rejected_products],
    ["Paused", stats.paused_products],
    ["Faults", stats.fault_count],
    ["Rerouted", stats.rerouted_products],
    ["Throughput", stats.throughput_per_tick.toFixed(2)],
    ["Avg Cycle", stats.average_cycle_time_ticks.toFixed(1)],
    ["Downtime", stats.total_downtime_ticks],
    ["Recovery", `${(stats.recovery_success_rate * 100).toFixed(0)}%`],
  ];
  document.getElementById("metricGrid").innerHTML = metrics
    .map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderMachines(state) {
  const html = state.machines
    .map((machine) => {
      const temp = machine.sensors.temperature_c;
      const capabilities = machine.capabilities.join(", ") || "monitoring";
      const fault = machine.active_fault;
      return `<div class="row machine-row machine-${classToken(machine.state)}">
        <div class="row-title"><span>${escapeHtml(machine.name)}</span>${badge(machine.state)}</div>
        <div class="muted">${escapeHtml(capabilities)}</div>
        <div class="muted">Temp ${temp} C | Health ${(machine.health_score * 100).toFixed(0)}% ${machine.maintenance_status}</div>
        <div class="muted">Queue ${machine.queue_length || 0} | Product ${machine.current_product_id || "none"}</div>
        ${fault ? `<div class="machine-alert">Fault: ${escapeHtml(displayLabel(fault.fault_type))} | ${escapeHtml(fault.recommendation)}</div>` : '<div class="muted">Fault none</div>'}
      </div>`;
    })
    .join("");
  document.getElementById("machineList").innerHTML = html || '<p class="muted">No machines.</p>';
}

function renderProductsList(state) {
  const html = state.products
    .slice()
    .reverse()
    .map((product) => `<div class="row">
      <div class="row-title"><span>${escapeHtml(product.product_id)} ${escapeHtml(product.display_name)}</span>${badge(product.status)}</div>
      <div class="muted">Next: ${escapeHtml(product.next_process || "done")} | Location: ${escapeHtml(product.current_location)}</div>
      <div class="muted">Quality: ${escapeHtml(product.quality)}${product.defect_reason ? ` | ${escapeHtml(product.defect_reason)}` : ""}</div>
    </div>`)
    .join("");
  document.getElementById("productList").innerHTML = html || '<p class="muted">No products yet.</p>';
}

function eventTone(event) {
  const eventType = event.event_type || "";
  if (event.severity === "critical" || eventType === "emergency_stop") return "critical";
  if (eventType.includes("fault") || event.severity === "high") return "fault";
  if (eventType === "product_rejected") return "rejected";
  if (eventType === "machine_recovered") return "recovered";
  if (eventType === "product_paused" || eventType === "reconfiguration_completed") return "warning";
  if (["product_completed", "process_completed", "vision_passed"].includes(eventType)) return "success";
  if (event.severity === "warning") return "warning";
  return "info";
}

function eventSourceLabel(event, machineNames) {
  const data = event.data || {};
  const machineId = data.machine_id || data.station || event.source;
  return machineNames[machineId] || displayLabel(machineId || "factory");
}

function eventDetailChips(event, machineNames) {
  const data = event.data || {};
  const chips = [];
  const add = (label, value) => {
    if (value === null || value === undefined || value === "") return;
    chips.push(`<span class="event-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(value)}</span>`);
  };

  if (data.machine_id) add("Machine", machineNames[data.machine_id] || displayLabel(data.machine_id));
  if (data.station) add("Station", machineNames[data.station] || displayLabel(data.station));
  if (data.product_id) add("Product", data.product_id);
  if (data.fault_type) add("Fault", displayLabel(data.fault_type));
  if (data.likely_cause) add("Cause", data.likely_cause);
  if (data.action_type) add("Action", displayLabel(data.action_type));
  if (data.process) add("Process", displayLabel(data.process));
  if (typeof data.accepted === "boolean") add("Result", data.accepted ? "accepted" : "rejected");
  if (Array.isArray(data.rerouted_products)) add("Rerouted", data.rerouted_products.length ? data.rerouted_products.join(", ") : "none");
  if (Array.isArray(data.paused_products)) add("Paused", data.paused_products.length ? data.paused_products.join(", ") : "none");
  if (data.reason) add("Reason", data.reason);
  if (data.recommendation) add("Action", data.recommendation);
  return chips.join("");
}

function renderEvents(state) {
  const machineNames = Object.fromEntries(state.machines.map((machine) => [machine.machine_id, machine.name]));
  const html = state.events
    .slice()
    .reverse()
    .slice(0, 25)
    .map((event) => {
      const tone = eventTone(event);
      const details = eventDetailChips(event, machineNames);
      return `<div class="row event-row event-${tone}">
        <div class="event-top">
          <span class="event-kind">${escapeHtml(displayLabel(event.event_type))}</span>
          ${badge(event.severity)}
        </div>
        <div class="event-message">${escapeHtml(event.message)}</div>
        ${details ? `<div class="event-details">${details}</div>` : ""}
        <div class="muted event-meta">${escapeHtml(eventSourceLabel(event, machineNames))} | ${new Date(event.timestamp).toLocaleTimeString()}</div>
      </div>`;
    })
    .join("");
  document.getElementById("eventLog").innerHTML = html || '<p class="muted">No events yet.</p>';
}

function renderRecoveryButtons(state) {
  const faulted = state.machines.filter((machine) => machine.state === "fault" || machine.state === "emergency_stop");
  document.getElementById("recoverButtons").innerHTML = faulted
    .map((machine) => `<button data-recover="${machine.machine_id}">Recover ${machine.name}</button>`)
    .join("") || '<p class="muted">No faulted machines.</p>';
}

function renderIntegrations(data) {
  const container = document.getElementById("integrationList");
  if (!container || !data.items) return;
  container.innerHTML = data.items
    .map((item) => `<div class="integration-item">
      <strong><span>${item.name.replaceAll("_", " ")}</span>${badge(item.installed ? "ready" : "missing", item.installed ? "completed" : "warning")}</strong>
      <div class="muted">${item.version || item.command || item.detail || "No details"}</div>
    </div>`)
    .join("");
}

async function refreshIntegrations() {
  try {
    const response = await fetch("/api/integrations");
    if (!response.ok) throw new Error(await response.text());
    renderIntegrations(await response.json());
  } catch (error) {
    document.getElementById("integrationList").innerHTML = `<p class="muted">Integration check failed: ${error.message}</p>`;
  }
}

function renderExperiment(result) {
  const failStop = result.without_recovery;
  const recovery = result.with_recovery;
  const rows = [
    ["Products completed", failStop.products_completed, recovery.products_completed],
    ["Products rejected", failStop.products_rejected, recovery.products_rejected],
    ["Products paused", failStop.products_paused, recovery.products_paused],
    ["Faults", failStop.fault_count, recovery.fault_count],
    ["Rerouted products", failStop.rerouted_products, recovery.rerouted_products],
    ["Ticks", failStop.ticks, recovery.ticks],
  ];
  document.getElementById("experimentResult").innerHTML = `<table class="comparison-table">
    <thead><tr><th>Metric</th><th>Without Recovery</th><th>With Recovery</th></tr></thead>
    <tbody>${rows.map((row) => `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td></tr>`).join("")}</tbody>
  </table>`;
}

async function runExperiment() {
  const target = document.getElementById("experimentResult");
  target.innerHTML = '<p class="muted">Running comparison...</p>';
  const response = await fetch("/api/experiments/recovery?product_count=12");
  if (!response.ok) throw new Error(await response.text());
  renderExperiment(await response.json());
}

function render(state) {
  latestState = state;
  updateProductTargets(state);
  document.getElementById("tickValue").textContent = state.tick;
  document.getElementById("lastDecision").textContent = state.last_decision;
  const runState = document.getElementById("runState");
  runState.textContent = state.running ? "Running" : "Paused";
  runState.classList.toggle("running", state.running);
  const runToggle = document.getElementById("runToggleBtn");
  const hasStarted = state.tick > 0 || state.products.length > 0;
  runToggle.textContent = state.running ? "Pause" : hasStarted ? "Resume" : "Start";
  runToggle.classList.toggle("secondary", !state.running && hasStarted);
  renderRoutes(state);
  renderStations(state);
  renderProducts(state);
  renderMetrics(state);
  renderMachines(state);
  renderProductsList(state);
  renderEvents(state);
  renderRecoveryButtons(state);
}

function setVisualView(view) {
  activeVisualView = view;
  document.querySelectorAll("[data-visual-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.visualView === view);
  });
  document.getElementById("factoryCanvas").hidden = view !== "main";
  document.getElementById("statisticsView").hidden = view !== "stats";
  if (latestState && view === "main") drawFactoryTwin(latestState);
}

async function apiPost(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  render(data.snapshot || data);
  return data;
}

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await response.text());
  const data = await response.json();
  render(data);
  return data;
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);
  socket.onmessage = (message) => render(JSON.parse(message.data));
  socket.onclose = () => {
    if (!fallbackPoll) fallbackPoll = setInterval(() => apiGet("/api/status"), 1200);
  };
}

document.getElementById("runToggleBtn").addEventListener("click", () => {
  apiPost(latestState?.running ? "/api/stop" : "/api/start");
});
document.getElementById("resetBtn").addEventListener("click", () => apiPost("/api/reset"));
document.querySelectorAll("[data-visual-view]").forEach((button) => {
  button.addEventListener("click", () => setVisualView(button.dataset.visualView));
});
document.getElementById("addProductBtn").addEventListener("click", () => {
  const defect = document.getElementById("defectType").value;
  apiPost("/api/products", {
    product_type: document.getElementById("productType").value,
    defect_flags: defect ? [defect] : [],
  });
});

document.querySelectorAll("[data-fault]").forEach((button) => {
  button.addEventListener("click", () => {
    apiPost("/api/faults", {
      machine_id: button.dataset.machine,
      fault_type: button.dataset.fault,
      reason: "Dashboard fault injection",
    });
  });
});

document.getElementById("recoverButtons").addEventListener("click", (event) => {
  const button = event.target.closest("[data-recover]");
  if (button) apiPost("/api/recover", { machine_id: button.dataset.recover });
});

document.getElementById("refreshIntegrationsBtn").addEventListener("click", refreshIntegrations);
document.getElementById("runExperimentBtn").addEventListener("click", runExperiment);
window.addEventListener("resize", () => {
  if (latestState) drawFactoryTwin(latestState);
});

startAnimation();
apiGet("/api/status").then(() => {
  connectWebSocket();
  refreshIntegrations();
});
