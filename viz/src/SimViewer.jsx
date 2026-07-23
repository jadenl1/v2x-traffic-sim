import React, { useEffect, useRef, useState, useCallback } from 'react'

// speed (m/s) -> colour ramp: stopped=red, mid=amber, free-flow=green
function speedColor(s) {
  const t = Math.max(0, Math.min(1, s / 14))
  if (t < 0.5) {
    const k = t / 0.5
    return `rgb(${224 + (232 - 224) * k},${72 + (161 - 72) * k},${61 + (58 - 61) * k})`
  }
  const k = (t - 0.5) / 0.5
  return `rgb(${232 + (62 - 232) * k},${161 + (207 - 161) * k},${58 + (148 - 58) * k})`
}

function meanSpeed(frame) {
  if (!frame || frame.length === 0) return 0
  let sum = 0, n = frame.length / 3
  for (let i = 2; i < frame.length; i += 3) sum += frame[i]
  return n ? sum / n : 0
}

export default function SimViewer() {
  const canvasRef = useRef(null)
  const wrapRef = useRef(null)
  const rafRef = useRef(0)
  const frameRef = useRef(0)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [scenario, setScenario] = useState('v2x')
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(2) // frames/tick multiplier
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}sim.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setData)
      .catch((e) => setErr(String(e)))
  }, [])

  const frames = data?.scenarios?.[scenario]?.frames ?? []
  const nFrames = frames.length

  // draw one frame onto the canvas
  const draw = useCallback((idx) => {
    const cv = canvasRef.current
    if (!cv || !data) return
    const ctx = cv.getContext('2d')
    const [w, h] = data.size
    const dpr = window.devicePixelRatio || 1
    const cw = cv.clientWidth, ch = cv.clientHeight
    if (cv.width !== cw * dpr) { cv.width = cw * dpr; cv.height = ch * dpr }
    const scale = Math.min((cw) / w, (ch) / h)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cw, ch)
    // center
    const ox = (cw - w * scale) / 2, oy = (ch - h * scale) / 2
    const X = (x) => ox + x * scale
    const Y = (y) => oy + (h - y) * scale // flip Y (SUMO y is up)

    // roads
    const dark = matchMedia('(prefers-color-scheme: dark)').matches
    ctx.strokeStyle = dark ? 'rgba(150,165,190,0.22)' : 'rgba(60,72,90,0.28)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (const e of data.network) {
      ctx.moveTo(X(e[0]), Y(e[1]))
      for (let i = 2; i < e.length; i += 2) ctx.lineTo(X(e[i]), Y(e[i + 1]))
    }
    ctx.stroke()

    // vehicles
    const fr = frames[idx] || []
    const r = Math.max(1.6, scale * 3)
    for (let i = 0; i < fr.length; i += 3) {
      ctx.fillStyle = speedColor(fr[i + 2])
      ctx.beginPath()
      ctx.arc(X(fr[i]), Y(fr[i + 1]), r, 0, 6.283)
      ctx.fill()
    }
  }, [data, frames])

  // animation loop
  useEffect(() => {
    if (!data) return
    let last = performance.now()
    const tick = (now) => {
      rafRef.current = requestAnimationFrame(tick)
      if (playing && now - last > 90 / speed) {
        last = now
        frameRef.current = (frameRef.current + 1) % (nFrames || 1)
        setFrame(frameRef.current)
      }
      draw(frameRef.current)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [data, playing, speed, nFrames, draw])

  // manual scrub
  const onScrub = (e) => {
    const v = Number(e.target.value)
    frameRef.current = v; setFrame(v); draw(v)
  }

  if (err) return <div className="msg">Could not load sim.json — {err}. Run <code>python scripts/11_export_replay.py</code>.</div>
  if (!data) return <div className="msg">Loading simulation…</div>

  const fr = frames[frame] || []
  const onScreen = fr.length / 3
  const ms = meanSpeed(fr)
  const other = scenario === 'v2x' ? 'baseline' : 'v2x'
  const otherFr = data.scenarios[other]?.frames?.[frame] || []
  const t0 = data.window[0]
  const clock = new Date((t0 + frame) * 1000).toISOString().substr(11, 8)

  return (
    <div className="app">
      <header>
        <div className="eyebrow">SUMO · Downtown DC · AM peak replay</div>
        <h1>V2X Traffic Simulation — Live Replay</h1>
        <p className="lede">Each dot is a vehicle, coloured by speed
          (<span className="sw red" /> stopped → <span className="sw grn" /> free-flow).
          Toggle between the fixed-signal baseline and V2X to watch the difference.</p>
      </header>

      <div className="toggle">
        {['baseline', 'v2x'].map((s) => (
          <button key={s} className={scenario === s ? 'on' : ''}
            onClick={() => setScenario(s)}>
            {s === 'v2x' ? 'V2X (adaptive)' : 'Baseline (fixed)'}
          </button>
        ))}
      </div>

      <div className="stage" ref={wrapRef}>
        <canvas ref={canvasRef} />
        <div className="hud">
          <div className="stat"><span>{Math.round(onScreen)}</span>vehicles on screen</div>
          <div className="stat"><span>{ms.toFixed(1)}</span>mean speed m/s</div>
          <div className="stat"><span>{clock}</span>sim clock</div>
          <div className="stat compare">
            <span className={onScreen <= otherFr.length / 3 ? 'good' : 'bad'}>
              {otherFr.length ? `${onScreen < otherFr.length / 3 ? '−' : '+'}${Math.abs(Math.round(onScreen - otherFr.length / 3))}` : '—'}
            </span>vs {other}
          </div>
        </div>
      </div>

      <div className="controls">
        <button className="play" onClick={() => setPlaying((p) => !p)}>
          {playing ? '❚❚' : '►'}
        </button>
        <input className="scrub" type="range" min={0} max={Math.max(0, nFrames - 1)}
          value={frame} onChange={onScrub} />
        <span className="fnum">{frame + 1}/{nFrames}</span>
        <label className="spd">speed
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            <option value={1}>1×</option><option value={2}>2×</option>
            <option value={4}>4×</option><option value={8}>8×</option>
          </select>
        </label>
      </div>

      <footer>
        {data.network.length.toLocaleString()} road segments · window {t0}s–{data.window[1]}s ·
        vehicles coloured by instantaneous speed · data from SUMO FCD output
      </footer>
    </div>
  )
}
