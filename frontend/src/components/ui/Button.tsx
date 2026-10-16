import {
  forwardRef,
  useCallback,
  useState,
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type PointerEvent,
  type ReactNode,
} from "react";
import { Link, type LinkProps } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "glass";
type Size = "sm" | "md" | "lg";

/* Tactile button system:
 *  - press: scales down slightly, so a tap is felt even before the result arrives
 *  - ripple: a ring of light spreads from exactly where the finger/cursor landed
 *  - hover (pointer devices): lifts 2px, the glow deepens, and a sheen sweeps across
 * All of it is skipped for disabled buttons and frozen under reduced motion. */
const BASE =
  "group relative isolate inline-flex select-none items-center justify-center overflow-hidden whitespace-nowrap font-medium " +
  "transition-[transform,box-shadow,background-color,border-color,color,opacity] duration-300 ease-spring active:scale-[0.97] " +
  "disabled:pointer-events-none disabled:opacity-55 disabled:shadow-none";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-brand text-white shadow-glow shadow-inner-hi hover:-translate-y-0.5 hover:shadow-glow-lg",
  secondary:
    "bg-primary-light text-primary-dark ring-1 ring-inset ring-primary/15 hover:-translate-y-0.5 hover:ring-primary/35 hover:shadow-soft",
  glass: "glass text-ink hover:-translate-y-0.5 hover:border-primary/40 hover:text-primary-dark",
  ghost: "bg-transparent text-muted hover:bg-ink/[0.06] hover:text-ink",
  danger:
    "bg-gradient-to-br from-[#d4513f] to-[#9b2c1f] text-white shadow-[0_10px_30px_-12px_rgb(178_52_38/0.7)] shadow-inner-hi " +
    "hover:-translate-y-0.5 hover:shadow-[0_16px_40px_-12px_rgb(178_52_38/0.75)]",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-9 rounded-xl px-3.5 text-sm gap-1.5",
  md: "h-11 rounded-xl px-5 text-sm gap-2",
  lg: "h-14 rounded-2xl px-7 text-base gap-2.5",
};

const SHEEN_VARIANTS: Variant[] = ["primary", "danger"];

function buttonClasses({
  variant = "primary",
  size = "md",
  fullWidth,
  className = "",
}: {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  className?: string;
}) {
  return `${BASE} ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${fullWidth ? "w-full" : ""} ${className}`;
}

interface Ripple {
  id: number;
  x: number;
  y: number;
  size: number;
}

function useRipple() {
  const [ripples, setRipples] = useState<Ripple[]>([]);

  const spawn = useCallback((e: PointerEvent<HTMLElement>) => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // Diameter that just reaches the farthest corner from where the press landed.
    const size = 2 * Math.hypot(Math.max(x, rect.width - x), Math.max(y, rect.height - y));
    setRipples((prev) => [...prev.slice(-3), { id: Date.now() + Math.random(), x, y, size }]);
  }, []);

  const layer = (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 -z-[1] overflow-hidden rounded-[inherit]">
      {ripples.map((r) => (
        <span
          key={r.id}
          className="ripple"
          style={{ left: r.x, top: r.y, width: r.size, height: r.size }}
          onAnimationEnd={() => setRipples((prev) => prev.filter((p) => p.id !== r.id))}
        />
      ))}
    </span>
  );

  return { spawn, layer };
}

function Sheen() {
  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 -z-[1] overflow-hidden rounded-[inherit]">
      <span className="absolute inset-y-0 start-0 w-1/2 -translate-x-[120%] bg-gradient-to-r from-transparent via-white/35 to-transparent group-hover:animate-shine group-disabled:hidden" />
    </span>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
    </svg>
  );
}

function Content({
  icon,
  iconEnd,
  isLoading,
  children,
}: {
  icon?: IconName;
  iconEnd?: IconName;
  isLoading?: boolean;
  children: ReactNode;
}) {
  const directional = iconEnd === "arrowRight" || iconEnd === "chevronRight";
  return (
    <>
      {isLoading ? <Spinner /> : icon && <Icon name={icon} className="h-[1.15em] w-[1.15em] shrink-0 transition-transform duration-300 ease-spring group-hover:scale-110" />}
      {children}
      {iconEnd && !isLoading && (
        <span className={directional ? "flip-rtl inline-flex" : "inline-flex"}>
          <Icon
            name={iconEnd}
            className="h-[1.1em] w-[1.1em] shrink-0 transition-transform duration-300 ease-spring group-hover:translate-x-1"
          />
        </span>
      )}
    </>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  isLoading?: boolean;
  fullWidth?: boolean;
  icon?: IconName;
  iconEnd?: IconName;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = "primary", size = "md", isLoading, fullWidth, icon, iconEnd, className = "", children, disabled, onPointerDown, type = "button", ...rest },
    ref
  ) => {
    const { spawn, layer } = useRipple();
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        className={buttonClasses({ variant, size, fullWidth, className })}
        onPointerDown={(e) => {
          spawn(e);
          onPointerDown?.(e);
        }}
        {...rest}
      >
        {layer}
        {SHEEN_VARIANTS.includes(variant) && <Sheen />}
        <Content icon={icon} iconEnd={iconEnd} isLoading={isLoading}>
          {children}
        </Content>
      </button>
    );
  }
);
Button.displayName = "Button";

interface ButtonLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">, Pick<LinkProps, "to" | "replace" | "state"> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  icon?: IconName;
  iconEnd?: IconName;
}

/** A router link styled (and animated) exactly like a Button — avoids nesting a
 * <button> inside an <a>, which is invalid HTML and confuses screen readers. */
export function ButtonLink({ variant = "primary", size = "md", fullWidth, icon, iconEnd, className = "", children, onPointerDown, ...rest }: ButtonLinkProps) {
  const { spawn, layer } = useRipple();
  return (
    <Link
      className={buttonClasses({ variant, size, fullWidth, className })}
      onPointerDown={(e) => {
        spawn(e);
        onPointerDown?.(e);
      }}
      {...rest}
    >
      {layer}
      {SHEEN_VARIANTS.includes(variant) && <Sheen />}
      <Content icon={icon} iconEnd={iconEnd}>
        {children}
      </Content>
    </Link>
  );
}
