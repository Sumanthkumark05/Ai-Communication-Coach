/**
 * SafeVideo — Drop-in replacement for <video> that permanently prevents
 * the React "empty src" warning.
 *
 * Guarantees:
 *  - Never renders when src is missing / empty / whitespace-only
 *  - Shows a loading state while `isLoading` prop is true
 *  - Shows an error state when `videoError` prop is set or when video fails
 *  - Logs "Invalid media source" in development mode (never crashes production)
 *  - Fully TypeScript-strict
 */

"use client";

import React, { useState, forwardRef, VideoHTMLAttributes } from "react";
import { safeSrc } from "../../utils/safeSrc";
import { AlertCircle, Loader2, Video } from "lucide-react";

// Omit native `src` from VideoHTMLAttributes to redefine it as accepting null
export interface SafeVideoProps extends Omit<VideoHTMLAttributes<HTMLVideoElement>, "src"> {
  /** Raw src from state/API — empty strings, null and undefined are safe */
  src?: string | null | undefined;
  /** Show a loading overlay */
  isLoading?: boolean;
  /** Show an error overlay with this message */
  videoError?: string | null;
  /** Alias: same as videoError, provided for ergonomics */
  error?: string | null;
  /** Node to render when src is invalid and no error/loading state */
  fallback?: React.ReactNode;
  /** Wrapper className (applied to the outer container div) */
  containerClassName?: string;
  /** Component name for dev-mode warning logging */
  _debugName?: string;
}

const DefaultFallback = () => (
  <div className="flex flex-col items-center justify-center gap-2 text-slate-500 w-full h-full min-h-[80px] bg-slate-900 rounded-xl">
    <Video className="w-8 h-8 opacity-30" />
    <span className="text-[10px] opacity-50 font-semibold">No recording available</span>
  </div>
);

const SafeVideo = forwardRef<HTMLVideoElement, SafeVideoProps>(
  (
    {
      src,
      isLoading = false,
      videoError = null,
      error = null,
      fallback,
      containerClassName,
      className,
      onError,
      _debugName = "SafeVideo",
      ...rest
    },
    ref
  ) => {
    const [internalError, setInternalError] = useState<string | null>(null);
    const safeSrcValue = safeSrc(src);

    // Dev-mode runtime protection
    if (process.env.NODE_ENV === "development" && src !== undefined && src !== null && !safeSrcValue) {
      console.warn(
        `[SafeMedia] Invalid media source detected\n` +
        `  Component: ${_debugName}\n` +
        `  Prop: src\n` +
        `  Value: ${JSON.stringify(src)}\n` +
        `  → Rendering suppressed to prevent empty-src browser warning.`
      );
    }

    const displayError = videoError || error || internalError;

    const handleError = (e: React.SyntheticEvent<HTMLVideoElement>) => {
      setInternalError("Video unavailable");
      if (onError) onError(e);
    };

    // Loading state
    if (isLoading) {
      return (
        <div className={`flex flex-col items-center justify-center gap-3 bg-slate-950 rounded-xl w-full h-full min-h-[80px] ${containerClassName ?? ""}`}>
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <span className="text-[10px] text-slate-400 font-semibold">Loading video...</span>
        </div>
      );
    }

    // Error state
    if (displayError) {
      return (
        <div className={`flex flex-col items-center justify-center gap-3 bg-slate-950 rounded-xl text-center p-6 w-full h-full min-h-[80px] ${containerClassName ?? ""}`}>
          <AlertCircle className="w-8 h-8 text-amber-500" />
          <p className="text-xs font-bold text-slate-300">{displayError}</p>
        </div>
      );
    }

    // No valid src — render fallback or default
    if (!safeSrcValue) {
      return <>{fallback ?? <DefaultFallback />}</>;
    }

    // Valid src — render the video
    return (
      <video
        ref={ref}
        src={safeSrcValue}
        className={className}
        onError={handleError}
        {...rest}
      />
    );
  }
);

SafeVideo.displayName = "SafeVideo";
export default SafeVideo;
