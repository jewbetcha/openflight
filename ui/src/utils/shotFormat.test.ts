import { describe, expect, it } from 'vitest';
import { PLACEHOLDER, fmtSigned, fmtSpin, shapeKeyFromSpinAxis } from './shotFormat';

describe('fmtSigned', () => {
  it('prefixes a plus on zero and positives', () => {
    expect(fmtSigned(0)).toBe('+0.0');
    expect(fmtSigned(2.34)).toBe('+2.3');
  });
  it('keeps the minus on negatives', () => {
    expect(fmtSigned(-1.1)).toBe('-1.1');
    expect(fmtSigned(-3.46)).toBe('-3.5');
  });
  it('honours the digits argument', () => {
    expect(fmtSigned(2.5, 0)).toBe('+3');
  });
  it('returns the placeholder for null/undefined/non-finite', () => {
    expect(fmtSigned(null)).toBe(PLACEHOLDER);
    expect(fmtSigned(undefined)).toBe(PLACEHOLDER);
    expect(fmtSigned(NaN)).toBe(PLACEHOLDER);
    expect(fmtSigned(Infinity)).toBe(PLACEHOLDER);
  });
});

describe('fmtSpin', () => {
  it('adds thousands separators', () => {
    expect(fmtSpin(2450)).toBe('2,450');
    expect(fmtSpin(11000)).toBe('11,000');
  });
  it('rounds to whole rpm', () => {
    expect(fmtSpin(2450.6)).toBe('2,451');
  });
  it('returns the placeholder for null/non-finite', () => {
    expect(fmtSpin(null)).toBe(PLACEHOLDER);
    expect(fmtSpin(NaN)).toBe(PLACEHOLDER);
  });
});

describe('shapeKeyFromSpinAxis', () => {
  it('maps the draw/fade bands by spin axis', () => {
    expect(shapeKeyFromSpinAxis(-5)).toBe('strongDraw');
    expect(shapeKeyFromSpinAxis(-2)).toBe('draw');
    expect(shapeKeyFromSpinAxis(0)).toBe('straight');
    expect(shapeKeyFromSpinAxis(1)).toBe('straight');
    expect(shapeKeyFromSpinAxis(3)).toBe('slightFade');
    expect(shapeKeyFromSpinAxis(5)).toBe('strongFade');
  });
  it('returns null for null/non-finite', () => {
    expect(shapeKeyFromSpinAxis(null)).toBeNull();
    expect(shapeKeyFromSpinAxis(NaN)).toBeNull();
  });
});
