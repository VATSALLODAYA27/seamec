import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

import { positionNote, type Position, type Vessel } from '../api'
import { STATUS } from '../brand'

const COLOUR: Record<Vessel['status'], string> = { ON_HIRE: STATUS.ok, AVAILABLE: STATUS.info, DRY_DOCK: STATUS.warn }

export interface MapPoint {
  id: string
  name: string
  status: Vessel['status']
  position: Position
}

const escape = (text: string) => text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)

/**
 * A small map of vessel positions on OpenStreetMap tiles. Each dot is coloured by status and opens the vessel when
 * clicked. With `track`, a dotted line shows where a single vessel has been.
 */
export default function FleetMap({ points, track, height = 360 }: { points: MapPoint[]; track?: [number, number][]; height?: number }) {
  const box = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!box.current) return
    const map = L.map(box.current, { scrollWheelZoom: false, worldCopyJump: true })
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 12,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)

    const corners: L.LatLngExpression[] = []
    if (track && track.length > 1) {
      L.polyline(track, { color: STATUS.info, weight: 2, dashArray: '4 6', opacity: 0.8 }).addTo(map)
      corners.push(...track)
    }
    for (const p of points) {
      const at: [number, number] = [p.position.lat, p.position.lon]
      corners.push(at)
      const when = positionNote(p.position)
      // An out-of-date or base-port position is drawn hollow, so a fresh fix stands out.
      const firm = p.position.source !== 'BASE' && !p.position.stale
      L.circleMarker(at, { radius: 8, color: firm ? '#fff' : COLOUR[p.status], weight: 2, fillColor: COLOUR[p.status], fillOpacity: firm ? 1 : 0.25 })
        .bindTooltip(`<b>${escape(p.name)}</b><br>${escape(p.position.label)}<br><small>${escape(when)} · ${p.position.lat.toFixed(3)}, ${p.position.lon.toFixed(3)}</small>`)
        .on('click', () => navigate(`/vessels/${encodeURIComponent(p.id)}`))
        .addTo(map)
    }
    if (corners.length === 1) map.setView(corners[0], 8)
    else if (corners.length) map.fitBounds(L.latLngBounds(corners), { padding: [30, 30], maxZoom: 9 })
    else map.setView([18, 72], 4) // Arabian Sea, when nothing has a position yet

    return () => {
      map.remove()
    }
  }, [points, track, navigate])

  return <div ref={box} className="fleet-map" style={{ height }} role="region" aria-label="Map of vessel positions" />
}

export function MapLegend() {
  return (
    <span className="map-legend">
      {(['ON_HIRE', 'AVAILABLE', 'DRY_DOCK'] as const).map((s) => (
        <span key={s}>
          <i style={{ background: COLOUR[s] }} />
          {s === 'ON_HIRE' ? 'On hire' : s === 'AVAILABLE' ? 'Available' : 'Dry dock'}
        </span>
      ))}
      <span>Hollow dot: base port or out of date</span>
    </span>
  )
}
