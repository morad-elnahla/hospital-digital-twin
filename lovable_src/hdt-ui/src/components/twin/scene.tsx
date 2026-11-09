import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { CameraControls, ContactShadows, Environment, Html, Lightformer, RoundedBox } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { FLOOR_D, FLOOR_H, FLOOR_W, FLOORS, deptLoad, type DeptBox, type RoomBox } from "./layout";

/** Scene palette (three.js needs concrete colours; mirrors the CSS tokens). */
export const PAL = {
  slab: "#eef3f5",
  slabEdge: "#c9d6dc",
  wall: "#dfe8ec",
  glass: "#bfe3e6",
  bedFree: "#f4f7f8",
  bedFrame: "#9fb3bd",
  occupied: "#2a8f93",
  occupiedGlow: "#5fc2c3",
  pillow: "#ffffff",
  good: "#52b48c",
  warn: "#e4a944",
  bad: "#d9604f",
  select: "#2a8f93",
  ink: "#20303f",
  tint: { ER: "#fbe9e4", ICU: "#e3eef9", WARD: "#e4f3ee", OR: "#ece8f7", CLINIC: "#fdf3df", IMAGING: "#e8eef2", LAB: "#eef4e3" } as Record<string, string>,
};

const heat = (v: number | null) => (v == null ? null : v >= 0.9 ? PAL.bad : v >= 0.75 ? PAL.warn : PAL.good);

export type Selection = { floor: number | null; dept: string | null; room: string | null; bed: string | null };

type Props = {
  layout: DeptBox[];
  sel: Selection;
  onSelect: (s: Partial<Selection>) => void;
  exploded: boolean;
  lang: "ar" | "en";
  labels: { occupied: string; free: string; beds: string };
  resetKey: number;
};

function useDamped(target: number, k = 6) {
  const v = useRef(target);
  return (dt: number) => {
    v.current += (target - v.current) * (1 - Math.exp(-k * dt));
    return v.current;
  };
}

function Bed({ bed, selected, onClick }: { bed: RoomBox["beds"][number]; selected: boolean; onClick: (e: ThreeEvent<MouseEvent>) => void }) {
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const grp = useRef<THREE.Group>(null);
  const [hover, setHover] = useState(false);
  const target = useMemo(() => new THREE.Color(bed.occupied ? PAL.occupied : PAL.bedFree), [bed.occupied]);
  useFrame((_, dt) => {
    if (mat.current) mat.current.color.lerp(target, 1 - Math.exp(-5 * dt));
    if (grp.current) {
      const s = selected || hover ? 1.12 : 1;
      grp.current.scale.lerp(new THREE.Vector3(s, s, s), 1 - Math.exp(-10 * dt));
    }
  });
  return (
    <group
      ref={grp}
      position={[bed.x, 0, bed.z]}
      onClick={onClick}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHover(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHover(false);
        document.body.style.cursor = "";
      }}
    >
      <mesh position={[0, 0.22, 0]} castShadow>
        <boxGeometry args={[0.95, 0.12, 1.75]} />
        <meshStandardMaterial color={PAL.bedFrame} metalness={0.4} roughness={0.4} />
      </mesh>
      <RoundedBox args={[0.88, 0.16, 1.62]} radius={0.06} position={[0, 0.36, 0]} castShadow>
        <meshStandardMaterial ref={mat} color={bed.occupied ? PAL.occupied : PAL.bedFree} roughness={0.7} />
      </RoundedBox>
      <RoundedBox args={[0.6, 0.1, 0.3]} radius={0.04} position={[0, 0.48, -0.6]}>
        <meshStandardMaterial color={PAL.pillow} roughness={0.9} />
      </RoundedBox>
      <mesh position={[0, 0.5, -0.86]}>
        <boxGeometry args={[0.95, 0.5, 0.05]} />
        <meshStandardMaterial color={PAL.bedFrame} />
      </mesh>
      {bed.occupied && (
        <mesh position={[0, 0.98, -0.86]}>
          <sphereGeometry args={[0.07, 12, 12]} />
          <meshBasicMaterial color={PAL.occupiedGlow} toneMapped={false} />
        </mesh>
      )}
      {selected && (
        <mesh rotation-x={-Math.PI / 2} position={[0, 0.03, 0]}>
          <ringGeometry args={[1.05, 1.2, 40]} />
          <meshBasicMaterial color={PAL.select} transparent opacity={0.9} />
        </mesh>
      )}
    </group>
  );
}

