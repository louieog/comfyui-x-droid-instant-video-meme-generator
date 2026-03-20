"use client";

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
  AlertCircle,
} from "lucide-react";

interface PipelineStage {
  id: string;
  label: string;
  icon: React.ReactNode;
  status: "pending" | "running" | "success" | "failed" | "partial";
  assets: { name: string; status: string; model: string; time?: string }[];
}

const MOCK_STAGES: PipelineStage[] = [
  {
    id: "images",
    label: "Images",
    icon: <Image className="w-4 h-4" />,
    status: "success",
    assets: [
      { name: "Scene 1 - Character", status: "success", model: "Flux Kontext Pro", time: "12s" },
      { name: "Scene 2 - Character", status: "success", model: "Flux Kontext Pro", time: "11s" },
      { name: "Scene 3 - Character", status: "success", model: "Flux Kontext Pro", time: "13s" },
    ],
  },
  {
    id: "tts",
    label: "TTS",
    icon: <Mic className="w-4 h-4" />,
    status: "success",
    assets: [
      { name: "Scene 1 - Line 1", status: "success", model: "ElevenLabs v3", time: "3s" },
      { name: "Scene 2 - Line 1", status: "success", model: "ElevenLabs v3", time: "3s" },
      { name: "Scene 2 - Line 2", status: "success", model: "ElevenLabs v3", time: "4s" },
      { name: "Scene 3 - Line 1", status: "success", model: "ElevenLabs v3", time: "3s" },
      { name: "Scene 3 - Line 2", status: "success", model: "ElevenLabs v3", time: "3s" },
    ],
  },
  {
    id: "video",
    label: "Video",
    icon: <Video className="w-4 h-4" />,
    status: "success",
    assets: [
      { name: "Scene 1 - Animation", status: "success", model: "Kling v2 Master", time: "3m 12s" },
      { name: "Scene 2 - Animation", status: "success", model: "Kling v2 Master", time: "4m 5s" },
      { name: "Scene 3 - Animation", status: "success", model: "Kling v2 Master", time: "2m 48s" },
    ],
  },
  {
    id: "lipsync",
    label: "Lip Sync",
    icon: <Laugh className="w-4 h-4" />,
    status: "partial",
    assets: [
      { name: "Scene 1 - Sync", status: "success", model: "Kling Lip Sync", time: "1m 2s" },
      { name: "Scene 2 - Sync", status: "failed", model: "Kling Lip Sync" },
      { name: "Scene 3 - Sync", status: "success", model: "Kling Lip Sync", time: "58s" },
    ],
  },
  {
    id: "assembly",
    label: "Assembly",
    icon: <Film className="w-4 h-4" />,
    status: "success",
    assets: [
      { name: "Concatenation", status: "success", model: "ffmpeg", time: "5s" },
      { name: "16:9 Export", status: "success", model: "ffmpeg", time: "3s" },
      { name: "9:16 Export", status: "success", model: "ffmpeg", time: "4s" },
      { name: "Thumbnail", status: "success", model: "ffmpeg", time: "1s" },
    ],
  },
];

function statusIcon(status: string) {
  switch (status) {
    case "success": return <Check className="w-3.5 h-3.5 text-green-500" />;
    case "failed": return <AlertCircle className="w-3.5 h-3.5 text-red-500" />;
    case "running": return <div className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />;
    case "partial": return <AlertCircle className="w-3.5 h-3.5 text-yellow-500" />;
    default: return <Clock className="w-3.5 h-3.5 text-muted-foreground" />;
  }
}

function stageColor(status: string) {
  switch (status) {
    case "success": return "border-green-500 bg-green-500/10";
    case "failed": return "border-red-500 bg-red-500/10";
    case "running": return "border-primary bg-primary/10 animate-pulse";
    case "partial": return "border-yellow-500 bg-yellow-500/10";
    default: return "border-border bg-secondary/30";
  }
}

export default function PipelinePage() {
  const params = useParams();
  const id = params.id as string;

  return (
    <div>
      <Header title="Generation Pipeline" description="Track asset generation progress" />

      <div className="max-w-5xl">
        {/* Stage Progress Bar */}
        <div className="flex items-center justify-between mb-8 px-4">
          {MOCK_STAGES.map((stage, i) => (
            <div key={stage.id} className="flex items-center">
              <div className="flex flex-col items-center">
                <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center ${stageColor(stage.status)}`}>
                  {stage.status === "success" ? (
                    <Check className="w-5 h-5 text-green-500" />
                  ) : (
                    stage.icon
                  )}
                </div>
                <span className="text-xs mt-1.5 font-medium">{stage.label}</span>
              </div>
              {i < MOCK_STAGES.length - 1 && (
                <div className={`w-16 h-px mx-2 ${
                  MOCK_STAGES[i + 1].status !== "pending" ? "bg-green-500" : "bg-border"
                }`} />
              )}
            </div>
          ))}
        </div>

        <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 mb-6 text-center">
          <p className="text-sm text-muted-foreground">
            Pipeline monitoring will be live when connected to the droid execution backend.
            Below is the output from the Feline Report generation run.
          </p>
        </div>

        {/* Stage Details */}
        <div className="space-y-4">
          {MOCK_STAGES.map((stage) => (
            <Card key={stage.id}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    {stage.icon} {stage.label}
                  </CardTitle>
                  <Badge variant={
                    stage.status === "success" ? "success" :
                    stage.status === "failed" ? "destructive" :
                    stage.status === "partial" ? "warning" : "secondary"
                  }>
                    {stage.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {stage.assets.map((asset) => (
                    <div
                      key={asset.name}
                      className="flex items-center justify-between p-3 bg-secondary/30 rounded-lg border border-border/50"
                    >
                      <div className="flex items-center gap-2">
                        {statusIcon(asset.status)}
                        <div>
                          <p className="text-sm">{asset.name}</p>
                          <p className="text-xs text-muted-foreground">{asset.model}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
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
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="flex gap-3 pt-6">
          <Link href={`/create/${id}/brief`}>
            <Button variant="ghost">Back to Brief</Button>
          </Link>
          <Link href={`/create/${id}/output`}>
            <Button>
              View Output <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
