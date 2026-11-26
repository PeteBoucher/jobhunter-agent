import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

describe("useDebouncedValue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("emits only the final value of a rapid burst", () => {
    const { result, rerender } = renderHook(
      ({ v }) => useDebouncedValue(v, 350),
      { initialProps: { v: "" } }
    );

    // Typing "test" one keystroke at a time, faster than the delay.
    for (const v of ["t", "te", "tes", "test"]) {
      rerender({ v });
      act(() => vi.advanceTimersByTime(100));
      expect(result.current).toBe("");
    }

    act(() => vi.advanceTimersByTime(350));
    expect(result.current).toBe("test");
  });
});
