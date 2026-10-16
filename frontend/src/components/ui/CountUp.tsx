import { useCountUp } from "@/hooks/useCountUp";

/** Renders `target` with a count-up, formatted with the given number of decimals. */
export function CountUp({ value, decimals = 0, duration, delay, suffix = "" }: { value: number; decimals?: number; duration?: number; delay?: number; suffix?: string }) {
  const v = useCountUp(value, duration, delay);
  return (
    <>
      {v.toFixed(decimals)}
      {suffix}
    </>
  );
}
