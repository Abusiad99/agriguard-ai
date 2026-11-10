/** Text direction for a UI locale. Arabic is right to left; every other locale is left to right. */
export const RTL_LOCALES: readonly string[] = ["ar"];

export function textDirection(locale: string): "ltr" | "rtl" {
  return RTL_LOCALES.includes(locale) ? "rtl" : "ltr";
}
