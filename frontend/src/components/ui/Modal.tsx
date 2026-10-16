import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

export function Modal({
  isOpen,
  onClose,
  title,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // Parents usually pass an inline arrow; keep the latest one in a ref so typing in
  // the form (which re-renders the parent) never re-runs the open/close effect.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      previouslyFocused?.focus?.();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Portal to <body> so page-level entrance animations (transforms) can never
  // trap the overlay inside the content column.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-grove/40 p-0 backdrop-blur-md animate-fade-in sm:items-center sm:p-4 dark:bg-black/60"
      role="presentation"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="glass max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-[1.75rem] p-6 shadow-elevate outline-none animate-scale-in sm:rounded-[1.75rem] sm:p-7 [--glass-bg:rgb(var(--c-surface)/0.94)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="font-display text-xl font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-all duration-300 ease-spring hover:rotate-90 hover:bg-ink/[0.06] hover:text-ink"
          >
            <Icon name="close" className="h-5 w-5" strokeWidth={2} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}
