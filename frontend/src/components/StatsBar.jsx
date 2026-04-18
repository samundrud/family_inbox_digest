export default function StatsBar({ upcomingCount, urgentCount, thisWeekCount }) {
  return (
    <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
      <StatCard value={upcomingCount} label="Upcoming"   color="var(--blue)" />
      <StatCard value={urgentCount}   label="Urgent ≤3d" color="var(--red)"  />
      <StatCard value={thisWeekCount} label="This Week"  color="var(--accent)" />
    </div>
  )
}

function StatCard({ value, label, color }) {
  return (
    <div style={{
      flex: 1,
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '12px 16px',
    }}>
      <div style={{
        fontSize: 26,
        fontWeight: 700,
        color,
        fontFamily: "'DM Mono', monospace",
        lineHeight: 1,
      }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
    </div>
  )
}