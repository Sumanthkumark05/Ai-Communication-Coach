import React from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";

interface BackButtonProps {
  currentModuleName?: string;
  onNavigateToDashboard?: () => void;
}

export default function BackButton({ currentModuleName, onNavigateToDashboard }: BackButtonProps) {
  const router = useRouter();

  const handleBack = (e: React.MouseEvent) => {
    e.preventDefault();
    if (typeof window !== "undefined" && window.history.length > 1) {
      window.history.back();
    } else {
      if (onNavigateToDashboard) {
        onNavigateToDashboard();
      } else {
        router.push("/dashboard");
      }
    }
  };

  const handleDashboardClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (onNavigateToDashboard) {
      onNavigateToDashboard();
    } else {
      router.push("/dashboard");
    }
  };

  return (
    <div className="flex flex-col gap-2 mb-4 animate-fadeIn">
      {/* Breadcrumb */}
      {currentModuleName && (
        <nav className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider select-none">
          <span 
            onClick={handleDashboardClick}
            className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-pointer"
          >
            Dashboard
          </span>
          <ChevronRight className="w-3 h-3 text-slate-300 dark:text-slate-800" />
          <span className="text-slate-500 dark:text-slate-400">{currentModuleName}</span>
        </nav>
      )}

      {/* Back Button */}
      <button
        onClick={handleBack}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 focus:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 rounded-lg transition-all cursor-pointer select-none border border-transparent hover:bg-slate-100 hover:border-slate-200 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800 dark:hover:border-slate-700 w-fit"
        aria-label="Go back to the previous page"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back</span>
      </button>
    </div>
  );
}
