import { discountPercent, formatRupees, groupIndian, rupeeDigits } from '../money';

describe('Indian digit grouping', () => {
  it.each([
    [0, '0'],
    [999, '999'],
    [1_299, '1,299'],
    [12_999, '12,999'],
    [1_00_499, '1,00,499'],
    [12_34_56_789, '12,34,56,789'],
  ])('%d → %s', (n, expected) => {
    expect(groupIndian(n)).toBe(expected);
  });

  it('formats paise as whole rupees with the ₹ sign', () => {
    expect(formatRupees(129_900)).toBe('₹1,299');
    expect(formatRupees(49_950)).toBe('₹500'); // rounds half up
    expect(formatRupees(-10_000)).toBe('−₹100');
    expect(rupeeDigits(1_00_49_900)).toBe('1,00,499');
  });
});

describe('discount', () => {
  it('is the rounded share off MRP, capped at 99', () => {
    expect(discountPercent(79_900, 129_900)).toBe(38);
    expect(discountPercent(100, 1_000_000)).toBe(99);
  });

  it('is zero without a higher MRP', () => {
    expect(discountPercent(79_900, null)).toBe(0);
    expect(discountPercent(79_900, 79_900)).toBe(0);
    expect(discountPercent(79_900, 50_000)).toBe(0);
  });
});
