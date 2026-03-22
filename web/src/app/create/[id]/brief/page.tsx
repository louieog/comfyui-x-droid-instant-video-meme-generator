"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  ArrowRight,
  Pencil,
  ArrowLeft,
  Clock,
  User,
  Camera,
  MessageSquare,
  Music,
  Type,
  Zap,
  Terminal,
  ChevronDown,
  ChevronUp,
  FileText,
  AlertCircle,
  RotateCcw,
} from "lucide-react";
import type { ProductionBrief } from "@/lib/types";

const BEAT_COLORS: Record<string, string> = {
  HOOK: "default",
  SETUP: "secondary",
  ESCALATION: "warning",
  PUNCHLINE: "success",
  TAG: "outline",
};

interface PipelineStatus {
  request_id: string;
  slug: string;
  status: string;
  stage: string;
  detail: string;
}

export default function BriefPage() {
  const params = useParams();
  const id = params.id as string;
  const [brief, setBrief] = useState<ProductionBrief | null>(null);
  const [editBrief, setEditBrief] = useState<ProductionBrief | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [assets, setAssets] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);

  const fetchData = useCallback(() => {
    fetch(`/api/requests/${id}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.brief) setBrief(data.brief);
        if (data.pipeline) setPipeline(data.pipeline);
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
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  async function retryPipeline() {
    setRetrying(true);
    try {
      await fetch(`/api/requests/${id}/retry`, { method: "POST" });
      setTimeout(fetchData, 2000);
    } catch {
      // handle
    } finally {
      setRetrying(false);
    }
  }

  function startEditing() {
    setEditBrief(JSON.parse(JSON.stringify(brief)));
    setEditing(true);
  }

  async function saveBrief() {
    if (!editBrief) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/requests/${id}/brief`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editBrief),
      });
      if (res.ok) {
        setBrief(editBrief);
        setEditing(false);
      }
    } catch {
      // handle
    } finally {
      setSaving(false);
    }
  }

  function updateScene(sceneIdx: number, field: string, value: unknown) {
    if (!editBrief) return;
    const scenes = [...editBrief.scenes];
    scenes[sceneIdx] = { ...scenes[sceneIdx], [field]: value };
    setEditBrief({ ...editBrief, scenes });
  }

  function updateDialogue(sceneIdx: number, dialogueIdx: number, field: string, value: string) {
    if (!editBrief) return;
    const scenes = [...editBrief.scenes];
    const dialogue = [...scenes[sceneIdx].dialogue];
    dialogue[dialogueIdx] = { ...dialogue[dialogueIdx], [field]: value };
    scenes[sceneIdx] = { ...scenes[sceneIdx], dialogue };
    setEditBrief({ ...editBrief, scenes });
  }

  // Which brief data to render
  const b = editing ? editBrief! : brief;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  // Log viewer component (reused in multiple states)
  const logViewer = (Object.keys(logs).length > 0 || assets.length > 0) && (
    <div className="w-full max-w-4xl mt-6">
      <button
        onClick={() => setShowLogs(!showLogs)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-2"
      >
        <Terminal className="w-4 h-4" />
        Pipeline Logs & Assets
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
          {assets.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Generated Assets ({assets.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {assets.map((a) => (
                    <Badge key={a} variant="outline" className="text-xs font-mono">{a}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );

  // Pipeline failed
  if (!brief && pipeline?.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <AlertCircle className="w-12 h-12 text-destructive mb-4" />
        <h3 className="text-lg font-medium mb-2">Pipeline Failed</h3>
        <p className="text-muted-foreground mb-1">
          Stage: <span className="text-foreground font-medium">{pipeline.stage}</span>
        </p>
        <p className="text-sm text-muted-foreground mb-4">{pipeline.detail}</p>
        <div className="flex gap-3">
          <Button onClick={retryPipeline} disabled={retrying}>
            <RotateCcw className="w-4 h-4 mr-2" />
            {retrying ? "Retrying..." : "Retry Pipeline"}
          </Button>
          <Link href="/create">
            <Button variant="ghost">Back to Create</Button>
          </Link>
        </div>
        {logViewer}
      </div>
    );
  }

  // Pipeline is running but brief not ready yet
  if (!brief && pipeline) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96">
        <div className="relative mb-6">
          <div className="w-16 h-16 rounded-full border-2 border-primary/30 flex items-center justify-center">
            <Zap className="w-8 h-8 text-primary animate-pulse" />
          </div>
          <div className="absolute inset-0 w-16 h-16 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        </div>
        <h3 className="text-lg font-medium mb-2">Pipeline Running</h3>
        <p className="text-muted-foreground mb-1">
          Stage: <span className="text-foreground font-medium">{pipeline.stage}</span>
        </p>
        <p className="text-sm text-muted-foreground">{pipeline.detail}</p>
        <p className="text-xs text-muted-foreground mt-4">Auto-refreshing every 5 seconds...</p>
        {logViewer}
      </div>
    );
  }

  // Nothing at all
  if (!brief) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground mb-4" />
        <p className="text-muted-foreground">Waiting for brief generation...</p>
        <p className="text-xs text-muted-foreground mt-2">The pipeline has been triggered. This page will auto-refresh.</p>
        {logViewer}
      </div>
    );
  }

  const totalDuration = b!.scenes.reduce((sum, s) => sum + s.duration_seconds, 0);
  const showPipelineBanner = pipeline && pipeline.status !== "complete" && pipeline.status !== "failed";

  return (
    <div>
      <Header
        title={b!.concept}
        description={editing ? "Editing brief -- make changes and save" : "Review the production brief"}
      />

      <div className="max-w-4xl space-y-6">
        {editing && (
          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 flex items-center justify-between">
            <p className="text-sm text-yellow-400">Editing mode -- click fields to modify, then Save.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              <Button size="sm" onClick={saveBrief} disabled={saving}>
                {saving ? "Saving..." : "Save Brief"}
              </Button>
            </div>
          </div>
        )}

        {showPipelineBanner && (
          <div className="bg-primary/10 border border-primary/20 rounded-lg p-4 flex items-center gap-3">
            <Loader2 className="w-5 h-5 animate-spin text-primary flex-shrink-0" />
            <div>
              <p className="text-sm font-medium">Pipeline running: {pipeline!.stage}</p>
              <p className="text-xs text-muted-foreground">{pipeline!.detail}</p>
            </div>
          </div>
        )}

        {pipeline?.status === "complete" && (
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4 flex items-center justify-between">
            <p className="text-sm font-medium text-green-400">Video generation complete!</p>
            <Link href={`/create/${id}/output`}>
              <Button size="sm">View Output <ArrowRight className="w-4 h-4 ml-1" /></Button>
            </Link>
          </div>
        )}

        {/* Overview */}
        <div className="flex flex-wrap gap-3 mb-2">
          <Badge>{b!.format}</Badge>
          <Badge variant="secondary">{b!.style}</Badge>
          <Badge variant="outline"><Clock className="w-3 h-3 mr-1" /> {totalDuration}s target</Badge>
          <Badge variant="outline">{b!.scenes.length} scenes</Badge>
          {b!.trend_score && (
            <Badge variant={b!.trend_score > 80 ? "success" : "warning"}>Trend: {b!.trend_score}/100</Badge>
          )}
        </div>

        {/* Characters */}
        {b!.characters?.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base"><User className="w-4 h-4 inline mr-2" />Characters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {b!.characters.map((char, ci) => (
                <div key={char.id} className="p-3 bg-secondary/50 rounded-lg">
                  <p className="text-sm font-medium mb-1">{char.id}</p>
                  {editing ? (
                    <textarea
                      className="w-full bg-black/30 border border-border rounded p-2 text-xs text-foreground resize-none"
                      rows={3}
                      value={editBrief!.characters[ci]?.description || ""}
                      onChange={(e) => {
                        const chars = [...editBrief!.characters];
                        chars[ci] = { ...chars[ci], description: e.target.value };
                        setEditBrief({ ...editBrief!, characters: chars });
                      }}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground leading-relaxed">{char.description}</p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Scene Timeline */}
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Scene Timeline</h3>
          {b!.scenes.map((scene, i) => (
            <Card key={scene.scene_id} className="relative">
              {i < b!.scenes.length - 1 && (
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
                      {editing ? (
                        <div className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <input
                            type="number"
                            className="w-12 bg-black/30 border border-border rounded px-1 text-xs text-center"
                            value={scene.duration_seconds}
                            onChange={(e) => updateScene(i, "duration_seconds", Number(e.target.value))}
                          />
                          <span className="text-xs">s</span>
                        </div>
                      ) : (
                        <Badge variant="outline"><Clock className="w-3 h-3 mr-1" /> {scene.duration_seconds}s</Badge>
                      )}
                      <Badge variant="outline"><Camera className="w-3 h-3 mr-1" /> {scene.camera}</Badge>
                    </div>

                    {/* Visual description */}
                    <div className="p-3 bg-secondary/30 rounded border border-border/50">
                      {editing ? (
                        <textarea
                          className="w-full bg-transparent border-none outline-none text-sm leading-relaxed resize-none"
                          rows={3}
                          value={scene.visual}
                          onChange={(e) => updateScene(i, "visual", e.target.value)}
                        />
                      ) : (
                        <p className="text-sm leading-relaxed">{scene.visual}</p>
                      )}
                    </div>

                    {/* Dialogue */}
                    {scene.dialogue?.length > 0 && (
                      <div className="space-y-2">
                        {scene.dialogue.map((d, di) => (
                          <div key={di} className="flex items-start gap-2">
                            <MessageSquare className="w-3.5 h-3.5 text-primary mt-1 flex-shrink-0" />
                            <div className="flex-1">
                              <span className="text-xs font-medium text-primary">{d.character}</span>
                              <span className="text-xs text-muted-foreground ml-2">({d.emotion})</span>
                              {editing ? (
                                <input
                                  className="w-full bg-black/30 border border-border rounded px-2 py-1 text-sm mt-0.5"
                                  value={d.line}
                                  onChange={(e) => updateDialogue(i, di, "line", e.target.value)}
                                />
                              ) : (
                                <p className="text-sm mt-0.5">&ldquo;{d.line}&rdquo;</p>
                              )}
                              <p className="text-xs text-muted-foreground mt-0.5 italic">{d.voice_style}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Text overlay */}
                    {(scene.text_overlay || editing) && (
                      <div className="bg-black border border-border rounded px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Type className="w-3 h-3 text-muted-foreground" />
                          {editing ? (
                            <input
                              className="flex-1 bg-transparent border-none outline-none text-xs font-bold uppercase tracking-wide"
                              value={scene.text_overlay || ""}
                              placeholder="Text overlay..."
                              onChange={(e) => updateScene(i, "text_overlay", e.target.value || null)}
                            />
                          ) : (
                            <span className="text-xs font-bold uppercase tracking-wide">{scene.text_overlay}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {(scene.sfx?.length > 0 || scene.music_cue) && (
                      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                        {scene.sfx?.map((s, si) => (
                          <span key={si} className="flex items-center gap-1"><Music className="w-3 h-3" /> {s}</span>
                        ))}
                        {scene.music_cue && (
                          <span className="flex items-center gap-1 italic"><Music className="w-3 h-3" /> {scene.music_cue}</span>
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
        {b!.generation_requirements && (
          <Card>
            <CardHeader><CardTitle className="text-base">Generation Models</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(b!.generation_requirements.models_preferred || {}).map(([key, val]) => (
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
            <Button variant="ghost"><ArrowLeft className="w-4 h-4 mr-2" /> Back</Button>
          </Link>
          {editing ? (
            <>
              <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              <Button onClick={saveBrief} disabled={saving}>{saving ? "Saving..." : "Save Brief"}</Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={startEditing}>
                <Pencil className="w-4 h-4 mr-2" /> Edit Brief
              </Button>
              <Link href={`/create/${id}/pipeline`}>
                <Button>Approve &amp; Generate <ArrowRight className="w-4 h-4 ml-2" /></Button>
              </Link>
            </>
          )}
        </div>

        {/* Log Viewer */}
        {logViewer}
      </div>
    </div>
  );
}
