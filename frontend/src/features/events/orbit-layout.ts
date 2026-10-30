const FIRST_RING = 180;
const RING_GAP = 78;
// Khoảng cách tối thiểu giữa hai hành tinh trên cùng một vòng
const SPACING = 72;

export interface OrbitPoint {
  ring: number;
  x: number;
  y: number;
}

/**
 * Xếp n đội lên các vòng quỹ đạo, không giới hạn n: vòng trong đầy thì mở vòng ngoài,
 * sức chứa mỗi vòng tỉ lệ với chu vi.
 */
export function orbitLayout(n: number): { rings: number[]; points: OrbitPoint[] } {
  const rings: number[] = [];
  const points: OrbitPoint[] = [];
  for (let k = 0, placed = 0; placed < n; k++) {
    const r = FIRST_RING + k * RING_GAP;
    const take = Math.min(n - placed, Math.floor((2 * Math.PI * r) / SPACING));
    rings.push(r);
    for (let i = 0; i < take; i++) {
      // Lệch pha mỗi vòng để các hành tinh không xếp thẳng hàng
      const a = (i / take) * 2 * Math.PI + k * 0.6;
      points.push({ ring: k, x: Math.round(r * Math.cos(a) * 10) / 10, y: Math.round(r * Math.sin(a) * 10) / 10 });
    }
    placed += take;
  }
  return { rings, points };
}
