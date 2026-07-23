import React, { useEffect, useRef, useState, useCallback } from 'react'

// speed (m/s) -> colour ramp: stopped=red, mid=amber, free-flow=green
function speedColor(s) {
  const t = Math.max(0, Math.min(1, s / 14))
  if (t < 0.5) {
    const k = t / 0.5
    return `rgb(${222 + (232 - 222) * k},${74 + (163 - 74) * k},${63 + (60 - 63) * k})`
  }
  const k = (t - 0.5) / 0.5
  return `rgb(${232 + (74 - 232) * k},${163 + (198 - 163) * k},${60 + (140 - 60) * k})`
}

function meanSpeed(frame) {
  if (!frame || frame.length === 0) return 0
  let sum = 0
  for (let i = 2; i < frame.length; i += 3) sum += frame[i]
  return frame.length ? sum / (frame.length / 3) : 0
}

// headline findings (full-V2X arm, AM-peak comparison — measured)
const FINDINGS = [
  { v: '−6.5%', k: 'trip travel time', d: '348s → 325s' },
  { v: '−11.1%', k: 'delay per trip', d: 'time lost to congestion' },
  { v: '−17.2%', k: 'time spent waiting', d: 'at signals & queues' },
  { v: '+26%', k: 'mean network speed', d: '11.9 → 15.1 mph' },
]

