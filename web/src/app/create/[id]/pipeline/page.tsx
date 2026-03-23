"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Image,
  Mic,
  Video,
  Laugh,
  Film,
  Check,
  Clock,
  RotateCcw,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Loader2,
  Terminal,
  ChevronDown,
  ChevronUp,
  FileText,
  Zap,
} from "lucide-react";

interface PipelineStatus {
  request_id: string;
  slug: string;
  status: string;
  stage: string;
  detail: string;
}

interface PipelineStage {
  id: string;
  label: string;
  icon: React.ReactNode;
  status: "pending" | "running" | "success" | "failed" | "partial" | "skipped";
  assets: { name: string; status: string; model: string; time?: string; size?: string }[];
}

function deriveStages(
  pipeline: PipelineStatus | null,
  assets: string[],
  logs: Record<string, string>,
  request: Record<string, unknown> | null
): PipelineStage[] {
  const modelOverrides = (request?.model_overrides || {}) as Record<string, string>;
  const ttsSkipped = modelOverrides.tts === "none";
  const lipSyncSkipped = modelOverrides.lip_sync === "none";

  const currentStage = pipeline?.stage || "";
  const pipelineStatus = pipeline?.status || "";
  const stageOrder = ["meme-scout", "comfy-dispatcher", "assembler"];
  const currentIdx = stageOrder.indexOf(currentStage);
  const isDone = pipelineStatus === "complete";
  const isFailed = pipelineStatus === "failed";

  // Parse assets into categories
  const imageAssets = assets.filter((a) => a.endsWith(".png") || a.endsWith(".jpg"));
  const audioAssets = assets.filter((a) => a.endsWith(".mp3") || a.endsWith(".wav"));
  const videoAssets = assets.filter((a) => a.endsWith(".mp4") && !a.includes("lipsync") && !a.includes("lip-sync"));
  const lipSyncAssets = assets.filter((a) => a.endsWith(".mp4") && (a.includes("lipsync") || a.includes("lip-sync")));

  function stageStatus(stageIdx: number, stageKey: string): "pending" | "running" | "success" | "failed" | "skipped" {
    if (isDone) return "success";
    if (isFailed && currentStage === stageKey) return "failed";
    if (isFailed && stageIdx > currentIdx) return "pending";
    if (currentIdx > stageIdx || (isDone)) return "success";
    if (currentIdx === stageIdx) return "running";
    return "pending";
  }

  // Determine comfy-dispatcher sub-stage status from assets
  const imagesStatus = imageAssets.length > 0 ? "success" : (currentIdx >= 1 || isDone ? "success" : "pending");
  const videoStatus = videoAssets.length > 0 ? "success" : (isDone ? "success" : "pending");

  const stages: PipelineStage[] = [
    {
      id: "images",
      label: "Images",
      icon: <Image className="w-4 h-4" />,
      status: isDone || imageAssets.length > 0 ? "success" : (currentIdx >= 1 ? "running" : "pending"),
      assets: imageAssets.length > 0
        ? imageAssets.map((a) => ({ name: a, status: "success", model: modelOverrides.image || "Flux Kontext Pro" }))
        : currentIdx >= 1 ? [{ name: "Generating...", status: "running", model: modelOverrides.image || "unknown" }] : [],
    },
    {
      id: "tts",
      label: "TTS",
      icon: <Mic className="w-4 h-4" />,
      status: ttsSkipped ? "skipped" : (isDone || audioAssets.length > 0 ? "success" : (currentIdx >= 1 && imagesStatus === "success" ? "running" : "pending")),
      assets: ttsSkipped
        ? [{ name: "Skipped (video model handles audio)", status: "skipped", model: "none" }]
        : audioAssets.length > 0
        ? audioAssets.map((a) => ({ name: a, status: "success", model: modelOverrides.tts || "ElevenLabs" }))
        : [],
    },
    {
      id: "video",
      label: "Video",
      icon: <Video className="w-4 h-4" />,
      status: isDone || videoAssets.length > 0 ? "success" : (currentIdx >= 1 ? "running" : "pending"),
      assets: videoAssets.length > 0
        ? videoAssets.map((a) => ({ name: a, status: "success", model: modelOverrides.video || "Kling v2" }))
        : [],
    },
    {
      id: "lipsync",
      label: "Lip Sync",
      icon: <Laugh className="w-4 h-4" />,
      status: lipSyncSkipped ? "skipped" : (isDone || lipSyncAssets.length > 0 ? "success" : (videoStatus === "success" ? "running" : "pending")),
      assets: lipSyncSkipped
        ? [{ name: "Skipped", status: "skipped", model: "none" }]
        : lipSyncAssets.length > 0
        ? lipSyncAssets.map((a) => ({ name: a, status: "success", model: modelOverrides.lip_sync || "Kling Lip Sync" }))
        : [],
    },
    {
      id: "assembly",
      label: "Assembly",
      icon: <Film className="w-4 h-4" />,
      status: stageStatus(2, "assembler") as "pending" | "running" | "success" | "failed",
      assets: isDone
        ? [
            { name: "16:9 Export", status: "success", model: "ffmpeg" },
            { name: "9:16 Export", status: "success", model: "ffmpeg" },
            { name: "Thumbnail", status: "success", model: "ffmpeg" },
          ]
        : currentStage === "assembler"
        ? [{ name: "Assembling...", status: "running", model: "ffmpeg" }]
        : [],
    },
  ];

  return stages;
}

