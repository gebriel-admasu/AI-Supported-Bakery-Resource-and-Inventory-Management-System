import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export interface LineSeriesConfig {
  dataKey: string;
  label: string;
  color: string;
  valueFormatter?: (v: number) => string;
}

interface LineTrendChartProps {
  data: Array<Record<string, string | number>>;
  xKey: string;
  series: LineSeriesConfig[];
  height?: number;
  xTickFormatter?: (value: string) => string;
  yTickFormatter?: (value: number) => string;
}

export default function LineTrendChart({
  data,
  xKey,
  series,
  height = 280,
  xTickFormatter,
  yTickFormatter,
}: LineTrendChartProps) {
  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center text-sm text-gray-400 italic"
        style={{ height }}
      >
        No data for the selected range.
      </div>
    );
  }
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={xTickFormatter}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={yTickFormatter}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            labelFormatter={xTickFormatter}
            formatter={(value: number, name: string, props) => {
              const config = series.find((s) => s.label === name || s.dataKey === props.dataKey);
              const formatted = config?.valueFormatter
                ? config.valueFormatter(value)
                : String(value);
              return [formatted, name];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((s) => (
            <Line
              key={s.dataKey}
              type="monotone"
              name={s.label}
              dataKey={s.dataKey}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
