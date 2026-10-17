import * as PIXI from 'pixi.js';

// Texture.fromURL and Sprite.from share PIXI's cache. Reserve URLs before loading
// and retain actual textures after loading so overlapping mounts cannot free one
// another's atlas. The final owner removes the texture and its GPU base together.
const urlRefs = new Map();
const textureRefs = new Map();
const releasedTextures = new WeakSet();
const deferredTextures = new Set();
const normalize = (url) => new URL(url, window.location.href).href;
const destroyTexture = (texture) => {
  if (!releasedTextures.has(texture)) { releasedTextures.add(texture); texture.destroy?.(true); }
};
const reservedTexture = (texture) => texture.textureCacheIds?.some((id) => urlRefs.has(normalize(id)));

export function createMascotResources() {
  const urls = new Map(), textures = new Set();
  const destroyedInternals = new WeakSet();
  let released = false;
  const owner = {
    addUrl(url) {
      if (released) return;
      const key = normalize(url);
      if (urls.has(key)) return;
      urls.set(key, url); urlRefs.set(key, (urlRefs.get(key) || 0) + 1);
    },
    addTexture(texture) {
      if (released || !texture || textures.has(texture)) return;
      textures.add(texture); textureRefs.set(texture, (textureRefs.get(texture) || 0) + 1);
    },
    release(instance, live) {
      if (released) {
        // The factory can finish a phase after its owner has retired. Its
        // assignment/events must never revive a disposed native core or atlas.
        instance.autoUpdate = false;
        if (live && instance.internalModel && !destroyedInternals.has(instance.internalModel)) {
          destroyedInternals.add(instance.internalModel); instance.internalModel.destroy?.();
        }
        for (const texture of instance.textures || []) {
          if (!textureRefs.has(texture) && !reservedTexture(texture)) destroyTexture(texture);
        }
        return;
      }
      released = true;
      const retained = new Set(textures);
      for (const [key, raw] of urls) {
        const count = (urlRefs.get(key) || 1) - 1;
        if (count) urlRefs.set(key, count); else urlRefs.delete(key);
        const texture = PIXI.utils.TextureCache[raw] || PIXI.utils.TextureCache[key];
        if (texture) textures.add(texture);
      }
      const free = [];
      for (const texture of textures) {
        const count = Math.max(0, (textureRefs.get(texture) || 0) - (retained.has(texture) ? 1 : 0));
        if (count) textureRefs.set(texture, count); else textureRefs.delete(texture);
        if (!count) deferredTextures.add(texture);
      }
      // Encoded/unencoded URLs can normalize to one reservation while PIXI has
      // distinct cache entries. The final reservation releases both entries.
      for (const texture of deferredTextures) {
        if (!textureRefs.has(texture) && !reservedTexture(texture)) {
          deferredTextures.delete(texture); free.push(texture);
        }
      }
      if (live) {
        // Partial loader failure can happen before internalModel is assigned.
        // Its public destroy requires internalModel, so use the PIXI base only
        // in that case, after signalling the loader to abort its own XHR tasks.
        instance.autoUpdate = false;
        if (instance.internalModel) {
          destroyedInternals.add(instance.internalModel);
          instance.textures = free;
          free.forEach((texture) => releasedTextures.add(texture));
          instance.destroy({ children: true, texture: true, baseTexture: true });
        } else {
          instance.emit('destroy');
          free.forEach(destroyTexture);
          PIXI.Container.prototype.destroy.call(instance, { children: true });
        }
        instance.once('modelLoaded', () => owner.release(instance, true));
        instance.once('textureLoaded', () => owner.release(instance, true));
      } else {
        instance.destroy({ children: true, texture: false, baseTexture: false });
        free.forEach(destroyTexture);
      }
    },
  };
  return owner;
}
