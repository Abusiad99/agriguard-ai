export function formatDate(iso: string, locale: string = "en"): string {
  try {
    return new Intl.DateTimeFormat(locale === "ar" ? "ar-EG" : "en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatMonth(monthStr: string): string {
  // monthStr format: "YYYY-MM"
  const [year, month] = monthStr.split("-");
  if (!year || !month) return monthStr;
  const date = new Date(Number(year), Number(month) - 1, 1);
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short" }).format(date);
}

export function bytesToMb(bytes: number): number {
  return Math.round((bytes / (1024 * 1024)) * 10) / 10;
}
