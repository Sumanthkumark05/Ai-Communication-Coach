/**
 * SafeAudio — Drop-in replacement for <audio> that prevents empty-src warnings.
 */
"use client";

import React, { useState, forwardRef, AudioHTMLAttributes } from "react";
import { safeSrc } from "../../utils/safeSrc";
import { Volume2, AlertCircle, Loader2 } from "lucide-react";

// Omit native `src` to redefine it as accepting null
export interface SafeAudioProps extends Omit<AudioHTMLAttributes<HTMLAudioElement>, "src"> {
  src?: string | null | undefined;
  isLoading?: boolean;
  audioError?: string | null;
  fallback?: React.ReactNode;
  _debugName?: string;
}

const SafeAudio = forwardRef<HTMLAudioElement, SafeAudioProps>(
  ({ src, isLoading = false, audioError = null, fallback, onError, _debugName = "SafeAudio", ...rest }, ref) => {
    const [internalError, setInternalError] = useState<string | null>(null);
    const safeSrcValue = safeSrc(src);

    if (process.env.NODE_ENV === "development" && src !== undefined && src !== null && !safeSrcValue) {
      console.warn(
        `[SafeMedia] Invalid media source detected\n` +
        `  Component: ${_debugName}\n  Prop: src\n  Value: ${JSON.stringify(src)}`
      );
    }

    const handleError = (e: React.SyntheticEvent<HTMLAudioElement>) => {
      setInternalError("Audio unavailable");
      if (onError) onError(e);
    };

    if (isLoading) {
      return (
        <div className="flex items-center gap-2 text-slate-400 text-xs">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Loading audio...</span>
        </div>
      );
    }

    const displayError = audioError || internalError;
    if (displayError) {
      return (
        <div className="flex items-center gap-2 text-amber-500 text-xs">
          <AlertCircle className="w-4 h-4" />
          <span>{displayError}</span>
        </div>
      );
    }

    if (!safeSrcValue) {
      return (
        <>
          {fallback ?? (
            <div className="flex items-center gap-2 text-slate-500 text-xs">
              <Volume2 className="w-4 h-4 opacity-30" />
              <span className="opacity-50">No audio available</span>
            </div>
          )}
        </>
      );
    }

    return <audio ref={ref} src={safeSrcValue} onError={handleError} {...rest} />;
  }
);

SafeAudio.displayName = "SafeAudio";
export default SafeAudio;
