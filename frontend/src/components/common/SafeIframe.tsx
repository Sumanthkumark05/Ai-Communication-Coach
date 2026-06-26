/**
 * SafeIframe — Drop-in replacement for <iframe> that prevents empty-src warnings.
 */
"use client";

import React, { forwardRef, IframeHTMLAttributes } from "react";
import { safeSrc } from "../../utils/safeSrc";
import { Globe, AlertCircle } from "lucide-react";

// Omit native `loading` (which is "eager"|"lazy") to redefine it as boolean
export interface SafeIframeProps extends Omit<IframeHTMLAttributes<HTMLIFrameElement>, "src" | "loading"> {
  src?: string | null | undefined;
  isLoading?: boolean;
  iframeError?: string | null;
  fallback?: React.ReactNode;
  _debugName?: string;
}

const SafeIframe = forwardRef<HTMLIFrameElement, SafeIframeProps>(
  ({ src, isLoading = false, iframeError = null, fallback, _debugName = "SafeIframe", title, ...rest }, ref) => {
    const safeSrcValue = safeSrc(src);

    if (process.env.NODE_ENV === "development" && src !== undefined && src !== null && !safeSrcValue) {
      console.warn(
        `[SafeMedia] Invalid media source detected\n` +
        `  Component: ${_debugName}\n  Prop: src\n  Value: ${JSON.stringify(src)}`
      );
    }

    if (isLoading) {
      return (
        <div className="flex items-center justify-center gap-2 text-slate-400 text-xs bg-slate-900 rounded-xl p-6">
          <Globe className="w-5 h-5 opacity-40 animate-pulse" />
          <span>Loading...</span>
        </div>
      );
    }

    if (iframeError) {
      return (
        <div className="flex items-center gap-2 text-amber-500 text-xs">
          <AlertCircle className="w-4 h-4" />
          <span>{iframeError}</span>
        </div>
      );
    }

    if (!safeSrcValue) {
      return (
        <>
          {fallback ?? (
            <div className="flex items-center gap-2 text-slate-500 text-xs">
              <Globe className="w-4 h-4 opacity-30" />
              <span className="opacity-50">Content unavailable</span>
            </div>
          )}
        </>
      );
    }

    return <iframe ref={ref} src={safeSrcValue} title={title ?? "Embedded content"} {...rest} />;
  }
);

SafeIframe.displayName = "SafeIframe";
export default SafeIframe;
