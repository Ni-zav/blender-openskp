"""SketchUp paint colorization in byte-image HLS space (no SDK at runtime).

Behavior reference: SketchUp/sketchup-colorize-algorithm, published by SketchUp.
https://github.com/SketchUp/sketchup-colorize-algorithm
RGB channel multiplication is not SketchUp's Shift/Tint operation.
"""
import numpy as np


def _hls(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    top, bottom = rgb.max(axis=-1), rgb.min(axis=-1)
    span = top - bottom
    light = (top + bottom) * .5
    saturation = np.divide(span, np.where(light <= .5, top + bottom, 2 - top - bottom),
                           out=np.zeros_like(light), where=span > .001)
    red, green, blue = np.moveaxis(rgb, -1, 0)
    hue = np.zeros_like(light)
    for channel, expression in [(2, 4 + np.divide(red-green,span,out=np.zeros_like(span),where=span>.001)),
                                (1, 2 + np.divide(blue-red,span,out=np.zeros_like(span),where=span>.001)),
                                (0, np.divide(green-blue,span,out=np.zeros_like(span),where=span>.001))]:
        hue = np.where(np.abs(rgb[...,channel]-top)<.001, expression, hue)
    hue = np.where(span > .001, (hue * 60) % 360, -1.)
    return np.stack([hue, light, saturation], axis=-1)


def _rgb(hls):
    hue, light, saturation = np.moveaxis(hls, -1, 0)
    high = np.where(light < .5, light * (1+saturation), light+saturation-light*saturation)
    low = 2*light-high
    channels = []
    for offset in (120, 0, -120):
        angle = (hue+offset) % 360
        value = np.select([angle<60,angle<180,angle<240],
                          [low+(high-low)*angle/60,high,low+(high-low)*(240-angle)/60], default=low)
        channels.append(np.where(saturation < .001, light, value))
    return np.stack(channels, axis=-1)


def colorize_pixels(pixels, target_rgb, colorize_type=0):
    """Return RGBA pixels with Shift (0) or Tint (1), preserving source alpha.

    Blender byte Image.pixels exposes normalized encoded RGB. SketchUp uses
    image-average byte RGB as the colorization reference, not a multiplier.
    """
    rgba = np.asarray(pixels, dtype=np.float32).reshape(-1,4)
    rgb = rgba[:,:3].astype(np.float64)
    # The source average is quantized to the same byte color used by SketchUp.
    average = np.floor(np.mean(rgb,axis=0)*255)/255
    base = _hls(average)
    target = _hls(np.asarray(target_rgb,dtype=np.float32).astype(np.float64))
    hls = _hls(rgb)
    delta_l = target[1]-base[1]
    if target[2] < .001:
        delta_s, delta_h = -1., 0.
    elif base[2] < .001:
        delta_s, delta_h = target[2], target[0]
    else:
        delta_s = target[2]-base[2]
        delta_h = target[0]-base[0] if colorize_type == 0 else target[0]
    hls[:,0] = (hls[:,0]+delta_h) % 360 if colorize_type == 0 else delta_h % 360
    hls[:,1] = np.clip(hls[:,1]+delta_l,.01,1)
    hls[:,2] = np.clip(hls[:,2]+delta_s,0,1)
    out = rgba.copy()
    out[:,:3] = np.floor(np.clip(_rgb(hls),0,1)*255)/255
    return out.reshape(-1)


def srgb_to_linear(rgb):
    return tuple(value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4 for value in rgb)
