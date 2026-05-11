type Props = { values: number[]; width?: number; height?: number; stroke?: string }

export function Sparkline({ values, width = 140, height = 32, stroke = '#60a5fa' }: Props) {
  if (values.length === 0) return <svg width={width} height={height} />
  const max = Math.max(1, ...values)
  const stepX = width / Math.max(1, values.length - 1)
  const pts = values.map((v, i) => {
    const x = i * stepX
    const y = height - (v / max) * (height - 2) - 1
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
