export function SkeletonLine({ width = "100%", height = 14 }: { width?: string | number; height?: number }) {
  return (
    <div className="skeleton" style={{ width, height, borderRadius: 6 }} />
  );
}

export function SkeletonCard() {
  return (
    <div className="card skeleton-card">
      <SkeletonLine width="60%" height={18} />
      <SkeletonLine width="80%" />
      <div className="row" style={{ marginTop: 12 }}>
        <SkeletonLine width={70} height={22} />
        <SkeletonLine width={70} height={22} />
      </div>
    </div>
  );
}

export function SkeletonGrid({ count = 3 }: { count?: number }) {
  return (
    <div className="grid-cards">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export function SkeletonProjectBoard() {
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <SkeletonLine width={200} height={28} />
        <div className="row">
          <SkeletonLine width={80} height={30} />
          <SkeletonLine width={80} height={30} />
        </div>
      </div>
      <SkeletonLine width="70%" />
      <div className="tab-bar" style={{ marginTop: 16 }}>
        <SkeletonLine width={100} height={32} />
        <SkeletonLine width={80} height={32} />
        <SkeletonLine width={100} height={32} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="card skeleton-card" style={{ padding: 18 }}>
            <SkeletonLine width="40%" height={16} />
            <SkeletonLine width="90%" />
            <div className="row" style={{ marginTop: 10 }}>
              <SkeletonLine width={60} height={20} />
              <SkeletonLine width={50} height={20} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