function OrTable({ util }: { util: number }) {
  const ring = useRef<THREE.Mesh>(null);
  useFrame((s) => {
    if (ring.current) ring.current.rotation.z = s.clock.elapsedTime * 0.4;
  });
  const color = heat(util) ?? PAL.good;
  return (
    <group>
      <mesh position={[0, 0.45, 0]} castShadow>
        <boxGeometry args={[0.9, 0.12, 2]} />
        <meshStandardMaterial color="#9ec7d0" metalness={0.5} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.2, 0]}>
        <cylinderGeometry args={[0.12, 0.25, 0.4, 16]} />
        <meshStandardMaterial color={PAL.bedFrame} metalness={0.6} />
      </mesh>
      <mesh position={[0, 2.3, 0]}>
        <cylinderGeometry args={[0.5, 0.35, 0.15, 24]} />
        <meshStandardMaterial color="#f8fbfc" emissive="#ffffff" emissiveIntensity={0.25} />
      </mesh>
      <mesh ref={ring} rotation-x={-Math.PI / 2} position={[0, 0.04, 0]}>
        <ringGeometry args={[1.25, 1.45, 64, 1, 0, Math.PI * 2 * Math.min(1, util)]} />
        <meshBasicMaterial color={color} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function ServiceProps({ type, n }: { type: string; n: number }) {
  if (type === "IMAGING")
    return (
      <group>
        <mesh position={[0, 0.9, 0]} rotation-x={Math.PI / 2} castShadow>
          <torusGeometry args={[0.9, 0.35, 20, 40]} />
          <meshStandardMaterial color="#f5f8f9" roughness={0.3} />
        </mesh>
        <mesh position={[0, 0.45, 1.3]}>
          <boxGeometry args={[0.6, 0.15, 2.4]} />
          <meshStandardMaterial color="#cfdde3" />
        </mesh>
      </group>
    );
  if (type === "LAB")
    return (
      <group>
        {[-1.2, 1.2].map((z) => (
          <mesh key={z} position={[0, 0.5, z]} castShadow>
            <boxGeometry args={[3.6, 1, 0.8]} />
            <meshStandardMaterial color="#e9eff1" />
          </mesh>
        ))}
        {Array.from({ length: Math.min(8, Math.round(n / 3)) }, (_, i) => (
          <mesh key={i} position={[-1.4 + i * 0.4, 1.15, -1.2]}>
            <cylinderGeometry args={[0.07, 0.07, 0.3, 10]} />
            <meshStandardMaterial color={i % 2 ? "#7fc4c6" : "#e8a598"} transparent opacity={0.85} />
          </mesh>
        ))}
      </group>
    );
  // clinic: desk + chairs
  return (
    <group>
      <mesh position={[0, 0.4, -0.4]} castShadow>
        <boxGeometry args={[1.6, 0.8, 0.7]} />
        <meshStandardMaterial color="#e6d6b8" />
      </mesh>
      {[-0.5, 0.5].map((x) => (
        <mesh key={x} position={[x, 0.25, 0.6]}>
          <boxGeometry args={[0.45, 0.5, 0.45]} />
          <meshStandardMaterial color="#9fb3bd" />
        </mesh>
      ))}
    </group>
  );
}

