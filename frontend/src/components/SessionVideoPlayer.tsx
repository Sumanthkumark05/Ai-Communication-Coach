import React, { useState, useEffect, useRef } from "react";
import { X, Loader2, AlertCircle, Download } from "lucide-react";
import { api } from "../utils/api";
import SafeVideo from "./common/SafeVideo";

interface SessionVideoPlayerProps {
  sessionId: string;
  onClose: () => void;
}

export default function SessionVideoPlayer({ sessionId, onClose }: SessionVideoPlayerProps) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let active = true;

    async function fetchVideo() {
      try {
        setLoading(true);
        setError(null);
        const data = await api.getSessionVideo(sessionId);
        
        if (!active) return;
        
        if (data && data.video_url) {
          const backendRoot = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          // If video_url is absolute, use it. Otherwise, prepend backend host.
          const fullUrl = data.video_url.startsWith("http")
            ? data.video_url
            : `${backendRoot}${data.video_url}`;
          setVideoUrl(fullUrl);
        } else {
          setError("This presentation recording is unavailable.");
        }
      } catch (err: any) {
        if (!active) return;
        console.error("Failed to load session recording:", err);
        setError("This presentation recording is unavailable.");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    fetchVideo();

    return () => {
      active = false;
    };
  }, [sessionId]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/80 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="relative bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl max-w-3xl w-full overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center px-5 py-4 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
          <div>
            <h3 className="text-xs font-extrabold text-slate-200 uppercase tracking-widest">Session Recording Playback</h3>
            <p className="text-[10px] text-slate-500 font-semibold mt-0.5">ID: {sessionId.substring(0, 8)}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800/80 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Player Area */}
        <div className="relative bg-black flex items-center justify-center" style={{ aspectRatio: "16/9" }}>
          {loading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-slate-950 text-slate-400">
              <Loader2 className="w-10 h-10 animate-spin text-blue-500" />
              <span className="text-xs font-semibold tracking-wide">Retrieving session video...</span>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-slate-950 text-slate-400 text-center p-6">
              <AlertCircle className="w-10 h-10 text-amber-500" />
              <p className="text-xs font-bold text-slate-300">{error}</p>
            </div>
          )}

          {videoUrl && (
            <SafeVideo
              ref={videoRef}
              src={videoUrl}
              controls
              autoPlay
              playsInline
              className="w-full h-full object-contain z-10"
              videoError={error ?? undefined}
              onError={() => setError("This presentation recording is unavailable.")}
              _debugName="SessionVideoPlayer"
            />
          )}
        </div>

        {/* Footer */}
        {videoUrl && !error && !loading && (
          <div className="px-5 py-4 border-t border-slate-800 bg-slate-950 flex flex-col sm:flex-row gap-3 items-center justify-between">
            <span className="text-[10px] text-slate-500 font-semibold text-center sm:text-left">
              Use the player controls to play, pause, seek, modify playback rate, or toggle fullscreen.
            </span>
            <a
              href={videoUrl}
              download={`recording_${sessionId}.webm`}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-blue-600 hover:bg-blue-700 text-white text-[10px] font-bold px-4 py-2 rounded-xl flex items-center gap-1.5 cursor-pointer transition-colors shrink-0"
            >
              <Download className="w-3.5 h-3.5" /> Download Recording
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
