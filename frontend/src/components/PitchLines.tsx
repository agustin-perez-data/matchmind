/** Pitch dimensions in metres; every pitch SVG in the app uses this viewBox. */
export const PITCH_W = 105
export const PITCH_H = 68

type Props = {
  /** Line colour; the live pitch uses a pale green, the pass network a softer one. */
  stroke?: string
  strokeWidth?: number
  strokeOpacity?: number
  /** The six-yard boxes are drawn on the live pitch and skipped on the small network diagram. */
  sixYardBoxes?: boolean
}

/** The markings of a football pitch (outline, halfway line, centre circle, penalty boxes) for a 105×68 viewBox. */
export function PitchLines({ stroke = '#e6f2ea', strokeWidth = 0.4, strokeOpacity = 1, sixYardBoxes = true }: Props) {
  const W = PITCH_W, H = PITCH_H
  return (
    <g fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeOpacity={strokeOpacity}>
      <rect x={0} y={0} width={W} height={H} /><line x1={W / 2} y1={0} x2={W / 2} y2={H} /><circle cx={W / 2} cy={H / 2} r={9.15} />
      <rect x={0} y={13.85} width={16.5} height={40.3} /><rect x={W - 16.5} y={13.85} width={16.5} height={40.3} />
      {sixYardBoxes && <><rect x={0} y={24.84} width={5.5} height={18.32} /><rect x={W - 5.5} y={24.84} width={5.5} height={18.32} /></>}
    </g>
  )
}

/** The turf: a gradient and faint mowing stripes, shared by the live pitch and the preview. */
export function Turf({ id = 'turf' }: { id?: string }) {
  const W = PITCH_W, H = PITCH_H
  return (
    <>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#2b7d4c" /><stop offset="1" stopColor="#17532f" /></linearGradient></defs>
      <rect width={W} height={H} fill={`url(#${id})`} />
      {[0, 2, 4, 6, 8, 10].map((i) => <rect key={i} x={i * (W / 12)} y={0} width={W / 12} height={H} fill="#ffffff0d" />)}
    </>
  )
}
