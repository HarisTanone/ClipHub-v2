import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 rounded-xl border border-rose-500/20 bg-rose-950/20 text-rose-300 space-y-2">
          <div className="flex items-center gap-2 font-medium text-xs">
            <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
            <span>{this.props.fallbackTitle || "Komponen mengalami kendala rendering"}</span>
          </div>
          <p className="text-[11px] text-zinc-400">
            {this.state.error?.message || "Terjadi kesalahan saat memuat tampilan komponen ini."}
          </p>
          <Button
            size="sm"
            variant="outline"
            className="text-xs h-7 gap-1 border-rose-500/30 text-rose-300 hover:bg-rose-500/20"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            <RefreshCw className="h-3 w-3" />
            <span>Coba Lagi</span>
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
