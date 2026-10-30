"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompact, formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { metricLabel } from "@/lib/metrics";
import type { Analytics, Histogram } from "@/lib/types";

export const SERIES = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
];

const axis = { fontSize: 11, fill: "var(--subtle)" };
const unitTicks = [0, 0.25, 0.5, 0.75, 1];
const unitTick = (value: number): string =>
  value === 0 || value === 1 ? String(value) : value.toFixed(2);

export function dayLabel(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

type TooltipEntry = {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string;
  payload?: Record<string, unknown>;
};

function ChartTooltip({
  active,
  payload,
  label,
  titleKey,
  formatLabel = (value) => value,
  formatValue = (value) => formatNumber(value),
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  /** A field of the data point to use as the title instead of the axis label. */
  titleKey?: string;
  formatLabel?: (label: string) => string;
  formatValue?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const fromPoint = titleKey ? payload[0]?.payload?.[titleKey] : undefined;
  const title =
    typeof fromPoint === "string"
      ? fromPoint
      : label !== undefined
        ? formatLabel(String(label))
        : "";
  return (
    <div className="border-border bg-card max-w-72 rounded-lg border px-3 py-2 text-xs shadow-md">
      {title ? <p className="mb-1 font-medium">{title}</p> : null}
      {payload.map((entry) => (
        <p
          key={`${entry.dataKey ?? entry.name}`}
          className="text-muted-foreground flex items-center gap-2"
        >
          <span className="size-2 shrink-0 rounded-full" style={{ background: entry.color }} />
          {entry.name}:{" "}
          <span className="text-foreground tabular font-medium">
            {typeof entry.value === "number" ? formatValue(entry.value) : (entry.value ?? "")}
          </span>
        </p>
      ))}
    </div>
  );
}

const legendStyle = { fontSize: 12, paddingTop: 8 };

/** Metric means across a dataset's runs, oldest first. */
export function TrendChart({
  points,
  metrics,
  k,
  height = 240,
}: {
  points: ({ name: string } & Record<string, number | string | null>)[];
  metrics: string[];
  k?: number;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="name"
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={16}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 1]}
          ticks={unitTicks}
          tickFormatter={unitTick}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip
          content={<ChartTooltip titleKey="label" formatValue={(v) => v.toFixed(3)} />}
          cursor={{ stroke: "var(--input)" }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} itemSorter={null} />
        {metrics.map((metric, index) => (
          <Line
            key={metric}
            type="monotone"
            dataKey={metric}
            name={metricLabel(metric, k)}
            stroke={SERIES[index % SERIES.length]}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: SERIES[index % SERIES.length] }}
            activeDot={{ r: 5 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** One group of horizontal bars per metric, one bar per run: labels stay readable at any width. */
export function MetricBars({
  rows,
  runs,
}: {
  rows: ({ metric: string } & Record<string, number | string | null>)[];
  runs: { key: string; name: string }[];
}) {
  const height = Math.max(260, rows.length * (runs.length * 12 + 24) + 60);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
        barCategoryGap="24%"
        barGap={2}
      >
        <CartesianGrid horizontal={false} stroke="var(--border)" />
        <XAxis
          type="number"
          domain={[0, 1]}
          ticks={unitTicks}
          tickFormatter={unitTick}
          tick={axis}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="metric"
          tick={{ ...axis, fill: "var(--muted-foreground)" }}
          tickLine={false}
          axisLine={false}
          width={92}
        />
        <Tooltip
          content={<ChartTooltip formatValue={(v) => v.toFixed(3)} />}
          cursor={{ fill: "var(--muted)" }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} itemSorter={null} />
        {runs.map((run, index) => (
          <Bar
            key={run.key}
            dataKey={run.key}
            name={run.name}
            fill={SERIES[index % SERIES.length]}
            radius={[0, 3, 3, 0]}
            maxBarSize={14}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function bucketLabel(bucket: Histogram[number]): string {
  return bucket.to === -1 ? `${bucket.from}+` : `${bucket.from}-${bucket.to}`;
}

/** Chunks per token-count bucket. Ticks show each bucket's lower bound; the tooltip the range. */
export function ChunkHistogram({
  histogram,
  height = 180,
}: {
  histogram: Histogram;
  height?: number;
}) {
  const data = histogram.map((bucket) => ({ bucket: bucketLabel(bucket), count: bucket.count }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="bucket"
          tick={axis}
          tickLine={false}
          axisLine={false}
          interval={0}
          tickFormatter={(value: string) =>
            value.endsWith("+") ? value : (value.split("-")[0] ?? value)
          }
        />
        <YAxis allowDecimals={false} tick={axis} tickLine={false} axisLine={false} width={40} />
        <Tooltip
          content={<ChartTooltip formatLabel={(l) => `${l} tokens`} />}
          cursor={{ fill: "var(--muted)" }}
        />
        <Bar
          dataKey="count"
          name="Chunks"
          fill="var(--primary)"
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Retrieval-only requests and answers per day, stacked: the two counts are disjoint. */
export function TrafficChart({ days }: { days: Analytics["days"] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={days} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="fill-retrieval" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.45} />
            <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient id="fill-answers" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--series-3)" stopOpacity={0.5} />
            <stop offset="100%" stopColor="var(--series-3)" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tickFormatter={dayLabel}
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          allowDecimals={false}
          tickFormatter={formatCompact}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip
          content={<ChartTooltip formatLabel={dayLabel} />}
          cursor={{ stroke: "var(--input)" }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} itemSorter={null} />
        <Area
          type="monotone"
          dataKey="queries"
          name="Retrieval"
          stackId="traffic"
          stroke="var(--series-1)"
          fill="url(#fill-retrieval)"
          strokeWidth={2}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="answers"
          name="Answers"
          stackId="traffic"
          stroke="var(--series-3)"
          fill="url(#fill-answers)"
          strokeWidth={2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const durationTick = (ms: number): string =>
  ms >= 1000 ? `${(ms / 1000).toFixed(ms % 1000 ? 1 : 0)} s` : `${Math.round(ms)} ms`;

export function LatencyChart({ days }: { days: Analytics["days"] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={days} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tickFormatter={dayLabel}
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          tickFormatter={durationTick}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <Tooltip
          content={<ChartTooltip formatLabel={dayLabel} formatValue={formatDuration} />}
          cursor={{ stroke: "var(--input)" }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={legendStyle} itemSorter={null} />
        <Line
          type="monotone"
          dataKey="p50_ms"
          name="p50"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="p95_ms"
          name="p95"
          stroke="var(--series-2)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ZeroHitChart({ days }: { days: Analytics["days"] }) {
  const data = days.map((d) => ({
    date: d.date,
    rate: d.queries + d.answers ? d.zero_hit / (d.queries + d.answers) : 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tickFormatter={dayLabel}
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          tickFormatter={(v: number) => formatPercent(v, 1)}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={44}
        />
        <Tooltip
          content={<ChartTooltip formatLabel={dayLabel} formatValue={(v) => formatPercent(v, 1)} />}
          cursor={{ fill: "var(--muted)" }}
        />
        <Bar
          dataKey="rate"
          name="Zero-hit rate"
          fill="var(--series-4)"
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
