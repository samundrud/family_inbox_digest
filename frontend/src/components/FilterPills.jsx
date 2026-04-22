const FILTERS = ['all', 'school', 'daycare', 'scouts', 'soccer', 'GFT', 'other']

export default function FilterPills({ active, onChange }) {
  return (
    <div className="filter-pills-scroll" style={{
      display: 'flex',
      gap: 8,
      overflowX: 'auto',
      scrollbarWidth: 'none',
      marginBottom: 20,
      paddingBottom: 2,
    }}>
      {FILTERS.map((f) => {
        const isActive = active === f
        return (
          <button
            key={f}
            onClick={() => onChange(f)}
            style={{
              whiteSpace: 'nowrap',
              padding: '6px 16px',
              border: isActive ? 'none' : '1px solid var(--border)',
              borderRadius: 99,
              cursor: 'pointer',
              background: isActive ? 'var(--accent)' : 'var(--card)',
              color: isActive ? '#000' : 'var(--muted)',
              fontWeight: isActive ? 700 : 400,
              fontSize: 13,
              minHeight: 44,
              fontFamily: 'inherit',
            }}
          >
            {f}
          </button>
        )
      })}
    </div>
  )
}