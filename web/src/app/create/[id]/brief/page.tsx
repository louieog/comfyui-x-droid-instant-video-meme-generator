"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, ArrowRight, Pencil, ArrowLeft, Clock, User, Camera, MessageSquare, Music, Type } from "lucide-react";
import type { ProductionBrief } from "@/lib/types";

const BEAT_COLORS: Record<string, string> = {
  HOOK: "default",
  SETUP: "secondary",
  ESCALATION: "warning",
  PUNCHLINE: "success",
  TAG: "outline",
};

export default function BriefPage() {
  const params = useParams();
  const id = params.id as string;
  const [brief, setBrief] = useState<ProductionBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`/api/requests/${id}/brief`)
      .then((r) => {
        if (!r.ok) throw new Error("Brief not found");
        return r.json();
      })
      .then((data) => setBrief(data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading brief...</p>
      </div>
    );
  }

  if (error || !brief) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <p className="text-muted-foreground mb-4">Brief is being generated...</p>
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <p className="text-xs text-muted-foreground mt-4">
          Run the meme-scout droid to generate a brief for this request
        </p>
      </div>
    );
  }

  const totalDuration = brief.scenes.reduce((sum, s) => sum + s.duration_seconds, 0);

  return (
    <div>
      <Header
        title={brief.concept}
        description="Review the production brief before generating"
      />

      <div className="max-w-4xl space-y-6">
        {/* Overview */}
        <div className="flex flex-wrap gap-3 mb-2">
          <Badge>{brief.format}</Badge>
          <Badge variant="secondary">{brief.style}</Badge>
          <Badge variant="outline">
            <Clock className="w-3 h-3 mr-1" /> {totalDuration}s target
          </Badge>
          <Badge variant="outline">{brief.scenes.length} scenes</Badge>
          {brief.trend_score && (
            <Badge variant={brief.trend_score > 80 ? "success" : "warning"}>
              Trend: {brief.trend_score}/100
            </Badge>
          )}
        </div>

        {/* Characters */}
        {brief.characters?.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                <User className="w-4 h-4 inline mr-2" />
                Characters
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {brief.characters.map((char) => (
                <div key={char.id} className="p-3 bg-secondary/50 rounded-lg">
                  <p className="text-sm font-medium mb-1">{char.id}</p>
                  <p className="text-xs text-muted-foreground leading-relaxed">{char.description}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Scene Timeline */}
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Scene Timeline</h3>
          {brief.scenes.map((scene, i) => (
            <Card key={scene.scene_id} className="relative">
              {i < brief.scenes.length - 1 && (
                <div className="absolute left-8 top-full w-px h-4 bg-border" />
              )}
              <CardContent className="p-5">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-sm font-bold">
                    {scene.scene_id}
                  </div>
                  <div className="flex-1 space-y-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={(BEAT_COLORS[scene.beat] as "default" | "secondary" | "warning" | "success" | "outline") || "outline"}>
                        {scene.beat}
                      </Badge>
                      <Badge variant="outline">
                        <Clock className="w-3 h-3 mr-1" /> {scene.duration_seconds}s
                      </Badge>
                      <Badge variant="outline">
                        <Camera className="w-3 h-3 mr-1" /> {scene.camera}
                      </Badge>
                    </div>

                    <div className="p-3 bg-secondary/30 rounded border border-border/50">
                      <p className="text-sm leading-relaxed">{scene.visual}</p>
                    </div>

                    {scene.dialogue?.length > 0 && (
                      <div className="space-y-2">
                        {scene.dialogue.map((d, di) => (
                          <div key={di} className="flex items-start gap-2">
                            <MessageSquare className="w-3.5 h-3.5 text-primary mt-1 flex-shrink-0" />
                            <div>
                              <span className="text-xs font-medium text-primary">{d.character}</span>
                              <span className="text-xs text-muted-foreground ml-2">({d.emotion})</span>
                              <p className="text-sm mt-0.5">&ldquo;{d.line}&rdquo;</p>
                              <p className="text-xs text-muted-foreground mt-0.5 italic">{d.voice_style}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {scene.text_overlay && (
                      <div className="bg-black border border-border rounded px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Type className="w-3 h-3 text-muted-foreground" />
                          <span className="text-xs font-bold uppercase tracking-wide">{scene.text_overlay}</span>
                        </div>
                      </div>
                    )}

                    {(scene.sfx?.length > 0 || scene.music_cue) && (
                      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                        {scene.sfx?.map((s, si) => (
                          <span key={si} className="flex items-center gap-1">
                            <Music className="w-3 h-3" /> {s}
                          </span>
                        ))}
                        {scene.music_cue && (
                          <span className="flex items-center gap-1 italic">
                            <Music className="w-3 h-3" /> {scene.music_cue}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Models */}
        {brief.generation_requirements && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Generation Models</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(brief.generation_requirements.models_preferred || {}).map(([key, val]) => (
                  <div key={key} className="p-3 bg-secondary/50 rounded-lg">
                    <p className="text-xs font-medium text-muted-foreground uppercase mb-1">{key}</p>
                    <p className="text-sm">{val}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-4">
          <Link href="/create">
            <Button variant="ghost">
              <ArrowLeft className="w-4 h-4 mr-2" /> Back
            </Button>
          </Link>
          <Button variant="secondary">
            <Pencil className="w-4 h-4 mr-2" /> Edit Brief
          </Button>
          <Link href={`/create/${id}/pipeline`}>
            <Button>
              Approve &amp; Generate <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
