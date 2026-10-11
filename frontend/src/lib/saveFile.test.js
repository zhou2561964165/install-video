import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveFile } from './saveFile.js';

afterEach(() => vi.restoreAllMocks());

describe('saveFile browser boundary', () => {
  it('clicks a temporary download anchor with the response filename and removes it', () => {
    let clicked;
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      clicked = { href: this.href, filename: this.download, attached: this.isConnected };
    });
    saveFile('blob:video', '测试.mp4');
    expect(clicked).toEqual({ href: 'blob:video', filename: '测试.mp4', attached: true });
    expect(document.querySelector('a[download]')).toBeNull();
  });

  it('surfaces save failures to allow UI retry and always removes the anchor', () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('save blocked'); });
    expect(() => saveFile('blob:video', 'video.mp4')).toThrow('save blocked');
    expect(document.querySelector('a[download]')).toBeNull();
  });
});
