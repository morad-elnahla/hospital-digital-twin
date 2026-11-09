import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApp } from "@/lib/app-state";
import { fmt } from "@/lib/i18n";

const tick = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  contentStyle: {
    background: "var(--popover)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    boxShadow: "var(--shadow-float)",
    fontSize: 12,
  },
  labelStyle: { color: "var(--muted-foreground)", fontWeight: 600 },
};

function useDay() {
  return (d: string) =>
    typeof d === "string" && /^\d{4}-\d{2}-\d{2}/.test(d) ? `${+d.slice(8, 10)}/${+d.slice(5, 7)}` : String(d);
}

export type Series = { key: string; label: string; color: string; dashed?: boolean; area?: boolean };

export function TrendChart({
  data,
  series,
  x = "date",
  height = 240,
  unit,
  marker,
}: {
  data: Record<string, unknown>[];
  series: Series[];
  x?: string;
  height?: number;
  unit?: string;
  marker?: string;
}) {
  const day = useDay();
  const { lang } = useApp();
  return (
    <div dir="ltr" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={x} tickFormatter={day} tick={tick} axisLine={false} tickLine={false} reversed={lang === "ar"} minTickGap={16} />
          <YAxis tick={tick} axisLine={false} tickLine={false} width={44} orientation={lang === "ar" ? "right" : "left"} />
          <Tooltip {...tooltipStyle} labelFormatter={day} formatter={(v: number, n: string) => [`${fmt(v)}${unit ? " " + unit : ""}`, n]} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />}
          {marker && <ReferenceLine x={marker} stroke="var(--simulation)" strokeDasharray="4 4" />}
          {series.map((s) =>
            s.area ? (
              <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} fill={`url(#g-${s.key})`} animationDuration={900} connectNulls />
            ) : (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} dot={false} animationDuration={900} connectNulls />
            ),
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Forecast with a shaded lower-upper band. Rows: {date, observed?, predicted, lower, upper, actual}. */
export function ForecastChart({ data, height = 240, unit, marker }: { data: Record<string, unknown>[]; height?: number; unit?: string; marker?: string }) {
  const day = useDay();
  const { t, lang } = useApp();
  const rows = data.map((r) => ({ ...r, band: r.lower != null && r.upper != null ? [r.lower, r.upper] : null }));
  return (
    <div dir="ltr" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" tickFormatter={day} tick={tick} axisLine={false} tickLine={false} reversed={lang === "ar"} minTickGap={16} />
          <YAxis tick={tick} axisLine={false} tickLine={false} width={44} orientation={lang === "ar" ? "right" : "left"} />
          <Tooltip
            {...tooltipStyle}
            labelFormatter={day}
            formatter={(v: number | number[], n: string) => [Array.isArray(v) ? `${fmt(v[0])} – ${fmt(v[1])}` : `${fmt(v)}${unit ? " " + unit : ""}`, n]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />
          {marker && <ReferenceLine x={marker} stroke="var(--simulation)" strokeDasharray="4 4" label={{ value: t("replay_marker"), fontSize: 10, fill: "var(--muted-foreground)" }} />}
          <Area type="monotone" dataKey="band" name={t("range_1sd")} stroke="none" fill="var(--forecast)" fillOpacity={0.14} animationDuration={900} />
          <Line type="monotone" dataKey="observed" name={t("observed")} stroke="var(--observed)" strokeWidth={2} dot={false} connectNulls animationDuration={900} />
          <Line type="monotone" dataKey="predicted" name={t("forecast")} stroke="var(--forecast)" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls animationDuration={900} />
          <Line type="monotone" dataKey="actual" name={t("observed") + " ✓"} stroke="var(--foreground)" strokeWidth={0} dot={{ r: 3, fill: "var(--foreground)" }} connectNulls={false} animationDuration={900} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Bars({
  data,
  x,
  series,
  height = 220,
  stacked,
  horizontal,
  unit,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
  stacked?: boolean;
  horizontal?: boolean;
  unit?: string;
}) {
  const day = useDay();
  const { lang } = useApp();
  return (
    <div dir="ltr" style={{ height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 8, left: horizontal ? 8 : -12, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={!!horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={tick} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey={x} tick={tick} axisLine={false} tickLine={false} width={110} orientation={lang === "ar" ? "right" : "left"} />
            </>
          ) : (
            <>
              <XAxis dataKey={x} tickFormatter={day} tick={tick} axisLine={false} tickLine={false} reversed={lang === "ar"} minTickGap={8} />
              <YAxis tick={tick} axisLine={false} tickLine={false} width={44} orientation={lang === "ar" ? "right" : "left"} />
            </>
          )}
          <Tooltip {...tooltipStyle} cursor={{ fill: "var(--muted)" }} labelFormatter={day} formatter={(v: number, n: string) => [`${fmt(v)}${unit ? " " + unit : ""}`, n]} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" iconSize={8} />}
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} stackId={stacked ? "a" : undefined} radius={stacked ? 0 : horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} animationDuration={900} maxBarSize={36} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Spark({ values, color = "var(--primary)" }: { values: number[]; color?: string }) {
  const data = values.map((v, i) => ({ i, v }));
  const id = "s" + Math.abs(values.reduce((a, b, i) => a + b * (i + 1), 0)).toFixed(0) + color.length;
  return (
    <div dir="ltr" className="h-10">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.8} fill={`url(#${id})`} isAnimationActive animationDuration={700} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export { LineChart };

/** zip {dates, a:[], b:[]} into rows */
export const zip = (dates: string[], cols: Record<string, (number | null)[] | undefined>) =>
  dates.map((date, i) => {
    const r: Record<string, unknown> = { date };
    for (const [k, v] of Object.entries(cols)) r[k] = v?.[i] ?? null;
    return r;
  });
