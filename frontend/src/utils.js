const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export function monthName(m) {
  return MONTHS[(m - 1) % 12] || "";
}

/** "June 2026" */
export function periodLabel(year, month) {
  return `${monthName(month)} ${year}`;
}

/** Human-readable file size. */
export function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatAmount(value) {
  if (value == null) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export const KIND_LABELS = {
  bank_statement: "Bank statement",
  invoice: "Invoice",
  receipt: "Receipt",
  other: "Other",
};

export const KINDS = ["bank_statement", "invoice", "receipt", "other"];
