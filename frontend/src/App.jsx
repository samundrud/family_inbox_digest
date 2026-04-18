import { useEffect, useState } from 'react'
import {
  addEvent,
  deleteEvent,
  dismissEvent,
  loadData,
  updateEvent,
} from './api.js'
import EventCard    from './components/EventCard.jsx'
import AddEventForm from './components/AddEventForm.jsx'
import DigestGroup  from './components/DigestGroup.jsx'
import StatsBar     from './components/StatsBar.jsx'
import FilterPills  from './components/FilterPills.jsx'

const TODAY = new Date().toISOString().slice(0, 10)

function daysUntil(dateStr) {
  return Math.ceil((new Date(dateStr) - new Date(TODAY)) / 86400000)
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '22px 16px' }}>
      {[1, 2, 3].map((i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton-line medium" />
          <div className="skeleton-line short" />
          <div className="skeleton-line long" style={{ marginBottom: 0 }} />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [data, setData]               = useState({ events: [], digestGroups: [], lastScanned: null })
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [activeTab, setActiveTab]     = useState('events')
  const [filter, setFilter]           = useState('all')
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingEventId, setEditingEventId] = useState(null)

  async function reload() {
    try {
      const fresh = await loadData()
      setData(fresh)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload().finally(() => setLoading(false))
  }, [])

  // Derived values
  const visibleEvents = (data.events || [])
    .filter((e) => e.dismissed !== true)
    .filter((e) => filter === 'all' || e.category === filter)
    .slice()
    .sort((a, b) => (a.date || '').localeCompare(b.date || ''))

  const upcomingEvents = visibleEvents.filter((e) => e.date && e.date >= TODAY)
  const urgentCount    = upcomingEvents.filter((e) => daysUntil(e.date) <= 3).length
  const thisWeekCount  = upcomingEvents.filter((e) => daysUntil(e.date) <= 7).length

  const visibleDigest = (data.digestGroups || []).filter(
    (g) => filter === 'all' || g.category === filter
  )

  // Handlers
  async function handleDismiss(id)         { try { setData(await dismissEvent(id))          } catch (e) { setError(e.message) } }
  async function handleDelete(id)          { try { setData(await deleteEvent(id))            } catch (e) { setError(e.message) } }
  async function handleAdd(obj)            { try { setData(await addEvent(obj)); setShowAddForm(false) } catch (e) { setError(e.message) } }
  async function handleUpdate(id, fields)  { try { setData(await updateEvent(id, fields)); setEditingEventId(null) } catch (e) { setError(e.message) } }

  const lastScannedLabel = data.lastScanned
    ? new Date(data.lastScanned).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : 'never'

  // ── Loading state ──
  if (loading) {
    return (
      <>
        <AppHeader lastScannedLabel="—" urgentCount={0} onAddClick={() => {}} />
        <LoadingSkeleton />
      </>
    )
  }

  // ── Error state ──
  if (error) {
    return (
      <>
        <AppHeader lastScannedLabel="—" urgentCount={0} onAddClick={() => {}} />
        <div style={{ maxWidth: 820, margin: '22px auto', padding: '0 16px' }}>
          <div style={{ background: '#2d1212', border: '1px solid var(--red)', borderRadius: 12, padding: '18px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
            <span style={{ color: 'var(--red)', fontSize: 14 }}><strong>Error:</strong> {error}</span>
            <button
              onClick={() => { setError(null); setLoading(true); reload().finally(() => setLoading(false)) }}
              style={{ background: 'var(--red)', border: 'none', borderRadius: 8, color: '#000', cursor: 'pointer', fontWeight: 700, padding: '8px 16px', flexShrink: 0 }}
            >
              Retry
            </button>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <AppHeader
        lastScannedLabel={lastScannedLabel}
        urgentCount={urgentCount}
        onAddClick={() => setShowAddForm(true)}
      />

      <div className="fadein" style={{ maxWidth: 820, margin: '0 auto', padding: '22px 16px' }}>

        <StatsBar
          upcomingCount={upcomingEvents.length}
          urgentCount={urgentCount}
          thisWeekCount={thisWeekCount}
        />

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: 'var(--surface)', borderRadius: 10, padding: 4 }}>
          {['events', 'digest'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                flex: 1, border: 'none', borderRadius: 8, cursor: 'pointer',
                fontWeight: 600, fontSize: 14, minHeight: 44, padding: '10px 0',
                background: activeTab === tab ? 'var(--accent)' : 'transparent',
                color:      activeTab === tab ? '#000' : 'var(--sub)',
                transition: 'background 0.15s, color 0.15s',
              }}
            >
              {tab === 'events' ? 'Upcoming Events' : 'Weekly Digest'}
            </button>
          ))}
        </div>

        <FilterPills active={filter} onChange={setFilter} />

        {/* Events tab */}
        {activeTab === 'events' && (
          <div>
            {visibleEvents.length === 0
              ? <EmptyState text="You're all clear! No upcoming events." />
              : visibleEvents.map((e) => (
                  <EventCard
                    key={e.id}
                    event={e}
                    isEditing={editingEventId === e.id}
                    onDismiss={handleDismiss}
                    onDelete={handleDelete}
                    onEdit={handleUpdate}
                    onEditStart={setEditingEventId}
                    onEditCancel={() => setEditingEventId(null)}
                  />
                ))
            }
          </div>
        )}

        {/* Digest tab */}
        {activeTab === 'digest' && (
          <div>
            {visibleDigest.length === 0
              ? <EmptyState text="No digest yet. Run the scanner to generate summaries." />
              : visibleDigest.map((g, i) => <DigestGroup key={i} group={g} />)
            }
          </div>
        )}

      </div>

      {showAddForm && (
        <AddEventForm onAdd={handleAdd} onClose={() => setShowAddForm(false)} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AppHeader({ lastScannedLabel, urgentCount, onAddClick }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      padding: '14px 24px',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      <div>
        <div style={{
          fontWeight: 700, fontSize: 18,
          background: 'linear-gradient(90deg, var(--text), var(--accent))',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}>
          🏫 Family Inbox Intelligence
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
          Last scanned: {lastScannedLabel}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {urgentCount > 0 && (
          <span style={{
            background: 'var(--red)', color: '#000',
            borderRadius: 99, padding: '3px 10px',
            fontSize: 12, fontWeight: 700,
          }}>
            {urgentCount} urgent
          </span>
        )}
        <button
          onClick={onAddClick}
          style={{
            background: 'var(--accent)', color: '#000',
            border: 'none', borderRadius: 8,
            padding: '8px 16px', fontWeight: 700,
            cursor: 'pointer', fontSize: 14, minHeight: 44,
          }}
        >
          + Add Event
        </button>
      </div>
    </header>
  )
}

function EmptyState({ text }) {
  return (
    <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '32px 0', fontSize: 15 }}>
      {text}
    </p>
  )
}
