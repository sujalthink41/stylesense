import Svg, { Circle, Defs, Ellipse, G, Path, Text as SvgText, TextPath } from 'react-native-svg';

/**
 * The buti: StyleSense's block-print motif, drawn as exact geometry (petals as rotated
 * ellipses). Used only in signature moments, never as wallpaper.
 */
export interface ButiProps {
  size: number;
  color: string;
  petals?: 4 | 6 | 8;
  /** Colour of the eye; omit to leave it solid. */
  eye?: string;
}

export function Buti({ size, color, petals = 8, eye }: ButiProps) {
  const step = 360 / petals;
  return (
    <Svg width={size} height={size} viewBox="-30 -30 60 60" accessible={false}>
      <G fill={color}>
        {Array.from({ length: petals }, (_, i) => (
          <Ellipse key={i} cx={0} cy={-13} rx={5.4} ry={10} rotation={i * step} originX={0} originY={0} />
        ))}
        <Circle r={5} fill={eye ?? color} />
        {eye ? <Circle r={2.4} fill={color} /> : null}
      </G>
    </Svg>
  );
}

/** The block stamp that lands on a liked card: ring text, double rule, buti at the centre. */
export function Stamp({ size, color, ground }: { size: number; color: string; ground: string }) {
  return (
    <Svg width={size} height={size} viewBox="-66 -66 132 132" accessibilityLabel="Saved">
      <Defs>
        <Path id="stampRing" d="M0,-50 a50,50 0 1,1 -0.01,0" />
      </Defs>
      <G fill="none" stroke={color} strokeWidth={2.5}>
        <Circle r={60} />
        <Circle r={40} />
      </G>
      <SvgText fill={color} fontSize={12.5} fontWeight="700" letterSpacing={5} fontFamily="AnekLatin-Bold">
        <TextPath href="#stampRing">SAVED · YOURS · SAVED · YOURS ·</TextPath>
      </SvgText>
      <G fill={color}>
        {Array.from({ length: 8 }, (_, i) => (
          <Ellipse key={i} cx={0} cy={-19} rx={7} ry={13} rotation={i * 45} originX={0} originY={0} />
        ))}
        <Circle r={7} fill={ground} />
        <Circle r={3.5} />
      </G>
    </Svg>
  );
}

/** The app mark: a carved block (rounded square) printed with the buti. */
export function LogoMark({ size, block, ink, eye }: { size: number; block: string; ink: string; eye: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 56 56" accessibilityLabel="StyleSense">
      <Path d="M14 0h28a14 14 0 0 1 14 14v28a14 14 0 0 1-14 14H14A14 14 0 0 1 0 42V14A14 14 0 0 1 14 0z" fill={block} />
      <G fill={ink} transform="translate(28 28)">
        {Array.from({ length: 8 }, (_, i) => (
          <Ellipse key={i} cx={0} cy={-12} rx={4.2} ry={8} rotation={i * 45} originX={0} originY={0} />
        ))}
        <Circle r={4.5} fill={block} />
        <Circle r={2.2} fill={eye} />
      </G>
    </Svg>
  );
}
