import { useEffect, useState } from 'react'
import { AI_CAPTION } from './format'

// Rayan's runtime crop manifest (/crops/manifest.json): for each thermal crop a robot can
// judge, the model's score, its Grad-CAM, what the real image shows and a caption. Fetched
// once when the app loads, so the first camera view or detection card already has it.
let manifest = null
const ready = fetch('/crops/manifest.json').then((r) => (r.ok ? r.json() : null)).then((j) => { manifest = j; return j }).catch(() => null)

export function useCropManifest() {
  const [m, setM] = useState(manifest)
  useEffect(() => { if (!manifest) ready.then(setM) }, [])
  return m
}

export const cropEntry = (m, file) => (file && m?.crops?.find((c) => c.file === file)) || null

// Every AI image says what it is: the manifest's own caption, else ours.
export const cropCaption = (m, entry) => entry?.caption ?? m?.caption ?? AI_CAPTION

// one full stop at the end, whichever caption it is, so more text can follow it
export const sentence = (text) => text.replace(/\.?\s*$/, '.')
