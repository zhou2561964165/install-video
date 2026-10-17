import { Point, Rectangle } from 'pixi.js';

// DOM geometry is only the broad phase. Consumers must ask the registered alpha
// provider before hiding the cursor circle; no React or download state is used.
const silhouettes = new WeakMap();
const MAX_SAMPLE_EDGE = 256;

export function getMascotSilhouette(element) { return silhouettes.get(element); }

export function registerMascotSilhouette(element, { app, model, now = () => performance.now(), cacheMs = 150, maxSampleEdge = MAX_SAMPLE_EDGE, alphaThreshold = 32 }) {
  const ttl = Number.isFinite(cacheMs) ? Math.max(100, Math.min(200, cacheMs)) : 150;
  const edge = Number.isFinite(maxSampleEdge) ? Math.max(1, Math.min(MAX_SAMPLE_EDGE, maxSampleEdge)) : MAX_SAMPLE_EDGE;
  const threshold = Number.isFinite(alphaThreshold) ? Math.max(1, Math.min(255, alphaThreshold)) : 32;
  let disposed = false, cache = null, sampledAt = -Infinity;
  let lastNotifiedAt = -Infinity, notificationQueued = false;
  const ownsElement = () => !disposed && element && silhouettes.get(element) === provider;
  const clearSample = () => { cache = null; sampledAt = -Infinity; };
  const notify = () => {
    if (!ownsElement()) return;
    lastNotifiedAt = now();
    const EventClass = element.ownerDocument.defaultView.CustomEvent;
    element.dispatchEvent(new EventClass('mascot-silhouette-change', { bubbles: true }));
  };
  const provider = {
    invalidate() {
      if (!ownsElement()) return;
      clearSample();
      // Stage expression changes can write several parameters in one turn. Query
      // only the completed pose, rather than extracting every intermediate one.
      if (notificationQueued) return;
      notificationQueued = true;
      queueMicrotask(() => { notificationQueued = false; notify(); });
    },
    tick() {
      if (!ownsElement() || notificationQueued || now() - lastNotifiedAt < ttl) return;
      clearSample(); notify();
    },
    destroy() {
      disposed = true; cache = null;
      if (element && silhouettes.get(element) === provider) silhouettes.delete(element);
    },
    overlapsCircle(clientX, clientY, radius) {
      if (disposed || !model.visible || !model.renderable || model.destroyed || !model.worldVisible || ![clientX, clientY, radius].every(Number.isFinite) || radius < 0) return false;
      const rect = app.view.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0 || !app.screen?.width || !app.screen?.height) return false;
      const bounds = model.getLocalBounds();
      if (!(bounds.width > 0 && bounds.height > 0)) return false;
      // toGlobal updates the real parent/anchor/pivot transform without changing it.
      model.toGlobal(new Point(bounds.x, bounds.y));
      if (!(model.worldAlpha > 0)) return false;
      const world = model.worldTransform.clone();
      const sx = rect.width / app.screen.width, sy = rect.height / app.screen.height;
      const matrix = { a: world.a * sx, b: world.b * sy, c: world.c * sx, d: world.d * sy, tx: rect.left + world.tx * sx, ty: rect.top + world.ty * sy };
      const corners = cornersOf(bounds, matrix);
      const left = Math.min(...corners.map(p => p.x)), right = Math.max(...corners.map(p => p.x));
      const top = Math.min(...corners.map(p => p.y)), bottom = Math.max(...corners.map(p => p.y));
      if (clientX + radius < left || clientX - radius > right || clientY + radius < top || clientY - radius > bottom) return false;
      const resolution = Math.min(1, edge / Math.max(bounds.width, bounds.height), Math.hypot(matrix.a, matrix.b), Math.hypot(matrix.c, matrix.d));
      if (!(resolution > 0)) return false;
      const key = `${bounds.x},${bounds.y},${bounds.width},${bounds.height},${resolution}`;
      const time = now();
      if ((cache && cache.key !== key) || time - sampledAt >= ttl) {
        cache = null; sampledAt = time;
        try { cache = sample(app.renderer, model, bounds, resolution); cache.key = key; }
        catch { /* An unavailable alpha shape leaves the circle visible; never hide by bbox. */ }
      }
      if (!cache) return false;
      const det = matrix.a * matrix.d - matrix.b * matrix.c;
      if (!det) return false;
      const local = (x, y) => ({ x: (matrix.d * (x - matrix.tx) - matrix.c * (y - matrix.ty)) / det, y: (-matrix.b * (x - matrix.tx) + matrix.a * (y - matrix.ty)) / det });
      const circleBox = [[-1,-1], [1,-1], [1,1], [-1,1]].map(([x,y]) => local(clientX + x * radius, clientY + y * radius));
      const dx = bounds.width / cache.width, dy = bounds.height / cache.height;
      const minX = Math.max(0, Math.floor((Math.min(...circleBox.map(p => p.x)) - bounds.x) / dx));
      const maxX = Math.min(cache.width - 1, Math.floor((Math.max(...circleBox.map(p => p.x)) - bounds.x) / dx));
      const minY = Math.max(0, Math.floor((Math.min(...circleBox.map(p => p.y)) - bounds.y) / dy));
      const maxY = Math.min(cache.height - 1, Math.floor((Math.max(...circleBox.map(p => p.y)) - bounds.y) / dy));
      // Include the preceding cell when the circle touches exactly a pixel edge.
      for (let y = Math.max(0, minY - 1); y <= maxY; y++) for (let x = Math.max(0, minX - 1); x <= maxX; x++) {
        if (cache.alpha[y * cache.width + x] < threshold) continue;
        const pixel = new Rectangle(bounds.x + x * dx, bounds.y + y * dy, dx, dy);
        if (circleTouchesPolygon(clientX, clientY, radius, cornersOf(pixel, matrix))) return true;
      }
      return false;
    },
  };
  if (element) silhouettes.set(element, provider);
  return provider;
}

