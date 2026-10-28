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
    // Vessels at the same spot (several at one anchorage) share one dot that names them all.
    const spots = new Map<string, MapPoint[]>()
    for (const p of points) {
      const key = `${p.position.lat.toFixed(4)},${p.position.lon.toFixed(4)}`
      spots.set(key, [...(spots.get(key) ?? []), p])
    }
    for (const group of spots.values()) {
      const p = group[0]
      const at: [number, number] = [p.position.lat, p.position.lon]
      corners.push(at)
      // An out-of-date or approximate position is drawn hollow, so a fresh fix stands out.
      const firm = group.every((g) => g.position.source !== 'BASE' && !g.position.stale)
      const lines = group.map((g) => `<b>${escape(g.name)}</b><br>${escape(g.position.label)}<br><small>${escape(positionNote(g.position))}</small>`)
      const dot = L.circleMarker(at, { radius: group.length > 1 ? 11 : 8, color: firm ? '#fff' : COLOUR[p.status], weight: 2, fillColor: COLOUR[p.status], fillOpacity: firm ? 1 : 0.25 })
        .bindTooltip(`${group.length > 1 ? `<b>${group.length} vessels here</b><br>` : ''}${lines.join('<hr style="margin:4px 0">')}<br><small>${p.position.lat.toFixed(3)}, ${p.position.lon.toFixed(3)}</small>`)
        .addTo(map)
      if (group.length > 1) {
        L.marker(at, { icon: L.divIcon({ className: 'map-count', html: String(group.length), iconSize: [22, 22] }), interactive: false }).addTo(map)
        dot.bindPopup(group.map((g) => `<a href="/vessels/${encodeURIComponent(g.id)}">${escape(g.name)}</a>`).join('<br>'))
      } else {
        dot.on('click', () => navigate(`/vessels/${encodeURIComponent(p.id)}`))
      }
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
      <span>Hollow dot: approximate or out of date · a number: several vessels at one spot</span>
    </span>
  )
}