function statusIcon(status: string) {
  switch (status) {
    case "success": return <Check className="w-3.5 h-3.5 text-green-500" />;
    case "failed": return <AlertCircle className="w-3.5 h-3.5 text-red-500" />;
    case "running": return <div className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />;
    case "skipped": return <span className="text-xs text-muted-foreground">--</span>;
    default: return <Clock className="w-3.5 h-3.5 text-muted-foreground" />;
  }
}

function stageColor(status: string) {
  switch (status) {
    case "success": return "border-green-500 bg-green-500/10";
    case "failed": return "border-red-500 bg-red-500/10";
    case "running": return "border-primary bg-primary/10 animate-pulse";
    case "skipped": return "border-border bg-secondary/20";
    default: return "border-border bg-secondary/30";
  }
}

export default function PipelinePage() {
  const params = useParams();
  const id = params.id as string;
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [assets, setAssets] = useState<string[]>([]);
  const [request, setRequest] = useState<Record<string, unknown> | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(() => {
    fetch(`/api/requests/${id}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.pipeline) setPipeline(data.pipeline);
        if (data.request) setRequest(data.request);
        setLoading(false);
      })
      .catch(() => setLoading(false));
    fetch(`/api/requests/${id}/logs`)
      .then((r) => r.json())
      .then((data) => {
        if (data.logs) setLogs(data.logs);
        if (data.assets) setAssets(data.assets);
      })
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    fetchData();
    const isActive = pipeline?.status === "generating" || !pipeline;
    const interval = setInterval(fetchData, isActive ? 5000 : 15000);
    return () => clearInterval(interval);
  }, [fetchData, pipeline?.status]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const stages = deriveStages(pipeline, assets, logs, request);
  const concept = (request as Record<string, string>)?.concept || pipeline?.slug || "Video";
  const isRunning = pipeline?.status === "generating";
  const isDone = pipeline?.status === "complete";
  const isFailed = pipeline?.status === "failed";

  return (
    <div>
      <Header
        title="Generation Pipeline"
        description={isRunning ? "Generating assets..." : isDone ? "Generation complete" : isFailed ? "Generation failed" : "Pipeline status"}
      />

      <div className="max-w-5xl">
        <p className="text-sm text-muted-foreground mb-6 line-clamp-1">{concept}</p>

        {/* Stage Progress Bar */}
        <div className="flex items-center justify-between mb-8 px-4">
          {stages.map((stage, i) => (
            <div key={stage.id} className="flex items-center">
              <div className="flex flex-col items-center">
                <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center ${stageColor(stage.status)}`}>
                  {stage.status === "success" ? (
                    <Check className="w-5 h-5 text-green-500" />
                  ) : stage.status === "skipped" ? (
                    <span className="text-xs text-muted-foreground">--</span>
                  ) : stage.status === "running" ? (
                    <Zap className="w-5 h-5 text-primary animate-pulse" />
                  ) : (
                    stage.icon
                  )}
                </div>
                <span className="text-xs mt-1.5 font-medium">{stage.label}</span>
                {stage.status === "skipped" && (
                  <span className="text-[10px] text-muted-foreground">skipped</span>
                )}
              </div>
              {i < stages.length - 1 && (
                <div className={`w-16 h-px mx-2 ${
                  stage.status === "success" || stage.status === "skipped" ? "bg-green-500" : "bg-border"
                }`} />
              )}
            </div>
          ))}
        </div>

        {isRunning && (
          <div className="bg-primary/10 border border-primary/20 rounded-lg p-4 mb-6 flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-primary flex-shrink-0" />
            <div>
              <p className="text-sm font-medium">Pipeline running: {pipeline!.stage}</p>
              <p className="text-xs text-muted-foreground">{pipeline!.detail}</p>
            </div>
          </div>
        )}

        {isFailed && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
            <p className="text-sm font-medium text-red-400">Pipeline failed at stage: {pipeline!.stage}</p>
            <p className="text-xs text-muted-foreground">{pipeline!.detail}</p>
          </div>
        )}

        {/* Stage Details */}
        <div className="space-y-4">
          {stages.map((stage) => (
            <Card key={stage.id} className={stage.status === "skipped" ? "opacity-50" : ""}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    {stage.icon} {stage.label}
                  </CardTitle>
                  <Badge variant={
                    stage.status === "success" ? "success" :
                    stage.status === "failed" ? "destructive" :
                    stage.status === "running" ? "default" :
                    stage.status === "skipped" ? "outline" : "secondary"
                  }>
                    {stage.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {stage.assets.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {stage.assets.map((asset) => (
                      <div
                        key={asset.name}
                        className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg border border-border/50"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {statusIcon(asset.status)}
                          <div className="min-w-0">
                            <p className="text-sm truncate">{asset.name}</p>
                            <p className="text-xs text-muted-foreground">{asset.model}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {asset.time && <span className="text-xs text-muted-foreground">{asset.time}</span>}
                          {asset.status === "failed" && (
                            <button className="p-1 hover:bg-secondary rounded">
                              <RotateCcw className="w-3.5 h-3.5 text-muted-foreground" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : stage.status === "pending" ? (
                  <p className="text-xs text-muted-foreground">Waiting for previous stages...</p>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Log Viewer */}
        {Object.keys(logs).length > 0 && (
          <div className="mt-6">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-2"
            >
              <Terminal className="w-4 h-4" />
              Pipeline Logs
              {showLogs ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {showLogs && (
              <div className="space-y-3">
                {Object.entries(logs).map(([stage, content]) => (
                  <Card key={stage}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5" /> {stage}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="text-xs bg-black/50 rounded-lg p-3 overflow-auto max-h-64 whitespace-pre-wrap font-mono text-muted-foreground">
                        {content || "(empty)"}
                      </pre>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-6">
          <Link href={`/create/${id}/brief`}>
            <Button variant="ghost"><ArrowLeft className="w-4 h-4 mr-2" /> Back to Brief</Button>
          </Link>
          {isDone && (
            <Link href={`/create/${id}/output`}>
              <Button>View Output <ArrowRight className="w-4 h-4 ml-2" /></Button>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
