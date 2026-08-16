// Spinner — used during loading states.

import { Loader2 } from "lucide-react";

export function Spinner({
  size = "md",
  className = "",
}: {
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const px = size === "sm" ? "w-3 h-3" : size === "lg" ? "w-6 h-6" : "w-4 h-4";
  return <Loader2 className={`${px} animate-spin text-slate-500 ${className}`} />;
}
