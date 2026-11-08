import { useEffect, useRef } from 'react'

export default function DataPanel({ title, onClose, children, className = '' }) {
  const root = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    root.current?.querySelector('button')?.focus()
    return () => { if (previous?.isConnected) previous.focus?.() }
  }, [])
  const trap = (event) => {
    if (event.key !== 'Tab') return
    const controls = [...root.current.querySelectorAll('button:not(:disabled), a[href], input, select')]
    const first = controls[0], last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
  return (
    <div className="data-panel-backdrop" onClick={onClose}>
      <section ref={root} role="dialog" aria-modal="true" aria-label={title}
               className={`data-panel ${className}`} onClick={(event) => event.stopPropagation()} onKeyDown={trap}>
        <header><h2>{title}</h2><button onClick={onClose} aria-label={`Close ${title}`}>Close · Esc</button></header>
        {children}
      </section>
    </div>
  )
}
