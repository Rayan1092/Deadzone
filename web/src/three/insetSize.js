// No imports, so Node can test it.
// One view's Command post inset size, as fractions of the pane so it scales with the window.
// The presenter drags its top-left corner (it sits bottom right); each browser remembers it.
export const INSET_KEY = 'dz-inset-size'
export const INSET_DEFAULT = { w: 0.34, h: 0.38 } // about a fifth of the screen at 16:9
export const INSET_MIN_PX = { w: 260, h: 180 }
export const INSET_MAX = { w: 0.9, h: 0.85 }

// Clamp a size (fractions) to the pane (px): never smaller than the header needs, never over the pane.
export function clampInset(size, paneW, paneH) {
  const w = Number.isFinite(size?.w) ? size.w : INSET_DEFAULT.w
  const h = Number.isFinite(size?.h) ? size.h : INSET_DEFAULT.h
  const minW = paneW > 0 ? Math.min(INSET_MIN_PX.w / paneW, INSET_MAX.w) : 0
  const minH = paneH > 0 ? Math.min(INSET_MIN_PX.h / paneH, INSET_MAX.h) : 0
  return { w: Math.min(INSET_MAX.w, Math.max(minW, w)), h: Math.min(INSET_MAX.h, Math.max(minH, h)) }
}

export function loadInset(storage) {
  try {
    const v = JSON.parse(storage?.getItem(INSET_KEY) ?? 'null')
    if (v && Number.isFinite(v.w) && Number.isFinite(v.h) && v.w > 0 && v.h > 0) return { w: v.w, h: v.h }
  } catch { /* private window or bad value: default */ }
  return { ...INSET_DEFAULT }
}

export function saveInset(storage, size) {
  try { storage?.setItem(INSET_KEY, JSON.stringify({ w: +size.w.toFixed(4), h: +size.h.toFixed(4) })) } catch { /* session only */ }
}
