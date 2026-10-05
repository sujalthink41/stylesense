import Svg, { Circle, Path } from 'react-native-svg';

/** One drawn icon family: 24-unit grid, round caps, 1.75 stroke (2 for small chevrons). */
const paths = {
  home: ['M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z'],
  stylist: [
    'M12 4.2a1.9 1.9 0 0 1 1.9 1.9c0 .8-.5 1.4-1.2 1.8-.4.2-.7.6-.7 1.1v.8',
    'M12 9.8 3.7 15.5c-.8.6-.4 1.9.6 1.9h15.4c1 0 1.4-1.3.6-1.9L12 9.8',
  ],
  saved: ['m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z'],
  me: ['M4 21a8 8 0 0 1 16 0'],
  search: ['m20.5 20.5-4.2-4.2'],
  camera: ['M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z'],
  close: ['M18 6 6 18', 'M6 6l12 12'],
  arrowLeft: ['M19 12H5', 'M12 19l-7-7 7-7'],
  arrowRight: ['M5 12h14', 'M13 5l7 7-7 7'],
  arrowUpRight: ['M7 17 17 7', 'M8 7h9v9'],
  chevronRight: ['m9 18 6-6-6-6'],
  check: ['M20 6 9 17l-5-5'],
  share: ['M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8', 'M16 6l-4-4-4 4', 'M12 2v13'],
  send: ['M5 12h14', 'M13 5l7 7-7 7'],
  refresh: ['M3 12a9 9 0 0 1 15.5-6.3L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-15.5 6.3L3 16', 'M3 21v-5h5'],
  logout: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'm16 17 5-5-5-5', 'M21 12H9'],
  info: ['M12 16v-4', 'M12 8h.01'],
  heartOutline: ['M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z'],
} as const;

const circles: Partial<Record<IconName, { cx: number; cy: number; r: number }>> = {
  me: { cx: 12, cy: 8, r: 4 },
  search: { cx: 11, cy: 11, r: 7.5 },
  camera: { cx: 12, cy: 13, r: 3.2 },
  info: { cx: 12, cy: 12, r: 9.5 },
};

const filled = {
  heart: 'M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z',
  star: 'M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z',
} as const;

export type IconName = keyof typeof paths | keyof typeof filled;

export interface IconProps {
  name: IconName;
  size?: number;
  color: string;
  strokeWidth?: number;
}

export function Icon({ name, size = 24, color, strokeWidth = 1.75 }: IconProps) {
  if (name in filled) {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24" accessible={false}>
        <Path d={filled[name as keyof typeof filled]} fill={color} />
      </Svg>
    );
  }
  const circle = circles[name];
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      {circle ? <Circle {...circle} stroke={color} strokeWidth={strokeWidth} /> : null}
      {paths[name as keyof typeof paths].map((d) => (
        <Path
          key={d}
          d={d}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </Svg>
  );
}