function Room({ room, deptSelected, sel, onSelect, lang, showLabels }: { room: RoomBox; deptSelected: boolean; sel: Selection; onSelect: Props["onSelect"]; lang: string; showLabels: boolean }) {
  const isSel = sel.room === room.key;
  const [hover, setHover] = useState(false);
  const occ = room.beds.filter((b) => b.occupied).length;
  const util = room.or ? room.or.booked_min_on_day / room.or.capacity_min : null;
  const floorMat = useRef<THREE.MeshStandardMaterial>(null);
  const base = useMemo(() => new THREE.Color(PAL.tint[room.type] ?? "#eef2f4"), [room.type]);
  const hi = useMemo(() => base.clone().lerp(new THREE.Color(PAL.select), 0.25), [base]);
  useFrame((_, dt) => {
    floorMat.current?.color.lerp(isSel || hover ? hi : base, 1 - Math.exp(-8 * dt));
  });
  const wallH = 1.1;
  const t = 0.08;
  return (
    <group>
      <mesh
        position={[room.cx, 0.02, room.cz]}
        receiveShadow
        onClick={(e) => {
          e.stopPropagation();
          onSelect({ room: room.key, dept: room.deptId, bed: null });
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHover(true);
        }}
        onPointerOut={() => setHover(false)}
      >
        <boxGeometry args={[room.w, 0.04, room.d]} />
        <meshStandardMaterial ref={floorMat} color={base} roughness={0.85} />
      </mesh>
      {/* partition walls */}
      {[
        [room.cx, room.cz - room.d / 2, room.w, t],
        [room.cx, room.cz + room.d / 2, room.w * 0.55, t],
        [room.cx - room.w / 2, room.cz, t, room.d],
        [room.cx + room.w / 2, room.cz, t, room.d],
      ].map(([x, z, w, d], i) => (
        <mesh key={i} position={[x + (i === 1 ? room.w * 0.22 : 0), wallH / 2, z]} castShadow>
          <boxGeometry args={[w, wallH, d]} />
          <meshStandardMaterial color={PAL.wall} transparent opacity={0.85} roughness={0.6} />
        </mesh>
      ))}
      <group position={[0, 0.04, 0]}>
        {room.beds.map((b) => (
          <Bed
            key={b.id}
            bed={b}
            selected={sel.bed === b.id}
            onClick={(e) => {
              e.stopPropagation();
              onSelect({ bed: b.id, room: room.key, dept: room.deptId });
            }}
          />
        ))}
        {room.or && (
          <group position={[room.cx, 0, room.cz]}>
            <OrTable util={util ?? 0} />
          </group>
        )}
        {!room.beds.length && !room.or && (
          <group position={[room.cx, 0, room.cz]}>
            <ServiceProps type={room.type} n={10} />
          </group>
        )}
      </group>
      {showLabels && (deptSelected || isSel) && (
        <Html position={[room.cx, wallH + 0.5, room.cz]} center distanceFactor={18} zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
          <div className="glass rounded-lg px-2 py-1 text-[11px] font-semibold whitespace-nowrap text-foreground" dir={lang === "ar" ? "rtl" : "ltr"}>
            {room.name}
            {room.beds.length > 0 && <span className="num ms-1.5 text-primary">{occ}/{room.beds.length}</span>}
            {util != null && <span className="num ms-1.5 text-primary">{Math.round(util * 100)}%</span>}
          </div>
        </Html>
      )}
    </group>
  );
}

