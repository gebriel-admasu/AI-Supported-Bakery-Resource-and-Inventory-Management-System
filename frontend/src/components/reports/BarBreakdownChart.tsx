import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface BarBreakdownChartProps {
  data: Array<Record<string, string | number>>;
  xKey: string;
  yKey: string;
  /** Display name for the bar (shown in the tooltip). */
  label: string;
  height?: number;
  layout?: 'horizontal' | 'vertical';
  yTickFormatter?: (v: number) => string;
  valueFormatter?: (v: number) => string;
  /** Optional accent palette — cycled across the bars. */
  colors?: string[];
}

const DEFAULT_COLORS = [
  '#2563eb',
  '#16a34a',
  '#f59e0b',
  '#dc2626',
  '#9333ea',
  '#0891b2',
  '#65a30d',
];

export default function BarBreakdownChart({
  data,
  xKey,
  yKey,
  label,
  height = 280,
  layout = 'vertical',
  yTickFormatter,
  valueFormatter,
  colors = DEFAULT_COLORS,
}: BarBreakdownChartProps) {
  if (!data.length) {
    return (
      <div
        className="flex items-center justify-center text-sm text-gray-400 italic"
        style={{ height }}
      >
        Nothing to show for the selected range.
      </div>
    );
  }
  const isHorizontal = layout === 'horizontal'; // category axis on the Y axis
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart
          data={data}
          layout={isHorizontal ? 'vertical' : 'horizontal'}
          margin={{
            top: 8,
            right: 16,
            bottom: 0,
            left: isHorizontal ? 24 : 0,
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          {isHorizontal ? (
            <>
              <XAxis
                type="number"
                tick={{ fontSize: 11, fill: '#6b7280' }}
                tickFormatter={yTickFormatter}
              />
              <YAxis
                type="category"
                dataKey={xKey}
                width={120}
                tick={{ fontSize: 11, fill: '#374151' }}
              />
            </>
          ) : (
            <>
              <XAxis
                dataKey={xKey}
                tick={{ fontSize: 11, fill: '#6b7280' }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#6b7280' }}
                tickFormatter={yTickFormatter}
              />
            </>
          )}
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            formatter={(value: number) => [
              valueFormatter ? valueFormatter(value) : String(value),
              label,
            ]}
          />
          <Bar dataKey={yKey} name={label} radius={[4, 4, 0, 0]}>
            {data.map((_, idx) => (
              <Cell key={idx} fill={colors[idx % colors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
