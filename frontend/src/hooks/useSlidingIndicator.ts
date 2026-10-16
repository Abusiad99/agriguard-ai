import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

export interface IndicatorRect {
  left: number;
  top: number;
  width: number;
  height: number;
  ready: boolean;
}

/**
 * Measures the child marked `data-active="true"` inside the returned container ref,
 * so a single absolutely-positioned "pill" can glide between tabs / nav items
 * instead of each item toggling its own background. Re-measures on resize and
 * whenever `activeKey` changes.
 */
export function useSlidingIndicator<T extends HTMLElement>(activeKey: unknown) {
  const containerRef = useRef<T>(null);
  const [rect, setRect] = useState<IndicatorRect>({ left: 0, top: 0, width: 0, height: 0, ready: false });

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const measure = () => {
      const active = container.querySelector<HTMLElement>('[data-active="true"]');
      if (!active) {
        setRect((r) => ({ ...r, width: 0, ready: false }));
        return;
      }
      setRect({ left: active.offsetLeft, top: active.offsetTop, width: active.offsetWidth, height: active.offsetHeight, ready: true });
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    container.querySelectorAll("[data-indicator-item]").forEach((el) => ro.observe(el));
    void document.fonts?.ready.then(measure);
    return () => ro.disconnect();
  }, [activeKey]);

  return { containerRef, rect };
}

/** Inline style that places the sliding pill over the measured active item. */
export function indicatorStyle(rect: IndicatorRect): CSSProperties {
  return {
    left: 0,
    top: 0,
    width: rect.width,
    height: rect.height,
    transform: `translate3d(${rect.left}px, ${rect.top}px, 0)`,
    opacity: rect.ready ? 1 : 0,
  };
}
