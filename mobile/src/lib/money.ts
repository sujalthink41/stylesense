/** Money is integer paise end to end; this is the only place it becomes text. */

/** Indian digit grouping: 1,299 · 12,999 · 1,00,499 · 12,34,56,789. */
export function groupIndian(n: number): string {
  const digits = Math.trunc(Math.abs(n)).toString();
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `${rest},${last3}`;
}

/** ₹ plus grouped rupees; paise are dropped (catalog prices are whole rupees). */
export function formatRupees(paise: number): string {
  const sign = paise < 0 ? '−' : '';
  return `${sign}₹${groupIndian(Math.round(paise / 100))}`;
}

/** Just the grouped number, for layouts that set the ₹ symbol separately. */
export function rupeeDigits(paise: number): string {
  return groupIndian(Math.round(paise / 100));
}

export function discountPercent(pricePaise: number, mrpPaise: number | null | undefined): number {
  if (!mrpPaise || mrpPaise <= pricePaise) return 0;
  return Math.min(99, Math.round(((mrpPaise - pricePaise) * 100) / mrpPaise));
}
