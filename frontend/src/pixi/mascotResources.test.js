import { describe, expect, it, vi } from 'vitest';
import { Sprite, Texture, Ticker, utils } from 'pixi.js';
import { createMascotResources } from './mascotResources.js';

describe('mascot atlas ownership', () => {
  it('uses the installed Live2D destructor to release its own native core and GPU atlas', async () => {
    const previousCore = window.Live2DCubismCore;
    // Only the unused Cubism runtime presence guard is stubbed. The wrapper,
    // native destroy implementation and PIXI texture/base cleanup remain real.
    window.Live2DCubismCore = {};
    const { Live2DModel } = await vi.importActual('pixi-live2d-display/cubism4');
    window.Live2DCubismCore = previousCore;
    Live2DModel.registerTicker(Ticker);
    const model = new Live2DModel({ autoUpdate: false, autoInteract: false });
    const coreDestroy = vi.fn(); model.internalModel = { destroy: coreDestroy };
    const texture = Texture.fromBuffer(new Uint8Array(4), 1, 1);
    const base = texture.baseTexture; model.textures = [texture];
    const owner = createMascotResources(); owner.addTexture(texture);
    owner.release(model, true); owner.release(model, true);
    expect(model.destroyed).toBe(true); expect(coreDestroy).toHaveBeenCalledOnce();
    expect(base.destroyed).toBe(true); expect(model.autoUpdate).toBe(false);
  });
  it('reclaims different PIXI cache spellings of the same reserved URL after the last mount', () => {
    const raw = '/live2d/白/shared.png';
    const encoded = '/live2d/%E7%99%BD/shared.png';
    const firstTexture = Texture.fromBuffer(new Uint8Array(4), 1, 1);
    const secondTexture = Texture.fromBuffer(new Uint8Array(4), 1, 1);
    Texture.addToCache(firstTexture, raw); Texture.addToCache(secondTexture, encoded);
    const first = createMascotResources(), second = createMascotResources();
    first.addUrl(raw); first.addTexture(firstTexture);
    second.addUrl(encoded); second.addTexture(secondTexture);
    const firstDestroy = vi.spyOn(firstTexture, 'destroy');
    const secondDestroy = vi.spyOn(secondTexture, 'destroy');
    first.release(new Sprite(firstTexture), false);
    expect(firstDestroy).not.toHaveBeenCalled();
    second.release(new Sprite(secondTexture), false);
    expect(firstDestroy).toHaveBeenCalledOnce(); expect(secondDestroy).toHaveBeenCalledOnce();
    expect(utils.TextureCache[raw]).toBeUndefined(); expect(utils.TextureCache[encoded]).toBeUndefined();
  });
});