function Floor({ floor, depts, props, yTarget, opacity }: { floor: number; depts: DeptBox[]; props: Props; yTarget: number; opacity: number }) {
  const g = useRef<THREE.Group>(null);
  const yd = useDamped(yTarget, 5);
  const od = useDamped(opacity, 6);
  const mats = useRef<THREE.Material[]>([]);
  useFrame((_, dt) => {
    if (!g.current) return;
    g.current.position.y = yd(dt);
    const o = od(dt);
    g.current.visible = o > 0.02;
    g.current.traverse((obj) => {
      const m = (obj as THREE.Mesh).material as THREE.Material & { opacity: number; userData: { base?: number } };
      if (!m || Array.isArray(m)) return;
      m.userData.base ??= m.transparent ? m.opacity : 1;
      m.transparent = true;
      m.opacity = m.userData.base * o;
    });
  });
  void mats;
  const { sel, onSelect, lang } = props;
  return (
    <group ref={g}>
      {/* slab */}
      <mesh
        position={[0, -0.12, 0]}
        receiveShadow
        onClick={(e) => {
          e.stopPropagation();
          onSelect({ floor, dept: null, room: null, bed: null });
        }}
      >
        <boxGeometry args={[FLOOR_W + 1.2, 0.24, FLOOR_D + 1.2]} />
        <meshStandardMaterial color={PAL.slab} roughness={0.9} />
      </mesh>
      <mesh position={[0, -0.25, 0]}>
        <boxGeometry args={[FLOOR_W + 1.3, 0.04, FLOOR_D + 1.3]} />
        <meshStandardMaterial color={PAL.slabEdge} />
      </mesh>
      {/* glass facade */}
      {[
        [0, -(FLOOR_D + 1.2) / 2, FLOOR_W + 1.2, 0.05],
        [-(FLOOR_W + 1.2) / 2, 0, 0.05, FLOOR_D + 1.2],
        [(FLOOR_W + 1.2) / 2, 0, 0.05, FLOOR_D + 1.2],
      ].map(([x, z, w, d], i) => (
        <mesh key={i} position={[x, 1.25, z]}>
          <boxGeometry args={[w, 2.5, d]} />
          <meshStandardMaterial color={PAL.glass} transparent opacity={0.22} roughness={0.05} metalness={0.2} />
        </mesh>
      ))}
      {depts.map((d) => {
        const load = deptLoad(d.dept);
        const hc = heat(load);
        const dSel = sel.dept === d.dept.id;
        return (
          <group key={d.dept.id}>
            {hc && (
              <mesh position={[d.cx, 0.005, d.cz]} rotation-x={-Math.PI / 2}>
                <planeGeometry args={[d.w + 0.2, d.d + 0.2]} />
                <meshBasicMaterial color={hc} transparent opacity={0.35} />
              </mesh>
            )}
            {d.rooms.map((r) => (
              <Room key={r.key} room={r} deptSelected={dSel} sel={sel} onSelect={onSelect} lang={lang} showLabels={opacity > 0.5} />
            ))}
            {opacity > 0.5 && <Html position={[d.cx, 2.6, d.cz]} center distanceFactor={22} zIndexRange={[20, 0]}>
              <button
                onClick={() => onSelect({ dept: d.dept.id, floor, room: null, bed: null })}
                dir={lang === "ar" ? "rtl" : "ltr"}
                className={
                  "glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold whitespace-nowrap transition-transform hover:scale-105 " +
                  (dSel ? "ring-2 ring-primary" : "")
                }
              >
                <span className="size-2 rounded-full" style={{ background: hc ?? PAL.bedFrame }} />
                {lang === "ar" ? d.dept.name_ar : d.dept.name}
                {d.dept.beds_total ? (
                  <span className="num text-primary">
                    {d.dept.occupied}/{d.dept.beds_total}
                  </span>
                ) : load != null ? (
                  <span className="num text-primary">{Math.round(load * 100)}%</span>
                ) : d.dept.arrivals != null ? (
                  <span className="num text-muted-foreground">{d.dept.arrivals}↗</span>
                ) : null}
              </button>
            </Html>}
          </group>
        );
      })}
    </group>
  );
}

