import { useId } from "react";

interface ChartProps {
  data: number[];
  labels?: string[];
  color?: string;
  height?: number;
  ariaLabel: string;
  showAxis?: boolean;
}

const pointsFor = (data: number[], width: number, height: number, padding = 12): string => {
  if (data.length === 0) return "";
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = Math.max(max - min, 1);
  return data.map((value, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(data.length - 1, 1);
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(" ");
};

export function LineChart({ data, labels = [], color = "#2878ff", height = 180, ariaLabel, showAxis = true }: ChartProps): JSX.Element {
  const gradientId = useId();
  const points = pointsFor(data, 560, height);
  const area = data.length ? `12,${height - 12} ${points} 548,${height - 12}` : "";
  return <div className="chart" role="img" aria-label={ariaLabel}><svg viewBox={`0 0 560 ${height}`} preserveAspectRatio="none"><defs><linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".24" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>{showAxis && [0, 1, 2, 3].map((line) => <line key={line} x1="12" x2="548" y1={12 + line * ((height - 24) / 3)} y2={12 + line * ((height - 24) / 3)} className="chart__grid" />)}<polygon points={area} fill={`url(#${gradientId})`} /><polyline points={points} fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />{data.map((value, index) => { const coordinate = points.split(" ")[index]?.split(","); return coordinate ? <circle key={`${value}-${index}`} cx={coordinate[0]} cy={coordinate[1]} fill="var(--surface-1)" r="4" stroke={color} strokeWidth="2" /> : null; })}</svg>{labels.length > 0 && <div className="chart__labels">{labels.map((label) => <span key={label}>{label}</span>)}</div>}</div>;
}

export function BarChart({ data, labels = [], color = "#2878ff", ariaLabel }: ChartProps): JSX.Element {
  const max = Math.max(...data, 1);
  return <div className="chart chart--bar" role="img" aria-label={ariaLabel}><div className="bars">{data.map((value, index) => <div className="bar-column" key={`${labels[index] ?? index}`}><span className="bar-column__value">{value}</span><div className="bar" style={{ height: `${Math.max(5, (value / max) * 100)}%`, background: color }} /><span className="bar-column__label">{labels[index] ?? index + 1}</span></div>)}</div></div>;
}

export function DonutChart({ value, label, color = "#2878ff", size = 132, ariaLabel }: { value: number; label: string; color?: string; size?: number; ariaLabel: string }): JSX.Element {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const safeValue = Math.max(0, Math.min(100, value));
  return <div className="donut" role="img" aria-label={ariaLabel} style={{ width: size, height: size }}><svg viewBox="0 0 120 120"><circle className="donut__track" cx="60" cy="60" r={radius} /><circle className="donut__value" cx="60" cy="60" r={radius} stroke={color} strokeDasharray={circumference} strokeDashoffset={circumference - (safeValue / 100) * circumference} /></svg><div className="donut__center"><strong>{safeValue}%</strong><span>{label}</span></div></div>;
}

export function Sparkline({ data, color = "#2878ff", ariaLabel }: { data: number[]; color?: string; ariaLabel: string }): JSX.Element {
  return <div className="sparkline" role="img" aria-label={ariaLabel}><svg viewBox="0 0 120 34" preserveAspectRatio="none"><polyline points={pointsFor(data, 120, 34, 3)} fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" /></svg></div>;
}
