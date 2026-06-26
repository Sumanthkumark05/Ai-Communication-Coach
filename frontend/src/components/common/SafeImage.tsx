/**
 * SafeImage — Drop-in replacement for <img> that permanently prevents
 * the React "empty src" warning.
 */
"use client";

import React, { useState, forwardRef, ImgHTMLAttributes } from "react";
import { safeSrc } from "../../utils/safeSrc";
import { ImageOff } from "lucide-react";

// Omit native `src` to redefine it as accepting null
export interface SafeImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> {
  src?: string | null | undefined;
  fallback?: React.ReactNode;
  _debugName?: string;
}

const DefaultImageFallback = ({ className }: { className?: string }) => (
  <div className={`flex items-center justify-center bg-slate-800 rounded ${className ?? "w-10 h-10"}`}>
    <ImageOff className="w-4 h-4 text-slate-500" />
  </div>
);

const SafeImage = forwardRef<HTMLImageElement, SafeImageProps>(
  ({ src, alt = "", fallback, className, onError, _debugName = "SafeImage", ...rest }, ref) => {
    const [failed, setFailed] = useState(false);
    const safeSrcValue = safeSrc(src);

    if (process.env.NODE_ENV === "development" && src !== undefined && src !== null && !safeSrcValue) {
      console.warn(
        `[SafeMedia] Invalid media source detected\n` +
        `  Component: ${_debugName}\n  Prop: src\n  Value: ${JSON.stringify(src)}\n` +
        `  → Rendering suppressed to prevent empty-src browser warning.`
      );
    }

    const handleError = (e: React.SyntheticEvent<HTMLImageElement>) => {
      setFailed(true);
      if (onError) onError(e);
    };

    if (!safeSrcValue || failed) {
      return <>{fallback ?? <DefaultImageFallback className={className} />}</>;
    }

    return (
      <img
        ref={ref}
        src={safeSrcValue}
        alt={alt}
        className={className}
        onError={handleError}
        {...rest}
      />
    );
  }
);

SafeImage.displayName = "SafeImage";
export default SafeImage;
