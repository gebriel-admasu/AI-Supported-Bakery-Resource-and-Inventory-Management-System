import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

export interface SparklineDatum {
  date: string;
  value: number;
}

interface MiniSparklineProps {
  data: SparklineDatum[];
  /** Tailwind color class used for the stroke + gradient. */
  color?: string;
  height?: number;
  valueFormatter?: (v: number) => string;
}

export default function MiniSparkline({
  data,
  color = '#2563eb',
  height = 60,
  valueFormatter,
}: MiniSparklineProps) {
  if (!data.length) {
    return (
      <div
        className="text-xs text-gray-400 italic"
        style={{ height }}
      >
        No trend data yet
      </div>
    );
  }
  const gradientId = `spark-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Tooltip
            cursor={false}
            contentStyle={{
              fontSize: '11px',
              padding: '4px 8px',
              borderRadius: '4px',
            }}
            labelFormatter={(label) => label}
            formatter={(value: number) => [
              valueFormatter ? valueFormatter(value) : String(value),
              '',
            ]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