function cornersOf(rect, m) {
  return [[rect.x, rect.y], [rect.x + rect.width, rect.y], [rect.x + rect.width, rect.y + rect.height], [rect.x, rect.y + rect.height]].map(([x,y]) => ({ x: m.a * x + m.c * y + m.tx, y: m.b * x + m.d * y + m.ty }));
}

function circleTouchesPolygon(x, y, radius, points) {
  let positive = false, negative = false;
  for (let i = 0; i < 4; i++) {
    const a = points[i], b = points[(i + 1) % 4];
    const vx = b.x - a.x, vy = b.y - a.y;
    const cross = vx * (y - a.y) - vy * (x - a.x);
    positive ||= cross > 0; negative ||= cross < 0;
    const length = vx * vx + vy * vy;
    const t = length ? Math.max(0, Math.min(1, ((x - a.x) * vx + (y - a.y) * vy) / length)) : 0;
    if ((x - a.x - t * vx) ** 2 + (y - a.y - t * vy) ** 2 <= radius ** 2) return true;
  }
  return !(positive && negative);
}

function sample(renderer, model, bounds, resolution) {
  const system = renderer.renderTexture;
  const target = system?.current;
  const source = system?.sourceFrame?.clone();
  const destination = system?.destinationFrame?.clone();
  const projection = renderer.projection?.transform;
  const renderingToScreen = renderer.renderingToScreen;
  const world = model.worldTransform.clone();
  let texture;
  try {
    // generateTexture uses an attached object's existing world transform in PIXI
    // 6.5. Render local coordinates, then restore before returning to the stage.
    model.worldTransform.identity();
    texture = renderer.generateTexture(model, { region: new Rectangle(bounds.x, bounds.y, bounds.width, bounds.height), resolution });
    const pixels = renderer.extract.pixels(texture);
    const width = Math.round(texture.width * texture.baseTexture.resolution);
    const height = Math.round(texture.height * texture.baseTexture.resolution);
    if (!width || !height || pixels.length !== width * height * 4) throw new Error('invalid mascot alpha sample');
    const alpha = new Uint8Array(width * height);
    for (let i = 0; i < alpha.length; i++) alpha[i] = pixels[i * 4 + 3];
    return { alpha, width, height };
  } finally {
    model.worldTransform.copyFrom(world);
    if (renderer.projection) renderer.projection.transform = projection;
    try { system?.bind(target, source, destination); }
    finally { renderer.renderingToScreen = renderingToScreen; texture?.destroy(true); }
  }
}