function Rig({ layout, sel, exploded, resetKey }: { layout: DeptBox[]; sel: Selection; exploded: boolean; resetKey: number }) {
  const ref = useRef<CameraControls>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const gap = exploded ? FLOOR_H * 2.2 : FLOOR_H;
    if (sel.room || sel.dept) {
      const d = layout.find((x) => x.dept.id === sel.dept);
      if (!d) return;
      const y = (sel.floor ?? d.floor) === d.floor && sel.floor != null ? 0 : d.floor * gap;
      const r = sel.room ? d.rooms.find((x) => x.key === sel.room) : null;
      const cx = r ? r.cx : d.cx;
      const cz = r ? r.cz : d.cz;
      const span = r ? Math.max(r.w, r.d) : Math.max(d.w, d.d);
      c.setLookAt(cx + span * 0.45, y + span * 1.05 + 2, cz + span * 1.0 + 2, cx, y, cz, true);
    } else if (sel.floor != null) {
      c.setLookAt(0, 24, 22, 0, 0, 0, true);
    } else {
      c.setLookAt(30, 26 + (exploded ? 8 : 0), 34, 0, (exploded ? FLOOR_H * 2.2 : FLOOR_H) * 1.5, 0, true);
    }
  }, [sel.floor, sel.dept, sel.room, exploded, layout, resetKey]);
  return <CameraControls ref={ref} makeDefault minDistance={6} maxDistance={90} maxPolarAngle={Math.PI / 2.1} smoothTime={0.55} />;
}

function Ready({ onReady }: { onReady: () => void }) {
  const n = useRef(0);
  useFrame(() => {
    if (++n.current === 3) onReady();
  });
  return null;
}

export default function TwinScene(props: Props) {
  const { layout, sel, exploded, resetKey } = props;
  const [ready, setReady] = useState(false);
  const gap = exploded ? FLOOR_H * 2.2 : FLOOR_H;
  return (
    <div className="absolute inset-0" data-scene-ready={ready ? "" : undefined}>
      <Canvas shadows dpr={[1, 2]} camera={{ position: [30, 28, 34], fov: 38 }} gl={{ antialias: true }} onPointerMissed={() => props.onSelect({ room: null, bed: null })}>
        <color attach="background" args={["#f2f6f8"]} />
        <fog attach="fog" args={["#f2f6f8", 70, 140]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[18, 30, 14]} intensity={1.5} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-25} shadow-camera-right={25} shadow-camera-top={25} shadow-camera-bottom={-25} />
        <Environment resolution={256}>
          <Lightformer intensity={2} position={[0, 10, 0]} scale={[20, 20, 1]} rotation-x={Math.PI / 2} />
          <Lightformer intensity={1} color="#cfeff0" position={[-10, 3, -5]} rotation-y={Math.PI / 2} scale={[30, 4, 1]} />
          <Lightformer intensity={0.8} color="#fff4e6" position={[10, 3, 5]} rotation-y={-Math.PI / 2} scale={[30, 4, 1]} />
        </Environment>
        {FLOORS.map((f) => {
          const focus = sel.floor;
          const above = focus != null && f > focus;
          const yT = focus != null ? (f === focus ? 0 : f < focus ? -f * 0 - (focus - f) * 0.6 - 0.2 : (f - focus) * gap + 14) : f * gap;
          const op = focus == null ? 1 : f === focus ? 1 : above ? 0 : 0.18;
          return <Floor key={f} floor={f} depts={layout.filter((d) => d.floor === f)} props={props} yTarget={focus != null && f < focus ? -(focus - f) * 0.5 - 0.3 : yT} opacity={op} />;
        })}
        <ContactShadows position={[0, -0.6, 0]} opacity={0.35} scale={70} blur={2.5} far={20} />
        <mesh rotation-x={-Math.PI / 2} position={[0, -0.62, 0]} receiveShadow>
          <circleGeometry args={[60, 64]} />
          <meshStandardMaterial color="#e7eef1" />
        </mesh>
        <Rig layout={layout} sel={sel} exploded={exploded} resetKey={resetKey} />
        <Ready onReady={() => setReady(true)} />
      </Canvas>
    </div>
  );
}
