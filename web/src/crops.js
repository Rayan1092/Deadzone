import { useEffect, useState } from 'react'
import { AI_CAPTION } from './format.js'

// Rayan's runtime crop manifest (/crops/manifest.json): for each thermal crop a robot can
// judge, the model's score, its Grad-CAM, what the real image shows and a caption. Fetched
// once when the app loads, so the first camera view or detection card already has it.
let manifest = null
const ready = fetch('/crops/manifest.json').then((r) => (r.ok ? r.json() : null)).then((j) => { manifest = j; return j }).catch(() => null)

// Calls back with the manifest once it is loaded, also when it already is. The #121 bug: the
// fetch finished between the cards' first render and their effect (the 3D panes compile their
// shaders in between), the effect saw it loaded and skipped the update, and the cards stayed on
// the fallback caption with no Grad-CAM for the whole run. Returns an unsubscribe.
export function onManifest(cb) {
  let live = true
  ready.then((j) => { if (live) cb(j) })
  return () => { live = false }
}
export const manifestReady = ready

export function useCropManifest() {
  const [m, setM] = useState(manifest)
  useEffect(() => onManifest(setM), [])
  return m
}

export const cropEntry = (m, file) => (file && m?.crops?.find((c) => c.file === file)) || null

// Every AI image says what it is: the manifest's own caption, else ours.
export const cropCaption = (m, entry) => entry?.caption ?? m?.caption ?? AI_CAPTION

// one full stop at the end, whichever caption it is, so more text can follow it
export const sentence = (text) => text.replace(/\.?\s*$/, '.')