export default function SimViewer() {
  const canvasRef = useRef(null)
  const rafRef = useRef(0)
  const frameRef = useRef(0)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [scenario, setScenario] = useState('v2x')
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(2)
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}sim.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(setData)
      .catch((e) => setErr(String(e)))
  }, [])

  const frames = data?.scenarios?.[scenario]?.frames ?? []
  const nFrames = frames.length

  const draw = useCallback((idx) => {
    const cv = canvasRef.current
    if (!cv || !data) return
    const ctx = cv.getContext('2d')
    const [w, h] = data.size
    const dpr = window.devicePixelRatio || 1
    const cw = cv.clientWidth, ch = cv.clientHeight
    if (cv.width !== Math.round(cw * dpr)) { cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr) }
    const scale = Math.min(cw / w, ch / h)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cw, ch)
    const ox = (cw - w * scale) / 2, oy = (ch - h * scale) / 2
    const X = (x) => ox + x * scale
    const Y = (y) => oy + (h - y) * scale

    // roads — faint warm lines on the dark instrument plate
    ctx.strokeStyle = 'rgba(198,186,168,0.16)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (const e of data.network) {
      ctx.moveTo(X(e[0]), Y(e[1]))
      for (let i = 2; i < e.length; i += 2) ctx.lineTo(X(e[i]), Y(e[i + 1]))
    }
    ctx.stroke()

    // vehicles
    const fr = frames[idx] || []
    const r = Math.max(1.5, scale * 3)
    for (let i = 0; i < fr.length; i += 3) {
      ctx.fillStyle = speedColor(fr[i + 2])
      ctx.beginPath()
      ctx.arc(X(fr[i]), Y(fr[i + 1]), r, 0, 6.283)
      ctx.fill()
    }
  }, [data, frames])

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

  const onScrub = (e) => {
    const v = Number(e.target.value)
    frameRef.current = v; setFrame(v); draw(v)
  }

  if (err) return <div className="boot">Couldn’t load <code>sim.json</code> — {err}.<br />Run <code>python scripts/11_export_replay.py</code> first.</div>
  if (!data) return <div className="boot">Loading simulation…</div>

  const fr = frames[frame] || []
  const onScreen = Math.round(fr.length / 3)
  const ms = meanSpeed(fr)
  const other = scenario === 'v2x' ? 'baseline' : 'v2x'
  const otherCount = Math.round((data.scenarios[other]?.frames?.[frame]?.length || 0) / 3)
  const delta = onScreen - otherCount
  const t0 = data.window[0]
  const clock = new Date((t0 + frame) * 1000).toISOString().substr(11, 8)

  return (
    <div className="page">
      <header className="masthead">
        <div className="brand">
          <span className="mark" aria-hidden="true"><i /><i /><i /></span>
          Mobility&nbsp;Systems&nbsp;Lab
        </div>
        <div className="issue">Simulation Study — Washington, DC</div>
      </header>

      <section className="hero">
        <p className="kicker">Vehicle-to-Everything · Signal Coordination</p>
        <h1>Watching a city’s morning rush learn to clear itself.</h1>
        <p className="deck">A microscopic traffic simulation of downtown Washington, DC,
        with demand calibrated to real DDOT counts. Replay the 7&nbsp;a.m. peak under today’s
        fixed-time signals, then under vehicle-to-everything coordination — and watch the
        queues drain.</p>
      </section>

      <figure className="figure">
        <div className="figbar">
          <div className="tabs" role="tablist" aria-label="scenario">
            {['baseline', 'v2x'].map((s) => (
              <button key={s} role="tab" aria-selected={scenario === s}
                className={scenario === s ? 'on' : ''} onClick={() => setScenario(s)}>
                {s === 'v2x' ? 'V2X coordination' : 'Fixed-signal baseline'}
              </button>
            ))}
          </div>
          <div className="ramp" aria-hidden="true">
            <span>stopped</span><i className="ramp-track" /><span>free-flow</span>
          </div>
        </div>

        <div className="stage">
          <canvas ref={canvasRef} />
        </div>

        <div className="telemetry">
          <div className="controls">
            <button className="play" onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'pause' : 'play'}>{playing ? '❚❚' : '►'}</button>
            <input className="scrub" type="range" min={0} max={Math.max(0, nFrames - 1)}
              value={frame} onChange={onScrub} aria-label="timeline" />
          </div>
          <div className="readout">
            <span><b>{onScreen}</b> vehicles</span>
            <span><b>{ms.toFixed(1)}</b> m/s avg</span>
            <span><b>{clock}</b></span>
            <span className={delta <= 0 ? 'd good' : 'd bad'}>
              <b>{delta === 0 ? '±0' : (delta < 0 ? '−' : '+') + Math.abs(delta)}</b> vs {other === 'v2x' ? 'V2X' : 'baseline'}
            </span>
            <label className="spd">
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="speed">
                <option value={1}>1×</option><option value={2}>2×</option>
                <option value={4}>4×</option><option value={8}>8×</option>
              </select>
            </label>
          </div>
        </div>

        <figcaption>
          <b>Fig. 1</b> — Each mark is a vehicle, coloured by instantaneous speed.
          Reds pool at saturated intersections; greens run the arterials. Toggle the
          scenario to compare the same minute of the peak. {data.network.length.toLocaleString()} road
          segments, {data.window[0]}s–{data.window[1]}s, sampled at 1&nbsp;Hz from SUMO floating-car data.
        </figcaption>
      </figure>

      <section className="findings">
        <p className="kicker">What changes, measured</p>
        <div className="stats">
          {FINDINGS.map((f) => (
            <div className="stat" key={f.k}>
              <div className="num">{f.v}</div>
              <div className="lab">{f.k}</div>
              <div className="det">{f.d}</div>
            </div>
          ))}
        </div>
        <p className="caveat">Full-V2X arm versus the fixed-signal control over the AM-peak
        window, identical demand. Gains come from adaptive signal coordination (V2I) and
        cooperative rerouting (V2V). One honest trade-off: the adaptive controller still
        teleports ~⅓ more stranded vehicles than fixed timing — the next thing to tighten.</p>
      </section>

      <footer className="colophon">
        <span>SUMO 1.27.1 · TraCI max-pressure control · scikit-learn / TensorFlow demand model</span>
        <span>Demand calibrated to DDOT AADT · GEH&lt;5 = 83%</span>
      </footer>
    </div>
  )
}
