/** Pure layout for the 3D twin. Positions are schematic: the data pack has departments, rooms and beds
 * but no building geometry, so each department type gets a fixed place on a floor. */

export type TwinBed = { id: string; room: string; occupied: boolean };
export type TwinOrRoom = { id: string; name: string; booked_min_on_day: number; capacity_min: number };
export type TwinDept = {
  id: string;
  type: string;
  name: string;
  name_ar: string;
  nurses: number | null;
  doctors: number | null;
  arrivals: number | null;
  avg_wait_min: number | null;
  day: string;
  beds?: TwinBed[];
  beds_total?: number;
  occupied?: number;
  rooms?: TwinOrRoom[];
};
export type TwinMap = { as_of: string; departments: TwinDept[]; closed_beds: number; note: string; sources: string[] };

export const FLOOR_OF: Record<string, number> = { ER: 0, IMAGING: 0, LAB: 0, OR: 1, CLINIC: 1, ICU: 2, WARD: 3 };
export const FLOORS = [0, 1, 2, 3];
export const FLOOR_W = 26;
export const FLOOR_D = 15;
export const FLOOR_H = 3.4;

// x0,x1 along width, z0,z1 along depth (centered at 0)
const RECT: Record<string, [number, number, number, number]> = {
  ER: [-12.5, 1.5, -6.8, 6.8],
  IMAGING: [2.2, 12.5, -6.8, -0.4],
  LAB: [2.2, 12.5, 0.4, 6.8],
  OR: [-12.5, 3.5, -6.8, 6.8],
  CLINIC: [4.2, 12.5, -6.8, 6.8],
  ICU: [-12.5, 12.5, -6.8, 6.8],
  WARD: [-12.5, 12.5, -6.8, 6.8],
};
// rooms of the service departments (rooms.csv), which the twin endpoint does not enumerate
const STATIC_ROOMS: Record<string, string[]> = {
  CLINIC: ["Cardiology Clinic 1", "Cardiology Clinic 2", "Cardiology Clinic 3", "Cardiology Clinic 4"],
  IMAGING: ["Imaging Room"],
  LAB: ["Laboratory Room"],
};

export type RoomBox = {
  key: string;
  name: string;
  deptId: string;
  type: string;
  cx: number;
  cz: number;
  w: number;
  d: number;
  beds: (TwinBed & { x: number; z: number })[];
  or?: TwinOrRoom;
};
export type DeptBox = { dept: TwinDept; floor: number; cx: number; cz: number; w: number; d: number; rooms: RoomBox[] };

function grid(n: number, w: number, d: number) {
  let best = { c: 1, r: n };
  let score = Infinity;
  for (let c = 1; c <= n; c++) {
    const r = Math.ceil(n / c);
    const s = Math.abs(w / c / (d / r) - 1.2) + (c * r - n) * 0.3;
    if (s < score) {
      score = s;
      best = { c, r };
    }
  }
  return best;
}

export function layoutDept(dept: TwinDept): DeptBox | null {
  const rect = RECT[dept.type];
  if (!rect) return null;
  const [x0, x1, z0, z1] = rect;
  const w = x1 - x0;
  const d = z1 - z0;
  const cx = (x0 + x1) / 2;
  const cz = (z0 + z1) / 2;
  let roomNames: string[] = [];
  const bedsByRoom = new Map<string, TwinBed[]>();
  if (dept.beds?.length) {
    for (const b of dept.beds) {
      if (!bedsByRoom.has(b.room)) bedsByRoom.set(b.room, []);
      bedsByRoom.get(b.room)!.push(b);
    }
    roomNames = [...bedsByRoom.keys()];
  } else if (dept.rooms?.length) roomNames = dept.rooms.map((r) => r.name);
  else roomNames = STATIC_ROOMS[dept.type] ?? [dept.name];

  const pad = 0.35;
  const { c, r } = grid(roomNames.length, w, d);
  const rw = w / c;
  const rd = d / r;
  const rooms: RoomBox[] = roomNames.map((name, i) => {
    const ci = i % c;
    const ri = Math.floor(i / c);
    const rcx = x0 + rw * (ci + 0.5);
    const rcz = z0 + rd * (ri + 0.5);
    const beds = bedsByRoom.get(name) ?? [];
    const bg = grid(Math.max(1, beds.length), rw - 1, rd - 1);
    const bw = (rw - 1.2) / bg.c;
    const bd = (rd - 1.2) / bg.r;
    return {
      key: `${dept.id}:${name}`,
      name,
      deptId: dept.id,
      type: dept.type,
      cx: rcx,
      cz: rcz,
      w: rw - pad,
      d: rd - pad,
      beds: beds.map((b, j) => ({
        ...b,
        x: rcx - (rw - 1.2) / 2 + bw * ((j % bg.c) + 0.5),
        z: rcz - (rd - 1.2) / 2 + bd * (Math.floor(j / bg.c) + 0.5),
      })),
      or: dept.rooms?.find((o) => o.name === name),
    };
  });
  return { dept, floor: FLOOR_OF[dept.type] ?? 0, cx, cz, w, d, rooms };
}

export function layoutTwin(twin: TwinMap | undefined) {
  if (!twin) return [] as DeptBox[];
  return twin.departments.map(layoutDept).filter((x): x is DeptBox => !!x);
}

/** occupancy / utilisation pressure 0..1 used for heat colouring */
export function deptLoad(d: TwinDept): number | null {
  if (d.beds_total) return (d.occupied ?? 0) / d.beds_total;
  if (d.rooms?.length) {
    const cap = d.rooms.reduce((a, r) => a + r.capacity_min, 0);
    return cap ? d.rooms.reduce((a, r) => a + r.booked_min_on_day, 0) / cap : null;
  }
  return null;
}
